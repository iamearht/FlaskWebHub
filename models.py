from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.ext.mutable import MutableDict
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import secrets
import string
import json

from extensions import db


def generate_affiliate_code():
    chars = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(chars) for _ in range(8))


class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    password_hash = db.Column(db.String(256), nullable=False)
    coins = db.Column(db.Integer, default=0, nullable=False)
    affiliate_code = db.Column(db.String(20), unique=True, nullable=True)
    referred_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
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

    def get_rakeback_progress(self):
        rp = RakebackProgress.query.filter_by(user_id=self.id).first()
        if not rp:
            rp = RakebackProgress(user_id=self.id)
            db.session.add(rp)
            db.session.flush()
        return rp


class WalletTransaction(db.Model):
    __tablename__ = 'wallet_transactions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    type = db.Column(db.String(30), nullable=False)
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


GAME_MODES = {
    'classic': {'name': 'BJ Classic', 'short': 'Auto dealer, standard deck'},
    'interactive': {'name': 'BJ Interactive', 'short': 'Manual dealer, standard deck'},
    'classic_joker': {'name': 'Classic Joker', 'short': 'Auto dealer + 4 jokers'},
    'interactive_joker': {'name': 'Interactive Joker', 'short': 'Manual dealer + 4 jokers'},
}

GAME_MODE_LIST = list(GAME_MODES.keys())


class Match(db.Model):
    __tablename__ = 'matches'
    id = db.Column(db.Integer, primary_key=True)
    player1_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    player2_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    stake = db.Column(db.Integer, nullable=False)
    game_mode = db.Column(db.String(30), default='classic', nullable=False)
    status = db.Column(db.String(20), default='waiting')
    winner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    game_state = db.Column(MutableDict.as_mutable(db.JSON), nullable=True)
    decision_started_at = db.Column(db.Float, nullable=True)
    decision_type = db.Column(db.String(20), nullable=True)
    is_waiting_decision = db.Column(db.Boolean, default=False)
    is_spectatable = db.Column(db.Boolean, default=True)
    tournament_match_id = db.Column(db.Integer, db.ForeignKey('tournament_matches.id'), nullable=True)
    rake_amount = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    player1 = db.relationship('User', foreign_keys=[player1_id], backref='matches_as_p1')
    player2 = db.relationship('User', foreign_keys=[player2_id], backref='matches_as_p2')
    winner = db.relationship('User', foreign_keys=[winner_id])


class Tournament(db.Model):
    __tablename__ = 'tournaments'
    id = db.Column(db.Integer, primary_key=True)
    stake_amount = db.Column(db.Integer, nullable=False)
    max_players = db.Column(db.Integer, default=8, nullable=False)
    game_mode = db.Column(db.String(30), default='classic', nullable=False)
    status = db.Column(db.String(20), default='waiting')
    current_round = db.Column(db.String(20), default='round_1')
    prize_pool = db.Column(db.Integer, default=0)
    rake_amount = db.Column(db.Integer, default=0)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    entries = db.relationship('TournamentEntry', backref='tournament', lazy='dynamic')
    matches = db.relationship('TournamentMatch', backref='tournament', lazy='dynamic')

    STAKES = [500, 1000, 2500, 5000, 10000]
    PLAYER_SIZES = [8, 16, 32, 64, 128]


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


class RakeTransaction(db.Model):
    __tablename__ = 'rake_transactions'
    id = db.Column(db.Integer, primary_key=True)
    source_type = db.Column(db.String(20), nullable=False)
    source_id = db.Column(db.Integer, nullable=False)
    amount = db.Column(db.Integer, nullable=False)
    stake_amount = db.Column(db.Integer, nullable=True)
    rake_percent = db.Column(db.Float, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class AdminConfig(db.Model):
    __tablename__ = 'admin_config'
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @staticmethod
    def get(key, default=None):
        config = AdminConfig.query.filter_by(key=key).first()
        if config:
            try:
                return json.loads(config.value)
            except (json.JSONDecodeError, TypeError):
                return config.value
        return default

    @staticmethod
    def set(key, value):
        config = AdminConfig.query.filter_by(key=key).first()
        val_str = json.dumps(value) if not isinstance(value, str) else value
        if config:
            config.value = val_str
            config.updated_at = datetime.utcnow()
        else:
            config = AdminConfig(key=key, value=val_str)
            db.session.add(config)
        db.session.flush()


class RakebackProgress(db.Model):
    __tablename__ = 'rakeback_progress'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    total_rake_paid = db.Column(db.Float, default=0.0)
    tier = db.Column(db.String(20), default='Bronze')
    period_start = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('rakeback_progress_rel', uselist=False))

    @staticmethod
    def _get_tiers():
        return AdminConfig.get('rakeback_tiers', [
            {'name': 'Bronze', 'threshold': 0, 'percent': 0},
            {'name': 'Silver', 'threshold': 500, 'percent': 5},
            {'name': 'Gold', 'threshold': 2000, 'percent': 10},
            {'name': 'Platinum', 'threshold': 5000, 'percent': 15},
        ])

    def check_reset(self):
        reset_days = AdminConfig.get('rakeback_reset_days', 60)
        if self.period_start and datetime.utcnow() > self.period_start + timedelta(days=reset_days):
            self.total_rake_paid = 0.0
            self.period_start = datetime.utcnow()
            self.update_tier()

    def add_rake(self, amount):
        self.check_reset()
        self.total_rake_paid += amount
        self.update_tier()

    def update_tier(self):
        tiers = self._get_tiers()
        lowest = tiers[0]['name'] if tiers else 'Bronze'
        self.tier = lowest
        for tier in reversed(tiers):
            if self.total_rake_paid >= tier['threshold']:
                self.tier = tier['name']
                break

    def ensure_consistent(self):
        self.check_reset()
        self.update_tier()

    @property
    def rakeback_percent(self):
        self.ensure_consistent()
        tiers = self._get_tiers()
        for tier in reversed(tiers):
            if tier['name'] == self.tier:
                return tier['percent']
        return 0

    @property
    def next_tier_info(self):
        self.ensure_consistent()
        tiers = self._get_tiers()
        for tier in tiers:
            if tier['threshold'] > self.total_rake_paid:
                return tier
        return None


