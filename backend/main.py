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

# Set up web server
app = web.Application()

# Replace this with your actual OpenAI API key retrieval function
OPENAI_API_KEY = get_openai_api_key()
openai.api_key = OPENAI_API_KEY

# Track start time of the session
start_time = datetime.datetime.now()

async def upload_audio(request):
    global counter, start_time

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

    try:
        # Convert WebM to WAV and save it
        audio = AudioSegment.from_file(save_path, format="webm")
        wav_path = save_path.replace(".webm", ".wav")
        audio.export(wav_path, format="wav")
        print(f"Conversion from WebM to WAV successful. Saved as: {wav_path}")

        # Check for silence
        if detect_silence(wav_path):
            silent_wav_path = wav_path.replace(".wav", "_silence.wav")
            os.rename(wav_path, silent_wav_path)
            print(f"Silence detected. Renamed to: {silent_wav_path}")

            # Check if both _1_silence.wav and _2_silence.wav exist
            first_silence_path = os.path.join(UPLOAD_DIR, f"audio_{timestamp}_1_silence.wav")
            second_silence_path = os.path.join(UPLOAD_DIR, f"audio_{timestamp}_2_silence.wav")
            
            if os.path.exists(first_silence_path) and os.path.exists(second_silence_path):
                await start_conversation()

        else:
            print(f"No extended silence detected in: {wav_path}")

    except Exception as e:
        print(f"Error while processing audio file: {e}")
        return web.Response(text="Failed to process audio", status=500)

    return web.Response(text="Audio uploaded successfully", status=200)

def detect_silence(audio_path, silence_threshold=-40.0, min_silence_duration=4900):
    audio = AudioSegment.from_file(audio_path, format="wav")
    silence_ranges = pydub_detect_silence(audio, min_silence_len=min_silence_duration, silence_thresh=silence_threshold)
    return len(silence_ranges) > 0

async def start_conversation():
    try:
        # Use the standard OpenAI ChatCompletion API to generate a conversation starter
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Say a conversation starter."}
            ],
            max_tokens=50,
            n=1  # Ensure that only one response is generated
        )

        # Extract the response message content
        if response and len(response.choices) > 0:
            message_content = response.choices[0].message

            # Save to CSV
            save_to_csv(datetime.datetime.now(), "AI", message_content)
            print(f"Assistant response saved: {message_content}")

    except Exception as e:
        print(f"Error while generating conversation starter: {e}")

def save_to_csv(timestamp, speaker, content):
    """Save transcription data to CSV."""
    with open(CSV_FILE, mode='a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow([timestamp.strftime('%Y-%m-%d %H:%M:%S'), speaker, content])

app.router.add_post("/upload_audio", upload_audio)

if __name__ == "__main__":
    web.run_app(app, port=8000)
