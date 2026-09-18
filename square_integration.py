# ===== SQUARE PAYMENT CONFIG =====
import os
try:
    from squareup.client import Client
    SQUARE_AVAILABLE = True
except ImportError:
    SQUARE_AVAILABLE = False
    logger.warning("⚠️ Square SDK not installed. Run: pip3 install squareup")

SQUARE_ACCESS_TOKEN = os.getenv('SQUARE_ACCESS_TOKEN')
SQUARE_APPLICATION_ID = os.getenv('SQUARE_APPLICATION_ID')
SQUARE_LOCATION_ID = os.getenv('SQUARE_LOCATION_ID')
SQUARE_ENVIRONMENT = os.getenv('SQUARE_ENVIRONMENT', 'production')

def get_square_client():
    """Initialize Square client"""
    if not SQUARE_ACCESS_TOKEN or not SQUARE_APPLICATION_ID:
        return None
    try:
        client = Client(
            access_token=SQUARE_ACCESS_TOKEN,
            environment=SQUARE_ENVIRONMENT
        )
        return client
    except Exception as e:
        logger.error(f"❌ Failed to initialize Square: {e}")
        return None
