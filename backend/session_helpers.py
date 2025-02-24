import aiosqlite
import datetime
from logger import logger

async def get_last_session_id(db_conn):
    """Retrieve the last session ID from the 'users' table."""
    async with db_conn.execute("SELECT session_id FROM users ORDER BY login_timestamp DESC LIMIT 1") as cursor:
        row = await cursor.fetchone()
        session_id = row[0] if row else None
        logger.info(f"Session ID found: {session_id}")
        return session_id

async def retrieve_face_emotions(db_conn):
    """
    Example logic. You might read from 'face_analysis' or 'users' depending on your schema.
    Currently reading from 'users.initial_mood' to keep consistent with older code.
    """
    async with db_conn.execute("SELECT initial_mood FROM users ORDER BY login_timestamp DESC LIMIT 1") as cursor:
        result = await cursor.fetchone()
        mood = result[0] if result else "Neutral"
        logger.info(f"Latest face emotions from DB: {mood}")
        return mood
