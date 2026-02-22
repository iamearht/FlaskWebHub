import os
import time

from flask import Flask
from extensions import db, login_manager

from auth import auth_bp, get_current_user
from game import game_bp
from wallet import wallet_bp
from account import account_bp
from tournament import tournament_bp
from affiliate import affiliate_bp
from admin import admin_bp
from jackpot import jackpot_bp

# 🔥 NEW IMPORTS FOR AUTO PROGRESSION
from models import Match
from engine import check_timeout, apply_timeout


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

    # ---------------------------------------------------
    # INIT EXTENSIONS
    # ---------------------------------------------------
    db.init_app(app)

    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    from models import User

    @login_manager.user_loader
    def load_user(user_id):
        try:
            return User.query.get(int(user_id))
        except Exception:
            return None

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
    # AUTO-PROGRESS STALE MATCHES
    # ---------------------------------------------------
    @app.before_request
    def auto_progress_stale_matches():
        """
        Ensures matches continue progressing even if both
        players disconnect.

        Runs synchronously on every request.
        """

        try:
            now = int(time.time())

            # ⚡ IMPORTANT:
            # Only load active matches.
            # Do NOT scan finished or waiting matches.
            active_matches = (
                Match.query
                .filter(Match.status == "active")
                .limit(50)  # safety cap per request
                .all()
            )

            updated = False

            for match in active_matches:
                # Drain ALL expired transitions
                loop_guard = 0
                while check_timeout(match):
                    apply_timeout(match)
                    updated = True

                    loop_guard += 1
                    if loop_guard > 20:
                        # Absolute safety guard against misconfigured engine logic
                        break

            if updated:
                db.session.commit()

        except Exception as e:
            # Never break the request pipeline
            print("Auto-progress error:", e)
            db.session.rollback()

    # ---------------------------------------------------
    # CREATE TABLES + AUTO PROMOTE ADMIN
    # ---------------------------------------------------
    with app.app_context():
        try:
            db.create_all()

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
    # ROOT ENTRY (Render health probe safe)
    # ---------------------------------------------------
    @app.route("/")
    def home():
        return "OK", 200

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
