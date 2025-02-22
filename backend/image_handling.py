import aiofiles
import aiosqlite
import asyncio
import datetime
import logging
import os
import uuid
import cv2
from aiohttp import web

from hume_face_analysis import analyze_face_image
from logger import logger
from config import IMAGES_PER_BATCH, IMAGE_DIR
from session_helpers import get_last_session_id

image_file_counter = 0
images_batch_list = []  # Collect filenames here until we have 40 images.

async def handle_image_upload(request):
    """
    Once we get 40 images, run face detection, pick best face, analyze with Hume, store in DB, delete others.
    """

    logger.info("📸 Received image upload request...")
    try:
        reader = await request.multipart()
        field = await reader.next()
        if not field or field.name != 'file':
            return web.Response(text="Invalid form field", status=400)

        original_filename = field.filename or f"image_{datetime.datetime.now().timestamp()}.jpg"
        unique_name = f"{uuid.uuid4()}_{original_filename}"
        save_path = os.path.join(IMAGE_DIR, unique_name)

        # Save image
        async with aiofiles.open(save_path, "wb") as f:
            while True:
                chunk = await field.read_chunk()
                if not chunk:
                    break
                await f.write(chunk)

        image_file_counter += 1
        images_batch_list.append(save_path)

        logger.info(f"✅ Image saved: {save_path} (count in batch: {len(images_batch_list)})")

        # If we reached 40 images, run face detection pipeline
        if len(images_batch_list) >= IMAGES_PER_BATCH:
            logger.info(f"🌟 We have {IMAGES_PER_BATCH} images. Processing face detection now.")
            await process_face_images_batch()

        return web.Response(text=f"✅ Image uploaded: {unique_name}")
    except Exception as e:
        logger.error(f"Image upload error: {str(e)}")
        return web.Response(text=f"❌ Upload failed: {str(e)}", status=500)

async def process_face_images_batch():
    """
    - Use OpenCV to detect largest face among the 40 images.
    - Send best face image to Hume for face emotion analysis.
    - Delete all other images.
    - Store face emotion in DB, clear images_batch_list.
    """

    if not images_batch_list:
        logger.info("No images to process.")
        return

    best_image_path = None
    best_area = 0

    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )

    for path_ in images_batch_list:
        try:
            img = cv2.imread(path_)
            if img is None:
                continue
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, 1.3, 5)
            if len(faces) > 0:
                (x, y, w, h) = max(faces, key=lambda f: f[2] * f[3])  # largest area
                area = w * h
                if area > best_area:
                    best_area = area
                    best_image_path = path_
        except Exception as e:
            logger.error(f"Error reading {path_} for face detection: {e}")

    if best_image_path is None:
        logger.warning("No face detected in these images. Deleting them all.")
        for path_ in images_batch_list:
            try:
                os.remove(path_)
            except:
                pass
        images_batch_list.clear()
        return

    logger.info(f"Best face found in {best_image_path}, area={best_area}. Deleting the rest.")
    # Delete others
    for path_ in images_batch_list:
        if path_ != best_image_path:
            try:
                os.remove(path_)
            except:
                pass

    images_batch_list.clear()
    # Analyze best face with Hume
    face_emotions = await analyze_face_image(best_image_path)
    logger.info(f"Face emotions from Hume: {face_emotions}")

    # Store in DB
    async with aiosqlite.connect(DB_FILE) as db_conn:
        session_id = await get_last_session_id(db_conn) or "unknown_session"
        timestamp = datetime.datetime.now().isoformat()
        face_file_name = os.path.basename(best_image_path)
        face_emotions_str = ", ".join(f"{k}: {v:.2f}" for k, v in face_emotions.items())

        await db_conn.execute('''
            INSERT INTO face_analysis (timestamp, session_id, face_file_name, face_emotions)
            VALUES (?, ?, ?, ?)
        ''', (timestamp, session_id, face_file_name, face_emotions_str))
        await db_conn.commit()
        logger.info(f"Saved face analysis: {face_file_name} => {face_emotions_str}")
