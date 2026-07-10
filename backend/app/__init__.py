import os
from flask import Flask
from flask_cors import CORS
from app.config import Config
from app.database import db
from app.utils.logger import logger
from app.utils.error_handlers import register_error_handlers

def create_app(config_class=Config):
    """
    Flask Application Factory
    """
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Enable CORS for React frontend (localhost:3000)
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    
    # Ensure static/uploads folder exists
    try:
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        logger.info(f"Uploads directory verified: {app.config['UPLOAD_FOLDER']}")
    except Exception as e:
        logger.error(f"Failed to create uploads directory: {e}")
        
    # Register error handlers
    register_error_handlers(app)
    
    # Register API blueprints
    from app.routes.api import api_bp
    app.register_blueprint(api_bp, url_prefix='/api')
    
    # Initialize the SQLite database tables
    with app.app_context():
        try:
            db.init_db()
            logger.info("SQLite Database initialized successfully.")
        except Exception as e:
            logger.exception("Failed to initialize database:")
            
    return app
