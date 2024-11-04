from fastapi import FastAPI, File, UploadFile
import cv2
import numpy as np
from datetime import datetime
import os
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Add CORS settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for testing; specify domains in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Set up directory for saving detected faces
DETECTED_FACE_DIR = "detected_faces"
INCOMING_FRAME_DIR = "incoming_frames"
if not os.path.exists(DETECTED_FACE_DIR):
    os.makedirs(DETECTED_FACE_DIR)
if not os.path.exists(INCOMING_FRAME_DIR):
    os.makedirs(INCOMING_FRAME_DIR)

@app.post("/detect_face")
async def detect_face(file: UploadFile = File(...)):
    # Read the image file
    image_data = await file.read()
    np_array = np.frombuffer(image_data, np.uint8)
    image = cv2.imdecode(np_array, cv2.IMREAD_COLOR)
    
    # Save the incoming frame to verify its quality and dimensions
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    incoming_frame_path = os.path.join(INCOMING_FRAME_DIR, f"incoming_frame_{timestamp}.png")
    cv2.imwrite(incoming_frame_path, image)
    print(f"Saved incoming frame for verification at {incoming_frame_path}")

    # Convert to grayscale for face detection
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    
    # Load OpenCV's pre-trained Haar Cascade for face detection
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_alt2.xml")
    
    # Detect faces
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=3, minSize=(30, 30))
    print(f"Faces detected: {len(faces)}")  # Debugging statement

    if len(faces) > 0:
        # Save the first detected face image
        filename = f"face_detected_{timestamp}.png"
        save_path = os.path.join(DETECTED_FACE_DIR, filename)
        cv2.imwrite(save_path, image)
        print(f"Image saved at {save_path}")  # Debugging statement
        return {"face_detected": True, "filename": filename}
    else:
        print("No face detected in the image")  # Debugging statement
        return {"face_detected": False}