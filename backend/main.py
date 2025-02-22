import os
import uuid
import hashlib
import asyncio
import datetime
import aiosqlite
import aiohttp
import aiofiles
import logging
import cv2  # For face detection
from aiohttp import web
from pydub import AudioSegment
from pydub.silence import detect_silence as pydub_detect_silence

from env_keys import get_openai_api_key, get_hume_api_key
import openai
from openai import OpenAI
import aiohttp_cors

# For Hume face analysis (image):
from hume import AsyncHumeClient
from hume.expression_measurement.stream import Config
from hume.expression_measurement.stream.socket_client import StreamConnectOptions
from hume.expression_measurement.stream.types import StreamFace

# Configuration Constants
UPLOAD_DIR = "uploaded_audio"
PROCESSED_DIR = "processed_audio"
IMAGE_DIR = "uploaded_images"
DB_FILE = "/Users/Parzon/Downloads/Artificial_Consciousness/InteractiveAvatarNextJSDemo-main/HeyGenPersonalised/users.db"

OPENAI_API_KEY = get_openai_api_key()
HUME_API_KEY = get_hume_api_key()
openai.api_key = OPENAI_API_KEY

SESSION_TIMEOUT = 30           # Not used heavily, but kept
MAX_FILE_SIZE_MB = 25          # Not used in this snippet
MIN_AUDIO_DURATION_MS = 0   # Minimum duration for valid chunk
SILENCE_THRESHOLD = -35        # pydub silence threshold in dB
MIN_SILENCE_LEN = 4000         # Silence must be >= 4s
CHUNK_SIZE_MS = 5000           # We aim for 5-second chunks
IMAGES_PER_BATCH = 40          # Once 40 images have arrived, detect face
AUDIO_FILE_EXT = ".webm"        # We convert all audio to WAV

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ensure directories exist
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(PROCESSED_DIR, exist_ok=True)
os.makedirs(IMAGE_DIR, exist_ok=True)

# Global session & counters
silence_counter = 0
processed_hashes = set()
audio_file_counter = 0
image_file_counter = 0
images_batch_list = []  # We'll collect filenames here until we have 40

# -------------------- DB Initialization --------------------

async def initialize_db():
    """Initialize the database and create tables if needed."""
    async with aiosqlite.connect(DB_FILE) as db_conn:
        # Existing tables
        await db_conn.execute('''
            CREATE TABLE IF NOT EXISTS audio_analysis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                session_id TEXT,
                audio_file_name TEXT,
                emotion_analysis TEXT
            )
        ''')
        await db_conn.execute('''
            CREATE TABLE IF NOT EXISTS conversation (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                session_id TEXT,
                transcription TEXT,
                ai_response TEXT
            )
        ''')
        # New table to store face analysis
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
        logger.info("Database initialized and tables created if needed.")

# -------------------- Session Helpers --------------------

async def get_last_session_id(db_conn):
    """Retrieve the last session ID from users table."""
    async with db_conn.execute("SELECT session_id FROM users ORDER BY login_timestamp DESC LIMIT 1") as cursor:
        row = await cursor.fetchone()
        session_id = row[0] if row else None
        logger.info(f"Session ID found: {session_id}")
        return session_id

async def retrieve_face_emotions(db_conn):
    """
    Example: If you store face emotions in the users table or somewhere else,
    adapt this function. Right now, we just do a minimal approach:
    read from face_analysis or users (depending on your schema).
    """
    # Here we read from 'users' -> 'initial_mood'. You might want to read from face_analysis instead.
    async with db_conn.execute("SELECT initial_mood FROM users ORDER BY login_timestamp DESC LIMIT 1") as cursor:
        result = await cursor.fetchone()
        face_emotions = result[0] if result else "Neutral"
        logger.info(f"Latest face emotions from DB: {face_emotions}")
        return face_emotions

# -------------------- Image Handling --------------------

