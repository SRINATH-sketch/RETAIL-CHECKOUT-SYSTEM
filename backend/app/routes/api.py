import os
import uuid
import cv2
import numpy as np
from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename
from app.config import Config
from app.services.detection_service import DetectionService
from app.services.tracking_service import TrackingService
from app.services.shopping_agent import ShoppingAgent
from app.services.checkout_service import CheckoutService
from app.services.retail_agent import RetailAgent
from app.utils.logger import logger
from app.utils.error_handlers import APIException
from app.database import db

api_bp = Blueprint('api', __name__)

# ---------------------------------------------------------------------------
# Singleton services shared across all requests
# ---------------------------------------------------------------------------
detection_service = DetectionService()      # stateless YOLO inference
checkout_service  = CheckoutService()       # cart helpers / product DB
_retail_agent     = RetailAgent()           # AI retail intelligence (stateless)

# One persistent agent + tracker for live webcam streaming sessions
_webcam_tracker = TrackingService()
_webcam_agent   = ShoppingAgent()


def allowed_file(filename, allowed_extensions):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions


# ---------------------------------------------------------------------------
# POST /api/detect
# ---------------------------------------------------------------------------
@api_bp.route('/detect', methods=['POST'])
def detect_video():
    """
    Upload and process a video file.

    Flow
    ----
    1. Receive video upload (or demo flag).
    2. Run YOLOv11 frame-by-frame.
    3. Feed detections into DeepSORT tracker.
    4. Pass tracked items to ShoppingAgent each frame.
       - Agent fires ENTER events → add to cart.
       - Agent fires EXIT events  → remove from cart.
    5. Draw annotated bounding boxes on each frame.
    6. Return JSON with cart summary + processed video URL.
    """
    use_demo = (
        request.form.get('use_demo') == 'true'
        or request.args.get('use_demo') == 'true'
    )

    # ── Resolve input video path ──────────────────────────────────────────
    if use_demo:
        demo_path = os.path.join(current_app.config['UPLOAD_FOLDER'], "demo.mp4")
        if not os.path.exists(demo_path):
            import urllib.request as _url
            demo_url = "https://www.w3schools.com/html/mov_bbb.mp4"
            try:
                logger.info("Downloading demo video from %s …", demo_url)
                os.makedirs(os.path.dirname(demo_path), exist_ok=True)
                req = _url.Request(
                    demo_url,
                    headers={
                        'User-Agent': (
                            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                            'AppleWebKit/537.36 (KHTML, like Gecko) '
                            'Chrome/58.0.3029.110 Safari/537.3'
                        )
                    }
                )
                with _url.urlopen(req) as resp, open(demo_path, 'wb') as f:
                    f.write(resp.read())
                logger.info("Demo video downloaded successfully.")
            except Exception as e:
                logger.error("Failed to download demo video: %s", e)
                raise APIException(f"Failed to download demo video: {e}", 500)

        unique_id = uuid.uuid4().hex[:8]
        input_filename = f"upload_{unique_id}_demo.mp4"
        input_path = os.path.join(current_app.config['UPLOAD_FOLDER'], input_filename)
        import shutil
        shutil.copy2(demo_path, input_path)
        filename_stem = "demo"
        logger.info("Demo video copied to: %s", input_path)

    else:
        if 'file' not in request.files:
            raise APIException("No video file in request.", 400)
        file = request.files['file']
        if file.filename == '':
            raise APIException("Empty filename.", 400)
        if not allowed_file(file.filename, Config.ALLOWED_VIDEO_EXTENSIONS):
            raise APIException("Invalid format. Supported: MP4, AVI, MOV, WEBM.", 400)

        filename = secure_filename(file.filename)
        unique_id = uuid.uuid4().hex[:8]
        input_filename = f"upload_{unique_id}_{filename}"
        input_path = os.path.join(current_app.config['UPLOAD_FOLDER'], input_filename)
        file.save(input_path)
        filename_stem = filename.rsplit('.', 1)[0]
        logger.info("Video saved to: %s", input_path)

    # ── Open video ────────────────────────────────────────────────────────
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise APIException("Cannot open uploaded video.", 400)

    width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps    = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total  = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    logger.info("Video: %dx%d  %.2f fps  %d frames", width, height, fps, total)

    # ── Output video writer ───────────────────────────────────────────────
    output_filename = f"processed_{unique_id}_{filename_stem}.mp4"
    output_path = os.path.join(current_app.config['UPLOAD_FOLDER'], output_filename)
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    # ── Per-video fresh agent + tracker ──────────────────────────────────
    # A new ShoppingAgent means we start from an empty basket for this video.
    video_tracker = TrackingService()
    agent = ShoppingAgent()
    db.clear_cart()  # reset DB cart for this session

    MAX_FRAMES = 600   # process at most 600 frames (~20 s at 30 fps)
    processed = 0
    _all_events: list[dict] = []   # accumulate enter/exit events across all frames

    LABEL_COLORS = {
        'banana': (0, 215, 255),
        'bananas': (0, 215, 255),
        'milk': (255, 255, 255),
        'bottle': (255, 200, 150),
        'bread': (50, 120, 200),
        'cookies': (100, 50, 150),
    }
    DEFAULT_COLOR = (0, 255, 0)

    try:
        while cap.isOpened() and processed < MAX_FRAMES:
            ret, frame = cap.read()
            if not ret:
                break

            # ── YOLO detection (unchanged) ────────────────────────────
            detections = detection_service.detect_frame(frame)

            # ── DeepSORT tracking ─────────────────────────────────────
            tracked_items = video_tracker.update(detections, frame)

            # ── AI Shopping Agent — basket update ─────────────────────
            cart_state = agent.update(tracked_items)
            frame_events = cart_state.get("events", [])
            _all_events.extend(frame_events)

            # Log any enter / exit events
            for evt in frame_events:
                if evt["type"] == "enter":
                    logger.debug(
                        "CART + %-12s  track_id=%s", evt["product_id"], evt["track_id"]
                    )
                elif evt["type"] == "exit":
                    logger.debug(
                        "CART - %-12s  track_id=%s", evt["product_id"], evt["track_id"]
                    )

            # ── Draw bounding boxes ───────────────────────────────────
            for item in tracked_items:
                track_id  = item['track_id']
                class_name = item['class_name']
                x1, y1, x2, y2 = item['box']
                color = LABEL_COLORS.get(class_name.lower(), DEFAULT_COLOR)

                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 3)

                label = f"{class_name.upper()} #{track_id}"
                font, fs, th = cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2
                (tw, tht), _ = cv2.getTextSize(label, font, fs, th)
                cv2.rectangle(frame, (x1, y1 - tht - 10), (x1 + tw + 10, y1), color, -1)
                text_color = (0, 0, 0) if color == (255, 255, 255) else (255, 255, 255)
                cv2.putText(frame, label, (x1 + 5, y1 - 5), font, fs, text_color, th)

            out.write(frame)
            processed += 1

    except Exception as e:
        logger.exception("Error during video frame processing:")
        raise APIException(f"Failed to process video: {e}", 500)
    finally:
        cap.release()
        out.release()
        if os.path.exists(input_path):
            os.remove(input_path)

    # ── Final cart summary + Retail Agent analysis ────────────────────────
    cart_summary = agent.get_cart()
    video_url    = f"http://localhost:5000/static/uploads/{output_filename}"

    # Collect all exit events accumulated during the video session
    all_exit_events = [
        evt for evt in _all_events if evt.get("type") == "exit"
    ]
    agent_analysis = _retail_agent.analyze(cart_summary, all_exit_events)

    logger.info(
        "Detection complete: %d frames | %d active tracks | ₹%.2f → ₹%.2f (after discounts)",
        processed,
        agent.active_track_count,
        cart_summary["total_bill"],
        agent_analysis["discounted_total"],
    )

    return jsonify({
        "success": True,
        "message": f"Processed {processed} frames.",
        "video_url": video_url,
        "products": cart_summary["products"],
        "total_bill": cart_summary["total_bill"],
        "agent": agent_analysis,
    })


