import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Security
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        raise ValueError("No SECRET_KEY set in .env file")

    # Session settings
    PERMANENT_SESSION_LIFETIME = 1800
    SESSION_COOKIE_SECURE      = False
    SESSION_COOKIE_HTTPONLY    = True
    SESSION_COOKIE_SAMESITE    = 'Lax'

    # Database — reads all values from .env
    DB_USERNAME = os.environ.get('DB_USERNAME')
    DB_PASSWORD = os.environ.get('DB_PASSWORD')
    DB_HOST     = os.environ.get('DB_HOST', 'localhost')
    DB_PORT     = os.environ.get('DB_PORT', '3306')        # ✅ port added
    DB_NAME     = os.environ.get('DB_NAME')

    if not all([DB_USERNAME, DB_PASSWORD, DB_NAME]):
        raise ValueError("Database credentials missing in .env file")

    SQLALCHEMY_DATABASE_URI = (
        f'mysql+pymysql://{DB_USERNAME}:{DB_PASSWORD}'
        f'@{DB_HOST}:{DB_PORT}/{DB_NAME}'                  # ✅ port in URI
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size':    10,
        'pool_recycle': 3600,
        'pool_pre_ping': True,
    }

    # Rate limiting
    RATELIMIT_ENABLED     = True
    RATELIMIT_DEFAULT     = "100 per minute"
    RATELIMIT_STORAGE_URL = "memory://"

    # CSRF
    WTF_CSRF_ENABLED    = True
    WTF_CSRF_TIME_LIMIT = 3600


class DevelopmentConfig(Config):
    DEBUG                  = True
    SESSION_COOKIE_SECURE  = False
    RATELIMIT_DEFAULT      = "1000 per minute"


class TestingConfig(Config):
    TESTING                = True
    DEBUG                  = True
    SESSION_COOKIE_SECURE  = False
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    RATELIMIT_ENABLED      = False
    WTF_CSRF_ENABLED       = False


class ProductionConfig(Config):
    DEBUG                  = False
    SESSION_COOKIE_SECURE  = True
    SESSION_COOKIE_SAMESITE = 'Strict'


config = {
    'development': DevelopmentConfig,
    'testing':     TestingConfig,
    'production':  ProductionConfig,
    'default':     DevelopmentConfig
}