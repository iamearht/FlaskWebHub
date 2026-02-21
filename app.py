import os

from flask import Flask, redirect, url_for
from extensions import db

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
    # BASIC CONFIG
    # ---------------------------------------------------
    app.config["SECRET_KEY"] = os.environ.get("SESSION_SECRET", "dev-fallback-key")

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set")

    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_recycle": 280,
        "pool_pre_ping": True,
    }

    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

    db.init_app(app)

    # ---------------------------------------------------
    # REGISTER BLUEPRINTS
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
    # CREATE TABLES + AUTO PROMOTE ADMIN
    # ---------------------------------------------------
    with app.app_context():
        try:
            db.create_all()

            from models import User

            user = User.query.filter(
                db.func.lower(User.username) == "iamearth"
            ).first()

            if user and not user.is_admin:
                user.is_admin = True
                db.session.commit()
                print("IAMEARTH promoted to admin.")

        except Exception as e:
            print("Startup error:", e)

    # ---------------------------------------------------
    # ROOT ENTRY → GAME LOBBY
    # ---------------------------------------------------
    @app.route("/")
    def home():
        return redirect(url_for("game.lobby"))

    # ---------------------------------------------------
    # HEALTH CHECK (Render uses this)
    # ---------------------------------------------------
    @app.route("/health")
    def health_check():
        return "ok", 200

    # ---------------------------------------------------
    # TEMPLATE CONTEXT
    # ---------------------------------------------------
    @app.context_processor
    def inject_user():
        return dict(get_current_user=get_current_user)

    # ---------------------------------------------------
    # DISABLE CACHING (important for live game state)
    # ---------------------------------------------------
    @app.after_request
    def add_header(response):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
