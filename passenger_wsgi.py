import os
import sys

# Set application directory
app_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, app_dir)

# Load environment variables from .env if present
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(app_dir, '.env'), override=True)
except ImportError:
    pass

# Ensure running in production mode
os.environ['FLASK_ENV'] = 'production'

# Import the application
from app import create_app

# Passenger requires the callable to be named 'application'
application = create_app('production')
