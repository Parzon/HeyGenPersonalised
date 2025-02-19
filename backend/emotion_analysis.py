import cv2
import asyncio
import logging
import os
import numpy as np
from hume import AsyncHumeClient
from hume.expression_measurement.stream import Config
from hume.expression_measurement.stream.socket_client import StreamConnectOptions
from env_keys import get_hume_api_key

# ✅ Load Hume API Key
HUME_API_KEY = get_hume_api_key()

# ✅ Explicitly define the Haar cascade path
HAAR_CASCADE_PATH = "/Users/Parzon/anaconda3/envs/heygenexec/share/opencv4/haarcascades/haarcascade_frontalface_default.xml"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EmotionAnalyzer:
    def __init__(self, hume_api_key: str):
        self.hume_api_key = hume_api_key
        self.face_cascade = cv2.CascadeClassifier(HAAR_CASCADE_PATH)  # ✅ Load classifier once

        if self.face_cascade.empty():
            logger.error("Failed to load Haar cascade for face detection.")

    def detect_faces_opencv(self, image: np.ndarray):
        """
        Uses OpenCV Haar cascades to detect faces (synchronous).
        """
        if image is None or not isinstance(image, np.ndarray):
            logger.error("Invalid image provided for face detection.")
            return []

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)
        return faces

    async def analyze_face(self, image: np.ndarray):
        """
        Sends an image (NumPy array) to Hume AI for emotion analysis asynchronously.
        """
        try:
            # Save image temporarily
            image_path = "/tmp/temp_face.jpg"
            cv2.imwrite(image_path, image)

            if not os.path.exists(image_path):
                logger.error("Failed to save face image for analysis.")
                return []

            # Initialize Hume client
            client = AsyncHumeClient(api_key=self.hume_api_key)
            model_config = Config(face={})
            stream_options = StreamConnectOptions(config=model_config)

            async with client.expression_measurement.stream.connect(options=stream_options) as socket:
                result = await socket.send_file(image_path)

                # Parse result
                if result and hasattr(result, "face") and result.face.predictions:
                    emotions = result.face.predictions[0].emotions
                    # Sort and take top 5 emotions
                    top_emotions = sorted(emotions, key=lambda e: e.score, reverse=True)[:5]
                    emotion_list = [
                        {"emotion": e.name, "score": e.score} for e in top_emotions
                    ]
                    logger.info(f"Top 3 emotions: {emotion_list[:3]}")
                    return emotion_list
                else:
                    logger.warning("No face emotion detected")
                    return []
        except Exception as e:
            logger.error(f"Emotion analysis error: {e}")
            return []
        finally:
            if os.path.exists(image_path):
                os.remove(image_path)  # Cleanup temp file
