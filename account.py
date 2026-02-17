from flask import Blueprint, render_template, request, redirect, url_for, flash
from models import db, User, Match, WalletTransaction, VIPProgress
from auth import login_required, get_current_user

account_bp = Blueprint('account', __name__)


def get_user_stats(user):
    total_matches = Match.query.filter(
        ((Match.player1_id == user.id) | (Match.player2_id == user.id)),
        Match.status == 'finished'
    ).count()

    wins = Match.query.filter(
        Match.winner_id == user.id,
        Match.status == 'finished'
    ).count()

    losses = total_matches - wins
    forfeits_given = Match.query.filter(
        ((Match.player1_id == user.id) | (Match.player2_id == user.id)),
        Match.status == 'finished',
        Match.winner_id != user.id,
        Match.winner_id.isnot(None),
    ).count()

    total_wagered_query = db.session.query(db.func.sum(Match.stake)).filter(
        ((Match.player1_id == user.id) | (Match.player2_id == user.id)),
        Match.status == 'finished'
    ).scalar()
    total_wagered = total_wagered_query or 0

    total_won = db.session.query(db.func.sum(Match.stake)).filter(
        Match.winner_id == user.id,
        Match.status == 'finished'
    ).scalar() or 0

    return {
        'total_matches': total_matches,
        'wins': wins,
        'losses': losses,
        'win_rate': round(wins / total_matches * 100, 1) if total_matches > 0 else 0,
        'total_wagered': total_wagered,
        'total_won': total_won,
        'net_profit': total_won - (total_wagered - total_won),
    }


@account_bp.route('/account')
@login_required
def account_page():
    user = get_current_user()
    user.ensure_affiliate_code()
    db.session.commit()
    stats = get_user_stats(user)
    vip = user.get_vip_progress()
    db.session.commit()

    referral_count = User.query.filter_by(referred_by_id=user.id).count()

    return render_template('account.html', user=user, stats=stats, vip=vip,
                           referral_count=referral_count)


@account_bp.route('/account/transactions')
@login_required
def transaction_history():
    user = get_current_user()
    page = request.args.get('page', 1, type=int)
    per_page = 20
    txns = WalletTransaction.query.filter_by(user_id=user.id)\
        .order_by(WalletTransaction.created_at.desc())\
        .paginate(page=page, per_page=per_page, error_out=False)
    return render_template('transaction_history.html', user=user, txns=txns)


@account_bp.route('/account/games')
@login_required
def game_history():
    user = get_current_user()
    page = request.args.get('page', 1, type=int)
    per_page = 20
    matches = Match.query.filter(
        ((Match.player1_id == user.id) | (Match.player2_id == user.id)),
        Match.status == 'finished'
    ).order_by(Match.created_at.desc())\
     .paginate(page=page, per_page=per_page, error_out=False)
    return render_template('game_history.html', user=user, matches=matches)


@account_bp.route('/account/update', methods=['POST'])
@login_required
def update_account():
    user = get_current_user()
    email = request.form.get('email', '').strip()

    if email:
        existing = User.query.filter(User.email == email, User.id != user.id).first()
        if existing:
            flash('Email already in use.', 'error')
            return redirect(url_for('account.account_page'))
        user.email = email
    db.session.commit()
    flash('Account updated.', 'success')
    return redirect(url_for('account.account_page'))
