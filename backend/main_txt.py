import os
import aiohttp
import asyncio
import datetime
import openai
import csv
import hashlib
import threading
from aiohttp import web
from pydub import AudioSegment
from pydub.silence import detect_silence as pydub_detect_silence
from env_keys import get_openai_api_key, get_hume_api_key

# Set up upload directory
UPLOAD_DIR = "uploaded_audio"
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

# get current session ID based on nearest time stamp from users.db and create a new table with the session ID to store transcriptions and responses from openai 
# new table name is conversation, it has the following columns: AI message, Human message, sessionID, conversation starter (NUllable). Each row is one full execution. Human to AI and AI to Human messages are stored in the same row.

# Replace this with your actual OpenAI API key retrieval function
OPENAI_API_KEY = get_openai_api_key()
openai.api_key = OPENAI_API_KEY

# Track start time of the session
start_time = datetime.datetime.now()

# Counter for unique naming
counter = 1

# Hashes of processed files to check for duplicates
processed_hashes = set()

# Lock to manage concurrent file writing
write_lock = threading.Lock()

async def upload_audio(request):
    global counter

    reader = await request.multipart()
    field = await reader.next()

    # Generate a unique filename with timestamp and counter
    timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')
    unique_filename = f"audio_{timestamp}_{counter}.wav"
    save_path = os.path.join(UPLOAD_DIR, unique_filename)

    # Write the file to disk using a lock to prevent concurrency issues
    with write_lock:
        with open(save_path, 'wb') as f:
            while True:
                chunk = await field.read_chunk()  # 8192 bytes by default.
                if not chunk:
                    break
                f.write(chunk)

    # Process the audio file and decide whether to keep it
    is_valid = await process_audio(save_path)

    # Increment the counter only if the file is not a duplicate and is valid
    if is_valid:
        counter += 1

    return web.Response(text="Audio uploaded successfully", status=200)

async def process_audio(save_path):
    try:
        print(f"Processing audio file: {save_path}")

        # Load the WAV file using pydub
        try:
            audio = AudioSegment.from_file(save_path, format="wav")
        except Exception as e:
            print(f"Failed to load {save_path}. Error: {e}")
            os.remove(save_path)
            return False

        # Hash the audio content to ensure no duplicates
        audio_hash = hashlib.md5(audio.raw_data).hexdigest()
        if is_duplicate(audio_hash):
            print(f"Duplicate audio detected, deleting: {save_path}")
            os.remove(save_path)
            return False

        # Save the hash to prevent future duplicates
        save_hash(audio_hash)

        # Check for silence
        silence_detected = detect_silence(save_path)
        if silence_detected:
            silent_wav_path = save_path.replace(".wav", "_silence.wav")
            os.rename(save_path, silent_wav_path)
            print(f"Silence detected. Renamed to: {silent_wav_path}")

            # Logic to handle silence detection
            await handle_silence_detection(silent_wav_path)

        else:
            print(f"No extended silence detected in: {save_path}")

        return True

    except Exception as e:
        print(f"Error while processing audio file {save_path if save_path else 'unknown'}: {e}")
        return False

def detect_initial_silence(audio_path):
    # if the first 2 files that have been uploaded are silent, then the conversation will start. loop through the file and count the files with _silence.wav
    # if counter == 2, then start the conversation
    audio_files_dir = '/uploaded_audio'
    audio_files = os.listdir(audio_files_dir)
    for i in audio_files: 
        if '_silence' in i:
            silence_counter += 1
            if silence_counter == 2:
                initial_start_conversation()
            elif silence_counter < 2:
                normal_start_conversation()

