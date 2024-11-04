"use client";

import React, { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import Recorder from 'recorder-js';

const InteractiveAvatar = () => {
  const recorderRef = useRef<Recorder | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const [audioCounter, setAudioCounter] = useState(1);
  const [timestamp] = useState(new Date().toISOString().replace(/[-:T]/g, '').split('.')[0]);

  useEffect(() => {
    navigator.mediaDevices.getUserMedia({ audio: true })
      .then((stream) => {
        audioContextRef.current = new AudioContext();
        recorderRef.current = new Recorder(audioContextRef.current, {
          onAnalysed: (data: any) => {
            console.log("Audio analysis data:", data);
          },
        });
        recorderRef.current.init(stream);
        startRecording();
      })
      .catch((err: Error) => {
        console.error('Error accessing microphone', err);
      });

    return () => {
      if (recorderRef.current) {
        recorderRef.current.stop();
      }
    };
  }, []);

  const startRecording = () => {
    recorderRef.current?.start()
      .then(() => {
        console.log("Recording started...");
        setTimeout(stopRecording, 4500); // Record for 5 seconds
      });
  };

  const stopRecording = () => {
    recorderRef.current?.stop()
      .then(({ blob }: { blob: Blob }) => {
        console.log("Recording stopped...");

        // Generate filename with timestamp and audio counter
        const currentCount = audioCounter;
        const filename = `${timestamp}_${currentCount}.wav`;

        // Send audio chunk and update the counter only after successful upload
        sendAudioChunk(blob, filename)
          .then(() => {
            setAudioCounter(prev => prev + 1); // Increment the counter only after a successful upload
            startRecording(); // Start the next recording
          });
      })
      .catch((error: Error) => {
        console.error("Error stopping recording:", error);
      });
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
      console.log('Audio uploaded successfully', response);
    } catch (error) {
      console.error('Error uploading audio', error);
    }
  };

  return (
    <div>
      <p>Recording in progress...</p>
    </div>
  );
};

export default InteractiveAvatar;