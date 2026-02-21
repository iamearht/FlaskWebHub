import os

from flask import Flask
from extensions import db
from models import db

from auth import auth_bp, get_current_user
from game import game_bp
from wallet import wallet_bp
from account import account_bp
from tournament import tournament_bp
from affiliate import affiliate_bp
from admin import admin_bp
from jackpot import jackpot_bp


def create_app():
    app = Flask(__name__)

    # ---------------------------------------------------
    # TEST ROOT ROUTE
    # ---------------------------------------------------
    @app.route("/")
    def test_home():
        return "HOME WORKING"

    # ---------------------------------------------------
    # BASIC CONFIG
    # ---------------------------------------------------
    app.config['SECRET_KEY'] = os.environ.get('SESSION_SECRET', 'dev-fallback-key')

    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set")

    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_recycle': 280,
        'pool_pre_ping': True,
    }

    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

    db.init_app(app)

    # ---------------------------------------------------
    # BLUEPRINTS
    # ---------------------------------------------------
    app.register_blueprint(auth_bp)
    app.register_blueprint(game_bp)
    app.register_blueprint(wallet_bp)
    app.register_blueprint(account_bp)
    app.register_blueprint(tournament_bp)
    app.register_blueprint(affiliate_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(jackpot_bp)

    # ---------------------------------------------------
    # CONTEXT
    # ---------------------------------------------------
    @app.context_processor
    def inject_user():
        return dict(get_current_user=get_current_user)

    # ---------------------------------------------------
    # DISABLE CACHE
    # ---------------------------------------------------
    @app.after_request
    def add_header(response):
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response

    # ---------------------------------------------------
    # HEALTH CHECK
    # ---------------------------------------------------
    @app.route('/health')
    def health_check():
        return 'ok', 200

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
