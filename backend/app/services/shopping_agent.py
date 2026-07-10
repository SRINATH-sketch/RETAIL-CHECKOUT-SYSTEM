"""
AI Shopping Agent
=================
Maintains a live basket by observing DeepSORT track enter/exit events.

Rules
-----
* **Enter** – a track_id seen for ENTRY_CONFIRM_FRAMES consecutive frames
  is added to the SQLite cart exactly once.
* **Persist** – the same track_id visible in subsequent frames → no-op.
* **Exit** – a track_id absent for EXIT_TIMEOUT_FRAMES frames is removed
  from the cart (the physical product has left the basket).

Quantity in the cart = number of distinct track_ids for that product class
that are currently in the active basket.
"""

from app.database import db
from app.utils.logger import logger


# ------------------------------------------------------------------
# Tuneable parameters
# ------------------------------------------------------------------
ENTRY_CONFIRM_FRAMES: int = 3    # consecutive frames required before adding to cart
EXIT_TIMEOUT_FRAMES: int = 15   # consecutive missing frames before removing from cart
DEFAULT_PRICE: float = 50.00    # fallback price for unregistered YOLO classes


class ShoppingAgent:
    """
    AI Shopping Agent — per-session, frame-driven basket manager.

    Instantiate one ShoppingAgent per video processing session (or one
    shared instance for a live webcam stream).

    Call `update(tracked_items)` every frame.
    Call `get_cart()` to read the current bill.
    Call `reset()` to clear state + DB cart.
    """

    def __init__(self):
        # track_id → {"class_name": str, "seen_count": int}
        # Items waiting for confirmation before entering the cart
        self._pending: dict[str, dict] = {}

        # track_id → {"class_name": str, "missing_frames": int}
        # Confirmed items currently in the active basket
        self._active: dict[str, dict] = {}

        self._frame_no: int = 0
        logger.info(
            "ShoppingAgent initialized "
            "(entry_confirm=%d, exit_timeout=%d frames)",
            ENTRY_CONFIRM_FRAMES, EXIT_TIMEOUT_FRAMES,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(self, tracked_items: list[dict]) -> dict:
        """
        Process one frame of DeepSORT output and update the basket.

        Args:
            tracked_items: list of dicts from TrackingService.update()
                           Each dict: {"track_id": str, "class_name": str, "box": list}

        Returns:
            cart_summary dict  →  {"products": [...], "total_bill": float,
                                   "events": [{"type": "enter"|"exit", ...}]}
        """
        self._frame_no += 1
        current_ids: set[str] = {item["track_id"] for item in tracked_items}
        id_to_class: dict[str, str] = {
            item["track_id"]: item["class_name"] for item in tracked_items
        }

        events: list[dict] = []

        # ── Step 1 · Process visible tracks ──────────────────────────
        for track_id, class_name in id_to_class.items():
            if track_id in self._active:
                # Already confirmed in basket — reset exit countdown
                self._active[track_id]["missing_frames"] = 0

            elif track_id in self._pending:
                # Accumulate confirmation frames
                self._pending[track_id]["seen_count"] += 1
                if self._pending[track_id]["seen_count"] >= ENTRY_CONFIRM_FRAMES:
                    # Promote to active basket
                    evt = self._enter_basket(track_id, class_name)
                    events.append(evt)
                    del self._pending[track_id]
            else:
                # Brand new track — start pending confirmation
                self._pending[track_id] = {
                    "class_name": class_name,
                    "seen_count": 1,
                }
                logger.debug(
                    "ShoppingAgent: track %s (%s) pending entry [1/%d]",
                    track_id, class_name, ENTRY_CONFIRM_FRAMES,
                )

        # ── Step 2 · Age tracks that are no longer visible ───────────
        for track_id in list(self._active.keys()):
            if track_id not in current_ids:
                self._active[track_id]["missing_frames"] += 1
                if self._active[track_id]["missing_frames"] >= EXIT_TIMEOUT_FRAMES:
                    evt = self._exit_basket(track_id)
                    events.append(evt)

        # Also prune pending tracks that have gone missing
        for track_id in list(self._pending.keys()):
            if track_id not in current_ids:
                logger.debug(
                    "ShoppingAgent: pending track %s gone before confirmation — discarded.",
                    track_id,
                )
                del self._pending[track_id]

        # ── Step 3 · Return current cart ─────────────────────────────
        summary = db.get_cart_summary()
        summary["events"] = events
        return summary

    def get_cart(self) -> dict:
        """Return the current cart summary from SQLite."""
        return db.get_cart_summary()

    def reset(self) -> dict:
        """Clear agent state and the SQLite cart."""
        self._pending.clear()
        self._active.clear()
        self._frame_no = 0
        db.clear_cart()
        logger.info("ShoppingAgent: basket reset — cart cleared.")
        return {"success": True, "message": "Shopping basket has been reset."}

    @property
    def active_track_count(self) -> int:
        """Number of confirmed track IDs currently in the basket."""
        return len(self._active)

    @property
    def pending_track_count(self) -> int:
        """Number of track IDs waiting for entry confirmation."""
        return len(self._pending)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _ensure_product(self, class_name: str) -> dict:
        """
        Look up a product by its YOLO class label.
        Auto-registers with a default price if not found in the DB,
        so a missing entry never crashes the pipeline.
        """
        product_id = class_name.lower().strip()
        product = db.get_product(product_id)

        if not product:
            default_name = product_id.replace("_", " ").title()
            logger.warning(
                "ShoppingAgent: product '%s' not in DB — auto-registering at ₹%.2f",
                product_id, DEFAULT_PRICE,
            )
            db.upsert_product(product_id, default_name, DEFAULT_PRICE)
            product = db.get_product(product_id)

        return dict(product)

    def _enter_basket(self, track_id: str, class_name: str) -> dict:
        """
        Confirmed entry event — add to SQLite cart and active state.
        INSERT OR IGNORE guarantees track_id is added exactly once even if
        called multiple times (extra safety net on top of agent logic).
        """
        product = self._ensure_product(class_name)
        product_id = product["id"]

        inserted = db.add_to_cart(track_id, product_id)

        self._active[track_id] = {
            "class_name": class_name,
            "product_id": product_id,
            "missing_frames": 0,
        }

        if inserted:
            logger.info(
                "ShoppingAgent ▶ ENTER  track_id=%-5s  product=%-15s  price=₹%.2f",
                track_id, product["name"], product["price"],
            )
        else:
            logger.debug(
                "ShoppingAgent: track %s already in cart (idempotent).", track_id
            )

        return {
            "type": "enter",
            "track_id": track_id,
            "product_id": product_id,
            "product_name": product["name"],
            "price": product["price"],
            "newly_inserted": inserted,
        }

    def _exit_basket(self, track_id: str) -> dict:
        """
        Confirmed exit event — remove from SQLite cart and active state.
        """
        track_data = self._active.pop(track_id, {})
        product_id = track_data.get("product_id", "unknown")
        class_name = track_data.get("class_name", "unknown")

        removed = db.remove_from_cart(track_id)

        logger.info(
            "ShoppingAgent ◀ EXIT   track_id=%-5s  product=%s  (removed=%s)",
            track_id, class_name, removed,
        )

        return {
            "type": "exit",
            "track_id": track_id,
            "product_id": product_id,
            "removed_from_db": removed,
        }
