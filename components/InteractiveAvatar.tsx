"use client";

import React, { useEffect, useRef, useState } from "react";
import axios from "axios";

const InteractiveAvatar = () => {
  /* -------------------------
   *  SESSION & TIMESTAMPS
   * ------------------------*/
  const [sessionId] = useState(() => `session_${Date.now()}`); // ✅ Unique session ID
  const [audioCounter, setAudioCounter] = useState(1);

  /* -------------------------
   *  AUDIO RECORDING
   * ------------------------*/
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const isRecordingRef = useRef<boolean>(false);

  /* -------------------------
   *  VIDEO STREAMING
   * ------------------------*/
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  /* ***********************************************
   *      INITIALIZE AUDIO & VIDEO ON MOUNT
   *************************************************/
  useEffect(() => {
    console.log("🔹 Initializing audio & video streams...");
    startAudioRecording();
    startVideoStreaming();

    return () => {
      console.log("🔻 Cleaning up WebSocket & Media Stream...");
      mediaRecorderRef.current?.stop();
      wsRef.current?.close();
    };
  }, []);

  /* ***********************************************
   *            AUDIO: Setup and Loop
   *************************************************/
  const startAudioRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

      const mediaRecorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
      mediaRecorderRef.current = mediaRecorder;

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };

      mediaRecorder.onstop = async () => {
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        chunksRef.current = [];

        const filename = `${sessionId}_${audioCounter}.webm`;
        await sendAudioChunk(blob, filename);
        setAudioCounter((prev) => prev + 1);

        // Restart recording after upload
        mediaRecorderRef.current?.start();
        setTimeout(() => mediaRecorderRef.current?.stop(), 5000);
      };

      // Start first recording
      mediaRecorder.start();
      setTimeout(() => mediaRecorderRef.current?.stop(), 5000);
    } catch (error) {
      console.error("🚨 Error accessing microphone:", error);
    }
  };

  /* ***********************************************
   *            SEND AUDIO CHUNK
   *************************************************/
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

  /* ***********************************************
   *            VIDEO STREAMING + WS
   *************************************************/
  const startVideoStreaming = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true });
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        videoRef.current.muted = true;
      }
      startWebSocketConnection();
      setInterval(sendVideoFrame, 3000);
    } catch (error) {
      console.error("🚨 Error accessing camera:", error);
    }
  };

  const startWebSocketConnection = () => {
    if (wsRef.current && wsRef.current.readyState !== WebSocket.CLOSED) {
      console.warn("⚠️ WebSocket already exists, skipping new connection.");
      return;
    }
    const ws = new WebSocket("ws://localhost:8000/ws/video");
    wsRef.current = ws;

    ws.onopen = () => console.log("✅ WebSocket connected");
    ws.onmessage = (event) => console.log("📩 Server response:", event.data);
    ws.onerror = (error) => console.error("🚨 WebSocket error:", error);
    ws.onclose = (event) => {
      console.log("❌ WebSocket closed", event);
      if (!event.wasClean) setTimeout(startWebSocketConnection, 5000);
    };
  };

  /* ***********************************************
   *            SEND VIDEO FRAME
   *************************************************/
  const sendVideoFrame = () => {
    if (!videoRef.current || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      return;
    }

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

  /* ***********************************************
   *                   RENDER
   *************************************************/
  return (
    <div>
      <h3>🎤 Recording audio in 5-second chunks</h3>
      <p>Audio chunk #{audioCounter} in progress... (auto-upload every 5s)</p>
      <h3>🎥 Video streaming frames via WebSocket</h3>
      <video ref={videoRef} autoPlay playsInline style={{ width: "320px", height: "auto" }} />
    </div>
  );
};

export default InteractiveAvatar;