async def handle_image_upload(request):
    """
    5) "Every time 40 images are captured, run face detection with opencv, pick the best,
       send to Hume for face emotion, store that in DB, and delete the rest."
    """
    global image_file_counter, images_batch_list

    logger.info("📸 Received image upload request...")
    try:
        reader = await request.multipart()
        field = await reader.next()
        if not field or field.name != 'file':
            return web.Response(text="Invalid form field", status=400)

        original_filename = field.filename
        if not original_filename:
            original_filename = f"image_{datetime.datetime.now().timestamp()}.jpg"

        # Force unique name
        unique_name = f"{uuid.uuid4()}_{original_filename}"
        save_path = os.path.join(IMAGE_DIR, unique_name)

        # Save file
        async with aiofiles.open(save_path, "wb") as f:
            while True:
                chunk = await field.read_chunk()
                if not chunk:
                    break
                await f.write(chunk)

        image_file_counter += 1
        images_batch_list.append(save_path)

        logger.info(f"✅ Image saved: {save_path} (count in batch: {len(images_batch_list)})")

        # If we reached 40 images in this batch, run the face detection pipeline
        if len(images_batch_list) >= IMAGES_PER_BATCH:
            logger.info(f"🌟 We have {IMAGES_PER_BATCH} images. Processing face detection now.")
            await process_face_images_batch()

        return web.Response(text=f"✅ Image uploaded: {unique_name}")

    except Exception as e:
        logger.error(f"Image upload error: {str(e)}")
        return web.Response(text=f"❌ Upload failed: {str(e)}", status=500)

async def process_face_images_batch():
    """
    - Use OpenCV to detect a face in each of the 40 images.
    - Choose the image that has the "largest" face (or first face found).
    - Send that one image to Hume for face emotion analysis.
    - Delete all the others.
    - Store the face emotion in DB.
    - Clear images_batch_list.
    """
    global images_batch_list

    if not images_batch_list:
        logger.info("No images to process.")
        return

    # 1) Detect face in each image, track largest bounding box
    best_image_path = None
    best_area = 0

    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    # You can use a more advanced model if you prefer

    for img_path in images_batch_list:
        try:
            img = cv2.imread(img_path)
            if img is None:
                continue
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, 1.3, 5)
            # faces => list of (x, y, w, h)

            if len(faces) > 0:
                # Pick largest face
                (x, y, w, h) = max(faces, key=lambda f: f[2] * f[3])
                area = w * h
                if area > best_area:
                    best_area = area
                    best_image_path = img_path
        except Exception as e:
            logger.error(f"Error reading {img_path} for face detection: {e}")

    if best_image_path is None:
        # No face found in any image
        logger.warning("No face detected in this batch of images. Deleting them all.")
        # Delete all
        for path_ in images_batch_list:
            try:
                os.remove(path_)
            except:
                pass
        images_batch_list.clear()
        return

    # 2) We have a best image
    logger.info(f"Best face found in: {best_image_path} (area={best_area}). Deleting the rest.")
    # 3) Delete all except best_image_path
    for path_ in images_batch_list:
        if path_ != best_image_path:
            try:
                os.remove(path_)
            except:
                pass

    # Clear the list so next batch can start
    images_batch_list.clear()

    # 4) Send best face to Hume for emotion analysis
    face_emotions = await analyze_face_image(best_image_path)
    logger.info(f"Face emotions from Hume: {face_emotions}")

    # 5) Insert into DB
    async with aiosqlite.connect(DB_FILE) as db_conn:
        session_id = await get_last_session_id(db_conn) or "unknown_session"
        timestamp = datetime.datetime.now().isoformat()
        face_file_name = os.path.basename(best_image_path)
        face_emotions_str = ", ".join(f"{k}: {v:.2f}" for k, v in face_emotions.items())

        await db_conn.execute(
            "INSERT INTO face_analysis (timestamp, session_id, face_file_name, face_emotions) VALUES (?, ?, ?, ?)",
            (timestamp, session_id, face_file_name, face_emotions_str)
        )
        await db_conn.commit()
        logger.info(f"Face analysis saved: {face_file_name} => {face_emotions_str}")

# -------------------- Hume Face Analysis for Images --------------------