def detect_emotions(audio_path):
    # open the audio file and detect emotions using the voice emotion detection model
    # whenever an audio file is detected, send it to the model and get the emotions detected asynchronously
    # store it in a seperate table in the users.db database called emotions along with the session ID, file name,fitimestamp and the detected emotions
    async def analyze_audio(file_path):
        client = AsyncHumeClient(api_key=get_hume_api_key)
        model_config = Config(prosody={})
        stream_options = StreamConnectOptions(config=model_config)
        
        retries = 3
        for attempt in range(retries):
            try:
                async with client.expression_measurement.stream.connect(options=stream_options) as socket:
                    result = await socket.send_file(file_path)
                    if hasattr(result, "prosody"):
                        return result.prosody.predictions
                    else:
                        logger.error(f"Unexpected response type: {type(result)}. Response: {result}")
                        return None
            except Exception as e:
                logger.error(f"Error during audio analysis (attempt {attempt + 1}): {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    logger.error("Exceeded maximum retries for audio analysis.")
                    return None
        

async def inital_start_conversation():
    # send the face emotions here as a converstaion starter from the users table in the users.db database from the inital mood column
    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Bearer {OPENAI_API_KEY}"
            }
            json_data = {
                "model": "gpt-4o",
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": "Say a conversation starter."} #add inital facial mood here adjust prompt to give a response based on the facial mood
                ],
                "max_tokens": 50,
                "n": 1
            }

            async with session.post("https://api.openai.com/v1/chat/completions", headers=headers, json=json_data) as resp:
                response = await resp.json()

                # Extract the response message content
                if response and 'choices' in response and len(response['choices']) > 0:
                    message_content = response['choices'][0]['message']['content']

                    # Save to the SQL Db file users.db in a tabl
                #then start the normal conversation

    except Exception as e:
        print(f"Error while generating conversation starter: {e}")

async def normal_start_conversation():
    # check the audio file path /Users/Parzon/Downloads/Artificial_Consciousness/InteractiveAvatarNextJSDemo-main/HeyGenPersonalised/uploaded_audio
    # if _silence exists in the file name then send to openai
    audio_files_dir = '/uploaded_audio'
    audio_files = os.listdir(audio_files_dir)
    for i+2 in audio_files: # to skip the inital conversation starter
        # collect all the audio files till you find '_silence' in the audio file name, that means user is expecting a response. 
        if '_silence' in i and '_silence' not in i-1: # meaning if the person spoke for 10 seconds, (audio is 5 second chunks) and stayed silent for 5 seconds that one gets tagged as a silence file and we send it to openai but if the next one is also silent, we ignore that one and go to the next not silent one. 
            #merge all the audio files
            #send the audio file to openai
            #transcribe the audio file from openai
            #and save it to the sqllite db table 'conversation' in the column 'Human message'
            #send it to openai for a response along with detected emotions
            from openai import OpenAI
            client = OpenAI()

            audio_file = open("/path/to/file/speech.mp3", "rb")
            transcription = client.audio.transcriptions.create(
            model="whisper-1", 
            file=audio_file, 
            response_format="text"
            )
            print(transcription.text)
            
            #check if file is less than 25mb, if not then split the file into 25mb chunks and send it to openai
 
    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Bearer {OPENAI_API_KEY}"
            }
            json_data = {
                "model": "gpt-4o",
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant."}, #prompt to help elders and be helpful and understanding
                    {"role": "user", "content": "{transcription.text}, {audio_emotions}"} #add emotions from the emotions table depending on the amount of files sent, if more than 5 files have been sent to openai, 5 second chunks, then send those emotions to openai as well. Add a prompt style to add it after the whole transciption but tell the time differneces.
                    # like *whole text* + "there were the change in emotions the person was feeling during the conversation, its in 5 second gaps" + *emotions detected*
                ],
                "max_tokens": 100,
                "n": 1
            }

            async with session.post("https://api.openai.com/v1/chat/completions", headers=headers, json=json_data) as resp:
                response = await resp.json()

                # Extract the response message content
                if response and 'choices' in response and len(response['choices']) > 0:
                    message_content = response['choices'][0]['message']['content']
                    # save this to the sql db table 'conversation' in the column 'AI message'

    except Exception as e:
        print(f"Error while generating conversation starter: {e}")

