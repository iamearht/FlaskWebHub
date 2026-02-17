from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    coins = db.Column(db.Integer, default=1000, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Match(db.Model):
    __tablename__ = 'matches'
    id = db.Column(db.Integer, primary_key=True)
    player1_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    player2_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    stake = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default='waiting')
    winner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    game_state = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    player1 = db.relationship('User', foreign_keys=[player1_id], backref='matches_as_p1')
    player2 = db.relationship('User', foreign_keys=[player2_id], backref='matches_as_p2')
    winner = db.relationship('User', foreign_keys=[winner_id])
