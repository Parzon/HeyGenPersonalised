import os
import aiohttp
from aiohttp import web
from pydub import AudioSegment
import datetime

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

    try:
        # Convert WebM to WAV and save it
        audio = AudioSegment.from_file(save_path, format="webm")
        wav_path = save_path.replace(".webm", ".wav")
        audio.export(wav_path, format="wav")
        print(f"Conversion from WebM to WAV successful. Saved as: {wav_path}")
    except Exception as e:
        print(f"Error while processing audio file: {e}")
        return web.Response(text="Failed to process audio", status=500)

    return web.Response(text="Audio uploaded successfully", status=200)

app.router.add_post("/upload_audio", upload_audio)

if __name__ == "__main__":
    web.run_app(app, port=8000)
