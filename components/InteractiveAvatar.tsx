"use client";

import React, { useEffect, useRef, useState } from "react";
import axios from "axios";

const InteractiveAvatar = () => {
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [audioCounter, setAudioCounter] = useState(1);
  const chunksRef = useRef<Blob[]>([]);
  const isRecordingRef = useRef<boolean>(false);
  const wsRef = useRef<WebSocket | null>(null);
  const [sessionId] = useState(() => `session_${Date.now()}`);

  useEffect(() => {
    let mediaRecorder: MediaRecorder;

    // Request camera and microphone access
    navigator.mediaDevices
      .getUserMedia({ audio: true, video: true })
      .then((stream) => {
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          videoRef.current.muted = true; // Prevents audio feedback
        }

        mediaRecorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
        mediaRecorderRef.current = mediaRecorder;

        mediaRecorder.ondataavailable = (e) => {
          if (e.data.size > 0) {
            chunksRef.current.push(e.data);
          }
        };

        mediaRecorder.onstop = async () => {
          const blob = new Blob(chunksRef.current, { type: "audio/webm" });
          chunksRef.current = [];
          const filename = `${sessionId}_${audioCounter}.webm`;

          await sendAudioChunk(blob, filename);
          setAudioCounter((prev) => prev + 1);
          startRecording(); // Restart recording
        };

        startRecording();
      })
      .catch((err) => console.error("Error accessing media devices", err));

    startWebSocketConnection();

    return () => {
      console.log("🔻 Cleaning up WebSocket & Media Stream...");
      if (mediaRecorderRef.current?.state !== "inactive") {
        mediaRecorderRef.current?.stop();
      }
      wsRef.current?.close(); // Close WebSocket on unmount
    };
  }, []);

  // Start recording audio
  const startRecording = () => {
    if (!mediaRecorderRef.current) return;
    if (mediaRecorderRef.current.state === "inactive") {
      mediaRecorderRef.current.start();
      isRecordingRef.current = true;
      setTimeout(() => {
        if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
          mediaRecorderRef.current.stop();
          isRecordingRef.current = false;
        }
      }, 4000);
    }
  };

  // Send audio chunk to backend
  const sendAudioChunk = async (audioBlob: Blob, filename: string) => {
    const formData = new FormData();
    formData.append("file", audioBlob, filename);
    formData.append("session_id", sessionId);

    try {
      const response = await axios.post("http://localhost:8000/upload_audio", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      console.log("✅ Audio uploaded successfully:", response.data);
    } catch (error) {
      console.error("🚨 Error uploading audio:", error);
    }
  };

  // WebSocket connection setup
  const startWebSocketConnection = () => {
    if (wsRef.current && wsRef.current.readyState !== WebSocket.CLOSED) {
      console.warn("⚠️ WebSocket already exists, skipping new connection.");
      return;
    }

    const websocket = new WebSocket("ws://localhost:8000/ws/video");
    wsRef.current = websocket;

    websocket.onopen = () => {
      console.log("✅ WebSocket connected");
    };

    websocket.onmessage = (event) => {
      console.log("📩 Server response:", event.data);
    };

    websocket.onerror = (error) => {
      console.error("🚨 WebSocket error:", error);
    };

    websocket.onclose = (event) => {
      console.log("❌ WebSocket closed", event);
      if (!event.wasClean) {
        console.warn("⚠️ WebSocket closed unexpectedly. Attempting reconnect...");
        setTimeout(startWebSocketConnection, 5000);
      }
    };
  };

  // Capture and send video frame to WebSocket
  const sendVideoFrame = () => {
    if (!videoRef.current || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      return;
    }

    // Debug logs
    console.log("Attempting to send a frame...");
    console.log("videoWidth:", videoRef.current.videoWidth, "videoHeight:", videoRef.current.videoHeight);

    const canvas = document.createElement("canvas");
    const context = canvas.getContext("2d");
    if (!context) {
      console.warn("Canvas 2D context not available");
      return;
    }

    canvas.width = videoRef.current.videoWidth;
    canvas.height = videoRef.current.videoHeight;
    context.drawImage(videoRef.current, 0, 0, canvas.width, canvas.height);

    canvas.toBlob((blob) => {
      if (blob) {
        console.log("Sending frame blob of size:", blob.size);
        wsRef.current?.send(blob);
      } else {
        console.warn("Canvas toBlob() returned null. Possibly 0x0 canvas dimensions?");
      }
    }, "image/png");
  };

  // Send video frames every 3 seconds
  useEffect(() => {
    const interval = setInterval(sendVideoFrame, 3000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div>
      <p>🎥 Recording & Streaming in progress...</p>
      <video
        ref={videoRef}
        autoPlay
        playsInline
        style={{ width: "320px", height: "auto" }}
      />
    </div>
  );
};

export default InteractiveAvatar;
