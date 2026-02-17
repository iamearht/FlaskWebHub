from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.ext.mutable import MutableDict
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import secrets
import string

db = SQLAlchemy()


def generate_affiliate_code():
    chars = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(chars) for _ in range(8))


class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    password_hash = db.Column(db.String(256), nullable=False)
    coins = db.Column(db.Integer, default=1000, nullable=False)
    affiliate_code = db.Column(db.String(20), unique=True, nullable=True)
    referred_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    referred_by = db.relationship('User', remote_side=[id], foreign_keys=[referred_by_id])

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def ensure_affiliate_code(self):
        if not self.affiliate_code:
            for _ in range(10):
                code = generate_affiliate_code()
                if not User.query.filter_by(affiliate_code=code).first():
                    self.affiliate_code = code
                    return code
        return self.affiliate_code

    @property
    def balance(self):
        return self.coins

    def get_vip_progress(self):
        vp = VIPProgress.query.filter_by(user_id=self.id).first()
        if not vp:
            vp = VIPProgress(user_id=self.id)
            db.session.add(vp)
            db.session.flush()
        return vp


class WalletTransaction(db.Model):
    __tablename__ = 'wallet_transactions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    type = db.Column(db.String(20), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(10), default='USD')
    crypto_address = db.Column(db.String(256), nullable=True)
    network = db.Column(db.String(50), nullable=True)
    status = db.Column(db.String(20), default='pending')
    description = db.Column(db.String(256), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    processed_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship('User', backref='wallet_transactions')


class VIPProgress(db.Model):
    __tablename__ = 'vip_progress'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    total_wagered = db.Column(db.Float, default=0.0)
    tier = db.Column(db.String(20), default='Bronze')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('vip_progress_rel', uselist=False))

    VIP_TIERS = [
        ('Bronze', 0),
        ('Silver', 500),
        ('Gold', 2000),
        ('Platinum', 5000),
        ('Diamond', 15000),
    ]

    def update_tier(self):
        for tier_name, threshold in reversed(self.VIP_TIERS):
            if self.total_wagered >= threshold:
                self.tier = tier_name
                break

    def add_wager(self, amount):
        self.total_wagered += amount
        self.update_tier()

    @property
    def next_tier(self):
        for tier_name, threshold in self.VIP_TIERS:
            if threshold > self.total_wagered:
                return tier_name, threshold
        return None, None

    @property
    def progress_percent(self):
        current_threshold = 0
        next_threshold = None
        for tier_name, threshold in self.VIP_TIERS:
            if threshold <= self.total_wagered:
                current_threshold = threshold
            else:
                next_threshold = threshold
                break
        if next_threshold is None:
            return 100
        range_size = next_threshold - current_threshold
        if range_size <= 0:
            return 100
        return min(100, int((self.total_wagered - current_threshold) / range_size * 100))


class AffiliateCommission(db.Model):
    __tablename__ = 'affiliate_commissions'
    id = db.Column(db.Integer, primary_key=True)
    referrer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    referred_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    source_match_id = db.Column(db.Integer, db.ForeignKey('matches.id'), nullable=True)
    amount = db.Column(db.Float, nullable=False)
    rate = db.Column(db.Float, default=0.05)
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    referrer = db.relationship('User', foreign_keys=[referrer_id], backref='commissions_earned')
    referred_user = db.relationship('User', foreign_keys=[referred_user_id])


class Match(db.Model):
    __tablename__ = 'matches'
    id = db.Column(db.Integer, primary_key=True)
    player1_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    player2_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    stake = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default='waiting')
    winner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    game_state = db.Column(MutableDict.as_mutable(db.JSON), nullable=True)
    decision_started_at = db.Column(db.Float, nullable=True)
    decision_type = db.Column(db.String(20), nullable=True)
    is_waiting_decision = db.Column(db.Boolean, default=False)
    is_spectatable = db.Column(db.Boolean, default=True)
    tournament_match_id = db.Column(db.Integer, db.ForeignKey('tournament_matches.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    player1 = db.relationship('User', foreign_keys=[player1_id], backref='matches_as_p1')
    player2 = db.relationship('User', foreign_keys=[player2_id], backref='matches_as_p2')
    winner = db.relationship('User', foreign_keys=[winner_id])


class Tournament(db.Model):
    __tablename__ = 'tournaments'
    id = db.Column(db.Integer, primary_key=True)
    stake_amount = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default='waiting')
    current_round = db.Column(db.String(20), default='quarterfinal')
    prize_pool = db.Column(db.Integer, default=0)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    entries = db.relationship('TournamentEntry', backref='tournament', lazy='dynamic')
    matches = db.relationship('TournamentMatch', backref='tournament', lazy='dynamic')

    STAKES = [5, 10, 25, 50, 100]

    PAYOUTS = {
        1: 0.50,
        2: 0.25,
        3: 0.15,
        4: 0.10,
    }


class TournamentEntry(db.Model):
    __tablename__ = 'tournament_entries'
    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournaments.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    seed = db.Column(db.Integer, nullable=True)
    placement = db.Column(db.Integer, nullable=True)
    eliminated_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='tournament_entries')

    __table_args__ = (
        db.UniqueConstraint('tournament_id', 'user_id', name='uq_tournament_user'),
    )


class TournamentMatch(db.Model):
    __tablename__ = 'tournament_matches'
    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournaments.id'), nullable=False)
    round = db.Column(db.String(20), nullable=False)
    bracket_position = db.Column(db.Integer, nullable=False)
    player1_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    player2_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    match_id = db.Column(db.Integer, db.ForeignKey('matches.id'), nullable=True)
    winner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    player1 = db.relationship('User', foreign_keys=[player1_id])
    player2 = db.relationship('User', foreign_keys=[player2_id])
    winner = db.relationship('User', foreign_keys=[winner_id])
    game_match = db.relationship('Match', foreign_keys=[match_id])
