import os
import sqlite3
from flask import Flask, render_template, request, redirect, session
import cv2
from datetime import datetime
import time
from config import SECRET_KEY

app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY

# Load admin usernames from the admin.txt file
def load_admin_usernames():
    if os.path.exists('/Users/Parzon/Downloads/Artificial_Consciousness/InteractiveAvatarNextJSDemo-main/HeyGenPersonalised/backend/admin.txt'):
        with open('/Users/Parzon/Downloads/Artificial_Consciousness/InteractiveAvatarNextJSDemo-main/HeyGenPersonalised/backend/admin.txt', 'r') as file:
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
        UNIQUE(username, login_timestamp)  -- Ensure the combination is unique
    )
''')
conn.commit()

@app.route('/')
def index():
    return render_template('login.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        print(f"Attempting to log in with username: {username}")  # Debug statement
        print(f"Admin usernames loaded: {admin_usernames}")  # Debug statement
        if username in admin_usernames:  
            session['username'] = username  # Store username in session
            capture_face()  # Capture the face after successful login
            return redirect("http://localhost:3000")  # Redirect to the Next.js application
        else:
            return "Invalid username. Please try again."
    return render_template('login.html')

def capture_face():
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

        # Convert the frame to grayscale for the face detection
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
            print(f"Captured face image saved as: {filename}")

            # Log the login time in the SQLite database with timestamp
            username = session.get('username')
            if username:
                login_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                try:
                    c.execute("INSERT INTO users (username, login_timestamp) VALUES (?, ?)", 
                              (username, login_timestamp))
                    conn.commit()
                except sqlite3.IntegrityError:
                    print("This entry already exists.")

            break  # Exit loop after capturing the face
        else:
            print("No face detected. Trying again...")

        # Check if 20 seconds have passed
        if time.time() - start_time > timeout:
            print("Timeout reached. No face detected.")
            break

        # Optionally, save or log the frame without displaying it
        cv2.imwrite("uploaded_images/frame_temp.png", frame)  # For debugging purposes, you can save a temp frame

    cap.release()
    cv2.destroyAllWindows()  # Ensure all OpenCV windows are closed
    
if __name__ == '__main__':
    app.run(debug=True)