def save_to_csv(timestamp, speaker, content):
    try:
        with open(CSV_FILE, mode='a', newline='') as file:
            writer = csv.writer(file)
            writer.writerow([timestamp.strftime('%Y-%m-%d %H:%M:%S'), speaker, content])
    except Exception as e:
        print(f"Error while saving to CSV: {e}")

def is_duplicate(audio_hash):
    return audio_hash in processed_hashes

def save_hash(audio_hash):
    processed_hashes.add(audio_hash)

async def init_app():
    # Initialize the web app
    app = web.Application()
    app.router.add_post("/upload_audio", upload_audio)
    return app

if __name__ == "__main__":
    try:
        web.run_app(init_app(), port=8000)
    except Exception as e:
        print(f"Server failed to start: {e}")







#---------------------BEST UPDATE---------------------#
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
from hume.models.config import ProsodyConfig
from hume.models.streaming.stream_result import StreamResult
from hume.error.hume_client_exception import HumeClientException
import openai

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
MIN_SILENCE_LEN = 2000   # Minimum duration of silence in milliseconds

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

# Lists to accumulate non-silent audio files and emotions
non_silent_files = []
voice_emotions = []

# -------------------- Initialization and Cleanup --------------------

async def initialize_db():
    """Initialize a single database connection and create tables if needed."""
    global db_connection
    db_connection = await aiosqlite.connect(DB_FILE)
    await db_connection.execute('''
        CREATE TABLE IF NOT EXISTS conversation (
            sessionID TEXT,
            timestamp TEXT,
            conversation_starter TEXT,
            human_message TEXT,
            ai_message TEXT
        )''')
    await db_connection.execute('''
        CREATE TABLE IF NOT EXISTS emotions (
            sessionID TEXT,
            timestamp TEXT,
            file_name TEXT,
            emotions_detected TEXT
        )''')
    await db_connection.commit()

async def close_db_connection(app):
    """Close the database connection on application shutdown."""
    await db_connection.close()

# -------------------- Audio Handling --------------------

async def handle_audio_upload(request):
    """Handles incoming audio uploads and initiates asynchronous processing."""
    reader = await request.multipart()
    field = await reader.next()

    # Generate unique filename
    timestamp = datetime.datetime.now().isoformat()
    filename = f"audio_{timestamp}.webm"  # Changed extension to match uploaded format
    save_path = os.path.join(UPLOAD_DIR, filename)

    # Save uploaded audio file asynchronously
    async with aiofiles.open(save_path, 'wb') as f:
        while True:
            chunk = await field.read_chunk()
            if not chunk:
                break
            await f.write(chunk)

    # Process audio file
    asyncio.create_task(process_uploaded_audio(save_path))
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

async def process_uploaded_audio(file_path):
    """Processes uploaded audio file, checking for duplicates, silence, and performing emotion analysis."""
    try:
        if await is_duplicate_audio(file_path):
            await asyncio.to_thread(os.remove, file_path)
            return

        # Convert audio to WAV format
        wav_file_path = await convert_to_wav(file_path)

        # Check for file duration before processing
        audio = AudioSegment.from_file(wav_file_path)
        duration = len(audio)
        if duration < MIN_AUDIO_DURATION_MS:
            logger.info(f"Audio file {wav_file_path} is too short ({duration} ms); skipping.")
            await asyncio.to_thread(os.remove, file_path)
            await asyncio.to_thread(os.remove, wav_file_path)
            return

        silence_detected = await detect_silence(wav_file_path)
        if silence_detected:
            # Rename the file to indicate it is silent
            silent_path = wav_file_path.replace(".wav", "_silence.wav")
            os.rename(wav_file_path, silent_path)
            logger.info(f"Silence detected, file renamed to: {silent_path}")

            global silence_counter
            if not non_silent_files:
                silence_counter += 1
                if silence_counter >= 2:
                    await handle_conversation_starter()
                    silence_counter = 0
            else:
                silence_counter = 0
                await manage_conversation_flow()
                non_silent_files.clear()
                voice_emotions.clear()
        else:
            silence_counter = 0
            emotions = await analyze_voice_emotions(wav_file_path)
            if emotions:
                voice_emotions.append(emotions)
            non_silent_files.append(wav_file_path)
    except Exception as e:
        logger.error(f"Error processing audio: {e}")
    finally:
        # Remove the original uploaded file after processing
        await asyncio.to_thread(os.remove, file_path)
        # Do not delete the WAV file here; it will be deleted after processing

