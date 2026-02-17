from flask import Blueprint, render_template, request, redirect, url_for, flash
from models import (db, User, AdminConfig, RakeTransaction, RakebackProgress,
                     Tournament, Match, get_lobby_rake_percent, get_tournament_rake_percent,
                     get_tournament_payouts)
from auth import login_required, get_current_user
from datetime import datetime, timedelta
from functools import wraps
import json

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


def admin_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user or not user.is_admin:
            flash('Access denied.', 'error')
            return redirect(url_for('game.lobby'))
        return f(*args, **kwargs)
    return decorated


@admin_bp.route('/')
@admin_required
def dashboard():
    user = get_current_user()
    total_users = User.query.count()
    total_matches = Match.query.count()
    total_tournaments = Tournament.query.count()

    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=now.weekday())
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    rake_today = db.session.query(db.func.coalesce(db.func.sum(RakeTransaction.amount), 0))\
        .filter(RakeTransaction.created_at >= today_start).scalar()
    rake_week = db.session.query(db.func.coalesce(db.func.sum(RakeTransaction.amount), 0))\
        .filter(RakeTransaction.created_at >= week_start).scalar()
    rake_month = db.session.query(db.func.coalesce(db.func.sum(RakeTransaction.amount), 0))\
        .filter(RakeTransaction.created_at >= month_start).scalar()
    rake_total = db.session.query(db.func.coalesce(db.func.sum(RakeTransaction.amount), 0)).scalar()

    recent_rake = RakeTransaction.query.order_by(RakeTransaction.created_at.desc()).limit(20).all()

    return render_template('admin/dashboard.html', user=user,
                           total_users=total_users, total_matches=total_matches,
                           total_tournaments=total_tournaments,
                           rake_today=rake_today, rake_week=rake_week,
                           rake_month=rake_month, rake_total=rake_total,
                           recent_rake=recent_rake)


@admin_bp.route('/rake-stats')
@admin_required
def rake_stats():
    user = get_current_user()
    period = request.args.get('period', '7d')

    now = datetime.utcnow()
    if period == '24h':
        start = now - timedelta(hours=24)
    elif period == '7d':
        start = now - timedelta(days=7)
    elif period == '30d':
        start = now - timedelta(days=30)
    elif period == '90d':
        start = now - timedelta(days=90)
    elif period == 'all':
        start = datetime(2020, 1, 1)
    else:
        start = now - timedelta(days=7)

    match_rake = db.session.query(db.func.coalesce(db.func.sum(RakeTransaction.amount), 0))\
        .filter(RakeTransaction.source_type == 'match', RakeTransaction.created_at >= start).scalar()
    tournament_rake = db.session.query(db.func.coalesce(db.func.sum(RakeTransaction.amount), 0))\
        .filter(RakeTransaction.source_type == 'tournament', RakeTransaction.created_at >= start).scalar()
    total_rake = match_rake + tournament_rake

    transactions = RakeTransaction.query.filter(RakeTransaction.created_at >= start)\
        .order_by(RakeTransaction.created_at.desc()).limit(50).all()

    return render_template('admin/rake_stats.html', user=user,
                           period=period, match_rake=match_rake,
                           tournament_rake=tournament_rake, total_rake=total_rake,
                           transactions=transactions)


@admin_bp.route('/lobby-rake', methods=['GET', 'POST'])
@admin_required
def lobby_rake():
    user = get_current_user()
    if request.method == 'POST':
        tiers = []
        i = 0
        while f'min_{i}' in request.form:
            try:
                tiers.append({
                    'min': int(request.form.get(f'min_{i}', 0)),
                    'max': int(request.form.get(f'max_{i}', 999999)),
                    'percent': float(request.form.get(f'percent_{i}', 1)),
                })
            except (ValueError, TypeError):
                pass
            i += 1
        if tiers:
            tiers.sort(key=lambda x: x['min'])
            AdminConfig.set('lobby_rake_tiers', tiers)
            db.session.commit()
            flash('Lobby rake tiers updated.', 'success')
        return redirect(url_for('admin.lobby_rake'))

    current_tiers = AdminConfig.get('lobby_rake_tiers', [
        {'min': 0, 'max': 250, 'percent': 1},
        {'min': 250, 'max': 1000, 'percent': 2},
        {'min': 1000, 'max': 5000, 'percent': 3},
        {'min': 5000, 'max': 999999, 'percent': 5},
    ])
    return render_template('admin/lobby_rake.html', user=user, tiers=current_tiers)


