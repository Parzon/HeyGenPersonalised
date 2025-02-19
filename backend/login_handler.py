from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import JSONResponse
import cv2
import numpy as np
import os
from datetime import datetime
import asyncio
from emotion_analysis import EmotionAnalyzer
import logging
from env_keys import get_hume_api_key, get_openai_api_key

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

CAPTURED_FACE_DIR = "captured_faces"
os.makedirs(CAPTURED_FACE_DIR, exist_ok=True)

hume_api_key = get_hume_api_key()
emotion_analyzer = EmotionAnalyzer(hume_api_key)

@app.post("/login")
async def login(file: UploadFile = File(...), username: str = Form(...)):
    try:
        # Read and decode the image file
        image_data = await file.read()
        np_array = np.frombuffer(image_data, np.uint8)
        image = cv2.imdecode(np_array, cv2.IMREAD_COLOR)

        # Save the captured image for records
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        image_path = os.path.join(CAPTURED_FACE_DIR, f"{username}_{timestamp}.png")
        cv2.imwrite(image_path, image)
        logger.info(f"Captured face image saved: {image_path}")

        # Run emotion analysis on the actual NumPy image
        emotions = await emotion_analyzer.analyze_face(image)

        # Here you would create a session record, store data in DB, etc.
        session_id = timestamp  # For demonstration, using timestamp as session ID

        return JSONResponse({
            "username": username,
            "session_id": session_id,
            "emotions": emotions
        })
    except Exception as e:
        logger.error(f"Login error: {e}")
        return JSONResponse({"error": "Login failed"}, status_code=500)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
