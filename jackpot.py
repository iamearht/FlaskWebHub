from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from models import (db, User, AdminConfig, JackpotPool, JackpotEntry,
                     get_jackpot_payouts, get_jackpot_rake_percent)
from auth import login_required, get_current_user
from sqlalchemy import func

jackpot_bp = Blueprint('jackpot', __name__)


def get_jackpot_data(pool_type='standard'):
    pool = JackpotPool.get_active_pool(pool_type)
    db.session.commit()
    top_entries = db.session.query(
        JackpotEntry.user_id,
        User.username,
        func.max(JackpotEntry.score).label('best_score'),
        func.max(JackpotEntry.finishing_chips).label('best_chips'),
        func.count(JackpotEntry.id).label('games_played'),
    ).join(User, JackpotEntry.user_id == User.id)\
     .filter(JackpotEntry.jackpot_id == pool.id)\
     .group_by(JackpotEntry.user_id, User.username)\
     .order_by(func.max(JackpotEntry.score).desc())\
     .limit(20).all()

    return {'pool': pool, 'leaderboard': top_entries}


def get_jackpot_countdown(pool):
    from datetime import datetime
    period_days = AdminConfig.get('jackpot_period_days', 7)
    if pool.period_start and period_days > 0:
        from datetime import timedelta
        deadline = pool.period_start + timedelta(days=period_days)
        now = datetime.utcnow()
        remaining = deadline - now
        if remaining.total_seconds() > 0:
            days = remaining.days
            hours = remaining.seconds // 3600
            minutes = (remaining.seconds % 3600) // 60
            seconds = remaining.seconds % 60
            return {
                'deadline': deadline,
                'days': days,
                'hours': hours,
                'minutes': minutes,
                'seconds': seconds,
                'total_seconds': int(remaining.total_seconds()),
            }
    return None


@jackpot_bp.route('/jackpots')
@login_required
def leaderboard():
    user = get_current_user()
    pool_type = request.args.get('type', 'standard')
    if pool_type not in ('standard', 'joker'):
        pool_type = 'standard'

    jackpot_data = get_jackpot_data(pool_type)
    payouts = get_jackpot_payouts()
    payouts_int = {int(k): v for k, v in payouts.items()}
    countdown = get_jackpot_countdown(jackpot_data['pool'])

    other_pool = JackpotPool.get_active_pool('joker' if pool_type == 'standard' else 'standard')
    db.session.commit()

    user_score = None
    entry = db.session.query(
        func.max(JackpotEntry.score).label('best_score'),
        func.count(JackpotEntry.id).label('games'),
    ).filter(
        JackpotEntry.jackpot_id == jackpot_data['pool'].id,
        JackpotEntry.user_id == user.id,
    ).first()
    if entry and entry.best_score:
        user_score = {
            'best_score': entry.best_score,
            'games': entry.games,
        }

    return render_template('jackpots.html', user=user, jackpot_data=jackpot_data,
                           payouts=payouts_int, user_score=user_score,
                           pool_type=pool_type, other_pool=other_pool,
                           countdown=countdown, pool_types=JackpotPool.POOL_TYPES)


@jackpot_bp.route('/api/jackpots')
@login_required
def api_jackpots():
    pools = JackpotPool.get_all_active_pools()
    db.session.commit()
    return jsonify({
        'standard': {
            'id': pools['standard'].id,
            'amount': pools['standard'].pool_amount,
        },
        'joker': {
            'id': pools['joker'].id,
            'amount': pools['joker'].pool_amount,
        },
    })
