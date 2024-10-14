import os
import aiohttp
from aiohttp import web
from pydub import AudioSegment, silence
import datetime
import asyncio

# Set up upload directory
UPLOAD_DIR = "uploaded_audio"
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

# Counter for unique naming
counter = 1

# Set up web server
app = web.Application()

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

    # Process the saved audio
    await process_audio(save_path)

    return web.Response(text="Audio uploaded successfully", status=200)

async def process_audio(filepath):
    try:
        # Convert WebM to WAV and save it
        if filepath.endswith(".webm"):
            audio = AudioSegment.from_file(filepath, format="webm")
            wav_path = filepath.replace(".webm", ".wav")
            audio.export(wav_path, format="wav")
            print(f"Conversion from WebM to WAV successful. Saved as: {wav_path}")
        else:
            wav_path = filepath

        # Load the WAV audio
        audio = AudioSegment.from_file(wav_path, format="wav")

        # Detect silence in the audio using pydub's detect_silence
        silence_threshold = -40  # Silence threshold in dBFS (adjust this if necessary)
        min_silence_len = 4900  # Minimum silence length in milliseconds (5 seconds)
        silent_ranges = silence.detect_silence(audio, min_silence_len=min_silence_len, silence_thresh=silence_threshold)

        if silent_ranges:
            print(f"Silence detected in: {wav_path}")
            silent_wav_path = wav_path.replace(".wav", "_silence.wav")
            os.rename(wav_path, silent_wav_path)
            wav_path = silent_wav_path
        else:
            print(f"No extended silence detected in: {wav_path}")

        # Simulate further processing, like transcription/emotion analysis, asynchronously
        await asyncio.sleep(1)  # Placeholder for transcription/emotion analysis logic
        print(f"Successfully processed audio: {wav_path}")

    except Exception as e:
        print(f"Error while processing audio file: {e}")

app.router.add_post("/upload_audio", upload_audio)

if __name__ == "__main__":
    web.run_app(app, port=8000)
