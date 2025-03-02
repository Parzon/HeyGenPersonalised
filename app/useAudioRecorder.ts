import { useEffect, useRef, useState } from "react";

const useAudioRecorder = (socket: WebSocket | null) => {
  const [recording, setRecording] = useState(false);
  const [audioChunks, setAudioChunks] = useState<Blob[]>([]);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);

  useEffect(() => {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      console.error("Audio recording is not supported in this browser.");
    }
  }, []);

  const startRecording = async () => {
    setRecording(true);
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

    mediaRecorderRef.current = new MediaRecorder(stream);

    mediaRecorderRef.current.ondataavailable = (event) => {
      if (event.data.size > 0) {
        setAudioChunks((prevChunks) => [...prevChunks, event.data]);

        // Send the audio chunk immediately if socket is open
        if (socket && socket.readyState === WebSocket.OPEN) {
          socket.send(event.data);
        }
      }
    };

    mediaRecorderRef.current.start(1000); // Set timeslice to 1000ms to get chunks every 1 second
  };

  const stopRecording = () => {
    setRecording(false);
    mediaRecorderRef.current?.stop();
  };

  return { recording, startRecording, stopRecording, audioChunks };
};

export default useAudioRecorder;
