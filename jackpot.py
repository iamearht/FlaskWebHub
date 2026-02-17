from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from models import (db, User, AdminConfig, JackpotPool, JackpotEntry,
                     get_jackpot_payouts, get_jackpot_rake_percent)
from auth import login_required, get_current_user
from sqlalchemy import func

jackpot_bp = Blueprint('jackpot', __name__)


def get_jackpot_data():
    pools = JackpotPool.get_or_create_pools()
    db.session.commit()
    jackpot_data = []
    for pool in pools:
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

        jackpot_data.append({
            'pool': pool,
            'leaderboard': top_entries,
        })
    return jackpot_data


@jackpot_bp.route('/jackpots')
@login_required
def leaderboard():
    user = get_current_user()
    jackpot_data = get_jackpot_data()
    payouts = get_jackpot_payouts()
    payouts_int = {int(k): v for k, v in payouts.items()}

    user_scores = {}
    for jd in jackpot_data:
        entry = db.session.query(
            func.max(JackpotEntry.score).label('best_score'),
            func.count(JackpotEntry.id).label('games'),
        ).filter(
            JackpotEntry.jackpot_id == jd['pool'].id,
            JackpotEntry.user_id == user.id,
        ).first()
        if entry and entry.best_score:
            user_scores[jd['pool'].id] = {
                'best_score': entry.best_score,
                'games': entry.games,
            }

    return render_template('jackpots.html', user=user, jackpot_data=jackpot_data,
                           payouts=payouts_int, user_scores=user_scores)


@jackpot_bp.route('/api/jackpots')
@login_required
def api_jackpots():
    pools = JackpotPool.get_or_create_pools()
    db.session.commit()
    result = []
    for pool in pools:
        result.append({
            'id': pool.id,
            'tier': pool.stake_tier,
            'amount': pool.pool_amount,
            'min_stake': pool.min_stake,
            'max_stake': pool.max_stake,
        })
    return jsonify(result)
