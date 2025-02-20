import os
import sqlite3
import cv2
import time
import base64
import asyncio
import pandas as pd
import nest_asyncio
from flask import Flask, render_template, request, redirect, session
from datetime import datetime
from pathlib import Path
from PIL import Image
from hume import AsyncHumeClient
from hume.expression_measurement.stream import Config
from hume.expression_measurement.stream.socket_client import StreamConnectOptions
from hume.expression_measurement.stream.types import StreamFace
from config import SECRET_KEY
from env_keys import get_hume_api_key

# Apply nest_asyncio for Flask async compatibility
nest_asyncio.apply()

last_insert_time = 0

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY

# Debugging logs
print("🚀 Application is starting...")

# Ensure pandas and numpy versions are compatible
import numpy as np
print(f"✅ Pandas Version: {pd.__version__}, Numpy Version: {np.__version__}")

# Ensure correct Python version
import sys
print(f"✅ Python Version: {sys.version}")

# Load admin usernames from file
def load_admin_usernames():
    admin_file_path = os.path.join(os.getcwd(), 'admin.txt')
    if os.path.exists(admin_file_path):
        with open(admin_file_path, 'r') as file:
            return [line.strip() for line in file if line.strip()]
    return []

admin_usernames = load_admin_usernames()
print(f"✅ Admin Usernames Loaded: {admin_usernames}")

# Create SQLite database if it doesn't exist
DB_PATH = "users.db"

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
c = conn.cursor()
c.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        login_timestamp TEXT,
        initial_mood TEXT,
        session_id TEXT,
        UNIQUE(username, login_timestamp, session_id)
    )
''')
conn.commit()
print(f"✅ Database Initialized: {DB_PATH}")

columns = ['Username', 'Initial Mood', 'Timestamp']
columns = list(columns)  # Ensure it is a list, not an ndarray
print(f"🛠 Debug: Columns type: {type(columns)}, Content: {columns}")

try:
    mood_df = pd.DataFrame(columns=columns)
    print(f"✅ DataFrame initialized successfully. Shape: {mood_df.shape}")
except Exception as e:
    print(f"❌ DataFrame Initialization Error: {e}")
    raise



@app.route('/')
def index():
    return render_template('login.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    global last_insert_time
    if request.method == 'POST':
        username = request.form['username']
        print(f"🛠 Attempting login for user: {username}")

        if username in admin_usernames:
            session['username'] = username
            login_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            session_id = str(int(time.time()))
            session['session_id'] = session_id
            session['login_timestamp'] = login_timestamp

            current_time = time.time()
            if current_time - last_insert_time >= 3:
                try:
                    # Delete previous pending records
                    c.execute("DELETE FROM users WHERE username = ? AND initial_mood = 'Pending'", (username,))
                    conn.commit()

                    # Insert a new record with "Pending" mood
                    c.execute("""
                        INSERT INTO users (username, login_timestamp, initial_mood, session_id)
                        VALUES (?, ?, ?, ?)
                    """, (username, login_timestamp, 'Pending', session_id))
                    conn.commit()
                    last_insert_time = current_time
                    print(f"✅ User {username} logged in at {login_timestamp} with Pending mood.")
                except sqlite3.Error as e:
                    print(f"❌ Database Error: {e}")

            # Capture face after inserting pending mood
            capture_face(username)

            return redirect("http://localhost:3000")  # Redirect to Next.js app
        else:
            return "Invalid username. Please try again."
    
    return render_template('login.html')


# Function to encode an image into base64
def encode_image(image_path: str):
    with open(image_path, 'rb') as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')


# Function to process face with Hume AI
async def process_face(image_path: str, username: str):
    client = AsyncHumeClient(api_key=get_hume_api_key())
    model_config = Config(face=StreamFace())
    stream_options = StreamConnectOptions(config=model_config)

    async with client.expression_measurement.stream.connect(options=stream_options) as socket:
        encoded_image = encode_image(image_path)
        result = await socket.send_file(encoded_image)

        face_predictions = result.face.predictions if result.face else None
        if face_predictions:
            emotions_sorted = sorted(face_predictions[0].emotions, key=lambda e: e.score, reverse=True)
            top_5_emotions = [(e.name, e.score) for e in emotions_sorted[:5]]
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Store mood in DataFrame
            global mood_df
            top_5_emotions_str = ', '.join([f"{name}: {score:.2f}" for name, score in top_5_emotions])
            new_row = pd.DataFrame([{'Username': username, 'Initial Mood': top_5_emotions_str, 'Timestamp': timestamp}])
            mood_df = pd.concat([mood_df, new_row], ignore_index=True)
            print(f"✅ Emotions for {username}: {top_5_emotions_str}")

        else:
            print("❌ No face detected. Retrying...")

        # Update database with mood
        save_face_analysis_to_db(username, top_5_emotions_str)
        return mood_df


# Capture face using OpenCV
def capture_face(username):
    cap = cv2.VideoCapture(0)
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

    start_time = time.time()
    timeout = 20  # Timeout in seconds

    while True:
        ret, frame = cap.read()
        if not ret:
            print("❌ Failed to capture frame.")
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)

        if len(faces) > 0:

            # Ensure directory exists
            os.makedirs("uploaded_images", exist_ok=True)

            filename = "uploaded_images/captured_face.png"
            cv2.imwrite(filename, frame)

            # Verify file is actually saved
            if not os.path.exists(filename):
                print(f"❌ Error: Failed to save image at {filename}")
            else:
                print(f"✅ Face image successfully saved at {filename}")

            print(f"✅ Face image saved: {filename}")

            loop = asyncio.get_event_loop()
            mood_df = loop.run_until_complete(process_face(filename, username))

            if len(mood_df) > 0:
                break
        else:
            print("🔄 No face detected. Retrying...")

        if time.time() - start_time > timeout:
            print("❌ Timeout: No face detected.")
            break

    cap.release()
    cv2.destroyAllWindows()


# Save mood analysis to database
def save_face_analysis_to_db(username, initial_mood):
    login_timestamp = session.get('login_timestamp')
    session_id = session.get('session_id')

    try:
        c.execute("UPDATE users SET initial_mood = ? WHERE username = ? AND login_timestamp = ? AND session_id = ?",
                  (initial_mood, username, login_timestamp, session_id))
        conn.commit()
        print(f"✅ Mood updated for {username}: {initial_mood}")

        # Remove captured face image
        file_path = 'uploaded_images/captured_face.png'
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"🗑 Deleted captured face image: {file_path}")

    except sqlite3.Error as e:
        print(f"❌ Error updating database: {e}")


if __name__ == '__main__':
    app.run(debug=True)
