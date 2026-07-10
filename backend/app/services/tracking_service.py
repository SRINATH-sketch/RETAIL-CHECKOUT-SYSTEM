from app.utils.logger import logger


class TrackingService:
    """
    Service to track detected products across frames using DeepSORT
    (deep-sort-realtime library with MobileNet appearance embedder).

    Input detections format:
        list of dicts: {"box": [x1, y1, x2, y2], "confidence": float, "class_name": str}

    Output format:
        list of dicts: {"track_id": str, "class_name": str, "box": [x1, y1, x2, y2]}
    """

    def __init__(self, max_age=30, n_init=3, max_cosine_distance=0.3):
        self.tracker = None
        self._use_deepsort = False
        self._try_init_deepsort(max_age, n_init, max_cosine_distance)

        if not self._use_deepsort:
            logger.warning("DeepSORT unavailable. Using centroid/IoU fallback tracker.")
            self._init_fallback_tracker()

    # ------------------------------------------------------------------
    # DeepSORT Initialization
    # ------------------------------------------------------------------
    def _try_init_deepsort(self, max_age, n_init, max_cosine_distance):
        try:
            from deep_sort_realtime.deepsort_tracker import DeepSort
            self.tracker = DeepSort(
                max_age=max_age,          # frames to keep a track alive without a match
                n_init=n_init,            # frames before a track is confirmed
                nms_max_overlap=1.0,      # allow overlapping boxes (handled by YOLO NMS)
                max_cosine_distance=max_cosine_distance,  # Re-ID appearance threshold
                embedder="mobilenet",     # MobileNet CNN for appearance feature extraction
                half=True,               # FP16 inference for speed
                bgr=True,                # OpenCV frames are BGR
                embedder_gpu=False,      # CPU embedder for compatibility
            )
            self._use_deepsort = True
            logger.info(
                "DeepSORT tracker initialized successfully "
                "(embedder=MobileNet, max_age=%d, n_init=%d, cosine_dist=%.2f)",
                max_age, n_init, max_cosine_distance,
            )
        except Exception:
            logger.exception("Failed to initialize DeepSORT tracker.")
            self.tracker = None
            self._use_deepsort = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def update(self, yolo_detections, frame):
        """
        Feed new YOLO detections into the tracker and return confirmed tracks.

        Args:
            yolo_detections: list of {"box": [x1,y1,x2,y2], "confidence": float, "class_name": str}
            frame: BGR numpy ndarray (H, W, 3)

        Returns:
            list of {"track_id": str, "class_name": str, "box": [x1,y1,x2,y2]}
        """
        if self._use_deepsort:
            return self._update_deepsort(yolo_detections, frame)
        return self._update_fallback(yolo_detections)

    # ------------------------------------------------------------------
    # DeepSORT Update Path
    # ------------------------------------------------------------------
    def _update_deepsort(self, yolo_detections, frame):
        """
        Convert YOLO detections → DeepSORT format → run tracker → extract results.

        DeepSORT expects each detection as:
            ([left, top, width, height], confidence, class_label)
        """
        # 1. Convert [x1,y1,x2,y2] → [left, top, w, h]
        raw_detections = []
        for det in yolo_detections:
            x1, y1, x2, y2 = det["box"]
            w = max(1, int(x2 - x1))
            h = max(1, int(y2 - y1))
            raw_detections.append(
                ([int(x1), int(y1), w, h], float(det["confidence"]), det["class_name"])
            )

        # 2. Run DeepSORT — it returns a list of Track objects
        try:
            tracks = self.tracker.update_tracks(raw_detections, frame=frame)
        except Exception as e:
            logger.error("DeepSORT update_tracks() failed: %s. Using temp IDs.", e)
            # Safe fallback: return detections with temporary IDs so the frame is not lost
            return [
                {"track_id": f"tmp_{i}", "class_name": d["class_name"], "box": d["box"]}
                for i, d in enumerate(yolo_detections)
            ]

        # 3. Extract only *confirmed* tracks (seen for at least n_init frames)
        active_tracks = []
        for track in tracks:
            if not track.is_confirmed():
                # Tentative tracks are not yet stable — skip them
                continue

            track_id = str(track.track_id)

            # Bounding box in [left, top, right, bottom] format
            ltrb = track.to_ltrb()
            x1, y1, x2, y2 = int(ltrb[0]), int(ltrb[1]), int(ltrb[2]), int(ltrb[3])

            # Class label — verified method name from deep-sort-realtime Track API
            class_name = track.get_det_class()

            # Fallback: if DeepSORT lost the class label, recover it via IoU matching
            if not class_name and yolo_detections:
                class_name = self._resolve_class_by_iou(ltrb, yolo_detections)

            if not class_name:
                # Skip tracks with no resolvable class
                continue

            active_tracks.append({
                "track_id": track_id,
                "class_name": str(class_name),
                "box": [x1, y1, x2, y2],
            })

        logger.debug(
            "DeepSORT: %d raw detections → %d confirmed tracks",
            len(yolo_detections), len(active_tracks),
        )
        return active_tracks

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _resolve_class_by_iou(self, ltrb, yolo_detections):
        """
        Recover the class label for a DeepSORT track whose det_class was lost
        by finding the detection with the highest IoU overlap.
        """
        tx1, ty1, tx2, ty2 = ltrb
        best_iou = 0.0
        best_class = None

        for det in yolo_detections:
            dx1, dy1, dx2, dy2 = det["box"]
            ix1 = max(tx1, dx1)
            iy1 = max(ty1, dy1)
            ix2 = min(tx2, dx2)
            iy2 = min(ty2, dy2)

            if ix2 > ix1 and iy2 > iy1:
                inter = (ix2 - ix1) * (iy2 - iy1)
                union = (tx2 - tx1) * (ty2 - ty1) + (dx2 - dx1) * (dy2 - dy1) - inter
                iou = inter / union if union > 0 else 0.0
                if iou > best_iou:
                    best_iou = iou
                    best_class = det["class_name"]

        return best_class or (yolo_detections[0]["class_name"] if yolo_detections else None)

    # ------------------------------------------------------------------
    # Fallback Tracker (centroid + IoU matching)
    # Used only if deep-sort-realtime fails to initialize
    # ------------------------------------------------------------------
    def _init_fallback_tracker(self):
        self.fallback_tracks = {}   # {track_id: {box, class_name, age, hits}}
        self.next_track_id = 1
        self._fb_max_age = 15
        self._fb_n_init = 2
        self._fb_max_dist = 150     # max pixel distance to match a track

    def _update_fallback(self, yolo_detections):
        """
        Simple centroid distance + class-consistency matching fallback.
        Guarantees the pipeline never crashes even without DeepSORT.
        """
        matched = [False] * len(yolo_detections)

        # Step 1 — match existing tracks to detections
        for tid, track in list(self.fallback_tracks.items()):
            bx1, by1, bx2, by2 = track["box"]
            tcx = (bx1 + bx2) / 2.0
            tcy = (by1 + by2) / 2.0

            best_idx, best_dist = -1, float("inf")
            for i, det in enumerate(yolo_detections):
                if matched[i] or det["class_name"] != track["class_name"]:
                    continue
                dx1, dy1, dx2, dy2 = det["box"]
                dcx = (dx1 + dx2) / 2.0
                dcy = (dy1 + dy2) / 2.0
                dist = ((tcx - dcx) ** 2 + (tcy - dcy) ** 2) ** 0.5
                if dist < self._fb_max_dist and dist < best_dist:
                    best_dist = dist
                    best_idx = i

            if best_idx != -1:
                matched[best_idx] = True
                self.fallback_tracks[tid]["box"] = yolo_detections[best_idx]["box"]
                self.fallback_tracks[tid]["age"] = 0
                self.fallback_tracks[tid]["hits"] += 1
            else:
                self.fallback_tracks[tid]["age"] += 1

        # Step 2 — create new tracks for unmatched detections
        for i, det in enumerate(yolo_detections):
            if not matched[i]:
                tid = str(self.next_track_id)
                self.next_track_id += 1
                self.fallback_tracks[tid] = {
                    "box": det["box"],
                    "class_name": det["class_name"],
                    "age": 0,
                    "hits": 1,
                }

        # Step 3 — prune stale tracks and return confirmed ones
        active = []
        for tid in list(self.fallback_tracks):
            t = self.fallback_tracks[tid]
            if t["age"] > self._fb_max_age:
                del self.fallback_tracks[tid]
            elif t["hits"] >= self._fb_n_init:
                active.append({
                    "track_id": tid,
                    "class_name": t["class_name"],
                    "box": [int(b) for b in t["box"]],
                })

        return active
