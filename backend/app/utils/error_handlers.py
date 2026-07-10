from flask import jsonify
import sqlite3
from app.utils.logger import logger

class APIException(Exception):
    """
    Custom exception class for backend API errors.
    """
    def __init__(self, message, status_code=400, payload=None):
        super().__init__()
        self.message = message
        self.status_code = status_code
        self.payload = payload

    def to_dict(self):
        rv = dict(self.payload or ())
        rv['success'] = False
        rv['message'] = self.message
        return rv

def register_error_handlers(app):
    """
    Attach error handlers to the Flask application.
    """
    @app.errorhandler(APIException)
    def handle_api_exception(error):
        logger.error(f"API Error: {error.message} (Status {error.status_code})")
        response = jsonify(error.to_dict())
        response.status_code = error.status_code
        return response

    @app.errorhandler(sqlite3.Error)
    def handle_database_error(error):
        logger.exception("Database transaction failed:")
        response = jsonify({
            'success': False,
            'message': 'A database error occurred while processing the checkout.',
            'error': str(error)
        })
        response.status_code = 500
        return response

    @app.errorhandler(404)
    def handle_not_found(error):
        logger.warning(f"Resource not found: {error}")
        return jsonify({
            'success': False,
            'message': 'The requested API endpoint does not exist.'
        }), 404

    @app.errorhandler(405)
    def handle_method_not_allowed(error):
        logger.warning(f"Method not allowed: {error}")
        return jsonify({
            'success': False,
            'message': 'HTTP method not allowed for this route.'
        }), 405

    @app.errorhandler(Exception)
    def handle_generic_exception(error):
        logger.exception("An unhandled system exception occurred:")
        return jsonify({
            'success': False,
            'message': 'An unexpected internal server error occurred.',
            'error': str(error)
        }), 500
