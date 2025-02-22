import os
import asyncio
import logging
from aiohttp import web
import aiohttp_cors

from config import UPLOAD_DIR, PROCESSED_DIR, IMAGE_DIR
from database import initialize_db
from audio_handling import handle_audio_upload
from image_handling import handle_image_upload

# Ensure directories exist
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(PROCESSED_DIR, exist_ok=True)
os.makedirs(IMAGE_DIR, exist_ok=True)


# -------------------- Server Setup --------------------

async def init_app():
    await initialize_db()
    app = web.Application()

    # CORS
    cors = aiohttp_cors.setup(app, defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
            allow_methods="*",
        )
    })

    app.router.add_post("/upload_audio", handle_audio_upload)
    app.router.add_post("/upload_image", handle_image_upload)

    # Enable CORS for all routes
    for route in list(app.router.routes()):
        cors.add(route)

    return app

if __name__ == "__main__":
    web.run_app(init_app(), port=8000)
