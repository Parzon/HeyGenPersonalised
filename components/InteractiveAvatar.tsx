"use client";

import React, { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import Recorder from 'recorder-js';

interface FaceDetectionResponse {
  face_detected: boolean;
  filename?: string;
}

interface AnalysisResponse {
  emotion_analysis?: string;
  background_analysis?: string;
}

const InteractiveAvatar = () => {
  const [faceDetected, setFaceDetected] = useState(false);
  const [analysisResults, setAnalysisResults] = useState<AnalysisResponse>({});
  const recorderRef = useRef<Recorder | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const audioStreamRef = useRef<MediaStream | null>(null); // Reference for audio stream

  useEffect(() => {
    console.log("useEffect triggered: Starting face detection.");
    startFaceDetection();

    return () => {
      stopVideoStream();
      stopAudioStream(); // Stop audio stream on component unmount
    };
  }, []);

  const startFaceDetection = async () => {
    console.log("Face detection function started.");
    
    // Initialize the video stream
    streamRef.current = await navigator.mediaDevices.getUserMedia({ video: true });
    videoRef.current!.srcObject = streamRef.current;
    videoRef.current!.play();

    const faceDetectionInterval = setInterval(async () => {
      const canvas = document.createElement("canvas");
      canvas.width = videoRef.current!.videoWidth;
      canvas.height = videoRef.current!.videoHeight;
      const context = canvas.getContext("2d");

      if (context) {
        context.drawImage(videoRef.current!, 0, 0, canvas.width, canvas.height);
        console.log("Image captured from video stream.");

        const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/png", 1.0));

        if (blob) {
          console.log("Blob created from canvas. Preparing to send to backend.");
          
          const formData = new FormData();
          formData.append("file", blob);

          try {
            const response = await axios.post<FaceDetectionResponse>("http://localhost:8000/detect_face", formData);

            if (response.data.face_detected) {
              clearInterval(faceDetectionInterval);
              setFaceDetected(true);
              console.log(`Face detected and saved as ${response.data.filename}`);
              stopVideoStream();
              sendImageForAnalysis(response.data.filename);
              startAudioRecording();
            } else {
              console.log("No face detected in this frame.");
            }
          } catch (error) {
            console.error("Error during face detection request:", error);
          }
        } else {
          console.error("Failed to capture image from canvas.");
        }
      } else {
        console.error("Canvas context not available.");
      }
    }, 2000); // Capture frame every 2 seconds
  };

  const stopVideoStream = () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop());
      videoRef.current!.srcObject = null; // Clear video source
      streamRef.current = null; // Release video stream
      console.log("Video stream stopped and tracks released.");
    }
  };

  const startAudioRecording = () => {
    audioContextRef.current = new AudioContext();
    recorderRef.current = new Recorder(audioContextRef.current, {
      onAnalysed: (data: any) => {
        console.log("Audio analysis data:", data);
      },
    });

    navigator.mediaDevices.getUserMedia({ audio: true }).then((stream) => {
      audioStreamRef.current = stream; // Store the audio stream reference
      recorderRef.current?.init(stream);
      recorderRef.current?.start()
        .then(() => {
          console.log("Audio recording started...");
        });
    }).catch((error) => {
      console.error("Error accessing microphone:", error);
    });
  };

  const stopAudioStream = () => {
    if (recorderRef.current) {
      recorderRef.current.stop().then(() => {
        console.log("Audio recording stopped.");
      }).catch((error) => {
        console.error("Error stopping audio recorder:", error);
      });
    }

    if (audioStreamRef.current) {
      audioStreamRef.current.getTracks().forEach(track => track.stop()); // Stop the audio track
      audioStreamRef.current = null; // Release audio stream
      console.log("Audio stream stopped and tracks released.");
    }

    if (audioContextRef.current) {
      audioContextRef.current.close().then(() => {
        console.log("Audio context closed.");
      }).catch((error) => {
        console.error("Error closing audio context:", error);
      });
      audioContextRef.current = null;
    }
  };

  const sendImageForAnalysis = async (filename: string | undefined) => {
    if (!filename) {
      console.error("Filename is undefined, cannot proceed with analysis.");
      return;
    }
    try {
      const response = await axios.post<AnalysisResponse>("http://localhost:8000/analyze_image", { filename });
      setAnalysisResults(response.data);
      console.log("Image sent for analysis:", response.data);
    } catch (error) {
      console.error("Error sending image for analysis:", error);
    }
  };

  return (
    <div>
      <video ref={videoRef} style={{ display: "none" }} /> {/* Hide the video element */}
      <p>{faceDetected ? "Face detected and processed. Audio recording started." : "Detecting face..."}</p>
      
      {/* Display the analysis results */}
      {analysisResults.emotion_analysis && (
        <div>
          <h3>Emotion Analysis:</h3>
          <p>{analysisResults.emotion_analysis}</p>
        </div>
      )}
      {analysisResults.background_analysis && (
        <div>
          <h3>Background Analysis:</h3>
          <p>{analysisResults.background_analysis}</p>
        </div>
      )}
    </div>
  );
};

export default InteractiveAvatar;
