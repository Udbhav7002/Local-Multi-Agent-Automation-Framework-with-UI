"""
Lightweight database migration runner.
Executes .sql files in order based on user_version.
"""
import glob
import os
import sqlite3

from core.logger import setup_logger

logger = setup_logger("Migrations")

def run_migrations(db_path: str):
    migrations_dir = os.path.dirname(os.path.abspath(__file__))
    sql_files = sorted(glob.glob(os.path.join(migrations_dir, "*.sql")))

    with sqlite3.connect(db_path) as conn:
        version = conn.execute("PRAGMA user_version").fetchone()[0]

        for i, sql_file in enumerate(sql_files, start=1):
            if version < i:
                filename = os.path.basename(sql_file)
                logger.info(f"Applying migration: {filename}")
                try:
                    with open(sql_file) as f:
                        script = f.read()
                    conn.executescript(script)
                    conn.execute(f"PRAGMA user_version = {i}")
                    conn.commit()
                except sqlite3.OperationalError as e:
                    # Ignore duplicate column errors if we are recovering from a bad previous state
                    if "duplicate column name" in str(e).lower():
                        logger.warning(f"Ignoring duplicate column error in {filename}: {e}")
                        conn.execute(f"PRAGMA user_version = {i}")
                        conn.commit()
                    else:
                        raise e
