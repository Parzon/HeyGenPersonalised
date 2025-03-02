import os
import asyncio
import logging
from aiohttp import web
import aiohttp_cors

from config import UPLOAD_DIR, PROCESSED_DIR, IMAGE_DIR
from database import initialize_db
from audio_handling import handle_audio_upload
from image_handling import handle_image_upload

# main.py
import aiosqlite
from aiohttp import web

DB_FILE = "/Users/Parzon/Downloads/Artificial_Consciousness/InteractiveAvatarNextJSDemo-main/HeyGenPersonalised/users.db"

async def get_latest_ai_response(request):
    """
    Returns the most recent AI response as JSON.
    """
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute(
            "SELECT ai_response FROM conversation ORDER BY id DESC LIMIT 1"
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return web.json_response({"ai_response": row[0]})
            else:
                return web.json_response({"ai_response": ""})  # Ensure key always exists

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
    # Inside init_app() or wherever you define your routes:
    app.router.add_get("/latest_ai_response", get_latest_ai_response)

    # Enable CORS for all routes
    for route in list(app.router.routes()):
        cors.add(route)

    return app

async def create_app():
    return await init_app()
    
if __name__ == "__main__":
    web.run_app(asyncio.run(init_app()), port=8000)

