import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Button } from "@/components/ui/button";

export default function VoiceChatDynamic() {
  const [isRecording, setIsRecording] = useState(false);
  const [userSpeaking, setUserSpeaking] = useState(false);
  const [userVolume, setUserVolume] = useState(0);
  const [avatarPlaying, setAvatarPlaying] = useState(false);
  const [avatarVolume, setAvatarVolume] = useState(0);
  const [avatarAudioUrl, setAvatarAudioUrl] = useState(null);

  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const avatarAudioRef = useRef(null);
  const userAudioCtxRef = useRef(null);
  const avatarAudioCtxRef = useRef(null);
  const animationFrameRef = useRef(null);

  // === Start recording and analyze mic volume ===
  const startRecording = async () => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const audioCtx = new AudioContext();
    userAudioCtxRef.current = audioCtx;

    const source = audioCtx.createMediaStreamSource(stream);
    const analyser = audioCtx.createAnalyser();
    analyser.fftSize = 256;
    source.connect(analyser);

    const dataArray = new Uint8Array(analyser.frequencyBinCount);

    const updateVolume = () => {
      analyser.getByteFrequencyData(dataArray);
      const avg = dataArray.reduce((a, b) => a + b, 0) / dataArray.length;
      setUserVolume(avg / 255);
      if (isRecording) animationFrameRef.current = requestAnimationFrame(updateVolume);
    };
    updateVolume();

    mediaRecorderRef.current = new MediaRecorder(stream);
    audioChunksRef.current = [];

    mediaRecorderRef.current.ondataavailable = (e) => {
      if (e.data.size > 0) audioChunksRef.current.push(e.data);
    };

    mediaRecorderRef.current.onstart = () => setUserSpeaking(true);

    mediaRecorderRef.current.onstop = async () => {
      setUserSpeaking(false);
      setUserVolume(0);
      if (animationFrameRef.current) cancelAnimationFrame(animationFrameRef.current);

      const blob = new Blob(audioChunksRef.current, { type: "audio/webm" });

      const formData = new FormData();
      formData.append("audio", blob, "recording.webm");

      // Send to backend
      const resp = await fetch("/api/voice-chat", { method: "POST", body: formData });
      const avatarBlob = await resp.blob();
      const url = URL.createObjectURL(avatarBlob);
      setAvatarAudioUrl(url);
      playAvatarAudio(url);
    };

    mediaRecorderRef.current.start();
    setIsRecording(true);
  };

  const stopRecording = () => {
    mediaRecorderRef.current.stop();
    setIsRecording(false);
  };

  // === Play avatar audio and analyze volume ===
  const playAvatarAudio = (url) => {
    const audio = new Audio(url);
    avatarAudioRef.current = audio;

    const audioCtx = new AudioContext();
    avatarAudioCtxRef.current = audioCtx;
    const source = audioCtx.createMediaElementSource(audio);
    const analyser = audioCtx.createAnalyser();
    analyser.fftSize = 256;
    source.connect(analyser);
    analyser.connect(audioCtx.destination);

    const dataArray = new Uint8Array(analyser.frequencyBinCount);

    const updateVolume = () => {
      analyser.getByteFrequencyData(dataArray);
      const avg = dataArray.reduce((a, b) => a + b, 0) / dataArray.length;
      setAvatarVolume(avg / 255);
      if (!audio.paused) animationFrameRef.current = requestAnimationFrame(updateVolume);
      else setAvatarVolume(0);
    };

    audio.onended = () => {
      setAvatarPlaying(false);
      setAvatarVolume(0);
      if (animationFrameRef.current) cancelAnimationFrame(animationFrameRef.current);
    };

    setAvatarPlaying(true);
    audio.play();
    updateVolume();
  };

  const toggleAvatarPlayback = () => {
    if (!avatarAudioRef.current) return;
    if (avatarPlaying) {
      avatarAudioRef.current.pause();
      setAvatarPlaying(false);
    } else {
      avatarAudioRef.current.play();
      setAvatarPlaying(true);
    }
  };

  // === Ripple style helper ===
  const getRippleStyle = (volume, baseSize, color) => ({
    width: `${baseSize}px`,
    height: `${baseSize}px`,
    borderRadius: "50%",
    backgroundColor: color,
    transform: `scale(${0.5 + volume * 2})`,
    opacity: 0.5 + volume * 0.5,
    transition: "transform 0.05s linear, opacity 0.05s linear",
  });

  return (
    <div className="min-h-screen bg-gradient-to-br from-emerald-100 to-stone-100 flex flex-col items-center justify-center p-4">
      <h1 className="text-3xl font-bold text-amber-700 mb-8">Lahn River: Voice Chat</h1>

      {/* User ripples */}
      <div className="mb-12 relative">
        <AnimatePresence>
          {userSpeaking && (
            <motion.div
              className="absolute"
              style={getRippleStyle(userVolume, 128, "#a3e635")}
            />
          )}
        </AnimatePresence>
        <div className="text-center mt-4 font-semibold text-stone-700">
          {userSpeaking ? "You are speaking…" : "Press mic to speak"}
        </div>
      </div>

      {/* Avatar ripples */}
      <div className="mb-8 relative">
        <AnimatePresence>
          {avatarPlaying && (
            <motion.div
              className="absolute"
              style={getRippleStyle(avatarVolume, 192, "#22d3ee")}
            />
          )}
        </AnimatePresence>
        {avatarAudioUrl && (
          <div className="flex justify-center mt-4">
            <Button onClick={toggleAvatarPlayback}>
              {avatarPlaying ? "⏸ Pause Avatar" : "▶ Resume Avatar"}
            </Button>
          </div>
        )}
      </div>

      {/* Recording button */}
      <div>
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
