import os
from app import create_app
from models import db


def migrate():
    app = create_app()

    with app.app_context():
        migrations = [
            # USERS
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS email VARCHAR(120)",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS affiliate_code VARCHAR(20)",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS referred_by_id INTEGER REFERENCES users(id)",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE",

            # MATCHES
            "ALTER TABLE matches ADD COLUMN IF NOT EXISTS is_spectatable BOOLEAN DEFAULT TRUE",
            "ALTER TABLE matches ADD COLUMN IF NOT EXISTS tournament_match_id INTEGER",
            "ALTER TABLE matches ADD COLUMN IF NOT EXISTS rake_amount INTEGER DEFAULT 0",
            "ALTER TABLE matches ADD COLUMN IF NOT EXISTS game_mode VARCHAR(30) DEFAULT 'classic'",

            # TOURNAMENTS
            "ALTER TABLE tournaments ADD COLUMN IF NOT EXISTS max_players INTEGER DEFAULT 8",
            "ALTER TABLE tournaments ADD COLUMN IF NOT EXISTS rake_amount INTEGER DEFAULT 0",
            "ALTER TABLE tournaments ADD COLUMN IF NOT EXISTS game_mode VARCHAR(30) DEFAULT 'classic'",
        ]

        for sql in migrations:
            try:
                db.session.execute(db.text(sql))
            except Exception as e:
                print(f"Migration note: {e}")
                db.session.rollback()
                continue

        db.session.commit()

        # Ensure tables exist
        db.create_all()

        # Backfill affiliate codes
        from models import User
        users = User.query.filter(User.affiliate_code.is_(None)).all()

        for user in users:
            user.ensure_affiliate_code()

        db.session.commit()

        print(f"Migration complete. Updated {len(users)} users with affiliate codes.")


if __name__ == "__main__":
    migrate()