# ---------------------------------------------------------------------------
# POST /api/detect-frame
# ---------------------------------------------------------------------------
@api_bp.route('/detect-frame', methods=['POST'])
def detect_frame():
    """
    Live webcam endpoint — processes one frame at a time.
    Uses a persistent global ShoppingAgent so basket state is maintained
    across successive frames from the same camera session.
    """
    if 'file' not in request.files:
        raise APIException("No image file uploaded.", 400)
    file = request.files['file']
    if file.filename == '':
        raise APIException("Empty filename.", 400)
    if not allowed_file(file.filename, Config.ALLOWED_IMAGE_EXTENSIONS):
        raise APIException("Invalid image format.", 400)

    file_bytes = np.frombuffer(file.read(), np.uint8)
    frame = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
    if frame is None:
        raise APIException("Cannot decode image frame.", 400)

    detections    = detection_service.detect_frame(frame)
    tracked_items = _webcam_tracker.update(detections, frame)
    cart_state    = _webcam_agent.update(tracked_items)
    exit_events   = [e for e in cart_state.get("events", []) if e["type"] == "exit"]
    agent_analysis = _retail_agent.analyze(
        {"products": cart_state["products"], "total_bill": cart_state["total_bill"]},
        exit_events,
    )

    return jsonify({
        "success": True,
        "detections": tracked_items,
        "products": cart_state["products"],
        "total_bill": cart_state["total_bill"],
        "events": cart_state.get("events", []),
        "agent": agent_analysis,
    })


