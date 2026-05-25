#!/usr/bin/env python
"""
Entry point for the banking application
Run this file to start the Flask development server
"""
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import the application factory
from banking_app import create_app

# Create application instance
app = create_app()

if __name__ == '__main__':
    # Get port from environment variable or use default
    port = int(os.environ.get('PORT', 5000))
    
    # Get debug setting from environment
    debug = os.environ.get('FLASK_ENV') == 'development'
    
    # Run the application
    app.run(
        host='0.0.0.0',  # Listen on all available network interfaces
        port=port,
        debug=debug,
        ssl_context='adhoc' if os.environ.get('FLASK_ENV') == 'production' else None  # Use HTTPS in production
    )