async def analyze_face_image(image_path: str) -> dict:
    """
    Calls Hume's streaming API for face analysis.
    Returns a dict of {emotion_name: score, ...}
    """
    try:
        client = AsyncHumeClient(api_key=get_hume_api_key())
        model_config = Config(face=StreamFace())
        stream_options = StreamConnectOptions(config=model_config)

        async with client.expression_measurement.stream.connect(options=stream_options) as socket:
            encoded_image = encode_image(image_path)
            result = await socket.send_file(encoded_image)

            face_predictions = result.face.predictions if result.face else None
            if not face_predictions:
                logger.warning("❌ No face detected in image.")
                return {}

            emotions_sorted = sorted(face_predictions[0].emotions, key=lambda e: e.score, reverse=True)
            emotions_dict = {e.name: e.score for e in emotions_sorted}

            logger.info("✅ Emotions extracted successfully.")
            return emotions_dict
    
    except Exception as e:
        logger.error(f"❌ Error analyzing face image with Hume: {e}")
        return {}
    
# -------------------- Audio Handling --------------------

async def handle_audio_upload(request):
    """
    Receives .webm audio, saves it, then processes in the background.
    """
    global audio_file_counter
    reader = await request.multipart()
    field = await reader.next()
    if not field:
        return web.Response(text="No audio file found", status=400)

    audio_file_counter += 1
    base_filename = f"audio_{audio_file_counter}"
    filename = base_filename + AUDIO_FILE_EXT
    save_path = os.path.join(UPLOAD_DIR, filename)

    # Save
    async with aiofiles.open(save_path, 'wb') as f:
        while True:
            chunk = await field.read_chunk()
            if not chunk:
                break
            await f.write(chunk)

    logger.info(f"Audio file uploaded: {save_path}")
    asyncio.create_task(process_uploaded_audio(save_path, base_filename))
    return web.Response(text="Audio uploaded successfully")

# -------------------- Audio Processing --------------------

async def process_uploaded_audio(file_path, base_filename):
    """
    1) If chunk < 5 seconds, combine it with next chunk.
    2) Don't delete any audio.
    3) If silence for more than 2 consecutive chunks => conversation starter.
    4) If silence for 1 chunk => transcribe that chunk, combine with face emotions => generate friendly response.
    5) No "Hume audio" analysis on the fly => removed.
    6) Everything stored in DB, keyed by session ID.
    """
    global silence_counter

    try:
        async with aiosqlite.connect(DB_FILE) as db_conn:
            session_id = await get_last_session_id(db_conn)
            if not session_id:
                logger.error("No session ID found in 'users'. Cannot process audio.")
                return

            # 1) Duplicate check
            if await is_duplicate_audio(file_path):
                logger.info(f"Skipping duplicate audio: {file_path}")
                return

            # 2) Convert to WAV
            wav_path = await convert_to_wav(file_path, base_filename)

            # 3) Split into 5-second chunks
            chunk_files = await split_audio_into_chunks(wav_path, base_filename, session_id)
            # We'll do a "combine short chunk" step for any chunk < 5000 ms
            chunk_files = await combine_short_chunks(chunk_files, base_filename, session_id)

            # 4) For each chunk, check if silent
            valid_chunks = []
            for chunk_f in chunk_files:
                duration_ms = len(AudioSegment.from_file(chunk_f))
                if duration_ms < MIN_AUDIO_DURATION_MS:
                    logger.info(f"Skipping tiny chunk <1s: {chunk_f}")
                    continue

                # Silence detection
                is_silent_chunk = await detect_silence(chunk_f)
                if is_silent_chunk:
                    silence_counter += 1
                    logger.info(f"Silence in chunk: {chunk_f}. silent_count={silence_counter}")

                    # 5) If silence for 1 chunk => transcribe + face emotions => friendly response
                    #    We do that now, for the single chunk
                    transcription = await transcribe_audio(chunk_f)
                    if transcription:
                        face_emotions = await retrieve_face_emotions(db_conn)
                        # Build prompt
                        prompt = (
                            f"The user was silent. The face emotions are: {face_emotions}.\n"
                            f"User's last transcript: {transcription}\n"
                            "Please generate a friendly, helpful response."
                        )
                        ai_response = await generate_openai_response(prompt)
                        if ai_response:
                            await save_conversation_data(db_conn, session_id, transcription, ai_response)

                    # 6) If silence_counter == 2 => conversation starter
                    if silence_counter == 2:
                        await handle_conversation_starter(session_id)
                        silence_counter = 0
                else:
                    silence_counter = 0
                    # Non-silent chunk => store in valid_chunks for combining/transcription
                    valid_chunks.append(chunk_f)

            # 7) Combine valid chunks => single file => transcribe => generate normal AI response
            if valid_chunks:
                combined_file = await combine_audio_chunks(valid_chunks, base_filename)
                transcribed_text = await transcribe_audio(combined_file)
                if transcribed_text:
                    # Provide a normal flow prompt, or store direct?
                    # We'll just do a normal Q->A conversation
                    ai_response = await generate_openai_response(transcribed_text)
                    if ai_response:
                        await save_conversation_data(db_conn, session_id, transcribed_text, ai_response)

            # 8) Do NOT delete any audio (as requested).
            #    So all chunk files, the combined file, and original files remain on disk.

    except Exception as e:
        logger.error(f"Error in process_uploaded_audio: {e}")

