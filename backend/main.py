import os
import hashlib
import asyncio
import datetime
import aiosqlite
import aiohttp
import aiofiles
import logging
from aiohttp import web
from pydub import AudioSegment
from pydub.silence import detect_silence as pydub_detect_silence
from env_keys import get_openai_api_key, get_hume_api_key
from hume import AsyncHumeClient
from hume.expression_measurement.stream import Config as HumeConfig
from hume.expression_measurement.stream.socket_client import StreamConnectOptions
import openai
from openai import OpenAI

# Configuration Constants
UPLOAD_DIR = "uploaded_audio"
PROCESSED_DIR = "processed_audio"
DB_FILE = "users.db"
OPENAI_API_KEY = get_openai_api_key()
HUME_API_KEY = get_hume_api_key()
openai.api_key = OPENAI_API_KEY
SESSION_TIMEOUT = 30  # Seconds of silence before ending a session
MAX_FILE_SIZE_MB = 25  # Maximum file size allowed for transcription
MIN_AUDIO_DURATION_MS = 1000  # Minimum duration to accept an audio file (in milliseconds)

# Silence detection settings
SILENCE_THRESHOLD = -35  # Adjusted threshold to filter background noise
MIN_SILENCE_LEN = 4000   # Minimum duration of silence in milliseconds

# Hume Streaming settings
HUME_STREAM_WINDOW_MS = 5000  # 5 seconds limit

# Set up logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ensure directories exist
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(PROCESSED_DIR, exist_ok=True)

# Global variables for session management
silence_counter = 0
processed_hashes = set()
db_connection = None
audio_file_counter = 0  # Added global counter for audio files

# -------------------- Initialization and Cleanup --------------------

async def initialize_db():
    """Initialize the database and create tables if needed."""
    async with aiosqlite.connect(DB_FILE) as db_connection:
        await db_connection.execute('''
            CREATE TABLE IF NOT EXISTS audio_analysis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                session_id TEXT,
                audio_file_name TEXT,
                emotion_analysis TEXT
            )
        ''')
        await db_connection.execute('''
            CREATE TABLE IF NOT EXISTS conversation (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                session_id TEXT,
                transcription TEXT,
                ai_response TEXT
            )
        ''')
        await db_connection.commit()
        logger.info("Database initialized and tables created if they didn't exist.")


async def close_db_connection(app):
    """Close the database connection on application shutdown."""
    if db_connection:
        await db_connection.close()
        logger.info("Database connection closed.")


# -------------------- Session Management --------------------

async def get_last_session_id(db_connection):
    """Retrieves the last session ID from the users table."""
    async with db_connection.execute("SELECT session_id FROM users ORDER BY login_timestamp DESC LIMIT 1") as cursor:
        result = await cursor.fetchone()
        session_id = result[0] if result else None
        logger.info(f"Retrieved session ID: {session_id}")
        return session_id


# -------------------- Audio Handling --------------------

async def handle_audio_upload(request):
    """Handles incoming audio uploads and initiates asynchronous processing."""
    global audio_file_counter
    reader = await request.multipart()
    field = await reader.next()

    # Generate unique filename
    audio_file_counter += 1
    base_filename = f"audio_{audio_file_counter}"
    filename = f"{base_filename}.webm"
    save_path = os.path.join(UPLOAD_DIR, filename)

    # Save uploaded audio file asynchronously
    async with aiofiles.open(save_path, 'wb') as f:
        while True:
            chunk = await field.read_chunk()
            if not chunk:
                break
            await f.write(chunk)

    logger.info(f"Audio file uploaded: {save_path}")

    # Process audio file
    asyncio.create_task(process_uploaded_audio(save_path, base_filename))
    return web.Response(text="Audio uploaded successfully")

# -------------------- Duplicate Check --------------------

