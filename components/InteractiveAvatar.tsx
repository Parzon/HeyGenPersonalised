"use client";

// Type Imports
// External Libraries
import React, { useEffect, useRef, useState } from "react";
import axios from "axios";
import { useMemoizedFn, usePrevious } from "ahooks";
// UI Components
import {
  Button,
  Card,
  CardBody,
  CardFooter,
  Divider,
  Input,
  Select,
  SelectItem,
  Spinner,
  Chip,
  Tabs,
  Tab,
} from "@nextui-org/react";
// HeyGen SDK
import StreamingAvatar, {
  AvatarQuality,
  StreamingEvents,
  TaskType,
  VoiceEmotion,
} from "@heygen/streaming-avatar";

// Local Imports
import InteractiveAvatarTextInput from "./InteractiveAvatarTextInput";

import { AVATARS, STT_LANGUAGE_LIST } from "@/app/lib/constants";

const InteractiveAvatar = () => {
  // ---------------------- AI RESPONSE POLLING (UNCHANGED) ----------------------
  const [latestAIResponse, setLatestAIResponse] = useState<string>("");

  interface AIResponse {
    ai_response: string | null;
  }

  // Poll the backend every 3s for latest AI response
  useEffect(() => {
    const intervalId = setInterval(async () => {
      try {
        const res = await axios.get<AIResponse>(
          "http://localhost:8000/latest_ai_response",
        );

        if (res.data.ai_response) {
          setLatestAIResponse(res.data.ai_response);
        }
      } catch (err) {
        console.error("Error fetching latest AI response:", err);
      }
    }, 3000);

    return () => clearInterval(intervalId);
  }, []);

  // ---------------------- HEYGEN STREAMING AVATAR STATE ----------------------
  const [isLoadingSession, setIsLoadingSession] = useState(false);
  const [isLoadingRepeat, setIsLoadingRepeat] = useState(false);
  const [heygenStream, setHeygenStream] = useState<MediaStream>();
  const [debug, setDebug] = useState<string>();
  const [avatarId, setAvatarId] = useState<string>("");
  const [language, setLanguage] = useState<string>("en");
  //const [data, setData] = useState<StartAvatarResponse | null>(null);

  const mediaStreamRef = useRef<HTMLVideoElement>(null);
  const heygenAvatar = useRef<StreamingAvatar | null>(null);

  // If you want a text mode: user types text for the avatar to speak
  const [chatMode, setChatMode] = useState("text_mode");
  const [isUserTalking, setIsUserTalking] = useState(false);
  const [heygenText, setHeygenText] = useState<string>("");
  const previousText = usePrevious(heygenText);

  // ---------------------- AUDIO CAPTURE STATE ----------------------
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const [audioCounter, setAudioCounter] = useState(1);
  const [timestamp] = useState(
    new Date().toISOString().replace(/[-:T]/g, "").split(".")[0],
  );
  const chunksRef = useRef<Blob[]>([]);
  const isRecordingRef = useRef<boolean>(false);

  // ---------------------- IMAGE CAPTURE STATE ----------------------
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [imageCounter, setImageCounter] = useState(1);

  // 1) AFTER user finishes selecting fields and clicks "Start session",
  //    we initiate the audio logic.
  const initAudioProcess = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream, {
        mimeType: "audio/webm",
      });

      mediaRecorderRef.current = mediaRecorder;

      mediaRecorder.ondataavailable = function (e) {
        if (e.data.size > 0) {
          chunksRef.current.push(e.data);
        }
      };

      mediaRecorder.onstop = function () {
        // Combine chunks into a Blob
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });

        chunksRef.current = []; // Reset chunks

        // Generate filename with timestamp and audio counter
        const currentCount = audioCounter;
        const filename = `${timestamp}_${currentCount}.webm`;

        // Send audio chunk and update the counter only after successful upload
        sendAudioChunk(blob, filename)
          .then(() => {
            setAudioCounter((prev) => prev + 1); // Increment after success
            startRecording();
          })
          .catch((error: Error) => {
            console.error("Error uploading audio chunk:", error);
            // Even if upload fails, restart recording
            startRecording();
          });
      };

      // Kick off recording loop
      startRecording();
    } catch (err) {
      console.error("Error accessing microphone", err);
    }
  };

  // 2) AFTER user finishes selecting fields and clicks "Start session",
  //    we initiate the video logic. Then wait 5 min, capture images, etc.
  const initVideoProcess = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true });

      if (videoRef.current) {
        videoRef.current.srcObject = stream;
      }

      // After 5 minutes, start capturing images
      setTimeout(() => {
        console.log("⏰ 5 minutes passed. Starting image capture...");
        startCapturingImages();
      }, 300000 /* 5 minutes = 300000 ms */);
      // If you prefer 3 minutes, use 180000 ms
    } catch (err) {
      console.error("Error accessing camera", err);
    }
  };

  // ---------------------- AUDIO-RELATED FUNCTIONS (unchanged) ----------------------
  const startRecording = () => {
    if (
      mediaRecorderRef.current &&
      mediaRecorderRef.current.state === "inactive"
    ) {
      mediaRecorderRef.current.start();
      isRecordingRef.current = true;
      // Stop recording after 5 seconds
      setTimeout(() => {
        if (
          mediaRecorderRef.current &&
          mediaRecorderRef.current.state !== "inactive"
        ) {
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
      const response = await axios.post(
        "http://localhost:8000/upload_audio",
        formData,
        {
          headers: {
            "Content-Type": "multipart/form-data",
          },
        },
      );

      console.log("Audio uploaded successfully", response.data);
    } catch (error) {
      console.error("Error uploading audio", error);
      throw error;
    }
  };

  // ---------------------- IMAGE-RELATED FUNCTIONS (unchanged) ----------------------
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
      canvasRef.current!.toBlob(resolve, "image/jpeg", 0.95),
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

    const response = await axios.post(
      "http://localhost:8000/upload_image",
      formData,
      {
        headers: { "Content-Type": "multipart/form-data" },
      },
    );

    console.log("Image uploaded successfully:", response.data);
  };

  // ---------------------- HEYGEN AVATAR FUNCTIONS (avoid default LLM) ----------------------
  async function fetchAccessToken() {
    try {
      const response = await fetch("/api/get-access-token", { method: "POST" });
      const token = await response.text();

      console.log("Access Token:", token);

      return token;
    } catch (error) {
      console.error("Error fetching access token:", error);

      return "";
    }
  }

  // Called when user clicks "Start session"
  async function startSession() {
    setIsLoadingSession(true);

    // Wait for user token
    const newToken = await fetchAccessToken();

    // Instantiate the streaming avatar
    heygenAvatar.current = new StreamingAvatar({
      token: newToken,
    });

    // Listen to streaming events
    heygenAvatar.current.on(StreamingEvents.AVATAR_START_TALKING, (_event) => {
      console.log("Avatar started talking");
    });
    heygenAvatar.current.on(StreamingEvents.AVATAR_STOP_TALKING, (_event) => {
      console.log("Avatar stopped talking");
    });
    heygenAvatar.current.on(StreamingEvents.STREAM_DISCONNECTED, () => {
      console.log("Stream disconnected");
      endSession();
    });
    heygenAvatar.current?.on(StreamingEvents.STREAM_READY, (_event) => {
      console.log(">>>>> Stream ready:", _event.detail);
      setHeygenStream(_event.detail);
    });
    // ✅ Prevent HeyGen from activating voice mode
    heygenAvatar.current?.on(StreamingEvents.USER_START, (_event) => {
      console.log("❌ Ignoring voice mode activation");
      setIsUserTalking(false); // Ignore talking state
      setChatMode("text_mode"); // Force text mode
    });

    // ✅ Also ensure it stays in text mode when user stops talking
    heygenAvatar.current?.on(StreamingEvents.USER_STOP, (_event) => {
      console.log("✅ User stopped talking, keeping text mode");
      setIsUserTalking(false);
      setChatMode("text_mode");
    });

    try {
      await heygenAvatar.current.createStartAvatar({
        // If you have a custom or empty avatar ID, pass it.
        // If you want a full-body existing avatar from your account, pass that ID
        avatarName: avatarId,
        quality: AvatarQuality.Low,
        voice: {
          rate: 1.5,
          emotion: VoiceEmotion.EXCITED,
        },
        language,
        // knowledgeId: optional if you have a knowledge base
        // knowledgeBase: optional if you have your own data
      });

      setChatMode("text_mode"); // ✅ Force text mode
      console.log("🔇 Voice chat disabled, using text mode only");

      // Now that user is "done," we start audio & video processes:
      await initAudioProcess();
      await initVideoProcess();
    } catch (error: any) {
      console.error("Error starting avatar session:", error);
      setDebug(error.message);
    } finally {
      setIsLoadingSession(false);
    }
  }

  // Use text_mode to speak typed text (if desired)
  async function handleSpeak() {
    setIsLoadingRepeat(true);
    if (!heygenAvatar.current) {
      setDebug("Avatar API not initialized");
      setIsLoadingRepeat(false);

      return;
    }
    try {
      await heygenAvatar.current.speak({
        text: latestAIResponse,
        task_type: TaskType.REPEAT,
      });
    } catch (e: any) {
      setDebug(e.message);
    }
    setIsLoadingRepeat(false);
  }

  // Manually interrupt the current speaking task
  async function handleInterrupt() {
    if (!heygenAvatar.current) {
      setDebug("Avatar API not initialized");

      return;
    }
    try {
      await heygenAvatar.current.interrupt();
    } catch (e: any) {
      setDebug(e.message);
    }
  }

  // End session & cleanup
  async function endSession() {
    await heygenAvatar.current?.stopAvatar();
    setHeygenStream(undefined);
  }

  const handleChangeChatMode = useMemoizedFn(async (v: string) => {
    // ✅ Completely prevent switching to voice mode
    if (v !== "text_mode") return;

    heygenAvatar.current?.closeVoiceChat();
    console.log("✅ Forced Text Mode: Voice Disabled");
    setChatMode("text_mode");
  });

  // If user typed something in text_mode, start/stop listening
  useEffect(() => {
    if (!previousText && heygenText) {
      heygenAvatar.current?.startListening();
    } else if (previousText && !heygenText) {
      heygenAvatar.current?.stopListening();
    }
  }, [heygenText, previousText]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      endSession();
    };
  }, []);

  // Hook up the streaming video to HTML <video> element
  useEffect(() => {
    if (heygenStream && mediaStreamRef.current) {
      mediaStreamRef.current.srcObject = heygenStream;
      mediaStreamRef.current.onloadedmetadata = () => {
        mediaStreamRef.current!.play();
        setDebug("Playing");
      };
    }
  }, [heygenStream]);

  // Whenever `latestAIResponse` changes, make the avatar speak it automatically
  useEffect(() => {
    if (
      heygenAvatar.current &&
      latestAIResponse &&
      latestAIResponse.trim().length > 0
    ) {
      console.log("New AI Response Received:", latestAIResponse);

      // ✅ Ensure avatar is ALWAYS in text mode
      setChatMode("text_mode");

      // ✅ Force speaking the AI response automatically
      setHeygenText(latestAIResponse); // Updates the text box

      setTimeout(() => {
        heygenAvatar.current
          ?.speak({
            text: latestAIResponse,
            task_type: TaskType.REPEAT,
          })
          .catch((err) => console.error("Error speaking AI response:", err));
      }, 500); // Small delay to prevent race conditions
    }
  }, [latestAIResponse]);

  // ---------------------- RENDER UI ----------------------
  return (
    <div>
      {/* A simple text area about what's happening */}
      <p>
        <strong>Note:</strong> Audio and image capture now only start after you
        press <em>Start session</em>.
      </p>

      <h3>AI Response (auto-spoken by avatar):</h3>
      <div style={{ whiteSpace: "pre-wrap" }}>{latestAIResponse}</div>

      {/* hidden elements for image capturing */}
      <video ref={videoRef} autoPlay playsInline style={{ display: "none" }} />
      <canvas ref={canvasRef} style={{ display: "none" }} />

      {/* This is the HeyGen UI portion */}
      <div className="w-full flex flex-col gap-4 mt-4">
        <Card>
          <CardBody className="h-[500px] flex flex-col justify-center items-center">
            {heygenStream ? (
              <div className="h-[500px] w-[900px] flex rounded-lg overflow-hidden relative">
                <video
                  ref={mediaStreamRef}
                  autoPlay
                  playsInline
                  style={{
                    width: "100%",
                    height: "100%",
                    objectFit: "contain",
                  }}
                />
                <div className="flex flex-col gap-2 absolute bottom-3 right-3">
                  <Button
                    className="bg-gradient-to-tr from-indigo-500 to-indigo-300 text-white rounded-lg"
                    size="md"
                    variant="shadow"
                    onClick={handleInterrupt}
                  >
                    Interrupt
                  </Button>
                  <Button
                    className="bg-gradient-to-tr from-indigo-500 to-indigo-300 text-white rounded-lg"
                    size="md"
                    variant="shadow"
                    onClick={endSession}
                  >
                    End session
                  </Button>
                </div>
              </div>
            ) : !isLoadingSession ? (
              <div className="h-full flex flex-col gap-8 w-[500px] self-center justify-center items-center">
                <div className="flex flex-col gap-2 w-full">
                  <p className="text-sm font-medium leading-none">
                    Custom Avatar ID (optional)
                  </p>
                  <Input
                    placeholder="Enter a custom avatar ID"
                    value={avatarId}
                    onChange={(e) => setAvatarId(e.target.value)}
                  />

                  <Select
                    placeholder="Or select one from these example avatars"
                    size="md"
                    onChange={(e) => {
                      setAvatarId(e.target.value);
                    }}
                  >
                    {AVATARS.map((avatar) => (
                      <SelectItem
                        key={avatar.avatar_id}
                        textValue={avatar.avatar_id}
                      >
                        {avatar.name}
                      </SelectItem>
                    ))}
                  </Select>

                  <Select
                    className="max-w-xs"
                    label="Select language"
                    placeholder="Select language"
                    selectedKeys={[language]}
                    onChange={(e) => {
                      setLanguage(e.target.value);
                    }}
                  >
                    {STT_LANGUAGE_LIST.map((lang) => (
                      <SelectItem key={lang.key}>{lang.label}</SelectItem>
                    ))}
                  </Select>
                </div>

                {/* START SESSION BUTTON */}
                <Button
                  className="bg-gradient-to-tr from-indigo-500 to-indigo-300 w-full text-white"
                  size="md"
                  variant="shadow"
                  onClick={startSession}
                >
                  Start session
                </Button>
              </div>
            ) : (
              <Spinner color="default" size="lg" />
            )}
          </CardBody>

          <Divider />

          {/* FOOTER: Chat-mode selection */}
          <CardFooter className="flex flex-col gap-3 relative">
            <Tabs
              aria-label="Options"
              selectedKey={chatMode}
              onSelectionChange={(v) => {
                handleChangeChatMode(v as string);
              }}
            >
              <Tab key="text_mode" title="Text mode" />
              <Tab key="voice_mode" title="Voice mode" />
            </Tabs>

            {chatMode === "text_mode" ? (
              <div className="w-full flex relative">
                <InteractiveAvatarTextInput
                  disabled={!heygenStream}
                  input={heygenText}
                  label="Chat"
                  loading={isLoadingRepeat}
                  placeholder="Type text for the avatar to repeat"
                  setInput={setHeygenText}
                  onSubmit={handleSpeak}
                />
                {heygenText && (
                  <Chip className="absolute right-16 top-3">Listening</Chip>
                )}
              </div>
            ) : (
              <div className="w-full text-center">
                <Button
                  className="bg-gradient-to-tr from-indigo-500 to-indigo-300 text-white"
                  isDisabled={!isUserTalking}
                  size="md"
                  variant="shadow"
                >
                  {isUserTalking ? "Listening" : "Voice chat"}
                </Button>
              </div>
            )}
          </CardFooter>
        </Card>

        <p className="font-mono text-right">
          <span className="font-bold">Console:</span>
          <br />
          {debug}
        </p>
      </div>
    </div>
  );
};

export default InteractiveAvatar;