# -------------------- Audio Conversion --------------------

async def convert_to_wav(file_path):
    """Converts the uploaded audio file to WAV format using pydub."""
    def process():
        audio = AudioSegment.from_file(file_path)
        wav_filename = os.path.basename(file_path).replace('.webm', '.wav')
        wav_file_path = os.path.join(PROCESSED_DIR, wav_filename)
        audio.export(wav_file_path, format='wav')
        return wav_file_path
    return await asyncio.to_thread(process)

# -------------------- Silence Detection --------------------

async def detect_silence(file_path):
    """Detects silence in the uploaded audio file with adjusted threshold."""
    def process():
        audio = AudioSegment.from_file(file_path, format="wav")
        silence_thresholds = pydub_detect_silence(
            audio, min_silence_len=MIN_SILENCE_LEN, silence_thresh=SILENCE_THRESHOLD
        )
        return len(silence_thresholds) > 0
    return await asyncio.to_thread(process)

# -------------------- Hume Emotion Analysis --------------------

async def analyze_voice_emotions(file_path):
    """Analyzes voice emotions using Hume's Streaming API and returns the top 5 results."""
    client = AsyncHumeClient(HUME_API_KEY)

    config = ProsodyConfig()
    try:
        # Hume's streaming API expects audio files no longer than 5 seconds
        # Ensure the audio file meets this requirement
        audio = AudioSegment.from_file(file_path)
        if len(audio) > 5000:
            logger.warning(f"Audio file {file_path} exceeds 5 seconds; trimming to 5 seconds.")
            audio = audio[:5000]
            audio.export(file_path, format='wav')

        job = await client.submit_job(
            files=[file_path],
            models={"prosody": config},
            is_async=False  # We will wait for the job to complete
        )

        logger.info("Waiting for Hume AI job to complete...")
        await job.await_complete()
        predictions = await job.get_predictions()
        if predictions:
            emotions = []
            # Extract prosody predictions
            for prediction in predictions:
                prosody_predictions = prediction["results"]["predictions"][0]["models"]["prosody"]["grouped_predictions"]
                for group in prosody_predictions:
                    for emotion_data in group["emotions"]:
                        emotion_name = emotion_data["name"]
                        score = emotion_data["score"]
                        emotions.append({'emotion': emotion_name, 'score': score})
            # Extract top emotions
            top_emotions = extract_top_emotions_from_streaming_result(emotions)
            await save_emotions_data(file_path, top_emotions)
            return top_emotions
    except HumeClientException as e:
        logger.error(f"Hume AI error: {e}")
        return None
    except Exception as e:
        logger.error(f"Error during Hume emotion analysis: {e}")
        return None

def extract_top_emotions_from_streaming_result(emotions):
    """Extracts the top 5 emotions from Hume AI predictions."""
    # Aggregate the scores for each emotion
    emotion_scores = {}
    for emotion_data in emotions:
        emotion = emotion_data['emotion']
        score = emotion_data['score']
        if emotion in emotion_scores:
            emotion_scores[emotion].append(score)
        else:
            emotion_scores[emotion] = [score]
    # Average the scores for each emotion
    averaged_emotions = {emotion: sum(scores)/len(scores) for emotion, scores in emotion_scores.items()}
    # Get top 5 emotions
    top_emotions = sorted(averaged_emotions.items(), key=lambda x: x[1], reverse=True)[:5]
    return top_emotions

