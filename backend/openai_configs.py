import os
import aiofiles
import aiosqlite
import aiohttp
import datetime
from logger import logger
from openai import OpenAI
from env_keys import get_openai_api_key, get_hume_api_key
from config import DB_FILE
from session_helpers import retrieve_face_emotions

OPENAI_API_KEY = get_openai_api_key()
HUME_API_KEY = get_hume_api_key()

async def transcribe_audio(audio_file_path):
    """Use OpenAI Whisper to transcribe. Return text or ''."""
    if not audio_file_path or not os.path.exists(audio_file_path):
        return ""

    try:
        url = 'https://api.openai.com/v1/audio/transcriptions'
        headers = {'Authorization': f'Bearer {OPENAI_API_KEY}'}
        form_data = aiohttp.FormData()
        async with aiofiles.open(audio_file_path, 'rb') as f:
            audio_data = await f.read()
            form_data.add_field('file', audio_data, filename=os.path.basename(audio_file_path), content_type='audio/wav')
        form_data.add_field('model', 'whisper-1')
        form_data.add_field('response_format', 'text')

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, data=form_data) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    logger.info(f"Transcription success: {audio_file_path} => {text.strip()}")
                    return text.strip()
                else:
                    err = await resp.text()
                    logger.error(f"Transcription failed {resp.status}: {err}")
                    return ""
    except Exception as e:
        logger.error(f"Error transcribing {audio_file_path}: {e}")
        return ""

async def generate_openai_response(prompt):
    """Basic GPT call."""
    try:
        client = OpenAI()
        client.api_key = OPENAI_API_KEY
        completion = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=150,
        )
        response_text = completion.choices[0].message.content
        logger.info("OpenAI response generated.")
        return response_text.strip()
    except Exception as e:
        logger.error(f"OpenAI error: {e}")
        return ""


async def handle_conversation_starter(session_id):
    """
    If we detect 2 consecutive silent chunks, create a conversation starter based on face emotions.
    """
    async with aiosqlite.connect(DB_FILE) as db_conn:
        face_emotions = await retrieve_face_emotions(db_conn)
        prompt = f"User has been silent for a while. Face emotions: {face_emotions}. Start a friendly conversation."
        ai_reply = await generate_openai_response(prompt)
        await save_conversation_data(db_conn, session_id, "Conversation Starter", ai_reply)
        logger.info(f"Conversation starter generated: {ai_reply}")


async def save_conversation_data(db_conn, session_id, transcription, ai_response, chunk_range):

    ts = datetime.datetime.now().isoformat()
    await db_conn.execute('''
        INSERT INTO conversation (timestamp, session_id, transcription, ai_response, chunk_range)
        VALUES (?, ?, ?, ?, ?)
    ''', (ts, session_id, transcription, ai_response, str(chunk_range)))
    await db_conn.commit()
    logger.info("Conversation data saved to DB.")

