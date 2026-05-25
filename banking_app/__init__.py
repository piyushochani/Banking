"""
Banking Application Package
"""
import os
from datetime import datetime

from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from dotenv import load_dotenv

load_dotenv()

db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()
csrf = CSRFProtect()
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["99999 per day"]   # ✅ effectively unlimited
)


def create_app(config_class=None):
    app = Flask(__name__)

    if config_class is None:
        env = os.environ.get('FLASK_ENV', 'development')
        from .config import config
        app.config.from_object(config[env])
    else:
        app.config.from_object(config_class)

    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    limiter.init_app(app)

    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'
    login_manager.session_protection = 'strong'

    from .routes.auth import auth_bp
    from .routes.main import main_bp
    from .routes.accounts import accounts_bp
    from .routes.transactions import transactions_bp
    from .routes.loans import loans_bp
    from .routes.admin import admin_bp
    from .routes.staff import staff_bp
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(staff_bp, url_prefix='/staff')

    app.register_blueprint(auth_bp,         url_prefix='/auth')
    app.register_blueprint(main_bp)
    app.register_blueprint(accounts_bp,     url_prefix='/accounts')
    app.register_blueprint(transactions_bp, url_prefix='/transactions')
    app.register_blueprint(loans_bp,        url_prefix='/loans')

    with app.app_context():
        from . import models
        db.create_all()

    register_error_handlers(app)
    register_context_processors(app)

    app.logger.info('Banking application started successfully')
    return app


def register_error_handlers(app):

    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return render_template('errors/500.html'), 500

    @app.errorhandler(429)
    def ratelimit_error(error):
        from flask import flash, redirect, url_for
        flash('Too many requests. Please wait a moment.', 'warning')
        return redirect(url_for('main.dashboard'))


def register_context_processors(app):

    @app.context_processor
    def utility_processor():
        return {
            'now': datetime.utcnow,
            'app_name': 'Secure Banking Application'
        }