import os
from pathlib import Path

# Base project directory
BASE_DIR = Path(__file__).resolve().parent.parent

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'smart-checkout-super-secret-key-12345')
    
    # SQLite Database settings
    DB_PATH = os.path.join(BASE_DIR, 'checkout.db')
    SQLALCHEMY_DATABASE_URI = f'sqlite:///{DB_PATH}'
    
    # Upload & Media settings
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100 MB max file size
    ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'avi', 'mov', 'webm'}
    ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}
    
    # AI Model Settings
    # Path to custom YOLOv11 model. Defaults to best.pt if present, else falls back to yolo11n.pt
    CUSTOM_MODEL_PATH = os.path.join(BASE_DIR, 'best.pt')
    FALLBACK_MODEL_PATH = os.path.join(BASE_DIR, 'yolo11n.pt')
    
    # Tracker parameters
    TRACKER_MAX_AGE = 30
    TRACKER_N_INIT = 3
    TRACKER_NMS_MAX_OVERLAP = 1.0
    TRACKER_MAX_COSINE_DISTANCE = 0.2
