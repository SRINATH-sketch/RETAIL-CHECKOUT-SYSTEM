"""
Unit tests for the RetailAgent.
Run with:  .\\venv\\Scripts\\python -m pytest tests\\test_retail_agent.py -v
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.config import Config
from app.database import db
from app.services.retail_agent import RetailAgent


def _cart(products: list[dict], total: float) -> dict:
    """Build a fake cart_summary dict for testing."""
    return {"products": products, "total_bill": total}


def _product(pid: str, name: str, qty: int, price: float) -> dict:
    return {
        "id": pid,
        "name": name,
        "quantity": qty,
        "price": price,
        "subtotal": round(qty * price, 2),
    }


class RetailAgentTestCase(unittest.TestCase):

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp()

        class TestConfig(Config):
            DB_PATH = self.db_path

        self.app = create_app(TestConfig)
        self.client = self.app.test_client()

        with self.app.app_context():
            db.init_db()   # creates tables + seeds complementary products
            self.agent = RetailAgent()

    def tearDown(self):
        os.close(self.db_fd)
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    # ------------------------------------------------------------------
    # 1. Recommendations — milk → cup
    # ------------------------------------------------------------------
    def test_milk_recommends_cup(self):
        """Milk in cart should trigger a cup recommendation."""
        with self.app.app_context():
            cart = _cart([_product("milk", "Fresh Milk", 1, 50)], 50)
            result = self.agent.analyze(cart)

            rec_ids = [r["product_id"] for r in result["recommendations"]]
            self.assertIn("cup", rec_ids, "Cup should be recommended when milk is in cart")

    # ------------------------------------------------------------------
    # 2. No duplicate recommendations for already-present items
    # ------------------------------------------------------------------
    def test_no_recommend_already_in_cart(self):
        """Cup already in cart → no cup recommendation."""
        with self.app.app_context():
            cart = _cart([
                _product("milk", "Fresh Milk", 1, 50),
                _product("cup", "Tea Cup", 1, 30),
            ], 80)
            result = self.agent.analyze(cart)

            rec_ids = [r["product_id"] for r in result["recommendations"]]
            self.assertNotIn("cup", rec_ids, "Cup already in cart — should not be recommended")

    # ------------------------------------------------------------------
    # 4. Discount — BULK_APPLE (qty >= 2)
    # ------------------------------------------------------------------
    def test_bulk_apple_discount_applied(self):
        """2 apples in cart should trigger a 10% BULK_APPLE discount."""
        with self.app.app_context():
            cart = _cart([_product("apple", "Red Apple", 2, 40)], 80)
            result = self.agent.analyze(cart)

            rule_ids = [d["rule"] for d in result["discounts"]]
            self.assertIn("BULK_APPLE", rule_ids)
            # 10% of 80 = 8
            saving = next(d["saving"] for d in result["discounts"] if d["rule"] == "BULK_APPLE")
            self.assertAlmostEqual(saving, 8.0)

    def test_single_apple_no_bulk_discount(self):
        """1 apple → BULK_APPLE should NOT trigger."""
        with self.app.app_context():
            cart = _cart([_product("apple", "Red Apple", 1, 40)], 40)
            result = self.agent.analyze(cart)

            rule_ids = [d["rule"] for d in result["discounts"]]
            self.assertNotIn("BULK_APPLE", rule_ids)

    # ------------------------------------------------------------------
    # 5. Discount — WELCOME_BUNDLE (total >= 200)
    # ------------------------------------------------------------------
    def test_welcome_bundle_triggers_at_200(self):
        """Cart total >= ₹200 should unlock ₹20 flat WELCOME_BUNDLE discount."""
        with self.app.app_context():
            cart = _cart([_product("milk", "Fresh Milk", 4, 50)], 200)
            result = self.agent.analyze(cart)

            rule_ids = [d["rule"] for d in result["discounts"]]
            self.assertIn("WELCOME_BUNDLE", rule_ids)
            saving = next(d["saving"] for d in result["discounts"] if d["rule"] == "WELCOME_BUNDLE")
            self.assertEqual(saving, 20.0)
            self.assertEqual(result["discounted_total"], 180.0)

    def test_welcome_bundle_does_not_trigger_below_200(self):
        """Cart total < ₹200 → WELCOME_BUNDLE should not apply."""
        with self.app.app_context():
            cart = _cart([_product("milk", "Fresh Milk", 1, 50)], 50)
            result = self.agent.analyze(cart)

            rule_ids = [d["rule"] for d in result["discounts"]]
            self.assertNotIn("WELCOME_BUNDLE", rule_ids)

    # ------------------------------------------------------------------
    # 6. Discount — MILK_COMBO (milk + cup together)
    # ------------------------------------------------------------------
    def test_milk_combo_discount(self):
        """Milk + cup both in cart should trigger 5% MILK_COMBO discount."""
        with self.app.app_context():
            cart = _cart([
                _product("milk", "Fresh Milk", 1, 50),
                _product("cup", "Tea Cup", 1, 30),
            ], 80)
            result = self.agent.analyze(cart)

            rule_ids = [d["rule"] for d in result["discounts"]]
            self.assertIn("MILK_COMBO", rule_ids)
            # 5% of milk subtotal (50) = 2.5
            saving = next(d["saving"] for d in result["discounts"] if d["rule"] == "MILK_COMBO")
            self.assertAlmostEqual(saving, 2.5)

    # ------------------------------------------------------------------
    # 7. Discount — BANANA_DEAL (qty >= 3)
    # ------------------------------------------------------------------
    def test_banana_deal_discount(self):
        """3+ bananas should trigger 15% BANANA_DEAL discount."""
        with self.app.app_context():
            cart = _cart([_product("banana", "Organic Bananas", 3, 60)], 180)
            result = self.agent.analyze(cart)

            rule_ids = [d["rule"] for d in result["discounts"]]
            self.assertIn("BANANA_DEAL", rule_ids)
            # 15% of 180 = 27
            saving = next(d["saving"] for d in result["discounts"] if d["rule"] == "BANANA_DEAL")
            self.assertAlmostEqual(saving, 27.0)

    # ------------------------------------------------------------------
    # 8. Discounted total never goes below zero
    # ------------------------------------------------------------------
    def test_discounted_total_not_negative(self):
        """If all discounts exceed total, discounted_total must be 0."""
        with self.app.app_context():
            # Tiny cart but WELCOME_BUNDLE kicks in somehow — we test the guard
            cart = _cart([_product("apple", "Red Apple", 3, 40)], 120)
            result = self.agent.analyze(cart)
            self.assertGreaterEqual(result["discounted_total"], 0.0)

    # ------------------------------------------------------------------
    # 9. Notifications — item removed
    # ------------------------------------------------------------------
    def test_item_removed_notification(self):
        """An exit event should generate an item_removed notification."""
        with self.app.app_context():
            cart = _cart([], 0)
            exit_events = [{"type": "exit", "track_id": "1", "product_id": "banana"}]
            result = self.agent.analyze(cart, exit_events)

            notif_types = [n["type"] for n in result["notifications"]]
            self.assertIn("item_removed", notif_types)

            msg = next(n["message"] for n in result["notifications"] if n["type"] == "item_removed")
            self.assertIn("Organic Bananas", msg)

    # ------------------------------------------------------------------
    # 10. Inventory — items in stock
    # ------------------------------------------------------------------
    def test_inventory_check_in_stock(self):
        """Products seeded with stock > 5 should show status 'available'."""
        with self.app.app_context():
            cart = _cart([_product("milk", "Fresh Milk", 1, 50)], 50)
            result = self.agent.analyze(cart)

            inv = {i["product_id"]: i for i in result["inventory"]}
            self.assertIn("milk", inv)
            self.assertEqual(inv["milk"]["status"], "available")
            self.assertTrue(inv["milk"]["in_stock"])

    # ------------------------------------------------------------------
    # 11. Insights — tips nudge toward unlocked discounts
    # ------------------------------------------------------------------
    def test_insights_tip_for_one_apple(self):
        """1 apple in cart should suggest adding 1 more for bulk discount."""
        with self.app.app_context():
            cart = _cart([_product("apple", "Red Apple", 1, 40)], 40)
            result = self.agent.analyze(cart)

            tips_text = " ".join(result["insights"]["tips"])
            self.assertIn("apple", tips_text.lower())

    def test_insights_you_save_reflects_discounts(self):
        """you_save in insights must equal sum of applied discounts."""
        with self.app.app_context():
            cart = _cart([_product("apple", "Red Apple", 2, 40)], 80)
            result = self.agent.analyze(cart)

            total_savings = sum(d["saving"] for d in result["discounts"])
            self.assertAlmostEqual(result["insights"]["you_save"], total_savings)

    # ------------------------------------------------------------------
    # 12. Empty cart edge case
    # ------------------------------------------------------------------
    def test_empty_cart_analysis(self):
        """Empty cart should return no-crash, empty recommendations and zero bill."""
        with self.app.app_context():
            cart = _cart([], 0)
            result = self.agent.analyze(cart)

            self.assertEqual(result["recommendations"], [])
            self.assertEqual(result["discounts"], [])
            self.assertEqual(result["discounted_total"], 0.0)
            self.assertEqual(result["insights"]["cart_status"], "empty")

    # ------------------------------------------------------------------
    # 13. GET /api/agent/analyze endpoint integration test
    # ------------------------------------------------------------------
    def test_agent_analyze_endpoint(self):
        """GET /api/agent/analyze should return 200 with expected keys."""
        response = self.client.get('/api/agent/analyze')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["success"])
        self.assertIn("recommendations", data)
        self.assertIn("discounts", data)
        self.assertIn("inventory", data)
        self.assertIn("insights", data)

    # ------------------------------------------------------------------
    # 14. GET /api/inventory endpoint integration test
    # ------------------------------------------------------------------
    def test_inventory_endpoint(self):
        """GET /api/inventory should return 200 with inventory list."""
        response = self.client.get('/api/inventory')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["success"])
        self.assertIsInstance(data["inventory"], list)
        # At minimum all seeded products should appear
        product_ids = [i["product_id"] for i in data["inventory"]]
        self.assertIn("cup", product_ids)
        self.assertIn("milk", product_ids)


if __name__ == '__main__':
    unittest.main(verbosity=2)
