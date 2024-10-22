import os
import aiohttp
import asyncio
import datetime
import openai
import json
import csv
import hashlib
import threading
from aiohttp import web
from pydub import AudioSegment
from pydub.silence import detect_silence as pydub_detect_silence
from env_keys import get_openai_api_key

# Set up upload directory
UPLOAD_DIR = "uploaded_audio"
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

# CSV to save conversation
CSV_FILE = "conversation_transcripts.csv"
if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['Timestamp', 'Speaker', 'Content'])

# Replace this with your actual OpenAI API key retrieval function
OPENAI_API_KEY = get_openai_api_key()
openai.api_key = OPENAI_API_KEY

# Track start time of the session
start_time = datetime.datetime.now()

# Counter for unique naming
file_counter = 1

# Hashes of processed files to check for duplicates
processed_hashes = set()

# Lock to manage concurrent file writing
write_lock = threading.Lock()

async def upload_audio(request):
    global file_counter

    reader = await request.multipart()
    field = await reader.next()

    # Generate a unique filename with timestamp and counter
    timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')
    unique_filename = f"audio_{timestamp}_{file_counter}.wav"
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
        file_counter += 1

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

            # Check if both _1_silence.wav and _2_silence.wav exist
            base_filename = "_".join(os.path.basename(silent_wav_path).split("_")[:2])
            first_silence_path = os.path.join(UPLOAD_DIR, f"{base_filename}_1_silence.wav")
            second_silence_path = os.path.join(UPLOAD_DIR, f"{base_filename}_2_silence.wav")

            # Log debug information about silence files
            print(f"Checking for existence of: {first_silence_path} and {second_silence_path}")

            if os.path.exists(first_silence_path) and os.path.exists(second_silence_path):
                print("Both silence files detected, initiating conversation starter.")
                await start_conversation()

        else:
            print(f"No extended silence detected in: {save_path}")

        return True

    except Exception as e:
        print(f"Error while processing audio file {save_path if save_path else 'unknown'}: {e}")
        return False

def detect_silence(audio_path, silence_threshold=-40.0, min_silence_duration=4900):
    try:
        audio = AudioSegment.from_file(audio_path, format="wav")
        silence_ranges = pydub_detect_silence(audio, min_silence_len=min_silence_duration, silence_thresh=silence_threshold)
        print(f"Silence ranges detected in {audio_path}: {silence_ranges}")
        return len(silence_ranges) > 0
    except Exception as e:
        print(f"Error during silence detection for {audio_path}: {e}")
        return False

async def start_conversation():
    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Bearer {OPENAI_API_KEY}"
            }
            json_data = {
                "model": "gpt-4o",
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": "Say a conversation starter."}
                ],
                "max_tokens": 50,
                "n": 1
            }

            async with session.post("https://api.openai.com/v1/chat/completions", headers=headers, json=json_data) as resp:
                response = await resp.json()

                # Extract the response message content
                if response and 'choices' in response and len(response['choices']) > 0:
                    message_content = response['choices'][0]['message']['content']

                    # Save to CSV
                    save_to_csv(datetime.datetime.now(), "AI", message_content)
                    print(f"Assistant response saved: {message_content}")
                else:
                    print(f"Unexpected response format from OpenAI API: {response}")

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