# -------------------- Short Chunk Combination (Step #2) --------------------

async def combine_short_chunks(chunk_files, base_filename, session_id):
    """
    If a chunk is < 5 seconds, combine it with the next chunk so we don't discard it.
    We'll produce a new list of chunk_files with no chunk under 5s, except maybe the last.

    This is a simple approach: if chunk i is < 5000 ms, merge it with chunk i+1.
    """
    if not chunk_files:
        return []

    # We'll read them all as AudioSegments, merging the short ones forward
    segments = []
    for cf in chunk_files:
        seg = AudioSegment.from_file(cf)
        segments.append((cf, seg))

    new_chunk_files = []
    i = 0
    while i < len(segments):
        cf, seg = segments[i]
        if len(seg) < CHUNK_SIZE_MS and i < len(segments) - 1:
            # Combine with next
            next_cf, next_seg = segments[i + 1]
            combined_seg = seg + next_seg
            # We need a new chunk file
            out_name = f"{base_filename}_combined_{uuid.uuid4().hex}.wav"
            out_path = os.path.join(PROCESSED_DIR, out_name)
            combined_seg.export(out_path, format='wav')
            logger.info(f"Combined short chunk {cf} + {next_cf} => {out_path}")
            # Replace next with the newly combined
            segments[i + 1] = (out_path, combined_seg)
            # We'll delete the old chunk files, except "don't delete audio" was requested
            # so we skip removing them. We'll keep them. 
            i += 1
        else:
            # Keep as is
            new_chunk_files.append(cf)
            i += 1

    return new_chunk_files

# -------------------- Duplicate Check --------------------

async def is_duplicate_audio(file_path):
    async with aiofiles.open(file_path, 'rb') as f:
        data = await f.read()
        audio_hash = hashlib.md5(data).hexdigest()

    if audio_hash in processed_hashes:
        logger.info(f"Duplicate audio detected: {file_path}")
        return True
    processed_hashes.add(audio_hash)
    return False

# -------------------- Silence Detection --------------------

async def detect_silence(file_path):
    """Return True if chunk is silent by pydub definition."""
    def _check():
        audio = AudioSegment.from_file(file_path, format="wav")
        silences = pydub_detect_silence(
            audio, min_silence_len=MIN_SILENCE_LEN, silence_thresh=SILENCE_THRESHOLD
        )
        return len(silences) > 0

    return await asyncio.to_thread(_check)

# -------------------- Audio Combination --------------------

async def combine_audio_chunks(chunk_files, base_filename):
    combined = AudioSegment.empty()
    for cf in chunk_files:
        seg = AudioSegment.from_file(cf)
        combined += seg
    out_name = f"{base_filename}_all_valid.wav"
    out_path = os.path.join(PROCESSED_DIR, out_name)
    combined.export(out_path, format='wav')
    logger.info(f"Combined valid chunks into {out_path}")
    return out_path

# -------------------- Audio Conversion --------------------

