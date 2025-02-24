from logger import logger
import datetime
from hume import AsyncHumeClient
from hume.expression_measurement.stream import Config
from hume.expression_measurement.stream.socket_client import StreamConnectOptions
from hume.expression_measurement.stream.types import StreamFace


async def analyze_face_image(image_path: str) -> dict:
    """
    Calls Hume's streaming API for face analysis on a single image.
    Returns {emotion_name: score, ...}
    """
    try:
        client = AsyncHumeClient(api_key=HUME_API_KEY)
        model_config = Config(face=StreamFace())
        stream_options = StreamConnectOptions(config=model_config)

        async with client.expression_measurement.stream.connect(options=stream_options) as socket:
            encoded_image = encode_image(image_path)
            result = await socket.send_file(encoded_image)

            if not result or not result.face or not result.face.predictions:
                logger.warning("No face predictions from Hume.")
                return {}

            face_predictions = result.face.predictions[0]  # first face
            if not face_predictions or not face_predictions.emotions:
                return {}

            emotions_sorted = sorted(face_predictions.emotions, key=lambda e: e.score, reverse=True)
            return {e.name: e.score for e in emotions_sorted}
    except Exception as e:
        logger.error(f"❌ Error analyzing face image with Hume: {e}")
        return {}

def encode_image(path_):
    """
    Helper to read the image and return raw bytes if needed for the streaming socket.
    """
    with open(path_, "rb") as f:
        return f.read()
