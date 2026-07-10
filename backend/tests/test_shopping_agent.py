"""
Unit tests for the AI ShoppingAgent.
Run with:  .\\venv\\Scripts\\python -m pytest tests/test_shopping_agent.py -v
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.config import Config
from app.database import db
from app.services.shopping_agent import ShoppingAgent, ENTRY_CONFIRM_FRAMES, EXIT_TIMEOUT_FRAMES


def _det(track_id: str, class_name: str) -> dict:
    """Helper: build a fake tracked item dict."""
    return {"track_id": str(track_id), "class_name": class_name, "box": [0, 0, 50, 50]}


class ShoppingAgentTestCase(unittest.TestCase):

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp()

        class TestConfig(Config):
            DB_PATH = self.db_path

        self.app = create_app(TestConfig)
        self.client = self.app.test_client()

        with self.app.app_context():
            db.init_db()
            db.upsert_product("apple", "Red Apple", 40.00)
            db.upsert_product("banana", "Organic Banana", 60.00)
            db.upsert_product("milk", "Fresh Milk", 50.00)
            self.agent = ShoppingAgent()

    def tearDown(self):
        os.close(self.db_fd)
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    # ------------------------------------------------------------------
    # 1. Entry confirmation
    # ------------------------------------------------------------------
    def test_entry_requires_confirmation_frames(self):
        """Item must be visible for ENTRY_CONFIRM_FRAMES before entering cart."""
        with self.app.app_context():
            item = _det("1", "apple")

            # Not added yet — below threshold
            for _ in range(ENTRY_CONFIRM_FRAMES - 1):
                result = self.agent.update([item])
                self.assertEqual(result["products"], [], "Cart should be empty before confirmation")

            # This frame pushes over the threshold
            result = self.agent.update([item])
            self.assertEqual(len(result["products"]), 1)
            self.assertEqual(result["products"][0]["id"], "apple")

    def test_enter_event_fired_on_confirmation(self):
        """An 'enter' event must appear in the result when an item is confirmed."""
        with self.app.app_context():
            item = _det("1", "banana")
            events = []
            for _ in range(ENTRY_CONFIRM_FRAMES):
                result = self.agent.update([item])
                events += result.get("events", [])

            enter_events = [e for e in events if e["type"] == "enter"]
            self.assertEqual(len(enter_events), 1)
            self.assertEqual(enter_events[0]["track_id"], "1")
            self.assertEqual(enter_events[0]["product_id"], "banana")

    # ------------------------------------------------------------------
    # 2. Idempotent add (same track ID seen many times = quantity 1)
    # ------------------------------------------------------------------
    def test_idempotent_add_same_track_id(self):
        """The same track_id seen 50 times must yield quantity = 1."""
        with self.app.app_context():
            item = _det("42", "milk")
            for _ in range(50):
                self.agent.update([item])

            cart = self.agent.get_cart()
            milk_rows = [p for p in cart["products"] if p["id"] == "milk"]
            self.assertEqual(len(milk_rows), 1)
            self.assertEqual(milk_rows[0]["quantity"], 1)

    # ------------------------------------------------------------------
    # 3. Multiple physical items of same class → correct quantity
    # ------------------------------------------------------------------
    def test_two_physical_apples_quantity_two(self):
        """Two distinct track IDs for 'apple' must result in quantity = 2."""
        with self.app.app_context():
            a1 = _det("10", "apple")
            a2 = _det("11", "apple")
            for _ in range(ENTRY_CONFIRM_FRAMES):
                self.agent.update([a1, a2])

            cart = self.agent.get_cart()
            apple_rows = [p for p in cart["products"] if p["id"] == "apple"]
            self.assertEqual(apple_rows[0]["quantity"], 2)
            self.assertAlmostEqual(apple_rows[0]["subtotal"], 80.00)

    # ------------------------------------------------------------------
    # 4. Exit — item removed after timeout
    # ------------------------------------------------------------------
    def test_exit_removes_item_after_timeout(self):
        """An item absent for EXIT_TIMEOUT_FRAMES frames must be removed from cart."""
        with self.app.app_context():
            item = _det("99", "banana")

            # Confirm entry
            for _ in range(ENTRY_CONFIRM_FRAMES):
                self.agent.update([item])
            self.assertEqual(len(self.agent.get_cart()["products"]), 1)

            # Item disappears — send empty frame list
            for _ in range(EXIT_TIMEOUT_FRAMES):
                self.agent.update([])
            
            # Item should be gone
            cart = self.agent.get_cart()
            self.assertEqual(cart["products"], [])
            self.assertEqual(cart["total_bill"], 0.0)

    def test_exit_event_fired(self):
        """An 'exit' event must appear when a track times out."""
        with self.app.app_context():
            item = _det("77", "apple")
            for _ in range(ENTRY_CONFIRM_FRAMES):
                self.agent.update([item])

            exit_events = []
            for _ in range(EXIT_TIMEOUT_FRAMES):
                result = self.agent.update([])
                exit_events += [e for e in result.get("events", []) if e["type"] == "exit"]

            self.assertEqual(len(exit_events), 1)
            self.assertEqual(exit_events[0]["track_id"], "77")

    # ------------------------------------------------------------------
    # 5. Transient occlusion does not remove item
    # ------------------------------------------------------------------
    def test_brief_occlusion_does_not_remove(self):
        """Item missing for fewer than EXIT_TIMEOUT_FRAMES frames should stay in cart."""
        with self.app.app_context():
            item = _det("5", "milk")
            for _ in range(ENTRY_CONFIRM_FRAMES):
                self.agent.update([item])

            # Disappear for fewer frames than timeout
            for _ in range(EXIT_TIMEOUT_FRAMES - 1):
                self.agent.update([])

            cart = self.agent.get_cart()
            self.assertEqual(len(cart["products"]), 1, "Item should still be in cart")

            # Reappear — missing_frames counter should reset
            self.agent.update([item])
            self.agent.update([])  # disappear once more — should NOT expire
            cart = self.agent.get_cart()
            self.assertEqual(len(cart["products"]), 1, "Item should still be in cart after reset")

    # ------------------------------------------------------------------
    # 6. Total bill correctness
    # ------------------------------------------------------------------
    def test_total_bill_with_multiple_products(self):
        """Total bill must equal sum of all (qty × price) for active items."""
        with self.app.app_context():
            items = [
                _det("1", "apple"),   # ₹40
                _det("2", "banana"),  # ₹60
                _det("3", "milk"),    # ₹50
            ]
            for _ in range(ENTRY_CONFIRM_FRAMES):
                self.agent.update(items)

            cart = self.agent.get_cart()
            self.assertAlmostEqual(cart["total_bill"], 150.00)

    # ------------------------------------------------------------------
    # 7. Reset clears everything
    # ------------------------------------------------------------------
    def test_reset_clears_cart_and_state(self):
        """After reset(), cart is empty and agent has no active/pending tracks."""
        with self.app.app_context():
            for _ in range(ENTRY_CONFIRM_FRAMES):
                self.agent.update([_det("1", "apple")])

            self.agent.reset()
            self.assertEqual(self.agent.active_track_count, 0)
            self.assertEqual(self.agent.pending_track_count, 0)
            self.assertEqual(self.agent.get_cart()["products"], [])

    # ------------------------------------------------------------------
    # 8. Auto-register unknown product
    # ------------------------------------------------------------------
    def test_auto_registers_unknown_product(self):
        """A YOLO class not in DB should be auto-registered with default price."""
        with self.app.app_context():
            item = _det("1", "chocolate_bar")
            for _ in range(ENTRY_CONFIRM_FRAMES):
                self.agent.update([item])

            cart = self.agent.get_cart()
            self.assertEqual(len(cart["products"]), 1)
            self.assertEqual(cart["products"][0]["id"], "chocolate_bar")
            self.assertGreater(cart["products"][0]["price"], 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