# -------------------- Transcription Function --------------------

async def transcribe_audio(file_path):
    """Transcribes audio using OpenAI's Whisper API and returns the text."""
    try:
        url = 'https://api.openai.com/v1/audio/transcriptions'
        headers = {
            'Authorization': f'Bearer {OPENAI_API_KEY}',
        }
        form_data = aiohttp.FormData()
        async with aiofiles.open(file_path, 'rb') as f:
            audio_data = await f.read()
            form_data.add_field('file', audio_data, filename=os.path.basename(file_path), content_type='audio/wav')
        form_data.add_field('model', 'whisper-1')
        form_data.add_field('response_format', 'text')
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, data=form_data) as response:
                if response.status == 200:
                    transcription = await response.text()
                    return transcription.strip()
                else:
                    error_text = await response.text()
                    logger.error(f"Error during transcription: {response.status}, {error_text}")
                    return None
    except Exception as e:
        logger.error(f"Error during transcription: {e}")
        return None

# -------------------- Conversation Management --------------------

async def handle_conversation_starter():
    """Initializes a conversation if two consecutive silent files are detected."""
    face_emotions = await retrieve_face_emotions()
    prompt = f"Start a conversation based on these emotions: {face_emotions}"
    response = await generate_openai_response(prompt)
    await save_conversation_data("Conversation Starter", response)
    logger.info(f"Conversation starter generated: {response}")

async def manage_conversation_flow():
    """Handles ongoing conversation by generating AI responses based on accumulated speech."""
    transcription_texts = []
    for file_path in non_silent_files:
        transcription = await transcribe_audio(file_path)
        if transcription:
            transcription_texts.append(transcription)
    transcript = " ".join(transcription_texts)

    if transcript:
        recent_emotions = combine_voice_emotions(voice_emotions)
        face_emotions = await retrieve_face_emotions()
        prompt = f"User said: {transcript}. Face emotions: {face_emotions}. Voice emotions: {recent_emotions}"
        response = await generate_openai_response(prompt)
        await save_conversation_data(transcript, response)
        logger.info(f"AI response generated: {response}")

    # Clean up files after processing
    for file_path in non_silent_files:
        await asyncio.to_thread(os.remove, file_path)

def combine_voice_emotions(emotions_list):
    """Combines a list of emotion tuples into a single dict of averaged emotions."""
    emotion_totals = {}
    emotion_counts = {}
    for emotions in emotions_list:
        for emotion, score in emotions:
            if emotion not in emotion_totals:
                emotion_totals[emotion] = 0
                emotion_counts[emotion] = 0
            emotion_totals[emotion] += score
            emotion_counts[emotion] += 1
    averaged_emotions = {emotion: emotion_totals[emotion] / emotion_counts[emotion] for emotion in emotion_totals}
    top_emotions = sorted(averaged_emotions.items(), key=lambda x: x[1], reverse=True)[:5]
    return ', '.join(f"{emotion}: {score:.2f}" for emotion, score in top_emotions)

# -------------------- OpenAI Completion --------------------

async def generate_openai_response(prompt):
    """Generates a response from OpenAI's GPT model based on a given prompt."""
    try:
        response = await asyncio.to_thread(
            openai.chat.completions.create,
            model="gpt-3.5-turbo",
            messages=[
                {"role": "user", "content": prompt}
            ],
            max_tokens=150
        )
        ai_text = response.choices[0].message.content.strip()
        return ai_text
    except openai.error.OpenAIError as e:
        logger.error(f"OpenAI API error: {e}")
        return None

# -------------------- Database Operations --------------------

