import os
from app import create_app
from models import db

def migrate():
    app = create_app()
    with app.app_context():
        migrations = [
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS email VARCHAR(120) UNIQUE",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS affiliate_code VARCHAR(20) UNIQUE",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS referred_by_id INTEGER REFERENCES users(id)",
            "ALTER TABLE matches ADD COLUMN IF NOT EXISTS is_spectatable BOOLEAN DEFAULT TRUE",
            "ALTER TABLE matches ADD COLUMN IF NOT EXISTS tournament_match_id INTEGER",
        ]
        for sql in migrations:
            try:
                db.session.execute(db.text(sql))
            except Exception as e:
                print(f"Migration note: {e}")
                db.session.rollback()
                continue
        db.session.commit()

        db.create_all()

        from models import User
        users = User.query.filter(User.affiliate_code.is_(None)).all()
        for user in users:
            user.ensure_affiliate_code()
        db.session.commit()
        print(f"Migration complete. Updated {len(users)} users with affiliate codes.")

if __name__ == '__main__':
    migrate()
