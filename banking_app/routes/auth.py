"""
Authentication routes: login, logout, register, profile.
"""
from datetime import datetime
from urllib.parse import urlparse
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from .. import db
from ..models import User, AuditLog

auth_bp = Blueprint('auth', __name__)


def log_audit(user_id, action, details=''):
    try:
        entry = AuditLog(
            user_id=user_id, action=action,
            ip_address=request.remote_addr,
            details=details, timestamp=datetime.utcnow()
        )
        db.session.add(entry)
        db.session.commit()
    except Exception as e:
        current_app.logger.error(f"Audit log failed: {str(e)}")


def is_strong_password(password):
    if len(password) < 8:
        return False, 'Password must be at least 8 characters long.'
    if not any(c.isupper() for c in password):
        return False, 'Password must contain at least one uppercase letter.'
    if not any(c.islower() for c in password):
        return False, 'Password must contain at least one lowercase letter.'
    if not any(c.isdigit() for c in password):
        return False, 'Password must contain at least one number.'
    if not any(c in '!@#$%^&*()_+-=[]{}|;:,.<>?' for c in password):
        return False, 'Password must contain at least one special character (!@#$%^&* etc).'
    return True, ''


def get_role_dashboard(user):
    return url_for('main.dashboard')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(get_role_dashboard(current_user))

    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        remember = bool(request.form.get('remember', False))

        if not email or not password:
            flash('Email and password are required.', 'danger')
            return render_template('auth/login.html')

        user = User.query.filter_by(email=email).first()

        if user and user.is_active and user.verify_password(password):
            login_user(user, remember=remember)
            user.last_login = datetime.utcnow()
            db.session.commit()
            log_audit(user.id, 'LOGIN_SUCCESS', f'Email: {email}')
            next_page = request.args.get('next')
            if not next_page or urlparse(next_page).netloc != '':
                next_page = get_role_dashboard(user)
            return redirect(next_page)
        else:
            user_id = user.id if user else None
            log_audit(user_id, 'LOGIN_FAILED', f'Email: {email}')
            flash('Invalid email or password.', 'danger')

    return render_template('auth/login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    log_audit(current_user.id, 'LOGOUT', f'User: {current_user.email}')
    logout_user()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/register')
def register():
    """Public registration is disabled — only Admin/Staff can create accounts."""
    if current_user.is_authenticated:
        return redirect(get_role_dashboard(current_user))
    flash('Public registration is not available. Please contact the bank to open an account.', 'warning')
    return redirect(url_for('auth.login'))


@auth_bp.route('/profile')
@login_required
def profile():
    return render_template('auth/profile.html', user=current_user)