async def save_conversation_data(human_message, ai_message):
    timestamp = datetime.datetime.now().isoformat()
    await db_connection.execute(
        "INSERT INTO conversation (sessionID, timestamp, human_message, ai_message) VALUES (?, ?, ?, ?)",
        ("default_session", timestamp, human_message, ai_message)
    )
    await db_connection.commit()

async def save_emotions_data(file_path, emotions):
    timestamp = datetime.datetime.now().isoformat()
    await db_connection.execute(
        "INSERT INTO emotions (sessionID, timestamp, file_name, emotions_detected) VALUES (?, ?, ?, ?)",
        ("default_session", timestamp, os.path.basename(file_path), str(emotions))
    )
    await db_connection.commit()

async def retrieve_face_emotions():
    async with db_connection.execute("SELECT initial_mood FROM users ORDER BY login_timestamp DESC LIMIT 1") as cursor:
        result = await cursor.fetchone()
        return result[0] if result else "Neutral"

# -------------------- Application Startup --------------------

async def init_app():
    await initialize_db()
    app = web.Application()
    app.router.add_post("/upload_audio", handle_audio_upload)
    app.on_cleanup.append(close_db_connection)
    return app

if __name__ == "__main__":
    web.run_app(init_app(), port=8000)





#---------------------BEST UPDATE (Hume Working)---------------------#
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
import asyncio
from hume import AsyncHumeClient
from hume.expression_measurement.stream import Config as HumeConfig
from hume.expression_measurement.stream.socket_client import StreamConnectOptions
import openai
from openai import OpenAIError


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

# Lists to accumulate non-silent audio files and emotions
non_silent_files = []
voice_emotions = []

# -------------------- Initialization and Cleanup --------------------

async def initialize_db():
    """Initialize a single database connection and create tables if needed."""
    global db_connection
    db_connection = await aiosqlite.connect(DB_FILE)
    await db_connection.execute('''
        CREATE TABLE IF NOT EXISTS conversation (
            sessionID TEXT,
            timestamp TEXT,
            conversation_starter TEXT,
            human_message TEXT,
            ai_message TEXT
        )
    ''')
    await db_connection.execute('''
        CREATE TABLE IF NOT EXISTS emotions (
            sessionID TEXT,
            timestamp TEXT,
            file_name TEXT,
            emotions_detected TEXT
        )
    ''')
    await db_connection.commit()

async def close_db_connection(app):
    """Close the database connection on application shutdown."""
    await db_connection.close()

# -------------------- Audio Handling --------------------

async def handle_audio_upload(request):
    """Handles incoming audio uploads and initiates asynchronous processing."""
    reader = await request.multipart()
    field = await reader.next()

    # Generate unique filename
    timestamp = datetime.datetime.now().isoformat()
    filename = f"audio_{timestamp}.webm"  # Changed extension to match uploaded format
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
    asyncio.create_task(process_uploaded_audio(save_path))
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

async def process_uploaded_audio(file_path):
    global silence_counter
    try:
        if await is_duplicate_audio(file_path):
            await asyncio.to_thread(os.remove, file_path)
            logger.info(f"Removed duplicate audio file: {file_path}")
            return

        # Convert audio to WAV format
        wav_file_path = await convert_to_wav(file_path)

        # Split audio into 5-second chunks
        chunk_files = await split_audio_into_chunks(wav_file_path)

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
                if silence_counter >= 2:
                    await handle_conversation_starter()
                    silence_counter = 0
                continue
            else:
                silence_counter = 0
                emotions = await analyze_voice_emotions(chunk_file)
                if emotions:
                    voice_emotions.append(emotions)
                non_silent_files.append(chunk_file)

        # If all chunks have been processed, manage conversation flow
        if non_silent_files:
            await manage_conversation_flow()
            non_silent_files.clear()
            voice_emotions.clear()

    except Exception as e:
        logger.error(f"Error processing audio: {e}")
    finally:
        # Remove the original uploaded file after processing
        try:
            await asyncio.to_thread(os.remove, file_path)
            logger.info(f"Removed uploaded audio file: {file_path}")
            await asyncio.to_thread(os.remove, wav_file_path)
            logger.info(f"Removed WAV audio file: {wav_file_path}")
        except Exception as e:
            logger.error(f"Error deleting file {file_path} or {wav_file_path}: {e}")

