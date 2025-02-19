import cv2
import asyncio
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VideoStream:
    def __init__(self, source=0):
        self.source = source
        self.capture = cv2.VideoCapture(source)
        self.running = False

    async def start_stream(self, frame_callback, interval=0.1):
        """
        Continuously capture video frames and process them with a callback.
        :param frame_callback: an async function to process each frame.
        :param interval: delay (in seconds) between frames.
        """
        self.running = True
        while self.running:
            ret, frame = self.capture.read()
            if ret:
                await frame_callback(frame)
            await asyncio.sleep(interval)

    def stop(self):
        self.running = False
        self.capture.release()

# Example usage (for testing only):
if __name__ == "__main__":
    async def process_frame(frame):
        logger.info(f"Processing frame of shape: {frame.shape}")

    stream = VideoStream()
    try:
        asyncio.run(stream.start_stream(process_frame))
    except KeyboardInterrupt:
        stream.stop()