async def is_duplicate_audio(file_path):
    """Checks if the uploaded audio file is a duplicate based on its content hash."""
    async with aiofiles.open(file_path, 'rb') as f:
        file_data = await f.read()
        audio_hash = hashlib.md5(file_data).hexdigest()

    if audio_hash in processed_hashes:
        logger.info(f"Duplicate audio detected: {file_path}")
        return True
    processed_hashes.add(audio_hash)
    return False

# -------------------- Audio Processing --------------------

async def process_uploaded_audio(file_path, base_filename):
    global silence_counter
    try:
        # Create a new database connection for this task
        async with aiosqlite.connect(DB_FILE) as db_connection:
            # Get the session ID
            session_id = await get_last_session_id(db_connection)
            if not session_id:
                logger.error("No session ID found. Cannot process audio.")
                return

            if await is_duplicate_audio(file_path):
                await asyncio.to_thread(os.remove, file_path)
                logger.info(f"Removed duplicate audio file: {file_path}")
                return

            # Convert audio to WAV format
            wav_file_path = await convert_to_wav(file_path, base_filename)

            # Split audio into 5-second chunks
            chunk_files = await split_audio_into_chunks(wav_file_path, base_filename, session_id)

            valid_chunk_files = []

            # Analyze emotions per chunk
            for chunk_file in chunk_files:
                # Check for file duration before processing
                audio = AudioSegment.from_file(chunk_file)
                duration = len(audio)
                logger.info(f"Audio chunk duration: {duration} ms")

                if duration < MIN_AUDIO_DURATION_MS:
                    logger.info(f"Audio chunk {chunk_file} is too short ({duration} ms); skipping.")
                    await asyncio.to_thread(os.remove, chunk_file)
                    continue

                silence_detected = await detect_silence(chunk_file)
                if silence_detected:
                    logger.info(f"Silence detected in chunk: {chunk_file}")
                    silence_counter += 1
                    if silence_counter == 2:
                        await handle_conversation_starter(session_id)
                        silence_counter = 0
                    await asyncio.to_thread(os.remove, chunk_file)
                    continue
                else:
                    silence_counter = 0
                    valid_chunk_files.append(chunk_file)
                    # Analyze emotions
                    emotions = await analyze_voice_emotions(chunk_file)
                    # Get top 5 emotions
                    top_emotions = get_top_emotions(emotions)
                    # Save data to database
                    await save_audio_analysis_data(db_connection, session_id, os.path.basename(chunk_file), top_emotions)

            # Combine valid chunks
            if valid_chunk_files:
                combined_audio_file = await combine_audio_chunks(valid_chunk_files, base_filename)
                # Transcribe combined audio
                transcription = await transcribe_audio(combined_audio_file)
                # Only proceed if transcription is not empty
                if transcription:
                    # Generate AI response
                    ai_response = await generate_openai_response(transcription)
                    # Save conversation data if AI response is not empty
                    if ai_response:
                        await save_conversation_data(db_connection, session_id, transcription, ai_response)
                        logger.info(f"AI response generated and saved to database.")
                    else:
                        logger.error("AI response was empty. Conversation data not saved.")
                else:
                    logger.error("Transcription was empty. Skipping AI response generation.")

                # Remove combined audio file
                await asyncio.to_thread(os.remove, combined_audio_file)
                logger.info(f"Removed combined audio file: {combined_audio_file}")

            # Remove processed chunk files
            for chunk_file in valid_chunk_files:
                await asyncio.to_thread(os.remove, chunk_file)
                logger.info(f"Removed processed chunk file: {chunk_file}")

            # Remove the original uploaded file and wav file after processing
            try:
                await asyncio.to_thread(os.remove, file_path)
                logger.info(f"Removed uploaded audio file: {file_path}")
                await asyncio.to_thread(os.remove, wav_file_path)
                logger.info(f"Removed WAV audio file: {wav_file_path}")
            except Exception as e:
                logger.error(f"Error deleting file {file_path} or {wav_file_path}: {e}")

    except Exception as e:
        logger.error(f"Error processing audio: {e}")

# -------------------- Audio Combination --------------------

