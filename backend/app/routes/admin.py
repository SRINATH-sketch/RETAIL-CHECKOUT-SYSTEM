"""
admin.py — Admin-only API routes
All endpoints are protected by @admin_required.
"""
from flask import Blueprint, request, jsonify, current_app
import jwt
from functools import wraps
from app.database import db
from app.utils.error_handlers import APIException

admin_bp = Blueprint('admin', __name__)


# ---------------------------------------------------------------------------
# Admin Auth Middleware
# ---------------------------------------------------------------------------
def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            parts = request.headers['Authorization'].split()
            if len(parts) == 2 and parts[0] == 'Bearer':
                token = parts[1]

        if not token:
            raise APIException("Authentication required", 401)

        try:
            data = jwt.decode(token, current_app.config['JWT_SECRET_KEY'], algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            raise APIException("Token expired", 401)
        except jwt.InvalidTokenError:
            raise APIException("Invalid token", 401)

        # Load the user from DB — do NOT trust the role from the JWT payload
        user = db.get_user_by_id(data['user_id'])
        if not user:
            raise APIException("User not found", 401)

        if user['role'] != 'admin':
            raise APIException("Administrator privileges required", 403)

        request.admin_user_id = user['id']
        request.admin_user = user
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# Admin Endpoints
# ---------------------------------------------------------------------------
@admin_bp.route('/dashboard', methods=['GET'])
@admin_required
def admin_dashboard():
    """Provide admin dashboard data for the frontend."""
    stats = db.get_admin_stats()
    # Expected structure matches frontend expectations
    return jsonify({"success": True, "dashboard": stats})


@admin_bp.route('/users', methods=['GET'])
@admin_required
def admin_list_users():
    users = db.get_all_users()
    return jsonify({"success": True, "users": users})


@admin_bp.route('/users/<int:user_id>/role', methods=['PUT'])
@admin_required
def admin_set_role(user_id):
    """Promote or demote a user. Only email-allowlisted emails can become admin."""
    data = request.get_json() or {}
    new_role = data.get('role', '').lower()

    if new_role not in ('admin', 'user'):
        raise APIException("role must be 'admin' or 'user'", 400)

    # Extra guard: only allowlisted emails can receive admin role
    if new_role == 'admin':
        target = db.get_user_by_id(user_id)
        if not target:
            raise APIException("User not found", 404)
        if target['email'].strip().lower() not in current_app.config['ADMIN_EMAILS']:
            raise APIException(
                "This email is not on the admin allowlist. "
                "Add it to ADMIN_EMAILS before granting admin role.", 403
            )

    updated = db.set_user_role(user_id, new_role)
    if not updated:
        raise APIException("User not found", 404)

    return jsonify({"success": True, "message": f"User {user_id} role set to '{new_role}'"})


@admin_bp.route('/stores', methods=['GET'])
@admin_required
def admin_list_stores():
    stores = db.get_all_stores_admin()
    return jsonify({"success": True, "stores": stores})


@admin_bp.route('/inventory', methods=['GET'])
@admin_required
def admin_inventory():
    inventory = db.get_all_inventory_admin()
    return jsonify({"success": True, "inventory": inventory})


@admin_bp.route('/products', methods=['GET'])
@admin_required
def admin_list_products():
    """All products across all stores."""
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT p.store_id, s.name as store_name, p.id, p.name, p.price
        FROM products p
        JOIN stores s ON p.store_id = s.id
        ORDER BY s.id, p.name
    ''')
    rows = cursor.fetchall()
    conn.close()
    return jsonify({"success": True, "products": [dict(r) for r in rows]})
