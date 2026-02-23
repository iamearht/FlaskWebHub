import os
import logging

from flask import Flask, request, abort
from extensions import db, login_manager

from auth import auth_bp, get_current_user
from game import game_bp
from wallet import wallet_bp
from account import account_bp
from tournament import tournament_bp
from affiliate import affiliate_bp
from admin import admin_bp
from jackpot import jackpot_bp


def _normalize_database_url(url: str) -> str:
    """
    Heroku-style DATABASE_URL historically used 'postgres://', which SQLAlchemy
    expects as 'postgresql://'. Normalize if needed.
    """
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://") :]
    return url


def create_app() -> Flask:
    app = Flask(__name__)

    # ---------------------------------------------------
    # LOGGING
    # ---------------------------------------------------
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(level=getattr(logging, log_level, logging.INFO))
    app.logger.setLevel(getattr(logging, log_level, logging.INFO))

    # ---------------------------------------------------
    # BASIC CONFIG
    # ---------------------------------------------------
    app.config["SECRET_KEY"] = os.environ.get("SESSION_SECRET", "dev-fallback-key")

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set")

    app.config["SQLALCHEMY_DATABASE_URI"] = _normalize_database_url(database_url)
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_recycle": int(os.environ.get("DB_POOL_RECYCLE", "280")),
        "pool_pre_ping": True,
    }

    # Disable static caching (helpful for rapid iteration)
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

    # ---------------------------------------------------
    # INIT EXTENSIONS
    # ---------------------------------------------------
    db.init_app(app)

    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    from models import User  # local import to avoid circulars

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
    # DB INIT + AUTO PROMOTE ADMIN
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
                app.logger.warning("IAMEARTH promoted to admin.")
        except Exception as e:
            # Don't crash boot if you prefer resilience; if you want strict boot, re-raise.
            app.logger.exception("Startup error during db init: %s", e)

    # ---------------------------------------------------
    # ROOT ENTRY
    # ---------------------------------------------------
    @app.route("/")
    def home():
        return "OK", 200

    # ---------------------------------------------------
    # HEALTH CHECK
    # ---------------------------------------------------
    @app.route("/health")
    def health_check():
        return "ok", 200

    # ---------------------------------------------------
    # CRON CLEANUP ENDPOINT
    #
    # IMPORTANT:
    # - Do NOT run commit-at-end logic based on check_timeout() loops.
    # - apply_timeout() is designed to be idempotent and safe to call repeatedly.
    # - We use a loop guard to prevent infinite loops if a phase handler misbehaves.
    # ---------------------------------------------------
    @app.route("/internal/cleanup")
    def internal_cleanup():
        cron_secret = os.environ.get("CRON_SECRET")
        provided = request.headers.get("X-CRON-KEY")

        if not cron_secret or provided != cron_secret:
            abort(403)

        from models import Match
        from engine import apply_timeout  # apply_timeout already checks timer internally

        active_matches = Match.query.filter(Match.status == "active").all()

        any_changed = False
        for match in active_matches:
            loop_guard = 0

            # Keep applying timeouts as long as state advances.
            # This allows chained transitions (e.g., ROUND_RESULT -> WAITING_BETS).
            while True:
                changed = apply_timeout(match)
                if not changed:
                    break

                any_changed = True
                loop_guard += 1
                if loop_guard > 50:
                    app.logger.error(
                        "Timeout loop guard hit for match_id=%s phase=%s",
                        getattr(match, "id", None),
                        getattr(getattr(match, "match_state", None), "phase", None),
                    )
                    break

        # Commit once per cleanup run (avoid extra churn).
        if any_changed:
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                app.logger.exception("Cleanup commit failed; rolled back.")
                abort(500)

        return "cleanup complete", 200

    # ---------------------------------------------------
    # TEMPLATE CONTEXT
    # ---------------------------------------------------
    @app.context_processor
    def inject_user():
        return dict(get_current_user=get_current_user)

    # ---------------------------------------------------
    # DISABLE CACHING
    # ---------------------------------------------------
    @app.after_request
    def add_header(response):
        response.headers["Cache-Control"] = (
            "no-store, no-cache, must-revalidate, max-age=0"
        )
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    # ---------------------------------------------------
    # SESSION CLEANUP (helps avoid stale sessions in long-running workers)
    # ---------------------------------------------------
    @app.teardown_appcontext
    def shutdown_session(exception=None):
        try:
            if exception:
                db.session.rollback()
        finally:
            db.session.remove()

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))
