import logging
import os
from pathlib import Path

def setup_logger(name="smart_checkout"):
    """
    Configure a standard logger that outputs messages to both a file and the console.
    """
    logger = logging.getLogger(name)
    
    # If logger is already configured, don't add handlers again
    if logger.handlers:
        return logger
        
    logger.setLevel(logging.INFO)
    
    # Define log message format
    formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
    )
    
    # Create console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # Create file handler
    base_dir = Path(__file__).resolve().parent.parent.parent
    log_file_path = os.path.join(base_dir, 'app.log')
    
    try:
        file_handler = logging.FileHandler(log_file_path)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        print(f"Failed to initialize file logger: {e}. Logging to console only.")
        
    return logger

# Create global logger instance
logger = setup_logger()
