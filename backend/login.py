import os
import sqlite3
from flask import Flask, render_template, request, redirect, session
import cv2
from datetime import datetime
import time
import base64
import asyncio
from pathlib import Path
from PIL import Image
from hume import AsyncHumeClient
from hume.expression_measurement.stream import Config
from hume.expression_measurement.stream.socket_client import StreamConnectOptions
from hume.expression_measurement.stream.types import StreamFace
from config import SECRET_KEY
from env_keys import get_hume_api_key
import nest_asyncio
import pandas as pd

# Apply nest_asyncio to allow running asyncio event loop in Flask
nest_asyncio.apply()

app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY

# Load admin usernames from the admin.txt file
def load_admin_usernames():
    admin_file_path = '/Users/Parzon/Downloads/Artificial_Consciousness/InteractiveAvatarNextJSDemo-main/HeyGenPersonalised/backend/admin.txt'
    if os.path.exists(admin_file_path):
        with open(admin_file_path, 'r') as file:
            return [line.strip() for line in file if line.strip()]  # Strip whitespace and ignore empty lines
    return []

admin_usernames = load_admin_usernames()

# Create SQLite database if it doesn't exist
conn = sqlite3.connect('users.db', check_same_thread=False)
c = conn.cursor()
c.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        login_timestamp TEXT,
        initial_mood TEXT,  -- Column for storing facial gesture analysis result
        session_id TEXT,
        UNIQUE(username, login_timestamp, session_id)  -- Ensure the combination is unique
    )
''')
conn.commit()

# Initialize a DataFrame to store the initial mood
columns = ['Username', 'Initial Mood', 'Timestamp']
mood_df = pd.DataFrame(columns=columns)

last_insert_time = 0  # Track last insert time for controlling interval

@app.route('/')
def index():
    return render_template('login.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    global last_insert_time
    if request.method == 'POST':
        username = request.form['username']
        print(f"Attempting to log in with username: {username}")  # Debug statement
        print(f"Admin usernames loaded: {admin_usernames}")  # Debug statement
        
        if username in admin_usernames:
            session['username'] = username  # Store username in session
            
            # Get current timestamp and session ID
            login_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            session_id = str(int(time.time()))  # Generate a unique session ID based on the current time
            session['session_id'] = session_id  # Store session ID in session
            session['login_timestamp'] = login_timestamp  # Store login_timestamp in session

            # Insert the record with "Pending" mood if enough time has passed (3 seconds)
            current_time = time.time()
            if current_time - last_insert_time >= 3:
                try:
                    # Delete any existing "Pending" mood record for the user
                    c.execute("DELETE FROM users WHERE username = ? AND initial_mood = 'Pending'", (username,))
                    conn.commit()  # Commit the delete operation
                    
                    # Insert the new record with "Pending" mood initially
                    c.execute("""
                        INSERT INTO users (username, login_timestamp, initial_mood, session_id)
                        VALUES (?, ?, ?, ?)
                    """, (username, login_timestamp, 'Pending', session_id))
                    conn.commit()  # Ensure changes are committed
                    last_insert_time = current_time  # Update the last insert time
                    print(f"Inserting new record for {username} at {login_timestamp} with Pending mood")
                except sqlite3.Error as e:
                    print(f"Error saving face analysis: {e}")

            # Now capture the face after inserting 'Pending' mood
            capture_face(username)
            
            return redirect("http://localhost:3000")  # Redirect to the Next.js application
        else:
            return "Invalid username. Please try again."
    return render_template('login.html')

# Function to base64 encode the image
def encode_image(image_path: str):
    with open(image_path, 'rb') as image_file:
        encoded_image = base64.b64encode(image_file.read()).decode('utf-8')
    return encoded_image

# Function to process face and get results from Hume
async def process_face(image_path: str, username: str):
    client = AsyncHumeClient(api_key=get_hume_api_key())  # Use your actual Hume API key

    model_config = Config(face=StreamFace())
    stream_options = StreamConnectOptions(config=model_config)

    # Using the async context manager to manage the connection
    async with client.expression_measurement.stream.connect(options=stream_options) as socket:
        encoded_image = encode_image(image_path)
        
        # Sending the base64-encoded image to Hume's API for analysis
        result = await socket.send_file(encoded_image)  # Use send_file to send image data
        
        print("Result received from Hume: ", result)

        # Directly access 'face' and 'predictions' attributes
        face_predictions = result.face.predictions if result.face else None

        if face_predictions:
            # Extract emotions from predictions and sort by score
            emotions = face_predictions[0].emotions if face_predictions else []
            emotions_sorted = sorted(emotions, key=lambda e: e.score, reverse=True)  # Sort by score descending
            
            # Get the top 5 emotions with their scores
            top_5_emotions = [(e.name, e.score) for e in emotions_sorted[:5]]  # List of tuples (emotion, score)
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Store the username, initial mood (emotions and scores), and timestamp in the DataFrame
            global mood_df
            top_5_emotions_str = ', '.join([f"{name}: {score:.2f}" for name, score in top_5_emotions])  # Format emotions with scores
            new_row = pd.DataFrame([{'Username': username, 'Initial Mood': top_5_emotions_str, 'Timestamp': timestamp}])
            mood_df = pd.concat([mood_df, new_row], ignore_index=True)
            print(f"Top 5 Emotions for {username}: {top_5_emotions_str} recorded at {timestamp}")
        else:
            print("No face detected. Retrying...")

        # Update the mood in the database as well
        save_face_analysis_to_db(username, top_5_emotions_str)

        return mood_df  # Return the updated DataFrame with the initial mood

# Function to start the camera and capture the image until a face is detected
def capture_face(username):
    cap = cv2.VideoCapture(0)

    # Load the Haar cascade for face detection
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

    start_time = time.time()  # Record the start time
    timeout = 20  # Timeout in seconds

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Failed to capture frame. Exiting...")
            break

        # Convert the frame to grayscale for face detection
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Detect faces in the frame
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)

        # Check if any faces are detected
        if len(faces) > 0:
            for (x, y, w, h) in faces:
                cv2.rectangle(frame, (x, y), (x + w, y + h), (255, 0, 0), 2)

            # Save the captured frame
            filename = f"uploaded_images/captured_face.png"
            cv2.imwrite(filename, frame)

            # Process the captured image using Hume's API
            print(f"Captured face image saved as: {filename}")
            loop = asyncio.get_event_loop()
            mood_df = loop.run_until_complete(process_face(filename, username))  # Process the face and get emotions

            # If face is detected and processed, break the loop
            if len(mood_df) > 0:
                break
        else:
            print("No face detected. Trying again...")

        # Check if 20 seconds have passed
        if time.time() - start_time > timeout:
            print("Timeout reached. No face detected.")
            break

    cap.release()
    cv2.destroyAllWindows()  # Ensure all OpenCV windows are closed

def save_face_analysis_to_db(username, initial_mood):
    login_timestamp = session.get('login_timestamp')
    session_id = session.get('session_id')
    
    try:
        # Update the mood in the database using consistent timestamp and session ID
        c.execute("UPDATE users SET initial_mood = ? WHERE username = ? AND login_timestamp = ? AND session_id = ?",
                  (initial_mood, username, login_timestamp, session_id))
        conn.commit()  # Ensure changes are committed
        print(f"Updated mood for {username} at {login_timestamp} with {initial_mood}")
        
    except sqlite3.Error as e:
        print(f"Error saving face analysis: {e}")

if __name__ == '__main__':
    app.run(debug=True)
