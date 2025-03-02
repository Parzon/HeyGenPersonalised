import { useEffect, useRef, useState } from "react";

const useWebSocket = () => {
  const [messages, setMessages] = useState<string[]>([]);
  const socket = useRef<WebSocket | null>(null);

  const connectWebSocket = () => {
    console.log("Attempting to connect to WebSocket...");
    socket.current = new WebSocket("ws://localhost:8000");

    socket.current.onopen = () => {
      console.log("Connected to the backend WebSocket");
    };

    socket.current.onmessage = (event) => {
      console.log("Received message:", event.data);
      setMessages((prevMessages) => [...prevMessages, event.data]);
    };

    socket.current.onerror = (error) => {
      console.error("WebSocket Error:", error);
    };

    socket.current.onclose = (event) => {
      console.log("WebSocket closed:", event);
      // Attempt to reconnect after 1 second if connection is closed unexpectedly
      setTimeout(connectWebSocket, 1000);
    };
  };

  useEffect(() => {
    connectWebSocket();

    // Cleanup function
    return () => {
      socket.current?.close();
    };
  }, []);

  const startRecording = async () => {
    console.log("Starting audio recording...");
    // Assuming useAudioRecorder is responsible for audio recording
    // Add your recording logic here if needed
  };

  return { messages, startRecording };
};

export default useWebSocket;