# -------------------- Audio Conversion --------------------

async def convert_to_wav(file_path):
    """Converts the uploaded audio file to WAV format using pydub."""
    def process():
        audio = AudioSegment.from_file(file_path)
        wav_filename = os.path.basename(file_path).replace('.webm', '.wav')
        wav_file_path = os.path.join(PROCESSED_DIR, wav_filename)
        audio.export(wav_file_path, format='wav')
        return wav_file_path
    wav_file_path = await asyncio.to_thread(process)
    logger.info(f"Converted to WAV: {wav_file_path}")
    return wav_file_path

# -------------------- Audio Splitting --------------------

async def split_audio_into_chunks(file_path):
    """Splits audio file into 5-second chunks and returns a list of chunk file paths."""
    audio = AudioSegment.from_file(file_path)
    chunks = []
    num_chunks = (len(audio) + HUME_STREAM_WINDOW_MS - 1) // HUME_STREAM_WINDOW_MS
    for idx in range(num_chunks):
        start_ms = idx * HUME_STREAM_WINDOW_MS
        end_ms = min((idx + 1) * HUME_STREAM_WINDOW_MS, len(audio))
        chunk = audio[start_ms:end_ms]
        chunk_filename = f"{os.path.splitext(file_path)[0]}_chunk_{idx}.wav"
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
            logger.info(f"Hume result for {file_path}: {result}")

            # Parse the result and extract emotions
            emotions = []
            if 'predictions' in result:
                for prediction in result['predictions']:
                    if 'models' in prediction:
                        models = prediction['models']
                        if 'prosody' in models:
                            prosody_model = models['prosody']
                            if 'predictions' in prosody_model:
                                for prosody_prediction in prosody_model['predictions']:
                                    if 'emotions' in prosody_prediction:
                                        for emotion_data in prosody_prediction['emotions']:
                                            emotion_name = emotion_data.get('name')
                                            score = emotion_data.get('score')
                                            emotions.append({'emotion': emotion_name, 'score': score})
            if emotions:
                # Store emotions in the database for this chunk
                await save_emotions_data(file_path, emotions)
                logger.info(f"Emotions extracted for {file_path}: {emotions}")
                return emotions
            else:
                logger.warning(f"No emotions found in Hume result for file: {file_path}")
                return None
    except Exception as e:
        logger.error(f"Error during Hume emotion analysis: {e}")
        return None



# -------------------- Transcription Function --------------------

async def transcribe_audio(file_paths):
    """Transcribes a list of audio files using OpenAI's Whisper API and returns the combined text."""
    transcripts = []
    for file_path in file_paths:
        try:
            url = 'https://api.openai.com/v1/audio/transcriptions'
            headers = {
                'Authorization': f'Bearer {OPENAI_API_KEY}',
            }
            form_data = aiohttp.FormData()
            async with aiofiles.open(file_path, 'rb') as f:
                audio_data = await f.read()
                form_data.add_field('file', audio_data, filename=os.path.basename(file_path), content_type='audio/wav')
            form_data.add_field('model', 'whisper-1')
            form_data.add_field('response_format', 'text')

            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, data=form_data) as response:
                    if response.status == 200:
                        transcription = await response.text()
                        logger.info(f"Transcription successful for file: {file_path}")
                        transcripts.append(transcription.strip())
                    else:
                        error_text = await response.text()
                        logger.error(f"Error during transcription: {response.status}, {error_text}")
        except Exception as e:
            logger.error(f"Error during transcription of {file_path}: {e}")
    combined_transcript = " ".join(transcripts)
    return combined_transcript

