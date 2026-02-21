from flask_sqlalchemy import SQLAlchemy
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

    STATUS = {
        'pending': 0,
        'approved': 1,
        'rejected': 2,
    }
    STATUS_LABEL = {v: k for k, v in STATUS.items()}

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    type = db.Column(db.String(30), nullable=False)
    amount = db.Column(db.Integer, nullable=False)

    currency = db.Column(db.String(10), default='USD')
    crypto_address = db.Column(db.String(256), nullable=True)
    network = db.Column(db.String(50), nullable=True)

    status_code = db.Column(
        'status',
        db.SmallInteger,
        default=STATUS['pending'],
        nullable=False,
        index=True
    )

    description = db.Column(db.String(256), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    processed_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship('User', backref='wallet_transactions')

    @property
    def status(self):
        return self.STATUS_LABEL.get(int(self.status_code), 'pending')

    @status.setter
    def status(self, label):
        if label not in self.STATUS:
            raise ValueError(f"Invalid transaction status: {label}")
        self.status_code = self.STATUS[label]

class VIPProgress(db.Model):
    __tablename__ = 'vip_progress'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    total_wagered = db.Column(db.Integer, default=0, nullable=False)
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

    STATUS = {
        'pending': 0,
        'approved': 1,
        'paid': 2,
    }
    STATUS_LABEL = {v: k for k, v in STATUS.items()}

    id = db.Column(db.Integer, primary_key=True)

    referrer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    referred_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    source_match_id = db.Column(db.Integer, db.ForeignKey('matches.id'), nullable=True)

    amount = db.Column(db.Integer, nullable=False)
    rate = db.Column(db.Float, default=0.05)

    status_code = db.Column(
        'status',
        db.SmallInteger,
        default=STATUS['pending'],
        nullable=False,
        index=True
    )

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    referrer = db.relationship('User', foreign_keys=[referrer_id], backref='commissions_earned')
    referred_user = db.relationship('User', foreign_keys=[referred_user_id])

    @property
    def status(self):
        return self.STATUS_LABEL.get(int(self.status_code), 'pending')

    @status.setter
    def status(self, label):
        if label not in self.STATUS:
            raise ValueError(f"Invalid commission status: {label}")
        self.status_code = self.STATUS[label]


GAME_MODES = {
    'classic': {'name': 'BJ Classic', 'short': 'Auto dealer, standard deck'},
    'interactive': {'name': 'BJ Interactive', 'short': 'Manual dealer, standard deck'},
    'classic_joker': {'name': 'Classic Joker', 'short': 'Auto dealer + 4 jokers'},
    'interactive_joker': {'name': 'Interactive Joker', 'short': 'Manual dealer + 4 jokers'},
}

GAME_MODE_LIST = list(GAME_MODES.keys())


class Match(db.Model):
    __tablename__ = 'matches'

    # ----------------------------
    # ENUM STORAGE MAPS
    # ----------------------------

    MATCH_STATUS = {
        'waiting': 0,
        'active': 1,
        'finished': 2,
    }
    MATCH_STATUS_LABEL = {v: k for k, v in MATCH_STATUS.items()}
    _MATCH_STATUS_ALIASES = {
        'completed': 'finished',
    }

    GAME_MODE_CODE = {mode: i for i, mode in enumerate(GAME_MODE_LIST)}
    GAME_MODE_LABEL = {v: k for k, v in GAME_MODE_CODE.items()}

    # ----------------------------
    # CORE COLUMNS
    # ----------------------------

    id = db.Column(db.Integer, primary_key=True)

    player1_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    player2_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    stake = db.Column(db.Integer, nullable=False)

    # Store integer codes in the existing column names
    game_mode_code = db.Column(
        'game_mode',
        db.SmallInteger,
        default=GAME_MODE_CODE['classic'],
        nullable=False,
        index=True
    )

    status_code = db.Column(
        'status',
        db.SmallInteger,
        default=MATCH_STATUS['waiting'],
        nullable=False,
        index=True
    )

    winner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    decision_started_at = db.Column(db.Float, nullable=True)
    decision_type = db.Column(db.String(20), nullable=True)

    is_waiting_decision = db.Column(db.Boolean, default=False)
    is_spectatable = db.Column(db.Boolean, default=True)

    tournament_match_id = db.Column(db.Integer, db.ForeignKey('tournament_matches.id'), nullable=True)

    rake_amount = db.Column(db.Integer, default=0)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # ----------------------------
    # RELATIONSHIPS
    # ----------------------------

    player1 = db.relationship('User', foreign_keys=[player1_id], backref='matches_as_p1')
    player2 = db.relationship('User', foreign_keys=[player2_id], backref='matches_as_p2')
    winner = db.relationship('User', foreign_keys=[winner_id])

    # ----------------------------
    # STRING-COMPATIBLE PROPERTIES
    # ----------------------------

    @property
    def status(self) -> str:
        return self.MATCH_STATUS_LABEL.get(int(self.status_code), 'waiting')

    @status.setter
    def status(self, label: str) -> None:
        if label in self._MATCH_STATUS_ALIASES:
            label = self._MATCH_STATUS_ALIASES[label]

        if label not in self.MATCH_STATUS:
            raise ValueError(f"Invalid match status: {label}")

        self.status_code = self.MATCH_STATUS[label]

    @property
    def game_mode(self) -> str:
        return self.GAME_MODE_LABEL.get(int(self.game_mode_code), 'classic')

    @game_mode.setter
    def game_mode(self, label: str) -> None:
        if label not in self.GAME_MODE_CODE:
            raise ValueError(f"Invalid game mode: {label}")

        self.game_mode_code = self.GAME_MODE_CODE[label]

    # ----------------------------
    # INDEXES
    # ----------------------------

    __table_args__ = (
        db.Index('idx_match_created', 'created_at'),
        db.Index('idx_match_player1', 'player1_id'),
        db.Index('idx_match_player2', 'player2_id'),
    )

class Tournament(db.Model):
    __tablename__ = 'tournaments'

    TOURNAMENT_STATUS = {
        'waiting': 0,
        'active': 1,
        'completed': 2,
    }
    TOURNAMENT_STATUS_LABEL = {v: k for k, v in TOURNAMENT_STATUS.items()}

    GAME_MODE_CODE = {mode: i for i, mode in enumerate(GAME_MODE_LIST)}
    GAME_MODE_LABEL = {v: k for k, v in GAME_MODE_CODE.items()}

    id = db.Column(db.Integer, primary_key=True)

    stake_amount = db.Column(db.Integer, nullable=False)
    max_players = db.Column(db.Integer, default=8, nullable=False)

    game_mode_code = db.Column(
        'game_mode',
        db.SmallInteger,
        default=GAME_MODE_CODE['classic'],
        nullable=False,
        index=True
    )

    status_code = db.Column(
        'status',
        db.SmallInteger,
        default=TOURNAMENT_STATUS['waiting'],
        nullable=False,
        index=True
    )

    current_round = db.Column(db.String(20), default='round_1')
    prize_pool = db.Column(db.Integer, default=0)
    rake_amount = db.Column(db.Integer, default=0)

    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    entries = db.relationship('TournamentEntry', backref='tournament', lazy='dynamic')
    matches = db.relationship('TournamentMatch', backref='tournament', lazy='dynamic')

    @property
    def status(self):
        return self.TOURNAMENT_STATUS_LABEL.get(int(self.status_code), 'waiting')

    @status.setter
    def status(self, label):
        if label not in self.TOURNAMENT_STATUS:
            raise ValueError(f"Invalid tournament status: {label}")
        self.status_code = self.TOURNAMENT_STATUS[label]

    @property
    def game_mode(self):
        return self.GAME_MODE_LABEL.get(int(self.game_mode_code), 'classic')

    @game_mode.setter
    def game_mode(self, label):
        if label not in self.GAME_MODE_CODE:
            raise ValueError(f"Invalid tournament game mode: {label}")
        self.game_mode_code = self.GAME_MODE_CODE[label]

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

    # ----------------------------
    # STATUS ENUM
    # ----------------------------

    STATUS = {
        'pending': 0,
        'active': 1,
        'completed': 2,
    }
    STATUS_LABEL = {v: k for k, v in STATUS.items()}

    # ----------------------------
    # COLUMNS
    # ----------------------------

    id = db.Column(db.Integer, primary_key=True)

    tournament_id = db.Column(db.Integer, db.ForeignKey('tournaments.id'), nullable=False)
    round = db.Column(db.String(20), nullable=False)
    bracket_position = db.Column(db.Integer, nullable=False)

    player1_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    player2_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    match_id = db.Column(db.Integer, db.ForeignKey('matches.id'), nullable=True)
    winner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    status_code = db.Column(
        'status',
        db.SmallInteger,
        default=STATUS['pending'],
        nullable=False,
        index=True
    )

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # ----------------------------
    # RELATIONSHIPS
    # ----------------------------

    player1 = db.relationship('User', foreign_keys=[player1_id])
    player2 = db.relationship('User', foreign_keys=[player2_id])
    winner = db.relationship('User', foreign_keys=[winner_id])
    game_match = db.relationship('Match', foreign_keys=[match_id])

    # ----------------------------
    # STRING PROPERTY
    # ----------------------------

    @property
    def status(self):
        return self.STATUS_LABEL.get(int(self.status_code), 'pending')

    @status.setter
    def status(self, label):
        if label not in self.STATUS:
            raise ValueError(f"Invalid tournament match status: {label}")
        self.status_code = self.STATUS[label]


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
    total_rake_paid = db.Column(db.Integer, default=0, nullable=False)
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
            self.total_rake_paid = 0
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

    # ----------------------------
    # STATUS ENUM
    # ----------------------------

    STATUS = {
        'inactive': 0,
        'active': 1,
        'paid': 2,
    }
    STATUS_LABEL = {v: k for k, v in STATUS.items()}

    # ----------------------------
    # COLUMNS
    # ----------------------------

    id = db.Column(db.Integer, primary_key=True)

    stake_tier = db.Column(db.String(50), nullable=False, default='Main')
    pool_type = db.Column(db.String(20), nullable=False, default='standard')

    min_stake = db.Column(db.Integer, nullable=False, default=0)
    max_stake = db.Column(db.Integer, nullable=False, default=999999)

    pool_amount = db.Column(db.Integer, default=0, nullable=False)

    status_code = db.Column(
        'status',
        db.SmallInteger,
        default=STATUS['active'],
        nullable=False,
        index=True
    )

    period_start = db.Column(db.DateTime, default=datetime.utcnow)
    paid_out_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # ----------------------------
    # RELATIONSHIPS
    # ----------------------------

    entries = db.relationship('JackpotEntry', backref='jackpot', lazy='dynamic')

    POOL_TYPES = {
        'standard': 'Standard (Classic & Interactive)',
        'joker': 'Joker (Classic Joker & Interactive Joker)',
    }

    # ----------------------------
    # STRING PROPERTY
    # ----------------------------

    @property
    def status(self):
        return self.STATUS_LABEL.get(int(self.status_code), 'active')

    @status.setter
    def status(self, label):
        if label not in self.STATUS:
            raise ValueError(f"Invalid jackpot status: {label}")
        self.status_code = self.STATUS[label]

    # ----------------------------
    # HELPERS
    # ----------------------------

    @staticmethod
    def get_active_pool(pool_type='standard'):
        pool = JackpotPool.query.filter(
            JackpotPool.status_code == JackpotPool.STATUS['active'],
            JackpotPool.pool_type == pool_type
        ).first()

        if not pool:
            label = 'Standard' if pool_type == 'standard' else 'Joker'
            pool = JackpotPool(
                stake_tier=label,
                pool_type=pool_type,
                min_stake=0,
                max_stake=999999,
                pool_amount=0,
                status='active'
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

# =============================================================================
# NORMALIZED MATCH STATE STORAGE (SQL-FIRST REPLACEMENT FOR JSON game_state)
# =============================================================================

CARD_RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A', 'JOKER']
CARD_SUITS = ['hearts', 'diamonds', 'clubs', 'spades', 'joker']


class MatchState(db.Model):
    __tablename__ = 'match_state'

    match_id = db.Column(db.Integer, db.ForeignKey('matches.id'), primary_key=True)

    phase = db.Column(db.String(30), nullable=False, default='CARD_DRAW')
    is_heads_up = db.Column(db.Boolean, nullable=False, default=False)

    draw_deck_pos = db.Column(db.SmallInteger, nullable=False, default=0)
    draw_winner = db.Column(db.SmallInteger, nullable=True)
    chooser = db.Column(db.SmallInteger, nullable=True)
    choice_made = db.Column(db.Boolean, nullable=False, default=False)
    draw_timestamp = db.Column(db.Float, nullable=True)

    current_turn = db.Column(db.SmallInteger, nullable=False, default=0)

    match_over = db.Column(db.Boolean, nullable=False, default=False)
    match_result_winner = db.Column(db.SmallInteger, nullable=True)
    match_result_reason = db.Column(db.String(40), nullable=True)

    __table_args__ = (
        db.Index('idx_match_state_phase', 'phase'),
    )


class MatchDrawDeckCard(db.Model):
    __tablename__ = 'match_draw_deck_cards'

    match_id = db.Column(db.Integer, db.ForeignKey('matches.id'), primary_key=True)
    pos = db.Column(db.SmallInteger, primary_key=True)
    rank_code = db.Column(db.SmallInteger, nullable=False)
    suit_code = db.Column(db.SmallInteger, nullable=False)


class MatchDrawCard(db.Model):
    __tablename__ = 'match_draw_cards'

    match_id = db.Column(db.Integer, db.ForeignKey('matches.id'), primary_key=True)
    player_num = db.Column(db.SmallInteger, primary_key=True)
    seq = db.Column(db.SmallInteger, primary_key=True)
    rank_code = db.Column(db.SmallInteger, nullable=False)
    suit_code = db.Column(db.SmallInteger, nullable=False)


class MatchTurn(db.Model):
    __tablename__ = 'match_turns'

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    match_id = db.Column(db.Integer, db.ForeignKey('matches.id'), nullable=False, index=True)
    turn_index = db.Column(db.SmallInteger, nullable=False)

    player_role = db.Column(db.SmallInteger, nullable=False)
    dealer_role = db.Column(db.SmallInteger, nullable=False)

    starting_chips = db.Column(db.Integer, nullable=False, default=100)
    chips = db.Column(db.Integer, nullable=False, default=100)

    cards_dealt = db.Column(db.SmallInteger, nullable=False, default=0)
    cut_card_reached = db.Column(db.Boolean, nullable=False, default=False)

    active_round_index = db.Column(db.SmallInteger, nullable=True)

    __table_args__ = (
        db.UniqueConstraint('match_id', 'turn_index', name='uq_match_turn'),
        db.Index('idx_turn_lookup', 'match_id', 'turn_index'),
    )


class MatchTurnDeckCard(db.Model):
    __tablename__ = 'match_turn_deck_cards'

    match_id = db.Column(db.Integer, primary_key=True)
    turn_index = db.Column(db.SmallInteger, primary_key=True)
    pos = db.Column(db.SmallInteger, primary_key=True)

    rank_code = db.Column(db.SmallInteger, nullable=False)
    suit_code = db.Column(db.SmallInteger, nullable=False)

    __table_args__ = (
        db.ForeignKeyConstraint(
            ['match_id', 'turn_index'],
            ['match_turns.match_id', 'match_turns.turn_index'],
            ondelete='CASCADE'
        ),
    )


class MatchRound(db.Model):
    __tablename__ = 'match_rounds'

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)

    match_id = db.Column(db.Integer, db.ForeignKey('matches.id'), nullable=False, index=True)
    turn_index = db.Column(db.SmallInteger, nullable=False)
    round_index = db.Column(db.SmallInteger, nullable=False)

    current_box = db.Column(db.SmallInteger, nullable=False, default=0)
    current_hand = db.Column(db.SmallInteger, nullable=False, default=0)

    insurance_offered = db.Column(db.Boolean, nullable=False, default=False)
    total_initial_bet = db.Column(db.Integer, nullable=False, default=0)
    resolved = db.Column(db.Boolean, nullable=False, default=False)

    __table_args__ = (
        db.UniqueConstraint('match_id', 'turn_index', 'round_index'),
        db.Index('idx_round_lookup', 'match_id', 'turn_index', 'round_index'),
    )


class MatchDealerCard(db.Model):
    __tablename__ = 'match_dealer_cards'

    match_id = db.Column(db.Integer, db.ForeignKey('matches.id'), primary_key=True)
    turn_index = db.Column(db.SmallInteger, primary_key=True)
    round_index = db.Column(db.SmallInteger, primary_key=True)
    seq = db.Column(db.SmallInteger, primary_key=True)

    rank_code = db.Column(db.SmallInteger, nullable=False)
    suit_code = db.Column(db.SmallInteger, nullable=False)
    joker_chosen_value = db.Column(db.SmallInteger, nullable=True)

    __table_args__ = (
        db.Index('idx_dealer_lookup', 'match_id', 'turn_index', 'round_index'),
    )


class MatchBox(db.Model):
    __tablename__ = 'match_boxes'

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)

    match_id = db.Column(db.Integer, db.ForeignKey('matches.id'), nullable=False, index=True)
    turn_index = db.Column(db.SmallInteger, nullable=False)
    round_index = db.Column(db.SmallInteger, nullable=False)
    box_index = db.Column(db.SmallInteger, nullable=False)

    bet = db.Column(db.Integer, nullable=False)

    __table_args__ = (
        db.UniqueConstraint('match_id', 'turn_index', 'round_index', 'box_index'),
        db.Index('idx_box_lookup', 'match_id', 'turn_index', 'round_index'),
    )


