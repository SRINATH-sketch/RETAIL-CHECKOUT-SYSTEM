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
import joblib
import jwt
import datetime
from flask_bcrypt import Bcrypt
from functools import wraps

#For chatbot
from app.chatbot.chatbot import chatbot_response

api_bp = Blueprint('api', __name__)
bcrypt = Bcrypt()

# ---------------------------------------------------------------------------
# Singleton services shared across all requests
# ---------------------------------------------------------------------------
detection_service = DetectionService()      # stateless YOLO inference
checkout_service  = CheckoutService()       # cart helpers / product DB
_retail_agent     = RetailAgent()           # AI retail intelligence (stateless)

chatbot_model = joblib.load("model/chatbot_model.pkl")
chatbot_vectorizer = joblib.load("model/vectorizer.pkl")

# One persistent agent + tracker for live webcam streaming sessions
_webcam_tracker = TrackingService()
_webcam_agent   = ShoppingAgent(store_id=1, user_id=1)


def allowed_file(filename, allowed_extensions):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions


# ---------------------------------------------------------------------------
# Auth Middleware
# ---------------------------------------------------------------------------
def token_optional(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            parts = request.headers['Authorization'].split()
            if len(parts) == 2 and parts[0] == 'Bearer':
                token = parts[1]
        
        user_id = 1 # default admin user for testing legacy frontend
        store_id = 1 # default store for testing legacy frontend
        
        if token:
            try:
                data = jwt.decode(token, current_app.config['JWT_SECRET_KEY'], algorithms=["HS256"])
                user_id = data['user_id']
                # Optionally client can pass store_id in headers, otherwise default to first store
                store_id = request.headers.get('X-Store-ID', type=int)
                if not store_id:
                    stores = db.get_user_stores(user_id)
                    if stores:
                        store_id = stores[0]['id']
                    else:
                        raise APIException("User does not belong to any store", 403)
                
                # verify membership
                role = db.check_store_membership(user_id, store_id)
                if not role:
                    raise APIException("Not authorized for this store", 403)
            except jwt.ExpiredSignatureError:
                raise APIException("Token has expired", 401)
            except jwt.InvalidTokenError:
                raise APIException("Invalid token", 401)
                
        request.user_id = user_id
        request.store_id = store_id
        return f(*args, **kwargs)
    return decorated

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            parts = request.headers['Authorization'].split()
            if len(parts) == 2 and parts[0] == 'Bearer':
                token = parts[1]
        
        if not token:
            raise APIException("Authentication token is missing", 401)
            
        try:
            data = jwt.decode(token, current_app.config['JWT_SECRET_KEY'], algorithms=["HS256"])
            user_id = data['user_id']
            store_id = request.headers.get('X-Store-ID', type=int)
            if not store_id:
                stores = db.get_user_stores(user_id)
                if stores:
                    store_id = stores[0]['id']
                else:
                    raise APIException("User does not belong to any store", 403)
                    
            role = db.check_store_membership(user_id, store_id)
            if not role:
                raise APIException("Not authorized for this store", 403)
                
            request.user_id = user_id
            request.store_id = store_id
            request.user_role = role
        except jwt.ExpiredSignatureError:
            raise APIException("Token has expired", 401)
        except jwt.InvalidTokenError:
            raise APIException("Invalid token", 401)
            
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# Auth Routes
# ---------------------------------------------------------------------------
@api_bp.route('/auth/register', methods=['POST'])
def register():
    data = request.get_json()
    if not data or not data.get('full_name') or not data.get('email') or not data.get('password'):
        raise APIException("Missing required fields", 400)
        
    hashed_pw = bcrypt.generate_password_hash(data['password']).decode('utf-8')
    user_id = db.create_user(data['full_name'], data['email'], hashed_pw)
    
    if not user_id:
        raise APIException("Email already exists", 400)
        
    # Requirements: "Create the initial store owner securely."
    # For this iteration, new registrations create a new store they own
    store_name = f"{data['full_name']}'s Store"
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO stores (name) VALUES (?)', (store_name,))
    store_id = cursor.lastrowid
    cursor.execute('INSERT INTO store_members (user_id, store_id, role) VALUES (?, ?, ?)', (user_id, store_id, 'owner'))
    conn.commit()
    conn.close()
    
    return jsonify({"success": True, "message": "User registered successfully"})

@api_bp.route('/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data or not data.get('email') or not data.get('password'):
        raise APIException("Missing email or password", 400)
        
    user = db.get_user_by_email(data['email'])
    if not user or not bcrypt.check_password_hash(user['password_hash'], data['password']):
        raise APIException("Invalid credentials", 401)
        
    # Determine if user is admin based on email allowlist
    is_admin = user['email'].strip().lower() in Config.ADMIN_EMAILS
    role = 'admin' if is_admin else 'user'
    
    # Keep the database role column in sync with the allowlist
    if user['role'] != role:
        db.set_user_role(user['id'], role)
    
    token = jwt.encode({
        'user_id': user['id'],
        'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)
    }, current_app.config['JWT_SECRET_KEY'], algorithm="HS256")
    
    stores = db.get_user_stores(user['id'])
    
    return jsonify({
        "success": True, 
        "token": token,
        "user": {
            "id": user['id'],
            "full_name": user['full_name'],
            "email": user['email'],
            "role": role
        },
        "stores": stores
    })

@api_bp.route('/auth/me', methods=['GET'])
@token_required
def auth_me():
    user = db.get_user_by_id(request.user_id)
    stores = db.get_user_stores(request.user_id)
    return jsonify({
        "success": True,
        "user": {
            "id": user['id'],
            "full_name": user['full_name'],
            "email": user['email']
        },
        "active_store": request.store_id,
        "role": request.user_role,
        "stores": stores
    })


# ---------------------------------------------------------------------------
# Core Routes
# ---------------------------------------------------------------------------
@api_bp.route('/detect', methods=['POST'])
@token_optional
def detect_video():
    use_demo = request.form.get('use_demo') == 'true' or request.args.get('use_demo') == 'true'

    if use_demo:
        demo_path = os.path.join(current_app.config['UPLOAD_FOLDER'], "demo.mp4")
        unique_id = uuid.uuid4().hex[:8]
        input_filename = f"upload_{unique_id}_demo.mp4"
        input_path = os.path.join(current_app.config['UPLOAD_FOLDER'], input_filename)
        import shutil
        if os.path.exists(demo_path):
            shutil.copy2(demo_path, input_path)
        filename_stem = "demo"
    else:
        if 'file' not in request.files:
            raise APIException("No video file in request.", 400)
        file = request.files['file']
        filename = secure_filename(file.filename)
        unique_id = uuid.uuid4().hex[:8]
        input_filename = f"upload_{unique_id}_{filename}"
        input_path = os.path.join(current_app.config['UPLOAD_FOLDER'], input_filename)
        file.save(input_path)
        filename_stem = filename.rsplit('.', 1)[0]

    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise APIException("Cannot open uploaded video.", 400)

    width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps    = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total  = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    output_filename = f"processed_{unique_id}_{filename_stem}.mp4"
    output_path = os.path.join(current_app.config['UPLOAD_FOLDER'], output_filename)
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    video_tracker = TrackingService()
    agent = ShoppingAgent(store_id=request.store_id, user_id=request.user_id)
    db.clear_cart(request.store_id, request.user_id)

    MAX_FRAMES = 600
    processed = 0
    _all_events = []

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

            detections = detection_service.detect_frame(frame)
            tracked_items = video_tracker.update(detections, frame)
            cart_state = agent.update(tracked_items)
            frame_events = cart_state.get("events", [])
            _all_events.extend(frame_events)

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

    cart_summary = agent.get_cart()
    video_url    = f"http://localhost:5000/static/uploads/{output_filename}"

    all_exit_events = [evt for evt in _all_events if evt.get("type") == "exit"]
    agent_analysis = _retail_agent.analyze(request.store_id, cart_summary, all_exit_events)

    return jsonify({
        "success": True,
        "message": f"Processed {processed} frames.",
        "video_url": video_url,
        "products": cart_summary["products"],
        "total_bill": cart_summary["total_bill"],
        "agent": agent_analysis,
    })


@api_bp.route('/detect-frame', methods=['POST'])
@token_optional
def detect_frame():
    if 'file' not in request.files:
        raise APIException("No image file uploaded.", 400)
    file = request.files['file']
    
    file_bytes = np.frombuffer(file.read(), np.uint8)
    frame = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)

    # Note: Using persistent webcam agent - realistically we'd need one per user
    # but maintaining compatibility for now. We update its store/user.
    _webcam_agent.store_id = request.store_id
    _webcam_agent.user_id = request.user_id

    detections    = detection_service.detect_frame(frame)
    tracked_items = _webcam_tracker.update(detections, frame)
    cart_state    = _webcam_agent.update(tracked_items)
    exit_events   = [e for e in cart_state.get("events", []) if e["type"] == "exit"]
    agent_analysis = _retail_agent.analyze(
        request.store_id,
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


@api_bp.route('/cart', methods=['GET'])
@token_optional
def get_cart():
    summary = db.get_cart_summary(request.store_id, request.user_id)
    return jsonify({"success": True, **summary})


@api_bp.route('/cart', methods=['DELETE'])
@token_optional
def clear_cart():
    _webcam_agent.store_id = request.store_id
    _webcam_agent.user_id = request.user_id
    result = _webcam_agent.reset()
    return jsonify(result)


@api_bp.route('/products', methods=['GET'])
@token_optional
def list_products():
    products = db.get_all_products(request.store_id)
    return jsonify({"success": True, "products": products})


@api_bp.route('/products', methods=['POST'])
@token_optional
def add_product():
    data = request.get_json() or {}
    if not data.get('id') or not data.get('name') or data.get('price') is None:
        raise APIException("Missing required fields: id, name, price", 400)
    try:
        price = float(data['price'])
    except (ValueError, TypeError):
        raise APIException("Price must be a valid number.", 400)

    db.upsert_product(request.store_id, data['id'], data['name'], price)
    return jsonify({
        "success": True,
        "message": f"Product '{data['name']}' registered/updated successfully.",
    })


@api_bp.route('/agent/analyze', methods=['GET'])
@token_optional
def agent_analyze():
    cart = db.get_cart_summary(request.store_id, request.user_id)
    analysis = _retail_agent.analyze(request.store_id, cart, exit_events=[])
    return jsonify({
        "success": True,
        "cart": cart,
        **analysis,
    })


@api_bp.route('/inventory', methods=['GET'])
@token_optional
def get_inventory():
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT i.product_id, p.name, i.stock
        FROM inventory i
        LEFT JOIN products p ON i.product_id = p.id AND i.store_id = p.store_id
        WHERE i.store_id = ?
        ORDER BY p.name
    ''', (request.store_id,))
    rows = cursor.fetchall()
    conn.close()
    return jsonify({
        "success": True,
        "inventory": [dict(r) for r in rows],
    })

@api_bp.route('/chat', methods=['POST'])
def chat():
    data = request.get_json() or {}
    message = data.get("message", "")

    if not message:
        return jsonify({
            "success": False,
            "response": "Please enter a message."
        }), 400

    vector_message = chatbot_vectorizer.transform([message])
    prediction = chatbot_model.predict(vector_message)
    intent = prediction[0]

    return jsonify({
        "success": True,
        "intent": intent,
        "response": f"Detected intent: {intent}"
    })


# ---------------------------------------------------------------------------
# Checkout Payment Route
# ---------------------------------------------------------------------------
@api_bp.route('/checkout/pay', methods=['POST'])
@token_optional
def checkout_pay():
    data = request.get_json() or {}
    items = data.get('items', [])
    payment_method = data.get('payment_method', 'Card')
    store_id = data.get('store_id') or request.store_id
    customer_name = data.get('customer_name')
    customer_email = data.get('customer_email')

    # If items not explicitly sent, read from active cart
    if not items:
        cart_summary = db.get_cart_summary(store_id, request.user_id)
        items = cart_summary.get('products', [])
        total_bill = cart_summary.get('total_bill', 0.0)
    else:
        total_bill = sum(float(item.get('price', item.get('unit_price', 0))) * int(item.get('quantity', 1)) for item in items)

    if not items:
        raise APIException("No items in cart to checkout", 400)

    tx_id = db.create_transaction(
        user_id=request.user_id,
        store_id=store_id,
        amount=round(total_bill, 2),
        items=items,
        payment_method=payment_method,
        status='completed',
        customer_name=customer_name,
        customer_email=customer_email
    )

    db.clear_cart(store_id, request.user_id)

    return jsonify({
        "success": True,
        "message": "Payment successful and transaction recorded.",
        "transaction_id": tx_id,
        "total_amount": round(total_bill, 2)
    })


# ---------------------------------------------------------------------------
# Retail Analytics API Routes
# ---------------------------------------------------------------------------
@api_bp.route('/analytics/overview', methods=['GET'])
@token_optional
def analytics_overview():
    store_id = request.args.get('store_id') or request.store_id
    date_range = request.args.get('date_range', '7d')
    overview = db.get_analytics_overview(store_id=store_id, date_range=date_range)
    return jsonify({"success": True, "overview": overview})


@api_bp.route('/analytics/sales-trend', methods=['GET'])
@token_optional
def analytics_sales_trend():
    store_id = request.args.get('store_id') or request.store_id
    date_range = request.args.get('date_range', '7d')
    trends = db.get_sales_trends(store_id=store_id, date_range=date_range)
    return jsonify({"success": True, "trends": trends})


@api_bp.route('/analytics/hourly-trend', methods=['GET'])
@token_optional
def analytics_hourly_trend():
    store_id = request.args.get('store_id') or request.store_id
    date_range = request.args.get('date_range', '7d')
    trends = db.get_hourly_sales_trends(store_id=store_id, date_range=date_range)
    return jsonify({"success": True, "trends": trends})


@api_bp.route('/analytics/top-products', methods=['GET'])
@token_optional
def analytics_top_products():
    store_id = request.args.get('store_id') or request.store_id
    date_range = request.args.get('date_range', '7d')
    limit = request.args.get('limit', 8, type=int)
    top_products = db.get_top_products(store_id=store_id, date_range=date_range, limit=limit)
    return jsonify({"success": True, "top_products": top_products})


@api_bp.route('/analytics/low-stock', methods=['GET'])
@token_optional
def analytics_low_stock():
    store_id = request.args.get('store_id') or request.store_id
    threshold = request.args.get('threshold', 20, type=int)
    items = db.get_low_stock_products(store_id=store_id, threshold=threshold)
    return jsonify({"success": True, "low_stock": items})


@api_bp.route('/analytics/restock', methods=['POST'])
@token_optional
def analytics_restock():
    data = request.get_json() or {}
    store_id = data.get('store_id') or request.store_id
    product_id = data.get('product_id')
    quantity = data.get('quantity', 50)

    if not product_id:
        raise APIException("Missing product_id for restock", 400)

    db.restock_inventory(store_id, product_id, int(quantity))
    return jsonify({
        "success": True,
        "message": f"Successfully added {quantity} units to product '{product_id}'."
    })


@api_bp.route('/analytics/transactions', methods=['GET'])
@token_optional
def analytics_transactions():
    store_id = request.args.get('store_id') or request.store_id
    date_range = request.args.get('date_range', 'all')
    search = request.args.get('search', '')
    limit = request.args.get('limit', 100, type=int)
    transactions = db.get_transactions_list(store_id=store_id, date_range=date_range, search=search, limit=limit)
    return jsonify({"success": True, "transactions": transactions})


@api_bp.route('/analytics/transactions/<int:tx_id>', methods=['GET'])
@token_optional
def analytics_transaction_detail(tx_id):
    tx = db.get_transaction_details(tx_id)
    if not tx:
        raise APIException("Transaction not found", 404)
    return jsonify({"success": True, "transaction": tx})


@api_bp.route('/analytics/reset', methods=['POST'])
@token_optional
def analytics_reset():
    data = request.get_json() or {}
    store_id = data.get('store_id') or request.args.get('store_id') or request.store_id
    db.reset_store_analytics(store_id=store_id)
    return jsonify({
        "success": True,
        "message": "All dashboard values and transactions have been reset to zero successfully."
    })


@api_bp.route('/analytics/seed-demo', methods=['POST'])
@token_optional
def analytics_seed_demo():
    data = request.get_json() or {}
    store_id = data.get('store_id') or request.args.get('store_id') or request.store_id
    result = db.seed_demo_analytics(store_id=store_id)
    return jsonify({
        "success": True,
        "message": "Demo amount and dashboard metrics loaded successfully.",
        **result
    })


@api_bp.route('/analytics/quick-purchase', methods=['POST'])
@token_optional
def analytics_quick_purchase():
    data = request.get_json() or {}
    store_id = data.get('store_id') or request.args.get('store_id') or request.store_id
    customer_name = data.get('customer_name', 'Rahul Sharma')
    customer_email = data.get('customer_email', 'customer@store.com')
    payment_method = data.get('payment_method', 'UPI')
    items = data.get('items')

    if not items:
        # Realistic quick sample checkout: 2x Fresh Milk + 1x Whole Wheat Bread
        items = [
            {"product_id": "milk", "name": "Fresh Milk", "quantity": 2, "price": 50.00},
            {"product_id": "bread", "name": "Whole Wheat Bread", "quantity": 1, "price": 70.00}
        ]

    total_bill = sum(float(item.get('price', item.get('unit_price', 0))) * int(item.get('quantity', 1)) for item in items)

    tx_id = db.create_transaction(
        user_id=request.user_id,
        store_id=store_id,
        amount=round(total_bill, 2),
        items=items,
        payment_method=payment_method,
        status='completed',
        customer_name=customer_name,
        customer_email=customer_email
    )

    return jsonify({
        "success": True,
        "message": f"Customer purchase of ₹{total_bill:.2f} recorded and added to dashboard.",
        "transaction_id": tx_id,
        "total_amount": round(total_bill, 2)
    })


