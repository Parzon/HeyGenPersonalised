"use client";

import React, { useEffect, useRef } from 'react';
import axios from 'axios';

const InteractiveAvatar = () => {
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  useEffect(() => {
    // Start recording when the component mounts
    navigator.mediaDevices.getUserMedia({ audio: true })
      .then((stream) => {
        const mediaRecorder = new MediaRecorder(stream);
        mediaRecorderRef.current = mediaRecorder;

        mediaRecorder.ondataavailable = (event) => {
          chunksRef.current.push(event.data);
        };

        mediaRecorder.onstop = () => {
          const blob = new Blob(chunksRef.current, { type: 'audio/webm' });
          sendAudioChunk(blob);
          chunksRef.current = []; // Clear after sending
        };

        // Start recording and send chunks every 5 seconds
        mediaRecorder.start();

        setInterval(() => {
          if (mediaRecorder.state === 'recording') {
            mediaRecorder.stop(); // Stop to collect the chunk
            mediaRecorder.start(); // Restart recording after stopping
          }
        }, 5000); // 5-second interval
      })
      .catch((err) => {
        console.error('Error accessing microphone', err);
      });
  }, []);

  const sendAudioChunk = (audioBlob: Blob) => {
    const formData = new FormData();
    const uniqueIdentifier = new Date().toISOString(); // Using timestamp to create a unique identifier
    formData.append('file', audioBlob, `audio_chunk_${uniqueIdentifier}.webm`);

    axios.post('http://localhost:8000/upload_audio', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    })
    .then((response: any) => {
      console.log('Audio uploaded successfully', response);
    })
    .catch((error: any) => {
      console.error('Error uploading audio', error);
    });
  };

  return (
    <div>
      <p>Recording in progress...</p>
    </div>
  );
};

export default InteractiveAvatar;