class MatchHand(db.Model):
    __tablename__ = 'match_hands'

    # ----------------------------
    # STATUS + RESULT ENUMS
    # ----------------------------

    STATUS = {
        'active': 0,
        'stand': 1,
        'bust': 2,
        'blackjack': 3,
        'push': 4,
        'lose': 5,
    }
    STATUS_LABEL = {v: k for k, v in STATUS.items()}

    RESULT = {
        'win': 1,
        'lose': 2,
        'push': 3,
        'blackjack_win': 4,
    }
    RESULT_LABEL = {v: k for k, v in RESULT.items()}

    # ----------------------------
    # COLUMNS
    # ----------------------------

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)

    match_id = db.Column(db.Integer, db.ForeignKey('matches.id'), nullable=False, index=True)
    turn_index = db.Column(db.SmallInteger, nullable=False)
    round_index = db.Column(db.SmallInteger, nullable=False)
    box_index = db.Column(db.SmallInteger, nullable=False)
    hand_index = db.Column(db.SmallInteger, nullable=False)

    bet = db.Column(db.Integer, nullable=False)

    status_code = db.Column(
        'status',
        db.SmallInteger,
        default=STATUS['active'],
        nullable=False,
        index=True
    )

    result_code = db.Column(
        'result',
        db.SmallInteger,
        nullable=True,
        index=True
    )

    is_split = db.Column(db.Boolean, nullable=False, default=False)
    is_doubled = db.Column(db.Boolean, nullable=False, default=False)

    from_split_aces = db.Column(db.Boolean, nullable=False, default=False)
    from_split_jokers = db.Column(db.Boolean, nullable=False, default=False)

    __table_args__ = (
        db.UniqueConstraint(
            'match_id', 'turn_index', 'round_index', 'box_index', 'hand_index'
        ),
        db.Index('idx_hand_lookup', 'match_id', 'turn_index', 'round_index'),
    )

    # ----------------------------
    # STRING PROPERTIES
    # ----------------------------

    @property
    def status(self):
        return self.STATUS_LABEL.get(int(self.status_code), 'active')

    @status.setter
    def status(self, label):
        if label not in self.STATUS:
            raise ValueError(f"Invalid hand status: {label}")
        self.status_code = self.STATUS[label]

    @property
    def result(self):
        if self.result_code is None:
            return None
        return self.RESULT_LABEL.get(int(self.result_code))

    @result.setter
    def result(self, label):
        if label is None:
            self.result_code = None
            return
        if label not in self.RESULT:
            raise ValueError(f"Invalid hand result: {label}")
        self.result_code = self.RESULT[label]