async def convert_to_wav(file_path, base_filename):
    """Converts input (e.g., .webm) to .wav using pydub."""
    def _conv():
        seg = AudioSegment.from_file(file_path)
        wav_name = f"{base_filename}.wav"
        wav_path = os.path.join(PROCESSED_DIR, wav_name)
        seg.export(wav_path, format='wav')
        return wav_path

    wav_path = await asyncio.to_thread(_conv)
    logger.info(f"Converted {file_path} => {wav_path}")
    return wav_path

# -------------------- Audio Splitting --------------------

async def split_audio_into_chunks(file_path, base_filename, session_id):
    """
    Splits the WAV file into 5s chunks. 
    Returns a list of chunk file paths (each ~5s, except maybe the last is shorter).
    """
    audio = AudioSegment.from_file(file_path)
    total_ms = len(audio)
    chunk_files = []
    start_ms = 0
    idx = 0

    while start_ms < total_ms:
        end_ms = min(start_ms + CHUNK_SIZE_MS, total_ms)
        chunk_seg = audio[start_ms:end_ms]
        ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        chunk_name = f"{base_filename}_session_{session_id}_chunk_{idx}_{ts}.wav"
        chunk_path = os.path.join(PROCESSED_DIR, chunk_name)
        chunk_seg.export(chunk_path, format='wav')
        chunk_files.append(chunk_path)
        logger.info(f"Created chunk {chunk_path} (duration={len(chunk_seg)} ms)")
        start_ms += CHUNK_SIZE_MS
        idx += 1

    return chunk_files

# -------------------- Transcription & OpenAI --------------------

async def transcribe_audio(audio_file_path):
    """Use OpenAI Whisper to transcribe. Return text or ''."""
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
                    logger.info(f"Transcription success for {audio_file_path}: {text.strip()}")
                    return text.strip()
                else:
                    err = await resp.text()
                    logger.error(f"Transcription failed: {resp.status} => {err}")
                    return ""
    except Exception as e:
        logger.error(f"Error in transcribe_audio: {e}")
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

# -------------------- Conversation & AI Data --------------------

async def handle_conversation_starter(session_id):
    """
    If we detect 2 consecutive silent chunks, we create a conversation starter
    based on current face emotion (from DB).
    """
    async with aiosqlite.connect(DB_FILE) as db_conn:
        face_emotions = await retrieve_face_emotions(db_conn)
        prompt = f"User has been silent for a while. Face emotions: {face_emotions}. Start a friendly conversation."
        ai_reply = await generate_openai_response(prompt)
        await save_conversation_data(db_conn, session_id, "Conversation Starter", ai_reply)
        logger.info(f"Conversation starter generated: {ai_reply}")

async def save_conversation_data(db_conn, session_id, transcription, ai_response):
    ts = datetime.datetime.now().isoformat()
    await db_conn.execute('''
        INSERT INTO conversation (timestamp, session_id, transcription, ai_response)
        VALUES (?, ?, ?, ?)
    ''', (ts, session_id, transcription, ai_response))
    await db_conn.commit()
    logger.info("Conversation data saved to DB.")

async def save_audio_analysis_data(db_conn, session_id, audio_file_name, emotions):
    """
    NOTE: The user said "remove Hume audio analysis on the fly," 
    so we might not call this. Kept for reference only if needed.
    """
    ts = datetime.datetime.now().isoformat()
    analysis = ', '.join(f"{e['emotion']}: {e['score']:.2f}" for e in emotions)
    await db_conn.execute('''
        INSERT INTO audio_analysis (timestamp, session_id, audio_file_name, emotion_analysis)
        VALUES (?, ?, ?, ?)
    ''', (ts, session_id, audio_file_name, analysis))
    await db_conn.commit()
    logger.info(f"Audio analysis data saved for {audio_file_name}.")

# -------------------- Server Setup --------------------

async def init_app():
    await initialize_db()
    app = web.Application()

    # CORS
    cors = aiohttp_cors.setup(app, defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
            allow_methods="*",
        )
    })

    app.router.add_post("/upload_audio", handle_audio_upload)
    app.router.add_post("/upload_image", handle_image_upload)

    # Enable CORS for all routes
    for route in list(app.router.routes()):
        cors.add(route)

    return app

if __name__ == "__main__":
    web.run_app(init_app(), port=8000)