class JackpotPool(db.Model):
    __tablename__ = 'jackpot_pools'
    id = db.Column(db.Integer, primary_key=True)
    stake_tier = db.Column(db.String(50), nullable=False, default='Main')
    pool_type = db.Column(db.String(20), nullable=False, default='standard')
    min_stake = db.Column(db.Integer, nullable=False, default=0)
    max_stake = db.Column(db.Integer, nullable=False, default=999999)
    pool_amount = db.Column(db.Integer, default=0, nullable=False)
    status = db.Column(db.String(20), default='active', nullable=False)
    period_start = db.Column(db.DateTime, default=datetime.utcnow)
    paid_out_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    entries = db.relationship('JackpotEntry', backref='jackpot', lazy='dynamic')

    POOL_TYPES = {
        'standard': 'Standard (Classic & Interactive)',
        'joker': 'Joker (Classic Joker & Interactive Joker)',
    }

    @staticmethod
    def get_active_pool(pool_type='standard'):
        pool = JackpotPool.query.filter_by(status='active', pool_type=pool_type).first()
        if not pool:
            label = 'Standard' if pool_type == 'standard' else 'Joker'
            pool = JackpotPool(
                stake_tier=label,
                pool_type=pool_type,
                min_stake=0,
                max_stake=999999,
                pool_amount=0,
                status='active',
            )
            db.session.add(pool)
            db.session.flush()
        return pool

    @staticmethod
    def get_all_active_pools():
        standard = JackpotPool.get_active_pool('standard')
        joker = JackpotPool.get_active_pool('joker')
        return {'standard': standard, 'joker': joker}

    @staticmethod
    def pool_type_for_mode(game_mode):
        if game_mode in ('classic_joker', 'interactive_joker'):
            return 'joker'
        return 'standard'


class JackpotEntry(db.Model):
    __tablename__ = 'jackpot_entries'
    id = db.Column(db.Integer, primary_key=True)

    jackpot_id = db.Column(db.Integer, db.ForeignKey('jackpot_pools.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    match_id = db.Column(db.Integer, db.ForeignKey('matches.id'), nullable=False)

    # NEW: store jackpot contribution amount for this entry (matches your game.py usage)
    amount = db.Column(db.Integer, nullable=False, default=0)

    # existing fields
    score = db.Column(db.Integer, nullable=False, default=0)
    finishing_chips = db.Column(db.Integer, nullable=False, default=0)
    match_stake = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='jackpot_entries')
    match = db.relationship('Match', backref='jackpot_entries')


def get_jackpot_rake_percent():
    return AdminConfig.get('jackpot_rake_percent', 20)


def get_jackpot_payouts():
    return AdminConfig.get('jackpot_payouts', {
        '1': 50, '2': 25, '3': 15, '4': 10
    })


def get_affiliate_tiers():
    return AdminConfig.get('affiliate_tiers', [
        {'name': 'Bronze', 'threshold': 0, 'percent': 2},
        {'name': 'Silver', 'threshold': 5000, 'percent': 5},
        {'name': 'Gold', 'threshold': 25000, 'percent': 8},
        {'name': 'Platinum', 'threshold': 100000, 'percent': 12},
    ])


def get_affiliate_tier_for_rake(total_rake):
    tiers = get_affiliate_tiers()
    current = tiers[0] if tiers else {'name': 'Bronze', 'threshold': 0, 'percent': 2}
    for tier in reversed(tiers):
        if total_rake >= tier['threshold']:
            current = tier
            break
    return current


def get_affiliate_next_tier(total_rake):
    tiers = get_affiliate_tiers()
    for tier in tiers:
        if tier['threshold'] > total_rake:
            return tier
    return None


def get_lobby_rake_percent(stake):
    tiers = AdminConfig.get('lobby_rake_tiers', [
        {'min': 0, 'max': 250, 'percent': 1},
        {'min': 250, 'max': 1000, 'percent': 2},
        {'min': 1000, 'max': 5000, 'percent': 3},
        {'min': 5000, 'max': 999999, 'percent': 5},
    ])
    for tier in tiers:
        if tier['min'] <= stake < tier['max']:
            return tier['percent']
    return 1


def get_tournament_rake_percent(stake, max_players):
    key = f'tournament_rake_{stake}_{max_players}'
    return AdminConfig.get(key, 5)


def get_tournament_payouts(max_players):
    key = f'tournament_payouts_{max_players}'
    default_payouts = {
        8: {1: 50, 2: 25, 3: 15, 4: 10},
        16: {1: 45, 2: 25, 3: 15, 4: 10, 5: 5},
        32: {1: 40, 2: 22, 3: 15, 4: 10, 5: 5, 6: 4, 7: 2, 8: 2},
        64: {1: 35, 2: 20, 3: 15, 4: 10, 5: 5, 6: 5, 7: 5, 8: 5},
        128: {1: 30, 2: 18, 3: 13, 4: 10, 5: 7, 6: 7, 7: 5, 8: 5, 9: 5},
    }
    result = AdminConfig.get(key, default_payouts.get(max_players, default_payouts[8]))
    if isinstance(result, dict):
        return {int(k): v for k, v in result.items()}
    return result
