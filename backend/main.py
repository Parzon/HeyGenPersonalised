import os
import aiohttp
import asyncio
import datetime
import openai
import json
import csv
import hashlib
import threading
import base64
import numpy as np
import cv2
from aiohttp import web
from pydub import AudioSegment
from pydub.silence import detect_silence as pydub_detect_silence
from env_keys import get_openai_api_key, get_hume_api_key

# Set up directories and API keys
UPLOAD_DIR = "uploaded_audio"
INCOMING_FRAMES_DIR = "incoming_frames"
DETECTED_FRAMES_DIR = "detected_frames"
CSV_FILE = "conversation_transcripts.csv"

# Ensure directories exist
for directory in [UPLOAD_DIR, INCOMING_FRAMES_DIR, DETECTED_FRAMES_DIR]:
    if not os.path.exists(directory):
        os.makedirs(directory)

# Set up CSV for conversation transcripts
if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['Timestamp', 'Speaker', 'Content'])

# API keys
OPENAI_API_KEY = get_openai_api_key()
HUME_API_KEY = get_hume_api_key()
openai.api_key = OPENAI_API_KEY

# Global variables
start_time = datetime.datetime.now()
file_counter = 1
processed_hashes = set()
write_lock = threading.Lock()
face_detected_flag = False  # Global flag for face detection

async def upload_audio(request):
    global file_counter
    reader = await request.multipart()
    field = await reader.next()

    timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')
    unique_filename = f"audio_{timestamp}_{file_counter}.wav"
    save_path = os.path.join(UPLOAD_DIR, unique_filename)

    with write_lock:
        with open(save_path, 'wb') as f:
            while True:
                chunk = await field.read_chunk()
                if not chunk:
                    break
                f.write(chunk)

    is_valid = await process_audio(save_path)
    if is_valid:
        file_counter += 1

    return web.Response(text="Audio uploaded successfully", status=200)

async def detect_face(request):
    global face_detected_flag  # Access the global flag

    if face_detected_flag:
        return web.json_response({"face_detected": False, "message": "Face already detected, stopping further processing."})

    reader = await request.multipart()
    file = await reader.next()

    if not file:
        return web.json_response({"error": "No file provided"}, status=400)

    contents = await file.read()
    timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')
    incoming_image_path = os.path.join(INCOMING_FRAMES_DIR, f"frame_{timestamp}.png")

    with open(incoming_image_path, 'wb') as f:
        f.write(contents)

    np_array = np.frombuffer(contents, np.uint8)
    image = cv2.imdecode(np_array, cv2.IMREAD_COLOR)
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))

    if len(faces) > 0:
        detected_image_path = os.path.join(DETECTED_FRAMES_DIR, f"detected_face_{timestamp}.png")
        cv2.imwrite(detected_image_path, image)
        face_detected_flag = True  # Set the flag when a face is detected
        return web.json_response({"face_detected": True, "filename": detected_image_path})
    else:
        return web.json_response({"face_detected": False, "filename": incoming_image_path})

async def init_app():
    app = web.Application()
    app.router.add_post("/upload_audio", upload_audio)
    app.router.add_post("/detect_face", detect_face)
    return app

if __name__ == "__main__":
    try:
        web.run_app(init_app(), port=8000)
    except Exception as e:
        print(f"Server failed to start: {e}")
