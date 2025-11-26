import os
from dotenv import load_dotenv

load_dotenv()

# Database configuration
DATABASE_URL = os.getenv('DATABASE_URL')
DB_PATH = os.getenv('DATABASE_PATH', 'voxiscribe.db')

# App configuration
SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key')
FLASK_ENV = os.getenv('FLASK_ENV', 'development')

# Proctoring configuration
PROCTORING_STORE_IN_DB = os.getenv('PROCTORING_STORE_IN_DB', 'True').lower() == 'true'