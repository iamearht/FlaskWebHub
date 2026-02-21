from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from models import db, User
from functools import wraps

auth_bp = Blueprint('auth', __name__)


def _is_api_request():
    # Treat any /api/* route as API (polling + AJAX calls)
    return request.path.startswith('/api/')


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            if _is_api_request():
                return jsonify({'error': 'Authentication required'}), 401
            return redirect(url_for('auth.login'))

        user = User.query.get(session['user_id'])
        if not user:
            session.clear()
            if _is_api_request():
                return jsonify({'error': 'Authentication required'}), 401
            return redirect(url_for('auth.login'))

        return f(*args, **kwargs)
    return decorated


def get_current_user():
    if 'user_id' not in session:
        return None
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        return None
    return user


@auth_bp.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('game.lobby'))
    return redirect(url_for('auth.login'))


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    ref_code = request.args.get('ref', '')
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        referral_code = request.form.get('referral_code', '').strip()

        if not username or not password:
            flash('Username and password are required.', 'error')
            return render_template('register.html', ref_code=ref_code)
        if len(username) < 3:
            flash('Username must be at least 3 characters.', 'error')
            return render_template('register.html', ref_code=ref_code)
        if len(password) < 4:
            flash('Password must be at least 4 characters.', 'error')
            return render_template('register.html', ref_code=ref_code)
        if User.query.filter(db.func.lower(User.username) == username.lower()).first():
            flash('Username already taken.', 'error')
            return render_template('register.html', ref_code=ref_code)
        if email and User.query.filter_by(email=email).first():
            flash('Email already in use.', 'error')
            return render_template('register.html', ref_code=ref_code)

        user = User(username=username)
        if email:
            user.email = email
        user.set_password(password)

        if referral_code:
            referrer = User.query.filter_by(affiliate_code=referral_code).first()
            if referrer:
                user.referred_by_id = referrer.id
            else:
                flash('Invalid referral code, registration continues without it.', 'error')

        db.session.add(user)
        db.session.flush()
        user.ensure_affiliate_code()
        db.session.commit()

        session['user_id'] = user.id
        flash('Registration successful! You start with 1000 coins.', 'success')
        return redirect(url_for('game.lobby'))

    return render_template('register.html', ref_code=ref_code)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        user = User.query.filter(db.func.lower(User.username) == username.lower()).first()
        if user and user.check_password(password):
            session['user_id'] = user.id
            return redirect(url_for('game.lobby'))

        flash('Invalid username or password.', 'error')

    return render_template('login.html')


@auth_bp.route('/logout')
def logout():
    session.clear()
    flash('Logged out.', 'success')
    return redirect(url_for('auth.login'))