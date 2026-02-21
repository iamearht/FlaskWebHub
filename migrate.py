import os
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
        # FIX jackpot_pools.status TYPE (VARCHAR -> SMALLINT)
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
        # ENSURE is_spectatable EXISTS ON match
        # ------------------------------------------------------------------

        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name='match'
                AND column_name='is_spectatable'
            ) THEN
                ALTER TABLE match
                ADD COLUMN is_spectatable BOOLEAN DEFAULT TRUE;
            END IF;
        END $$;
        """,

        # ------------------------------------------------------------------
        # ENSURE game_mode EXISTS ON match
        # ------------------------------------------------------------------

        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name='match'
                AND column_name='game_mode'
            ) THEN
                ALTER TABLE match
                ADD COLUMN game_mode VARCHAR(50) DEFAULT 'classic';
            END IF;
        END $$;
        """,

        # ------------------------------------------------------------------
        # ENSURE winner_id EXISTS ON match
        # ------------------------------------------------------------------

        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name='match'
                AND column_name='winner_id'
            ) THEN
                ALTER TABLE match
                ADD COLUMN winner_id INTEGER;
            END IF;
        END $$;
        """,

        # ------------------------------------------------------------------
        # ENSURE match_state TABLE EXISTS
        # ------------------------------------------------------------------

        """
        CREATE TABLE IF NOT EXISTS match_state (
            id SERIAL PRIMARY KEY,
            match_id INTEGER NOT NULL,
            phase VARCHAR(50),
            is_heads_up BOOLEAN DEFAULT FALSE,
            draw_deck_pos INTEGER DEFAULT 0,
            draw_winner INTEGER,
            chooser INTEGER,
            choice_made BOOLEAN DEFAULT FALSE,
            draw_timestamp DOUBLE PRECISION,
            current_turn INTEGER DEFAULT 0,
            match_over BOOLEAN DEFAULT FALSE,
            match_result_winner INTEGER,
            match_result_reason VARCHAR(255)
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
