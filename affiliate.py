from flask import Blueprint, render_template
from models import db, User, AffiliateCommission
from auth import login_required, get_current_user

affiliate_bp = Blueprint('affiliate', __name__)

AFFILIATE_RATE = 0.05


def process_affiliate_commission(match):
    if not match.winner_id or match.stake <= 0:
        return

    for player_id in [match.player1_id, match.player2_id]:
        if not player_id:
            continue
        player = User.query.get(player_id)
        if not player or not player.referred_by_id:
            continue

        rake = match.stake * AFFILIATE_RATE
        if rake < 0.01:
            continue

        existing = AffiliateCommission.query.filter_by(
            referrer_id=player.referred_by_id,
            referred_user_id=player_id,
            source_match_id=match.id,
        ).first()
        if existing:
            continue

        commission = AffiliateCommission(
            referrer_id=player.referred_by_id,
            referred_user_id=player_id,
            source_match_id=match.id,
            amount=rake,
            rate=AFFILIATE_RATE,
            status='approved',
        )
        db.session.add(commission)

        referrer = User.query.get(player.referred_by_id)
        if referrer:
            referrer.coins += int(rake)


@affiliate_bp.route('/affiliate')
@login_required
def affiliate_page():
    user = get_current_user()
    user.ensure_affiliate_code()
    db.session.commit()

    referrals = User.query.filter_by(referred_by_id=user.id)\
        .order_by(User.created_at.desc()).all()

    commissions = AffiliateCommission.query.filter_by(referrer_id=user.id)\
        .order_by(AffiliateCommission.created_at.desc()).limit(50).all()

    total_earned = db.session.query(db.func.sum(AffiliateCommission.amount))\
        .filter_by(referrer_id=user.id, status='approved').scalar() or 0

    return render_template('affiliate.html', user=user, referrals=referrals,
                           commissions=commissions, total_earned=total_earned)
