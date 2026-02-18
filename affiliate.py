from flask import Blueprint, render_template
from models import (db, User, AffiliateCommission, Match, RakeTransaction,
                    get_affiliate_tiers, get_affiliate_tier_for_rake, get_affiliate_next_tier)
from auth import login_required, get_current_user
from sqlalchemy import func as sqlfunc

affiliate_bp = Blueprint('affiliate', __name__)


def get_total_referred_rake(user_id):
    referred_ids = [r.id for r in User.query.filter_by(referred_by_id=user_id).all()]
    if not referred_ids:
        return 0
    total = 0
    matches = Match.query.filter(
        Match.status == 'completed',
        Match.rake_amount > 0,
        db.or_(
            Match.player1_id.in_(referred_ids),
            Match.player2_id.in_(referred_ids),
        )
    ).all()
    for m in matches:
        player_rake = m.rake_amount / 2
        if m.player1_id in referred_ids:
            total += player_rake
        if m.player2_id in referred_ids:
            total += player_rake
    return int(total)


def process_affiliate_commission(match):
    if not match.winner_id or match.stake <= 0:
        return

    if not match.rake_amount or match.rake_amount <= 0:
        return

    player_rake = match.rake_amount / 2

    for player_id in [match.player1_id, match.player2_id]:
        if not player_id:
            continue
        player = User.query.get(player_id)
        if not player or not player.referred_by_id:
            continue

        existing = AffiliateCommission.query.filter_by(
            referrer_id=player.referred_by_id,
            referred_user_id=player_id,
            source_match_id=match.id,
        ).first()
        if existing:
            continue

        total_rake = get_total_referred_rake(player.referred_by_id)
        tier = get_affiliate_tier_for_rake(total_rake)
        rate = tier['percent'] / 100.0

        commission_amount = player_rake * rate
        if commission_amount < 0.01:
            continue

        commission = AffiliateCommission(
            referrer_id=player.referred_by_id,
            referred_user_id=player_id,
            source_match_id=match.id,
            amount=commission_amount,
            rate=rate,
            status='approved',
        )
        db.session.add(commission)

        referrer = User.query.get(player.referred_by_id)
        if referrer:
            referrer.coins += int(commission_amount)


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

    total_earned = db.session.query(sqlfunc.coalesce(sqlfunc.sum(AffiliateCommission.amount), 0))\
        .filter_by(referrer_id=user.id, status='approved').scalar() or 0

    total_referred_rake = get_total_referred_rake(user.id)
    current_tier = get_affiliate_tier_for_rake(total_referred_rake)
    next_tier = get_affiliate_next_tier(total_referred_rake)
    all_tiers = get_affiliate_tiers()

    return render_template('affiliate.html', user=user, referrals=referrals,
                           commissions=commissions, total_earned=total_earned,
                           total_referred_rake=total_referred_rake,
                           current_tier=current_tier, next_tier=next_tier,
                           all_tiers=all_tiers)
