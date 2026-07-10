"""
Retail Assistant AI Agent
=========================
Analyses the live shopping cart and produces five types of intelligence:

  1. Recommendations  – complementary products not yet in the basket
  2. Discounts        – best available offers auto-applied
  3. Inventory        – stock availability check per cart item
  4. Notifications    – human-readable alerts for basket exit events
  5. Insights         – shopping tips and savings summary

Usage
-----
    agent = RetailAgent()
    result = agent.analyze(cart_summary, exit_events=[])

The `cart_summary` dict is exactly what `db.get_cart_summary()` returns:
    {
        "products": [{"id", "name", "quantity", "price", "subtotal"}, ...],
        "total_bill": float
    }

`exit_events` is the list produced by ShoppingAgent.update() events with type "exit".
"""

from app.database import db
from app.utils.logger import logger


# ---------------------------------------------------------------------------
# Complementary product map
# key   = YOLO class name (must match products.id in DB)
# value = list of suggested product_ids + reason strings
# ---------------------------------------------------------------------------
COMPLEMENTARY_MAP: dict[str, list[dict]] = {
    "milk": [
        {
            "product_id": "cup",
            "reason": "Don't forget a cup to go with your milk! 🥛☕",
        }
    ]
}

# ---------------------------------------------------------------------------
# Discount rules
# Each rule is evaluated in order; multiple rules can stack.
# ---------------------------------------------------------------------------
DISCOUNT_RULES: list[dict] = [
    {
        "id": "BULK_APPLE",
        "description": "Buy 2+ apples and save 10% on apples",
        "condition": lambda cart: _qty(cart, "apple") >= 2,
        "apply": lambda cart: _pct_discount(cart, "apple", 10),
        "badge": "🍎 Bulk Deal",
    },
    {
        "id": "MILK_COMBO",
        "description": "Buy milk + cup together and save 5% on milk",
        "condition": lambda cart: _in_cart(cart, "milk") and _in_cart(cart, "cup"),
        "apply": lambda cart: _pct_discount(cart, "milk", 5),
        "badge": "🥛 Combo Saver",
    },
    {
        "id": "BANANA_DEAL",
        "description": "Buy 3+ bananas and save 15% on bananas",
        "condition": lambda cart: _qty(cart, "banana") >= 3,
        "apply": lambda cart: _pct_discount(cart, "banana", 15),
        "badge": "🍌 Banana Bundle",
    },
    {
        "id": "WELCOME_BUNDLE",
        "description": "Spend ₹200 or more and get a flat ₹20 off",
        "condition": lambda cart: cart.get("total_bill", 0) >= 200,
        "apply": lambda cart: 20.0,
        "badge": "🎁 Welcome Bundle",
    },
    {
        "id": "BIG_SPENDER",
        "description": "Spend ₹500 or more and get a flat ₹75 off",
        "condition": lambda cart: cart.get("total_bill", 0) >= 500,
        "apply": lambda cart: 75.0,
        "badge": "💎 Big Spender",
    },
]

# ---------------------------------------------------------------------------
# Helpers for discount lambdas
# ---------------------------------------------------------------------------

def _qty(cart: dict, product_id: str) -> int:
    for p in cart.get("products", []):
        if p["id"] == product_id:
            return p["quantity"]
    return 0

def _in_cart(cart: dict, product_id: str) -> bool:
    return any(p["id"] == product_id for p in cart.get("products", []))

def _pct_discount(cart: dict, product_id: str, pct: float) -> float:
    for p in cart.get("products", []):
        if p["id"] == product_id:
            return round(p["subtotal"] * pct / 100, 2)
    return 0.0


# ---------------------------------------------------------------------------
# Retail Assistant AI Agent
# ---------------------------------------------------------------------------