# -------------------- Conversation Management --------------------

async def handle_conversation_starter():
    """Initializes a conversation if two consecutive silent files are detected."""
    face_emotions = await retrieve_face_emotions()
    prompt = f"Start a conversation based on these emotions: {face_emotions}"
    response = await generate_openai_response(prompt)
    await save_conversation_data("Conversation Starter", response)
    logger.info(f"Conversation starter generated: {response}")

async def manage_conversation_flow():
    """Handles ongoing conversation by generating AI responses based on accumulated speech."""
    if non_silent_files:
        transcript = await transcribe_audio(non_silent_files)
        if transcript:
            recent_emotions = combine_voice_emotions(voice_emotions)
            face_emotions = await retrieve_face_emotions()
            prompt = f"User said: {transcript}. Face emotions: {face_emotions}. Voice emotions: {recent_emotions}"
            response = await generate_openai_response(prompt)
            await save_conversation_data(transcript, response)
            logger.info(f"AI response generated: {response}")
        else:
            logger.warning("No transcript available for AI response generation.")
    else:
        logger.warning("No non-silent audio files to process.")

    # Clean up files after processing
    for file_path in non_silent_files:
        try:
            await asyncio.to_thread(os.remove, file_path)
            logger.info(f"Removed processed audio file: {file_path}")
        except Exception as e:
            logger.error(f"Error deleting processed file {file_path}: {e}")

def combine_voice_emotions(emotions_list):
    """Combines a list of emotion dictionaries into a single dict of averaged emotions."""
    emotion_totals = {}
    emotion_counts = {}
    for emotions in emotions_list:
        for emotion_data in emotions:
            emotion = emotion_data['emotion']
            score = emotion_data['score']
            if emotion not in emotion_totals:
                emotion_totals[emotion] = 0
                emotion_counts[emotion] = 0
            emotion_totals[emotion] += score
            emotion_counts[emotion] += 1
    if emotion_totals:
        averaged_emotions = {emotion: emotion_totals[emotion] / emotion_counts[emotion] for emotion in emotion_totals}
        top_emotions = sorted(averaged_emotions.items(), key=lambda x: x[1], reverse=True)[:5]
        return ', '.join(f"{emotion}: {score:.2f}" for emotion, score in top_emotions)
    else:
        return "No emotions detected"

# -------------------- OpenAI Completion --------------------

openai.api_key = OPENAI_API_KEY

async def generate_openai_response(prompt):
    try:
        # For streaming response
        completion = await client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=150,
            stream=True
        )
        response = ""
        async for chunk in completion:
            delta = chunk.choices[0].delta.get('content', '')
            response += delta
        logger.info("OpenAI response generated successfully.")
        return response.strip()
    except openai.error.OpenAIError as e:
        logger.error(f"OpenAI API error: {e}")
        return None


# -------------------- Database Operations --------------------

async def save_conversation_data(human_message, ai_message):
    timestamp = datetime.datetime.now().isoformat()
    await db_connection.execute(
        "INSERT INTO conversation (sessionID, timestamp, conversation_starter, human_message, ai_message) VALUES (?, ?, ?, ?, ?)",
        ("default_session", timestamp, "", human_message, ai_message)
    )
    await db_connection.commit()
    logger.info("Conversation data saved to database.")

async def save_emotions_data(file_path, emotions):
    timestamp = datetime.datetime.now().isoformat()
    await db_connection.execute(
        "INSERT INTO emotions (sessionID, timestamp, file_name, emotions_detected) VALUES (?, ?, ?, ?)",
        ("default_session", timestamp, os.path.basename(file_path), str(emotions))
    )
    await db_connection.commit()
    logger.info(f"Emotions data saved to database for {file_path}.")

async def retrieve_face_emotions():
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
    app.on_cleanup.append(close_db_connection)
    return app

if __name__ == "__main__":
    web.run_app(init_app(), port=8000)