class MatchHandCard(db.Model):
    __tablename__ = 'match_hand_cards'

    match_id = db.Column(db.Integer, db.ForeignKey('matches.id'), primary_key=True)
    turn_index = db.Column(db.SmallInteger, primary_key=True)
    round_index = db.Column(db.SmallInteger, primary_key=True)
    box_index = db.Column(db.SmallInteger, primary_key=True)
    hand_index = db.Column(db.SmallInteger, primary_key=True)
    seq = db.Column(db.SmallInteger, primary_key=True)

    rank_code = db.Column(db.SmallInteger, nullable=False)
    suit_code = db.Column(db.SmallInteger, nullable=False)
    joker_chosen_value = db.Column(db.SmallInteger, nullable=True)

    __table_args__ = (
        db.Index(
            'idx_hand_card_lookup',
            'match_id', 'turn_index', 'round_index', 'box_index', 'hand_index'
        ),
    )


class MatchHandInsurance(db.Model):
    __tablename__ = 'match_hand_insurance'

    match_id = db.Column(db.Integer, db.ForeignKey('matches.id'), primary_key=True)
    turn_index = db.Column(db.SmallInteger, primary_key=True)
    round_index = db.Column(db.SmallInteger, primary_key=True)
    box_index = db.Column(db.SmallInteger, primary_key=True)
    hand_index = db.Column(db.SmallInteger, primary_key=True)

    offered = db.Column(db.Boolean, nullable=False, default=False)
    taken = db.Column(db.Boolean, nullable=False, default=False)
    amount = db.Column(db.Integer, nullable=False, default=0)
    decided = db.Column(db.Boolean, nullable=False, default=False)

    __table_args__ = (
        db.Index(
            'idx_insurance_lookup',
            'match_id', 'turn_index', 'round_index', 'box_index', 'hand_index'
        ),
    )


class MatchTurnResult(db.Model):
    __tablename__ = 'match_turn_results'

    match_id = db.Column(db.Integer, db.ForeignKey('matches.id'), primary_key=True)
    player_num = db.Column(db.SmallInteger, primary_key=True)
    turn_number = db.Column(db.SmallInteger, primary_key=True)

    chips_end = db.Column(db.Integer, nullable=False)
