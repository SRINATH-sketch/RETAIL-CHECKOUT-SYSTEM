"""
Trace the recommendation pipeline:
YOLO detection -> DeepSORT tracking -> ShoppingAgent confirm -> RetailAgent recommend
"""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

fd, db_path = tempfile.mkstemp()
os.close(fd)

from app.config import Config
Config.DB_PATH = db_path

from app import create_app
app = create_app()

with app.app_context():
    from app.database import db
    from app.services.shopping_agent import ShoppingAgent, ENTRY_CONFIRM_FRAMES
    from app.services.retail_agent import RetailAgent, COMPLEMENTARY_MAP

    db.init_db()

    print("=" * 60)
    print("COMPLEMENTARY MAP (detection class -> recommendation)")
    print("=" * 60)
    for detected_class, suggestions in COMPLEMENTARY_MAP.items():
        for s in suggestions:
            print(f"  YOLO detects '{detected_class}' -> recommends '{s['product_id']}'")
            print(f"    Reason: {s['reason']}")

    print()
    print("=" * 60)
    print("SIMULATING: YOLO detects 'milk' and 'banana'")
    print("=" * 60)

    agent = ShoppingAgent()
    retail = RetailAgent()

    # Simulate 3 frames of YOLO detecting milk (track 7) and banana (track 8)
    fake_tracks = [
        {"track_id": "7", "class_name": "milk",   "box": [10, 20, 80, 100]},
        {"track_id": "8", "class_name": "banana", "box": [90, 20, 160, 100]},
    ]

    for i in range(1, ENTRY_CONFIRM_FRAMES + 1):
        result = agent.update(fake_tracks)
        events = result.get("events", [])
        enter = [e for e in events if e["type"] == "enter"]
        print(f"  Frame {i}: YOLO detects milk + banana -> ", end="")
        if enter:
            for e in enter:
                print(f"CONFIRMED '{e['product_id']}' added to cart!", end=" ")
            print()
        else:
            print(f"pending ({i}/{ENTRY_CONFIRM_FRAMES})")

    print()
    cart = agent.get_cart()
    print("Cart contents after YOLO detection:")
    for p in cart["products"]:
        print(f"  - {p['name']} (x{p['quantity']}) @ Rs.{p['price']}")

    print()
    analysis = retail.analyze(cart)
    print("=" * 60)
    print("RETAIL AGENT RECOMMENDATIONS (based on detected products):")
    print("=" * 60)
    if analysis["recommendations"]:
        for rec in analysis["recommendations"]:
            print(f"  Triggered by: '{rec['triggered_by']}'")
            print(f"  Suggest:       {rec['name']} @ Rs.{rec['price']}")
            print(f"  Reason:        {rec['reason']}")
            print()
    else:
        print("  No recommendations (all complementary items already in cart)")

    print("INSIGHTS:")
    for tip in analysis["insights"]["tips"]:
        print(f"  {tip}")

os.unlink(db_path)
