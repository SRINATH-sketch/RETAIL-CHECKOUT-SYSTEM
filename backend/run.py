import os
from app import create_app
from app.utils.logger import logger

app = create_app()

if __name__ == '__main__':
    # Start the Flask development server on port 5000
    # Host '0.0.0.0' allows external devices (like a mobile client or testing device) to connect
    logger.info("Starting AI Smart Retail Checkout Flask Server on http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)
