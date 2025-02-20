"use client";

import React, { useEffect, useRef, useState } from "react";
import axios from "axios";

const InteractiveAvatar = () => {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [imageCounter, setImageCounter] = useState(1);
  const [timestamp] = useState(
    new Date().toISOString().replace(/[-:T]/g, "").split(".")[0]
  );
  const chunksRef = useRef<Blob[]>([]);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const isRecordingRef = useRef<boolean>(false);

  useEffect(() => {
    navigator.mediaDevices
      .getUserMedia({ video: true, audio: true })
      .then((stream) => {
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
        }

        mediaRecorderRef.current = new MediaRecorder(stream, {
          mimeType: "audio/webm",
        });

        mediaRecorderRef.current.ondataavailable = (e) => {
          if (e.data.size > 0) {
            chunksRef.current.push(e.data);
          }
        };

        mediaRecorderRef.current.onstop = () => {
          const audioBlob = new Blob(chunksRef.current, { type: "audio/webm" });
          chunksRef.current = [];
          const audioFilename = `${timestamp}_${imageCounter}_audio.webm`;
          sendAudioChunk(audioBlob, audioFilename);
          startRecording();
        };

        setTimeout(() => {
          console.log("📸 Starting image capture after 2 minutes...");
          startCapturingImages();
          startRecording();
        }, 120000); // 2 minutes delay
      })
      .catch((err: Error) => {
        console.error("❌ Error accessing webcam/microphone", err);
      });

    return () => {
      if (videoRef.current && videoRef.current.srcObject) {
        const tracks = (videoRef.current.srcObject as MediaStream).getTracks();
        tracks.forEach((track) => track.stop());
      }
    };
  }, []);

  const startCapturingImages = () => {
    let imagesCaptured = 0;
    const captureInterval = setInterval(() => {
      if (imagesCaptured >= 40) {
        clearInterval(captureInterval);
        console.log("✅ Stopped image capture after 40 images.");
        return;
      }

      captureAndSendImage();
      imagesCaptured++;
    }, 1500); // Capture image every 1.5 seconds
  };

  const captureAndSendImage = () => {
    if (!videoRef.current || !canvasRef.current) return;
  
    const context = canvasRef.current.getContext("2d");
    if (!context) return;
  
    // Draw
    canvasRef.current.width = videoRef.current.videoWidth;
    canvasRef.current.height = videoRef.current.videoHeight;
    context.drawImage(videoRef.current, 0, 0);
  
    canvasRef.current.toBlob(async (blob) => {
      if (blob) {
        // Generate a brand-new timestamp or random ID each capture
        const uniqueTimestamp = Date.now();  
        // or use uuid: const uniqueId = crypto.randomUUID();
        
        const filename = `${uniqueTimestamp}_${imageCounter}_image.jpg`;
  
        try {
          await sendImage(blob, filename);
          setImageCounter((prev) => prev + 1);
        } catch (err) {
          console.error("❌ Error uploading image:", err);
        }
      }
    }, "image/jpeg", 0.95);
  };
  

  const sendImage = async (imageBlob: Blob, filename: string) => {
    const formData = new FormData();
    formData.append("file", imageBlob, filename);

    try {
      const response = await axios.post("http://localhost:8000/upload_image", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      console.log("✅ Image uploaded successfully:", filename, response.data);
    } catch (error) {
      console.error("❌ Error uploading image", error);
      throw error;
    }
  };

  const startRecording = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === "inactive") {
      console.log("🎙️ Starting audio recording...");
      mediaRecorderRef.current.start();
      isRecordingRef.current = true;

      setTimeout(() => {
        if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
          console.log("🛑 Stopping audio recording...");
          mediaRecorderRef.current.stop();
          isRecordingRef.current = false;
        }
      }, 5000);
    }
  };

  const sendAudioChunk = async (audioBlob: Blob, filename: string) => {
    const formData = new FormData();
    formData.append("file", audioBlob, filename);

    try {
      const response = await axios.post("http://localhost:8000/upload_audio", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      console.log("✅ Audio uploaded successfully:", filename, response.data);
    } catch (error) {
      console.error("❌ Error uploading audio", error);
      throw error;
    }
  };

  return (
    <div>
      <p>Recording in progress...</p>
      <video ref={videoRef} autoPlay playsInline />
      <canvas ref={canvasRef} style={{ display: "none" }} />
    </div>
  );
};

export default InteractiveAvatar;
