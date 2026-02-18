import os
from flask import Flask
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
    app.config['SECRET_KEY'] = os.environ.get('SESSION_SECRET', 'dev-fallback-key')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_recycle': 280,
        'pool_pre_ping': True,
    }
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

    db.init_app(app)

    app.register_blueprint(auth_bp)
    app.register_blueprint(game_bp)
    app.register_blueprint(wallet_bp)
    app.register_blueprint(account_bp)
    app.register_blueprint(tournament_bp)
    app.register_blueprint(affiliate_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(jackpot_bp)

    @app.context_processor
    def inject_user():
        return dict(get_current_user=get_current_user)

    @app.context_processor
    def inject_known_matches():
        from flask import session as flask_session, request as flask_request
        if flask_session.get('user_id'):
            accept = flask_request.headers.get('Accept', '')
            if 'text/html' not in accept:
                return dict(known_match_ids=[])
            from models import Match
            user_id = flask_session['user_id']
            active = Match.query.filter(
                Match.status == 'active',
                db.or_(Match.player1_id == user_id, Match.player2_id == user_id),
            ).with_entities(Match.id).all()
            return dict(known_match_ids=[m.id for m in active])
        return dict(known_match_ids=[])

    with app.app_context():
        db.create_all()
        from models import User
        admin_user = User.query.filter(db.func.lower(User.username) == 'iamearth').first()
        if admin_user and not admin_user.is_admin:
            admin_user.is_admin = True
            db.session.commit()

    @app.after_request
    def add_header(response):
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response

    @app.route('/health')
    def health_check():
        return 'ok', 200

    return app

app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