async def combine_audio_chunks(chunk_files, base_filename):
    """Combines audio chunks into a single audio file."""
    combined = AudioSegment.empty()
    for chunk_file in chunk_files:
        audio = AudioSegment.from_file(chunk_file)
        combined += audio
    combined_filename = os.path.join(PROCESSED_DIR, f"{base_filename}_combined.wav")
    combined.export(combined_filename, format='wav')
    logger.info(f"Combined audio chunks into: {combined_filename}")
    return combined_filename

# -------------------- Audio Conversion --------------------

async def convert_to_wav(file_path, base_filename):
    """Converts the uploaded audio file to WAV format using pydub."""
    def process():
        audio = AudioSegment.from_file(file_path)
        wav_filename = f"{base_filename}.wav"
        wav_file_path = os.path.join(PROCESSED_DIR, wav_filename)
        audio.export(wav_file_path, format='wav')
        return wav_file_path
    wav_file_path = await asyncio.to_thread(process)
    logger.info(f"Converted to WAV: {wav_file_path}")
    return wav_file_path

# -------------------- Audio Splitting --------------------

async def split_audio_into_chunks(file_path, base_filename, session_id):
    """Splits audio file into 5-second chunks and returns a list of chunk file paths."""
    audio = AudioSegment.from_file(file_path)
    chunks = []
    num_chunks = (len(audio) + HUME_STREAM_WINDOW_MS - 1) // HUME_STREAM_WINDOW_MS
    for idx in range(num_chunks):
        start_ms = idx * HUME_STREAM_WINDOW_MS
        end_ms = min((idx + 1) * HUME_STREAM_WINDOW_MS, len(audio))
        chunk = audio[start_ms:end_ms]
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        chunk_filename = os.path.join(
            PROCESSED_DIR,
            f"{base_filename}_session_{session_id}_chunk_{idx}_{timestamp}.wav"
        )
        chunk.export(chunk_filename, format='wav')
        chunks.append(chunk_filename)
        logger.info(f"Created audio chunk: {chunk_filename}")
    return chunks


# -------------------- Silence Detection --------------------

async def detect_silence(file_path):
    """Detects silence in the uploaded audio file with adjusted threshold."""
    def process():
        audio = AudioSegment.from_file(file_path, format="wav")
        silence_thresholds = pydub_detect_silence(
            audio, min_silence_len=MIN_SILENCE_LEN, silence_thresh=SILENCE_THRESHOLD
        )
        return len(silence_thresholds) > 0
    is_silent = await asyncio.to_thread(process)
    logger.info(f"Silence detected in {file_path}: {is_silent}")
    return is_silent

# -------------------- Hume Emotion Analysis --------------------

async def analyze_voice_emotions(file_path):
    """Analyzes voice emotions using Hume's Streaming API and returns the emotions."""
    client = AsyncHumeClient(api_key=HUME_API_KEY)
    model_config = HumeConfig(prosody={})
    stream_options = StreamConnectOptions(config=model_config)

    try:
        async with client.expression_measurement.stream.connect(options=stream_options) as socket:
            logger.info(f"Connected to Hume Streaming API for file: {file_path}")
            result = await socket.send_file(file_path)
            logger.info(f"Hume Streaming result received for file: {file_path}")

            # Parse the result and extract emotions
            emotions = []
            if result and result.prosody and result.prosody.predictions:
                for prosody_prediction in result.prosody.predictions:
                    if prosody_prediction.emotions:
                        for emotion_data in prosody_prediction.emotions:
                            emotion_name = emotion_data.name
                            score = emotion_data.score
                            emotions.append({'emotion': emotion_name, 'score': score})
            if emotions:
                top_emotions = get_top_emotions(emotions)
                logger.info(f"Top emotions for {file_path}: {top_emotions}")
                return emotions
            else:
                logger.warning(f"No emotions found in Hume result for file: {file_path}")
                return []
    except Exception as e:
        logger.error(f"Error during Hume emotion analysis: {e}")
        return []

# -------------------- Transcription Function --------------------