@admin_bp.route('/tournament-rake', methods=['GET', 'POST'])
@admin_required
def tournament_rake():
    user = get_current_user()
    stakes = Tournament.STAKES
    sizes = Tournament.PLAYER_SIZES

    if request.method == 'POST':
        for stake in stakes:
            for size in sizes:
                key = f'rake_{stake}_{size}'
                val = request.form.get(key)
                if val is not None:
                    try:
                        AdminConfig.set(f'tournament_rake_{stake}_{size}', float(val))
                    except (ValueError, TypeError):
                        pass
        db.session.commit()
        flash('Tournament rake settings updated.', 'success')
        return redirect(url_for('admin.tournament_rake'))

    current_rates = {}
    for stake in stakes:
        for size in sizes:
            current_rates[f'{stake}_{size}'] = get_tournament_rake_percent(stake, size)

    return render_template('admin/tournament_rake.html', user=user,
                           stakes=stakes, sizes=sizes, current_rates=current_rates)


@admin_bp.route('/tournament-payouts', methods=['GET', 'POST'])
@admin_required
def tournament_payouts():
    user = get_current_user()
    sizes = Tournament.PLAYER_SIZES

    if request.method == 'POST':
        size = int(request.form.get('size', 8))
        payouts = {}
        i = 1
        while f'place_{i}' in request.form:
            try:
                payouts[i] = float(request.form.get(f'place_{i}', 0))
            except (ValueError, TypeError):
                pass
            i += 1
        if payouts:
            AdminConfig.set(f'tournament_payouts_{size}', payouts)
            db.session.commit()
            flash(f'Payouts for {size}-player tournaments updated.', 'success')
        return redirect(url_for('admin.tournament_payouts'))

    all_payouts = {}
    for size in sizes:
        all_payouts[size] = get_tournament_payouts(size)

    return render_template('admin/tournament_payouts.html', user=user,
                           sizes=sizes, all_payouts=all_payouts)


@admin_bp.route('/coins', methods=['GET', 'POST'])
@admin_required
def manage_coins():
    user = get_current_user()
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        action = request.form.get('action', 'add')
        try:
            amount = int(request.form.get('amount', 0))
        except (ValueError, TypeError):
            flash('Invalid amount.', 'error')
            return redirect(url_for('admin.manage_coins'))

        if amount <= 0:
            flash('Amount must be positive.', 'error')
            return redirect(url_for('admin.manage_coins'))

        target = User.query.filter_by(username=username).first()
        if not target:
            flash(f'User "{username}" not found.', 'error')
            return redirect(url_for('admin.manage_coins'))

        if action == 'add':
            target.coins += amount
            flash(f'Added {amount} coins to {username}. New balance: {target.coins}', 'success')
        elif action == 'remove':
            target.coins = max(0, target.coins - amount)
            flash(f'Removed {amount} coins from {username}. New balance: {target.coins}', 'success')
        elif action == 'set':
            target.coins = amount
            flash(f'Set {username} balance to {amount} coins.', 'success')

        db.session.commit()
        return redirect(url_for('admin.manage_coins'))

    users = User.query.order_by(User.username).all()
    return render_template('admin/coins.html', user=user, users=users)


@admin_bp.route('/rakeback', methods=['GET', 'POST'])
@admin_required
def rakeback_config():
    user = get_current_user()
    if request.method == 'POST':
        if 'reset_days' in request.form:
            try:
                days = int(request.form.get('reset_days', 60))
                AdminConfig.set('rakeback_reset_days', days)
                db.session.commit()
                flash(f'Rakeback reset period set to {days} days.', 'success')
            except (ValueError, TypeError):
                flash('Invalid number of days.', 'error')
        elif 'tier_name_0' in request.form:
            tiers = []
            i = 0
            while f'tier_name_{i}' in request.form:
                try:
                    tiers.append({
                        'name': request.form.get(f'tier_name_{i}', ''),
                        'threshold': float(request.form.get(f'tier_threshold_{i}', 0)),
                        'percent': float(request.form.get(f'tier_percent_{i}', 0)),
                    })
                except (ValueError, TypeError):
                    pass
                i += 1
            if tiers:
                tiers.sort(key=lambda x: x['threshold'])
                AdminConfig.set('rakeback_tiers', tiers)
                db.session.commit()
                flash('Rakeback tiers updated.', 'success')

        return redirect(url_for('admin.rakeback_config'))

    current_tiers = AdminConfig.get('rakeback_tiers', [
        {'name': 'Bronze', 'threshold': 0, 'percent': 0},
        {'name': 'Silver', 'threshold': 500, 'percent': 5},
        {'name': 'Gold', 'threshold': 2000, 'percent': 10},
        {'name': 'Platinum', 'threshold': 5000, 'percent': 15},
    ])
    reset_days = AdminConfig.get('rakeback_reset_days', 60)

    return render_template('admin/rakeback.html', user=user,
                           tiers=current_tiers, reset_days=reset_days)
