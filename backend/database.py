import aiosqlite
from logger import logger

from config import DB_FILE

# -------------------- DB Initialization --------------------

async def initialize_db():
    """Initialize the database and create tables if needed."""
    async with aiosqlite.connect(DB_FILE) as db_conn:
        # Conversation table
        await db_conn.execute('''
            CREATE TABLE IF NOT EXISTS conversation (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                session_id TEXT,
                transcription TEXT,
                ai_response TEXT
            )
        ''')
        # Face analysis table
        await db_conn.execute('''
            CREATE TABLE IF NOT EXISTS face_analysis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                session_id TEXT,
                face_file_name TEXT,
                face_emotions TEXT
            )
        ''')
        await db_conn.commit()
        logger.info("Database initialized (conversation & face_analysis tables exist).")
