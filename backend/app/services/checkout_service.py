from app.database import db
from app.utils.logger import logger

class CheckoutService:
    """
    Service to manage products in the shopping cart and lookup prices in SQLite.
    """
    def __init__(self):
        # Ensure database tables are initialized
        db.init_db()

    def process_tracked_item(self, track_id, class_name):
        """
        Processes a tracked item. Looks up the product in the SQLite database by class_name.
        If it doesn't exist, automatically registers the product with a default price.
        Adds the unique track_id to the cart (enforcing single-add constraints).
        """
        # Clean class name for matching (e.g., lowercased and stripped)
        product_id = class_name.lower().strip()
        
        # Check if product exists in database
        product = db.get_product(product_id)
        
        if not product:
            # Auto-register product with a default price to prevent system crash
            # Name will be capitalized class name
            default_name = product_id.replace('_', ' ').title()
            default_price = 50.00
            
            logger.warning(
                f"Product class '{product_id}' not found in database. "
                f"Auto-registering product: '{default_name}' at ₹{default_price:.2f}."
            )
            db.upsert_product(product_id, default_name, default_price)
            
        # Add to cart using the unique track_id.
        # SQLite PRIMARY KEY constraint handles adding exactly once.
        inserted = db.add_to_cart(track_id, product_id)
        
        if inserted:
            product_data = db.get_product(product_id)
            logger.info(f"Added to cart: {product_data['name']} (Track ID: {track_id})")
            return {
                "track_id": track_id,
                "product_id": product_id,
                "name": product_data["name"],
                "price": product_data["price"],
                "newly_added": True
            }
            
        return {
            "track_id": track_id,
            "product_id": product_id,
            "newly_added": False
        }

    def get_cart(self):
        """
        Retrieve the current cart summary: products list with subtotals and the total bill.
        """
        return db.get_cart_summary()

    def reset_checkout(self):
        """
        Clear all items in the active checkout session cart.
        """
        db.clear_cart()
        logger.info("Checkout session cart has been reset.")
        return {"success": True, "message": "Shopping cart has been cleared."}
        
    def populate_product_database(self, products_list):
        """
        Populate the database with a list of products (typically for seeding).
        products_list is a list of tuples: (product_id, name, price)
        """
        for pid, name, price in products_list:
            db.upsert_product(pid, name, price)
        logger.info(f"Seeded/Updated {len(products_list)} products in the SQLite database.")