class RetailAgent:
    """
    Stateless AI agent — safe to use as a singleton or instantiate per request.
    All intelligence is derived from the live cart snapshot passed to analyze().
    """

    def analyze(self, cart: dict, exit_events: list[dict] | None = None) -> dict:
        """
        Produce a full AI analysis of the current cart.

        Args:
            cart        : dict from db.get_cart_summary()
            exit_events : list of exit-event dicts from ShoppingAgent (optional)

        Returns:
            {
                "recommendations": [...],
                "free_gifts": [...],
                "discounts": [...],
                "discounted_total": float,
                "notifications": [...],
                "inventory": [...],
                "insights": {...}
            }
        """
        if exit_events is None:
            exit_events = []

        recommendations = self._recommend(cart)
        free_gifts = self._evaluate_free_gifts(cart)
        discounts, discounted_total = self._apply_discounts(cart)
        notifications = self._build_notifications(exit_events, cart)
        inventory = self._check_inventory(cart)
        insights = self._generate_insights(cart, discounts, discounted_total, recommendations)

        logger.info(
            "RetailAgent analysis: %d items | ₹%.2f → ₹%.2f after discounts | "
            "%d recommendations | %d gifts | %d notifications",
            len(cart.get("products", [])),
            cart.get("total_bill", 0),
            discounted_total,
            len(recommendations),
            len(free_gifts),
            len(notifications),
        )

        return {
            "recommendations": recommendations,
            "free_gifts": free_gifts,
            "discounts": discounts,
            "discounted_total": round(discounted_total, 2),
            "notifications": notifications,
            "inventory": inventory,
            "insights": insights,
        }

    # ------------------------------------------------------------------
    # 1. Recommendations
    # ------------------------------------------------------------------

    def _recommend(self, cart: dict) -> list[dict]:
        """
        For each item in the cart, check the COMPLEMENTARY_MAP.
        Only suggest products not already in the cart.
        """
        cart_ids = {p["id"] for p in cart.get("products", [])}
        seen_suggestions: set[str] = set()
        recommendations = []

        for product in cart.get("products", []):
            pid = product["id"]
            for suggestion in COMPLEMENTARY_MAP.get(pid, []):
                sugg_id = suggestion["product_id"]
                if sugg_id not in cart_ids and sugg_id not in seen_suggestions:
                    seen_suggestions.add(sugg_id)
                    # Try to fetch price from DB
                    db_product = db.get_product(sugg_id)
                    recommendations.append({
                        "product_id": sugg_id,
                        "name": db_product["name"] if db_product else sugg_id.replace("_", " ").title(),
                        "price": db_product["price"] if db_product else None,
                        "reason": suggestion["reason"],
                        "triggered_by": pid,
                    })

        return recommendations

    def _evaluate_free_gifts(self, cart: dict) -> list[dict]:
        """
        Evaluate conditions for complementary free gifts.
        e.g., Buy 4 Fresh Milk 1L -> Get 1 Cup free.
        """
        gifts = []
        milk_qty = _qty(cart, "milk")
        
        if milk_qty >= 4:
            free_cups = milk_qty // 4
            db_product = db.get_product("cup")
            gifts.append({
                "product_id": "cup",
                "name": db_product["name"] if db_product else "Tea Cup",
                "quantity": free_cups,
                "description": f"Free gift! {free_cups}x {db_product['name'] if db_product else 'Tea Cup'} for buying {free_cups * 4}+ Fresh Milk 1L."
            })
            
        return gifts

    # ------------------------------------------------------------------
    # 2. Discounts
    # ------------------------------------------------------------------

    def _apply_discounts(self, cart: dict) -> tuple[list[dict], float]:
        """
        Evaluate all DISCOUNT_RULES against the current cart.
        Returns (applied_discounts_list, final_total_after_discounts).
        """
        applied = []
        total_saving = 0.0

        for rule in DISCOUNT_RULES:
            try:
                if rule["condition"](cart):
                    saving = rule["apply"](cart)
                    if saving > 0:
                        applied.append({
                            "rule": rule["id"],
                            "description": rule["description"],
                            "badge": rule["badge"],
                            "saving": round(saving, 2),
                        })
                        total_saving += saving
                        logger.debug("Discount applied: %s → saves ₹%.2f", rule["id"], saving)
            except Exception as exc:
                logger.warning("Discount rule %s failed: %s", rule["id"], exc)

        discounted_total = max(0.0, cart.get("total_bill", 0) - total_saving)
        return applied, discounted_total

    # ------------------------------------------------------------------
    # 3. Notifications (basket exit events)
    # ------------------------------------------------------------------

    def _build_notifications(self, exit_events: list[dict], cart: dict) -> list[dict]:
        """
        Convert raw ShoppingAgent exit events into human-readable notifications.
        Also adds low-stock warnings from inventory.
        """
        notifications = []

        for evt in exit_events:
            if evt.get("type") == "exit":
                pid = evt.get("product_id", "item")
                # Try to get the friendly name
                db_product = db.get_product(pid)
                name = db_product["name"] if db_product else pid.replace("_", " ").title()
                notifications.append({
                    "type": "item_removed",
                    "product_id": pid,
                    "message": f"⚠️  '{name}' was removed from your basket.",
                    "severity": "warning",
                })

        # Low-stock warnings
        for product in cart.get("products", []):
            stock = db.get_stock(product["id"])
            if stock is not None and 0 < stock <= 5:
                notifications.append({
                    "type": "low_stock",
                    "product_id": product["id"],
                    "message": f"🔔 Only {stock} unit(s) of '{product['name']}' left in stock!",
                    "severity": "info",
                })

        return notifications

    # ------------------------------------------------------------------
    # 4. Inventory check
    # ------------------------------------------------------------------

    def _check_inventory(self, cart: dict) -> list[dict]:
        """
        For every item in the active cart, verify stock availability.
        """
        inventory_status = []
        for product in cart.get("products", []):
            stock = db.get_stock(product["id"])
            qty_needed = product["quantity"]

            if stock is None:
                # Product not tracked in inventory table — assume available
                status = "available"
                in_stock = True
                stock_level = "unknown"
            elif stock == 0:
                status = "out_of_stock"
                in_stock = False
                stock_level = 0
            elif stock < qty_needed:
                status = "insufficient"
                in_stock = False
                stock_level = stock
            elif stock <= 5:
                status = "low_stock"
                in_stock = True
                stock_level = stock
            else:
                status = "available"
                in_stock = True
                stock_level = stock

            inventory_status.append({
                "product_id": product["id"],
                "name": product["name"],
                "quantity_in_cart": qty_needed,
                "stock": stock_level,
                "in_stock": in_stock,
                "status": status,
            })

        return inventory_status

    # ------------------------------------------------------------------
    # 5. Insights
    # ------------------------------------------------------------------

    def _generate_insights(
        self,
        cart: dict,
        discounts: list[dict],
        discounted_total: float,
        recommendations: list[dict],
    ) -> dict:
        """
        Generate a shopping insights summary.
        """
        products = cart.get("products", [])
        total_bill = cart.get("total_bill", 0)
        item_count = sum(p["quantity"] for p in products)
        total_saving = sum(d["saving"] for d in discounts)

        tips = []

        # Nudges toward discounts not yet unlocked
        apple_qty = _qty(cart, "apple")
        if apple_qty == 1:
            tips.append("🍎 Add 1 more apple to unlock a 10% bulk discount!")
        banana_qty = _qty(cart, "banana")
        if 0 < banana_qty < 3:
            tips.append(f"🍌 Add {3 - banana_qty} more banana(s) to unlock a 15% deal!")
        if total_bill < 200 and total_bill > 0:
            gap = round(200 - total_bill, 2)
            tips.append(f"🎁 Spend ₹{gap} more to unlock a ₹20 flat discount!")
        if total_bill < 500 and total_bill >= 200:
            gap = round(500 - total_bill, 2)
            tips.append(f"💎 Spend ₹{gap} more to unlock a ₹75 Big Spender discount!")

        # Complementary product nudge
        if recommendations:
            rec = recommendations[0]
            tips.append(f"💡 {rec['reason']}")

        # Best value item
        best_value = None
        if products:
            best_value = min(products, key=lambda p: p["price"])["name"]

        return {
            "item_count": item_count,
            "unique_products": len(products),
            "original_total": round(total_bill, 2),
            "you_save": round(total_saving, 2),
            "discounted_total": round(discounted_total, 2),
            "discounts_applied": len(discounts),
            "best_value_item": best_value,
            "tips": tips,
            "cart_status": (
                "empty" if item_count == 0
                else "ready_to_checkout" if item_count >= 2
                else "keep_shopping"
            ),
        }