async def transcribe_audio(audio_file_path):
    """Transcribes the audio file using OpenAI's Whisper API and returns the text."""
    try:
        url = 'https://api.openai.com/v1/audio/transcriptions'
        headers = {
            'Authorization': f'Bearer {OPENAI_API_KEY}',
        }
        form_data = aiohttp.FormData()
        async with aiofiles.open(audio_file_path, 'rb') as f:
            audio_data = await f.read()
            form_data.add_field('file', audio_data, filename=os.path.basename(audio_file_path), content_type='audio/wav')
        form_data.add_field('model', 'whisper-1')
        form_data.add_field('response_format', 'text')

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, data=form_data) as response:
                if response.status == 200:
                    transcription = await response.text()
                    logger.info(f"Transcription successful for file: {audio_file_path}")
                    return transcription.strip()
                else:
                    error_text = await response.text()
                    logger.error(f"Error during transcription: {response.status}, {error_text}")
                    return ""
    except Exception as e:
        logger.error(f"Error during transcription of {audio_file_path}: {e}")
        return ""


# -------------------- Conversation Management --------------------

async def handle_conversation_starter(session_id):
    """Initializes a conversation if two consecutive silent files are detected."""
    async with aiosqlite.connect(DB_FILE) as db_connection:
        face_emotions = await retrieve_face_emotions(db_connection)
        prompt = f"Start a conversation based on these emotions: {face_emotions}"
        response = await generate_openai_response(prompt)
        await save_conversation_data(db_connection, session_id, "Conversation Starter", response)
        logger.info(f"Conversation starter generated: {response}")


def get_top_emotions(emotions):
    """Extracts the top 5 emotions from the emotions list."""
    if emotions:
        # Emotions is a list of dicts with 'emotion' and 'score'
        # Sort by score
        sorted_emotions = sorted(emotions, key=lambda x: x['score'], reverse=True)
        top_5 = sorted_emotions[:5]
        return top_5
    else:
        return []

# -------------------- OpenAI Completion --------------------\
async def generate_openai_response(prompt):
    try:
        # For streaming response
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
        response = completion.choices[0].message
        logger.info("OpenAI response generated successfully.")
        return response.strip()
    except Exception as e:
        logger.error(f"Error generating OpenAI response: {e}")
        return ""

# -------------------- Database Operations --------------------

async def save_audio_analysis_data(db_connection, session_id, audio_file_name, emotions):
    timestamp = datetime.datetime.now().isoformat()
    emotion_analysis = ', '.join(f"{e['emotion']}: {e['score']:.2f}" for e in emotions)
    await db_connection.execute(
        "INSERT INTO audio_analysis (timestamp, session_id, audio_file_name, emotion_analysis) VALUES (?, ?, ?, ?)",
        (timestamp, session_id, audio_file_name, emotion_analysis)
    )
    await db_connection.commit()
    logger.info(f"Audio analysis data saved to database for {audio_file_name}.")


async def save_conversation_data(db_connection, session_id, transcription, ai_response):
    timestamp = datetime.datetime.now().isoformat()
    await db_connection.execute(
        "INSERT INTO conversation (timestamp, session_id, transcription, ai_response) VALUES (?, ?, ?, ?)",
        (timestamp, session_id, transcription, ai_response)
    )
    await db_connection.commit()
    logger.info("Conversation data saved to database.")


async def retrieve_face_emotions(db_connection):
    async with db_connection.execute("SELECT initial_mood FROM users ORDER BY login_timestamp DESC LIMIT 1") as cursor:
        result = await cursor.fetchone()
        face_emotions = result[0] if result else "Neutral"
        logger.info(f"Retrieved face emotions: {face_emotions}")
        return face_emotions


# -------------------- Application Startup --------------------

async def init_app():
    await initialize_db()
    app = web.Application()
    app.router.add_post("/upload_audio", handle_audio_upload)
    return app


if __name__ == "__main__":
    web.run_app(init_app(), port=8000)
