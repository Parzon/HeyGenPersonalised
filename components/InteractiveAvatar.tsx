"use client";

import React, { useEffect, useRef, useState } from 'react';
import axios from 'axios';

const InteractiveAvatar = () => {
  // ------------------------ AUDIO LOGIC (UNCHANGED) ------------------------
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const [audioCounter, setAudioCounter] = useState(1);
  const [timestamp] = useState(new Date().toISOString().replace(/[-:T]/g, '').split('.')[0]);
  const chunksRef = useRef<Blob[]>([]);
  const isRecordingRef = useRef<boolean>(false);

  useEffect(() => {
    let mediaRecorder: MediaRecorder;

    navigator.mediaDevices.getUserMedia({ audio: true })
      .then((stream) => {
        mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
        mediaRecorderRef.current = mediaRecorder;

        mediaRecorder.ondataavailable = function (e) {
          if (e.data.size > 0) {
            chunksRef.current.push(e.data);
          }
        };

        mediaRecorder.onstop = function () {
          // Combine chunks into a Blob
          const blob = new Blob(chunksRef.current, { type: 'audio/webm' });
          chunksRef.current = []; // Reset chunks

          // Generate filename with timestamp and audio counter
          const currentCount = audioCounter;
          const filename = `${timestamp}_${currentCount}.webm`;

          // Send audio chunk and update the counter only after successful upload
          sendAudioChunk(blob, filename)
            .then(() => {
              setAudioCounter(prev => prev + 1); // Increment after success
              // Restart recording immediately
              startRecording();
            })
            .catch((error: Error) => {
              console.error("Error uploading audio chunk:", error);
              // Even if upload fails, restart recording
              startRecording();
            });
        };

        // Start the 5-second recording loop
        startRecording();
      })
      .catch((err: Error) => {
        console.error('Error accessing microphone', err);
      });

    return () => {
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop();
      }
    };
  }, []);

  const startRecording = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'inactive') {
      mediaRecorderRef.current.start();
      isRecordingRef.current = true;
      // Stop recording after 5 seconds
      setTimeout(() => {
        if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
          mediaRecorderRef.current.stop();
          isRecordingRef.current = false;
        }
      }, 5000);
    }
  };

  const sendAudioChunk = async (audioBlob: Blob, filename: string) => {
    const formData = new FormData();
    formData.append('file', audioBlob, filename);

    try {
      const response = await axios.post('http://localhost:8000/upload_audio', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });
      console.log('Audio uploaded successfully', response.data);
    } catch (error) {
      console.error('Error uploading audio', error);
      throw error; // Re-throw error to handle in the calling function
    }
  };

  // ---------------------- IMAGE LOGIC (ADDED, ONLY 5-MIN CHANGE) ----------------------
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [imageCounter, setImageCounter] = useState(1);

  useEffect(() => {
    let videoStream: MediaStream | null = null;

    // Request video only
    navigator.mediaDevices.getUserMedia({ video: true })
      .then((stream) => {
        videoStream = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
        }
        // Wait 5 minutes, then start capturing images (instead of 2 minutes)
        setTimeout(() => {
          console.log("⏰ 5 minutes passed. Starting image capture...");
          startCapturingImages();
        }, 180000); // 300,000 ms = 5 minutes
      })
      .catch((err) => {
        console.error("Error accessing camera", err);
      });

    return () => {
      if (videoStream) {
        videoStream.getTracks().forEach((track) => track.stop());
      }
    };
  }, []);

  const startCapturingImages = () => {
    let imagesCaptured = 0;
    const maxImages = 20;
    const captureIntervalMS = 1500; // capture one image every 1.5s

    const captureInterval = setInterval(() => {
      if (imagesCaptured >= maxImages) {
        clearInterval(captureInterval);
        console.log("✅ Stopped image capture after 40 images.");
        return;
      }
      captureAndSendImage();
      imagesCaptured++;
    }, captureIntervalMS);
  };

  const captureAndSendImage = async () => {
    if (!videoRef.current || !canvasRef.current) return;

    const ctx = canvasRef.current.getContext("2d");
    if (!ctx) return;

    // Copy current video frame
    canvasRef.current.width = videoRef.current.videoWidth;
    canvasRef.current.height = videoRef.current.videoHeight;
    ctx.drawImage(videoRef.current, 0, 0);

    const blob = await new Promise<Blob | null>((resolve) =>
      canvasRef.current!.toBlob(resolve, "image/jpeg", 0.95)
    );
    if (!blob) return;

    const filename = `${Date.now()}_${imageCounter}_image.jpg`;
    try {
      await sendImage(blob, filename);
      setImageCounter((prev) => prev + 1);
    } catch (err) {
      console.error("Error uploading image:", err);
    }
  };

  const sendImage = async (imageBlob: Blob, filename: string) => {
    const formData = new FormData();
    formData.append("file", imageBlob, filename);

    const response = await axios.post("http://localhost:8000/upload_image", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    console.log("Image uploaded successfully:", response.data);
  };

  return (
    <div>
      <p>Recording in progress (audio)... Images will start after 5 minutes, capture 40, then stop.</p>

      {/* Hidden video & canvas for capturing images */}
      <video ref={videoRef} autoPlay playsInline style={{ display: "none" }} />
      <canvas ref={canvasRef} style={{ display: "none" }} />
    </div>
  );
};

export default InteractiveAvatar;
