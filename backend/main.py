import os
import aiohttp
import asyncio
import datetime
import openai
import json
import csv
from aiohttp import web
from pydub import AudioSegment
from pydub.silence import detect_silence as pydub_detect_silence
from env_keys import get_openai_api_key  # Retrieve OpenAI API key securely

# Set up upload directory
UPLOAD_DIR = "uploaded_audio"
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

# CSV to save conversation
CSV_FILE = "conversation_transcripts.csv"
if not os.path.exists(CSV_FILE):
    # Create the CSV file and write the headers
    with open(CSV_FILE, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['Timestamp', 'Speaker', 'Content'])

# Counter for unique naming
counter = 1

# Replace this with your actual OpenAI API key retrieval function
OPENAI_API_KEY = get_openai_api_key()
openai.api_key = OPENAI_API_KEY

# Track start time of the session
start_time = datetime.datetime.now()

# Initialize an async queue for storing audio files to be processed
audio_queue = None  # Will be initialized in main loop

async def upload_audio(request):
    global counter

    reader = await request.multipart()
    field = await reader.next()

    # Generate a unique filename with timestamp and counter
    timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    unique_filename = f"audio_{timestamp}_{counter}.webm"
    save_path = os.path.join(UPLOAD_DIR, unique_filename)

    # Increment the counter for the next file
    counter += 1

    # Write the file to disk
    with open(save_path, 'wb') as f:
        while True:
            chunk = await field.read_chunk()  # 8192 bytes by default.
            if not chunk:
                break
            f.write(chunk)

    # Add the audio file to the processing queue
    await audio_queue.put(save_path)
    print(f"Audio file {unique_filename} added to the processing queue.")

    return web.Response(text="Audio uploaded successfully", status=200)

async def process_audio():
    while True:
        save_path = None
        try:
            # Get the next audio file from the queue
            save_path = await audio_queue.get()
            print(f"Processing audio file: {save_path}")

            # Convert WebM to WAV
            audio = AudioSegment.from_file(save_path, format="webm")
            wav_path = save_path.replace(".webm", ".wav")
            audio.export(wav_path, format="wav")
            print(f"Conversion from WebM to WAV successful. Saved as: {wav_path}")

            # Delete the original WebM file after successful conversion
            os.remove(save_path)
            print(f"Deleted original WebM file: {save_path}")

            # Check for silence
            silence_detected = detect_silence(wav_path)
            if silence_detected:
                silent_wav_path = wav_path.replace(".wav", "_silence.wav")
                os.rename(wav_path, silent_wav_path)
                print(f"Silence detected. Renamed to: {silent_wav_path}")

                # Check if both _1_silence.wav and _2_silence.wav exist
                base_filename = "_".join(os.path.basename(save_path).split("_")[:2])
                first_silence_path = os.path.join(UPLOAD_DIR, f"{base_filename}_1_silence.wav")
                second_silence_path = os.path.join(UPLOAD_DIR, f"{base_filename}_2_silence.wav")

                # Log debug information about silence files
                print(f"Checking for existence of: {first_silence_path} and {second_silence_path}")

                if os.path.exists(first_silence_path) and os.path.exists(second_silence_path):
                    print("Both silence files detected, initiating conversation starter.")
                    await start_conversation()

            else:
                print(f"No extended silence detected in: {wav_path}")

        except Exception as e:
            print(f"Error while processing audio file {save_path if save_path else 'unknown'}: {e}")

        finally:
            if save_path is not None:
                audio_queue.task_done()

async def start_conversation():
    try:
        # Use aiohttp to call OpenAI API asynchronously
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

def detect_silence(audio_path, silence_threshold=-40.0, min_silence_duration=4900):
    try:
        audio = AudioSegment.from_file(audio_path, format="wav")
        silence_ranges = pydub_detect_silence(audio, min_silence_len=min_silence_duration, silence_thresh=silence_threshold)
        print(f"Silence ranges detected in {audio_path}: {silence_ranges}")
        return len(silence_ranges) > 0
    except Exception as e:
        print(f"Error during silence detection for {audio_path}: {e}")
        return False

def save_to_csv(timestamp, speaker, content):
    """Save transcription data to CSV."""
    try:
        with open(CSV_FILE, mode='a', newline='') as file:
            writer = csv.writer(file)
            writer.writerow([timestamp.strftime('%Y-%m-%d %H:%M:%S'), speaker, content])
    except Exception as e:
        print(f"Error while saving to CSV: {e}")

async def init_app():
    global audio_queue

    # Initialize the web app
    app = web.Application()
    app.router.add_post("/upload_audio", upload_audio)

    # Initialize the async queue
    audio_queue = asyncio.Queue()

    # Start the background task to process audio
    loop = asyncio.get_running_loop()
    loop.create_task(process_audio())

    return app

if __name__ == "__main__":
    try:
        # Run the web server with the initialized app
        web.run_app(init_app(), port=8000)
    except Exception as e:
        print(f"Server failed to start: {e}")