# ---------------------------------------------------------------------------
# GET  /api/cart
# ---------------------------------------------------------------------------
@api_bp.route('/cart', methods=['GET'])
def get_cart():
    """Return current shopping cart contents."""
    summary = db.get_cart_summary()
    return jsonify({"success": True, **summary})


# ---------------------------------------------------------------------------
# DELETE /api/cart
# ---------------------------------------------------------------------------
@api_bp.route('/cart', methods=['DELETE'])
def clear_cart():
    """Reset cart — also resets the webcam agent basket state."""
    result = _webcam_agent.reset()
    return jsonify(result)


# ---------------------------------------------------------------------------
# GET /api/products
# ---------------------------------------------------------------------------
@api_bp.route('/products', methods=['GET'])
def list_products():
    """List all registered products and prices."""
    products = db.get_all_products()
    return jsonify({"success": True, "products": products})


# ---------------------------------------------------------------------------
# POST /api/products
# ---------------------------------------------------------------------------
@api_bp.route('/products', methods=['POST'])
def add_product():
    """
    Add or update a product.
    Body: {"id": "banana", "name": "Organic Bananas", "price": 60.00}
    """
    data = request.get_json() or {}
    if not data.get('id') or not data.get('name') or data.get('price') is None:
        raise APIException("Missing required fields: id, name, price", 400)
    try:
        price = float(data['price'])
    except (ValueError, TypeError):
        raise APIException("Price must be a valid number.", 400)

    db.upsert_product(data['id'], data['name'], price)
    return jsonify({
        "success": True,
        "message": f"Product '{data['name']}' registered/updated successfully.",
    })


# ---------------------------------------------------------------------------
# GET /api/agent/analyze
# ---------------------------------------------------------------------------
@api_bp.route('/agent/analyze', methods=['GET'])
def agent_analyze():
    """
    On-demand Retail Agent analysis of the current cart.
    The frontend can poll this endpoint at any time to get:
      - Complementary product recommendations
      - Applied discounts and savings
      - Inventory availability
      - Shopping insights and tips
    No body required — reads the live SQLite cart.
    """
    cart = db.get_cart_summary()
    analysis = _retail_agent.analyze(cart, exit_events=[])
    return jsonify({
        "success": True,
        "cart": cart,
        **analysis,
    })


# ---------------------------------------------------------------------------
# GET /api/inventory
# ---------------------------------------------------------------------------
@api_bp.route('/inventory', methods=['GET'])
def get_inventory():
    """
    Return stock levels for all products in the inventory table.
    """
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT i.product_id, p.name, i.stock
        FROM inventory i
        LEFT JOIN products p ON i.product_id = p.id
        ORDER BY p.name
    ''')
    rows = cursor.fetchall()
    conn.close()
    return jsonify({
        "success": True,
        "inventory": [dict(r) for r in rows],
    })
