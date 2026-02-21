from sqlalchemy import text
from extensions import db


def run_migrations():
    """
    Safe idempotent migrations for production.
    Can be run multiple times without breaking.
    """

    print("Running database migrations...")

    migrations = [

        # ------------------------------------------------------------------
        # FIX jackpot_pools.status (VARCHAR -> SMALLINT)
        # ------------------------------------------------------------------

        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name='jackpot_pools'
                AND column_name='status'
                AND data_type='character varying'
            ) THEN
                ALTER TABLE jackpot_pools
                ALTER COLUMN status TYPE SMALLINT
                USING (
                    CASE
                        WHEN status ~ '^\\d+$' THEN status::smallint
                        WHEN lower(status)='inactive' THEN 0
                        WHEN lower(status)='active' THEN 1
                        WHEN lower(status)='paid' THEN 2
                        ELSE 1
                    END
                );
            END IF;
        END $$;
        """,

        """
        ALTER TABLE jackpot_pools
        ALTER COLUMN status SET DEFAULT 1;
        """,

        # ------------------------------------------------------------------
        # FIX matches.status (VARCHAR -> SMALLINT)
        # ------------------------------------------------------------------

        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name='matches'
                AND column_name='status'
                AND data_type='character varying'
            ) THEN
                ALTER TABLE matches
                ALTER COLUMN status TYPE SMALLINT
                USING (
                    CASE
                        WHEN status ~ '^\\d+$' THEN status::smallint
                        WHEN lower(status)='waiting' THEN 0
                        WHEN lower(status)='active' THEN 1
                        WHEN lower(status)='finished' THEN 2
                        ELSE 0
                    END
                );
            END IF;
        END $$;
        """,

        """
        ALTER TABLE matches
        ALTER COLUMN status SET DEFAULT 0;
        """,

        # ------------------------------------------------------------------
        # ENSURE is_spectatable EXISTS ON matches
        # ------------------------------------------------------------------

        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name='matches'
                AND column_name='is_spectatable'
            ) THEN
                ALTER TABLE matches
                ADD COLUMN is_spectatable BOOLEAN DEFAULT TRUE;
            END IF;
        END $$;
        """,

        # ------------------------------------------------------------------
        # ENSURE game_mode EXISTS AND IS SMALLINT
        # ------------------------------------------------------------------

        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name='matches'
                AND column_name='game_mode'
            ) THEN
                ALTER TABLE matches
                ADD COLUMN game_mode SMALLINT DEFAULT 0;

            ELSIF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name='matches'
                AND column_name='game_mode'
                AND data_type='character varying'
            ) THEN
                ALTER TABLE matches
                ALTER COLUMN game_mode TYPE SMALLINT
                USING (
                    CASE
                        WHEN game_mode ~ '^\\d+$' THEN game_mode::smallint
                        WHEN lower(game_mode)='classic' THEN 0
                        WHEN lower(game_mode)='interactive' THEN 1
                        WHEN lower(game_mode)='classic_joker' THEN 2
                        WHEN lower(game_mode)='interactive_joker' THEN 3
                        ELSE 0
                    END
                );
            END IF;
        END $$;
        """,

        # ------------------------------------------------------------------
        # ENSURE winner_id EXISTS ON matches
        # ------------------------------------------------------------------

        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name='matches'
                AND column_name='winner_id'
            ) THEN
                ALTER TABLE matches
                ADD COLUMN winner_id INTEGER;
            END IF;
        END $$;
        """,

        # ------------------------------------------------------------------
        # ENSURE match_state TABLE EXISTS (MATCHES MODEL EXACTLY)
        # ------------------------------------------------------------------

        """
        CREATE TABLE IF NOT EXISTS match_state (
            match_id INTEGER PRIMARY KEY REFERENCES matches(id),

            phase VARCHAR(30) NOT NULL DEFAULT 'CARD_DRAW',
            is_heads_up BOOLEAN NOT NULL DEFAULT FALSE,

            draw_deck_pos SMALLINT NOT NULL DEFAULT 0,
            draw_winner SMALLINT,
            chooser SMALLINT,
            choice_made BOOLEAN NOT NULL DEFAULT FALSE,
            draw_timestamp DOUBLE PRECISION,

            current_turn SMALLINT NOT NULL DEFAULT 0,

            match_over BOOLEAN NOT NULL DEFAULT FALSE,
            match_result_winner SMALLINT,
            match_result_reason VARCHAR(40)
        );
        """,
    ]

    for migration in migrations:
        try:
            db.session.execute(text(migration))
            db.session.commit()
            print("✓ Migration applied")
        except Exception as e:
            db.session.rollback()
            print("Migration skipped or failed safely:", e)

    print("Database migrations complete.")


if __name__ == "__main__":
    from flask import Flask
    import os

    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)

    with app.app_context():
        run_migrations()
