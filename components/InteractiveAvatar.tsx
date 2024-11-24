"use client";

import React, { useEffect, useRef, useState } from 'react';
import axios from 'axios';

const InteractiveAvatar = () => {
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
              setAudioCounter(prev => prev + 1); // Increment the counter only after a successful upload
              // Restart recording immediately
              startRecording();
            })
            .catch((error: Error) => {
              console.error("Error uploading audio chunk:", error);
              // Optionally, handle retry logic here
              // Restart recording even if upload fails
              startRecording();
            });
        };

        // Start the recording loop
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
      console.log('Audio uploaded successfully', response);
    } catch (error) {
      console.error('Error uploading audio', error);
      throw error; // Re-throw error to handle in the calling function
    }
  };

  return (
    <div>
      <p>Recording in progress...</p>
    </div>
  );
};

export default InteractiveAvatar;
