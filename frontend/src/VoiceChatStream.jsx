import { useState, useRef, useEffect } from "react";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";

export default function VoiceChatStream() {
  const [isRecording, setIsRecording] = useState(false);
  const [userSpeaking, setUserSpeaking] = useState(false);
  const [userVolume, setUserVolume] = useState(0);

  const [avatarPlaying, setAvatarPlaying] = useState(false);
  const [avatarVolume, setAvatarVolume] = useState(0);
  const [avatarThinking, setAvatarThinking] = useState(false);

  const wsRef = useRef(null);

  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const userStreamRef = useRef(null);
  const userAnalyserRef = useRef(null);

  const avatarAudioRef = useRef(null);
  const avatarAnalyserRef = useRef(null);

  const pmBufferRef = useRef([]);
  const rafIdRef = useRef(null);

  // ─────────────────────────────────────────────────────────────
  // START STREAMING RECORDING
  // ─────────────────────────────────────────────────────────────
  const startRecording = async () => {
    // Create websocket
    wsRef.current = new WebSocket("wss://" + window.location.host + "/api/voice-chat-stream");
    wsRef.current.onmessage = handleWsMessage;

    // Wait until connected before starting to record
    await new Promise((resolve, reject) => {
      wsRef.current.onopen = () => {
        console.log("✅ WS connected");
        resolve();
      };
      wsRef.current.onerror = (e) => {
        console.error("❌ WebSocket error:", e);
        reject(e);
      };
    });

    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    userStreamRef.current = stream;

    mediaRecorderRef.current = new MediaRecorder(stream, {
      mimeType: "audio/webm",
    });
    audioChunksRef.current = [];

    /** Live volume meter */
    const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const source = audioCtx.createMediaStreamSource(stream);
    const analyser = audioCtx.createAnalyser();
    analyser.fftSize = 256;
    source.connect(analyser);
    userAnalyserRef.current = analyser;

    const dataArray = new Uint8Array(analyser.frequencyBinCount);

    const updateVolume = () => {
      analyser.getByteFrequencyData(dataArray);
      const rms = Math.sqrt(
        dataArray.reduce((sum, v) => sum + v * v, 0) / dataArray.length
      );
      setUserVolume(rms / 128);
      rafIdRef.current = requestAnimationFrame(updateVolume);
    };
    updateVolume();

    setAvatarThinking(true);

    mediaRecorderRef.current.ondataavailable = (e) => {
      if (e.data.size > 0) {
        // Stream raw chunks to backend
        const reader = new FileReader();
        reader.onloadend = () => {
          const base64data = reader.result.split(',')[1]; // strip "data:audio/webm;base64,"
          if (wsRef.current.readyState === WebSocket.OPEN) {
            wsRef.current.send(base64data);
          }
        };
        reader.readAsDataURL(e.data);

      }
    };

    mediaRecorderRef.current.onstart = () => setUserSpeaking(true);

    mediaRecorderRef.current.onstop = () => {
      setUserSpeaking(false);
      cancelAnimationFrame(rafIdRef.current);
      setUserVolume(0);

      // tell backend input is complete
      wsRef.current.send("END");
      userStreamRef.current.getTracks().forEach((t) => t.stop());
    };

    mediaRecorderRef.current.start(250); // send chunks every 250ms
    setIsRecording(true);
  };

  // ─────────────────────────────────────────────────────────────
  // STOP RECORDING
  // ─────────────────────────────────────────────────────────────
  const stopRecording = () => {
    mediaRecorderRef.current.stop();
    setIsRecording(false);
  };

  // ─────────────────────────────────────────────────────────────
  // WebSocket handler (receiving streamed chunks)
  // ─────────────────────────────────────────────────────────────
  const handleWsMessage = (e) => {
    const msg = JSON.parse(e.data);

    if (msg.delta) {
      // Avatar begins responding — stop thinking state
      if (avatarThinking) setAvatarThinking(false);

      const base64Data = msg.delta;
      const pcm = atob(base64Data);

      // Accumulate until playback object exists
      pmBufferRef.current.push(pcm);

      // Lazy-initialize audio system
      if (!avatarAudioRef.current) {
        initAvatarAudio();
      }

      // Append PCM
      feedPCMToAvatar(pcm);
    }
  };

  // Initialize WebAudio node graph
  const initAvatarAudio = () => {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const dest = ctx.createBufferSource();

    avatarAudioRef.current = ctx;
    avatarPlaying && ctx.resume();

    // analyser for ripple
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 256;
    avatarAnalyserRef.current = analyser;

    updateAvatarVolume();
  };

  // Feed PCM blocks into audio context
  const feedPCMToAvatar = (pcmString) => {
    const ctx = avatarAudioRef.current;
    if (!ctx) return;

    const pcmArray = new Int16Array(pcmString.length / 2);
    for (let i = 0; i < pcmArray.length; i++) {
      pcmArray[i] = pcmString.charCodeAt(i * 2) | (pcmString.charCodeAt(i * 2 + 1) << 8);
    }

    const buffer = ctx.createBuffer(1, pcmArray.length, 24000);
    buffer.getChannelData(0).set(pcmArray.map((v) => v / 32768));

    const src = ctx.createBufferSource();
    src.buffer = buffer;
    src.connect(avatarAnalyserRef.current);
    avatarAnalyserRef.current.connect(ctx.destination);

    src.start();
    setAvatarPlaying(true);
  };

  // ─────────────────────────────────────────────────────────────
  // Avatar ripple audio volume
  // ─────────────────────────────────────────────────────────────
  const updateAvatarVolume = () => {
    if (!avatarAnalyserRef.current) return;

    const analyser = avatarAnalyserRef.current;
    const dataArray = new Uint8Array(analyser.frequencyBinCount);

    const loop = () => {
      analyser.getByteFrequencyData(dataArray);
      const rms = Math.sqrt(
        dataArray.reduce((s, v) => s + v * v, 0) / dataArray.length
      );
      setAvatarVolume(rms / 128);

      if (avatarPlaying) requestAnimationFrame(loop);
      else setAvatarVolume(0);
    };
    loop();
  };

  // ─────────────────────────────────────────────────────────────
  // UI
  // ─────────────────────────────────────────────────────────────
  const userRippleScale = 1 + userVolume * 1.5;
  const avatarRippleScale = 1 + avatarVolume * 1.5;

  return (
    <div className="min-h-screen bg-gradient-to-br from-emerald-100 to-stone-100 flex flex-col items-center justify-center p-4">
      <h1 className="text-3xl font-bold text-amber-700 mb-8">
        Lahn River: Voice Chat (Streaming)
      </h1>

      {/* USER RIPPLE */}
      <div className="mb-8 flex flex-col items-center relative">
        <motion.div
          className="w-32 h-32 rounded-full bg-lime-300 absolute"
          style={{ zIndex: 0, pointerEvents: "none" }}
          animate={{
            scale: userRippleScale,
            opacity: userSpeaking ? 0.7 : 0,
          }}
          transition={{ duration: 0.1 }}
        />
        <div className="relative z-10 mt-20 font-semibold text-stone-700">
          {userSpeaking ? "You are speaking…" : "Press mic to speak"}
        </div>
      </div>

      {avatarThinking && (
        <div className="text-lime-700 italic mt-4">
          the river contemplates…
        </div>
      )}

      {/* AVATAR RIPPLE */}
      <div className="mb-8 flex flex-col items-center relative">
        <motion.div
          className="w-48 h-48 rounded-full bg-cyan-300 absolute"
          style={{ zIndex: 0, pointerEvents: "none" }}
          animate={{
            scale: avatarRippleScale,
            opacity: avatarPlaying ? 0.7 : 0,
          }}
          transition={{ duration: 0.1 }}
        />
      </div>

      {/* MIC BUTTON */}
      <div className="mt-12">
        {!isRecording ? (
          <Button
            onClick={startRecording}
            className="bg-amber-600 text-white rounded-full px-6 py-2"
          >
            🎤 Start Speaking
          </Button>
        ) : (
          <Button
            onClick={stopRecording}
            className="bg-red-600 text-white rounded-full px-6 py-2"
          >
            ⏹ Stop
          </Button>
        )}
      </div>
    </div>
  );
}
