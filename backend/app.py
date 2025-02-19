import os
import datetime
import json
import numpy as np
import asyncio
import logging
import aiosqlite
import aiofiles
import cv2
import uvicorn
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from env_keys import get_hume_api_key, get_openai_api_key

# Import our modules
from audio_processing import AudioProcessor
from emotion_analysis import EmotionAnalyzer
from context_manager import ConversationMemory
from response_generator import ResponseGenerator

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("BabyClaireApp")

# Constants and configuration
DB_FILE = "users.db"
UPLOAD_DIR = "uploaded_audio"
PROCESSED_DIR = "processed_audio"
FACE_DIR = "captured_faces"
os.makedirs(FACE_DIR, exist_ok=True)

# Replace with actual API keys
OPENAI_API_KEY = get_openai_api_key()
HUME_API_KEY = get_hume_api_key()

# Initialize our modules
audio_processor = AudioProcessor(upload_dir=UPLOAD_DIR, processed_dir=PROCESSED_DIR)
emotion_analyzer = EmotionAnalyzer(hume_api_key=HUME_API_KEY)
response_generator = ResponseGenerator(openai_api_key=OPENAI_API_KEY)
conversation_memory = ConversationMemory(max_length=20)

# Create FastAPI app
app = FastAPI(title="BabyClaire AI Assistant")

# Enable CORS (adjust origins as needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------
# WEB SOCKET ENDPOINT
# ------------------------------------------------
@app.websocket("/ws/video")
async def websocket_video_endpoint(websocket: WebSocket):
    """Handles WebSocket video frames for face detection and emotion analysis."""

    await websocket.accept()
    session_id = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    last_face_time = datetime.datetime.now()

    logger.info("✅ WebSocket connection established.")

    try:
        while True:
            data = await websocket.receive_bytes()

            if not data:
                logger.warning("Received empty frame")
                await websocket.send_json({"error": "Empty frame received"})
                continue

            # Convert byte data to OpenCV image
            np_arr = np.frombuffer(data, np.uint8)
            image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

            if image is None:
                logger.error("Error decoding video frame")
                await websocket.send_json({"error": "Invalid image data"})
                continue

            # Detect faces
            faces = emotion_analyzer.detect_faces_opencv(image)

            if len(faces) > 0:
                now = datetime.datetime.now()

                # Store once per minute
                if (now - last_face_time).seconds >= 60:
                    face_path = os.path.join(FACE_DIR, f"{session_id}_{now.strftime('%H%M%S')}.png")
                    cv2.imwrite(face_path, image)
                    last_face_time = now

                    # Analyze face
                    emotions = await emotion_analyzer.analyze_face(image)
                    logger.info(f"Stored face & detected emotions: {emotions}")

                    await websocket.send_json({
                        "message": "Face detected",
                        "num_faces": len(faces),
                        "emotions": emotions
                    })
                else:
                    await websocket.send_json({"message": "Face detected, but skipping storage"})
            else:
                await websocket.send_json({"message": "No face detected"})

    except WebSocketDisconnect:
        logger.info("❌ WebSocket disconnected.")
    except Exception as e:
        logger.error(f"🚨 Unexpected error: {e}")
        await websocket.send_json({"error": str(e)})

    finally:
        logger.info("✅ WebSocket connection closed.")


# ------------------------------------------------
# AUDIO UPLOAD & TRANSCRIPTION ENDPOINT
# ------------------------------------------------
@app.post("/upload_audio")
async def upload_audio(file: UploadFile = File(...), session_id: str = Form(...)):
    """
    Receives audio chunks from the client, converts them to WAV,
    transcribes them with OpenAI, and returns a GPT response.
    """

    # ----------------------------
    # 1) Save Audio to Disk
    # ----------------------------
    file_bytes = await file.read()
    saved_path = await audio_processor.save_audio_file(file_bytes, file.filename)

    # ----------------------------
    # 2) Convert to WAV
    # ----------------------------
    wav_path = await audio_processor.convert_to_wav(saved_path)

    # ----------------------------
    # 3) Optional: Detect Silence
    # ----------------------------
    is_silent = await audio_processor.detect_silence(wav_path, min_silence_len=3000, silence_thresh=-40)
    if is_silent:
        logger.info(f"Session {session_id}: Silence detected, skipping transcription.")
        return {
            "session_id": session_id,
            "transcript": "",
            "response": "No audible speech detected."
        }

    # ----------------------------
    # 4) Transcribe with OpenAI
    # ----------------------------
    transcription = await audio_processor.transcribe_audio(wav_path, OPENAI_API_KEY)
    logger.info(f"Session {session_id}: Transcription => {transcription}")

    if not transcription:
        return {
            "session_id": session_id,
            "transcript": "",
            "response": "Transcription failed or was empty."
        }

    # ----------------------------
    # 5) Generate GPT Response
    # ----------------------------
    # We'll gather the entire response from the streaming generator.
    # If you prefer a simpler approach, you can do a non-stream call.
    response_chunks = []
    async for chunk in response_generator.generate_response(transcription):
        response_chunks.append(chunk)
    ai_response = "".join(response_chunks)

    # ----------------------------
    # 6) Update Conversation Memory
    # ----------------------------
    conversation_memory.add_interaction(user_input=transcription, ai_response=ai_response)

    # Return the final transcript & GPT response
    return {
        "session_id": session_id,
        "transcript": transcription,
        "response": ai_response
    }


# ------------------------------------------------
# MAIN ENTRYPOINT
# ------------------------------------------------
if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
