import os
from dotenv import load_dotenv
from urllib.parse import urlparse

load_dotenv()

# Database configuration
DATABASE_URL = os.getenv('DATABASE_URL')
if DATABASE_URL:
    url = urlparse(DATABASE_URL)
    DB_HOST = url.hostname
    DB_USER = url.username
    DB_PASSWORD = url.password
    DB_NAME = url.path[1:]  # Remove leading slash
    DB_PORT = url.port or 5432
else:
    # Fallback for local development
    DB_HOST = 'localhost'
    DB_USER = 'root'
    DB_PASSWORD = 'Shashi@30'
    DB_NAME = 'voxiscribe'
    DB_PORT = 3306

# App configuration
SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key')
FLASK_ENV = os.getenv('FLASK_ENV', 'development')

# Proctoring configuration
PROCTORING_STORE_IN_DB = os.getenv('PROCTORING_STORE_IN_DB', 'True').lower() == 'true'