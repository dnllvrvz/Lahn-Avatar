import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Button } from "@/components/ui/button";

export default function VoiceChatSimple() {
  const [isRecording, setIsRecording] = useState(false);
  const [userSpeaking, setUserSpeaking] = useState(false);
  const [userVolume, setUserVolume] = useState(0);
  const [avatarPlaying, setAvatarPlaying] = useState(false);
  const [avatarVolume, setAvatarVolume] = useState(0);
  const [avatarAudioUrl, setAvatarAudioUrl] = useState(null);

  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const avatarAudioRef = useRef(null);
  const userStreamRef = useRef(null);
  const userAnalyserRef = useRef(null);
  const avatarAnalyserRef = useRef(null);
  const rafIdRef = useRef(null);

  // ------------------ User microphone ripple ------------------
  const startRecording = async () => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    userStreamRef.current = stream;
    mediaRecorderRef.current = new MediaRecorder(stream);
    audioChunksRef.current = [];

    const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const source = audioCtx.createMediaStreamSource(stream);
    const analyser = audioCtx.createAnalyser();
    analyser.fftSize = 256;
    source.connect(analyser);
    userAnalyserRef.current = analyser;

    const dataArray = new Uint8Array(analyser.frequencyBinCount);

    const updateVolume = () => {
      analyser.getByteFrequencyData(dataArray);
      const rms = Math.sqrt(dataArray.reduce((sum, val) => sum + val * val, 0) / dataArray.length);
      setUserVolume(rms / 128); // normalize roughly 0-1
      rafIdRef.current = requestAnimationFrame(updateVolume);
    };
    updateVolume();

    mediaRecorderRef.current.ondataavailable = (e) => {
      if (e.data.size > 0) audioChunksRef.current.push(e.data);
    };

    mediaRecorderRef.current.onstart = () => setUserSpeaking(true);

    mediaRecorderRef.current.onstop = async () => {
      setUserSpeaking(false);
      cancelAnimationFrame(rafIdRef.current);
      setUserVolume(0);
      userStreamRef.current.getTracks().forEach((track) => track.stop());

      const blob = new Blob(audioChunksRef.current, { type: "audio/webm" });
      const formData = new FormData();
      formData.append("audio", blob, "recording.webm");

      // Send to backend
      const resp = await fetch("/api/voice-chat", {
        method: "POST",
        body: formData,
      });

      const avatarBlob = await resp.blob();
      const url = URL.createObjectURL(avatarBlob);
      setAvatarAudioUrl(url);
      setAvatarPlaying(true);

      const audio = new Audio(url);
      avatarAudioRef.current = audio;

      // Setup analyser for avatar playback
      const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      const sourceNode = audioCtx.createMediaElementSource(audio);
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 256;
      sourceNode.connect(analyser);
      analyser.connect(audioCtx.destination);
      avatarAnalyserRef.current = analyser;

      const dataArray = new Uint8Array(analyser.frequencyBinCount);
      const updateAvatarVolume = () => {
        analyser.getByteFrequencyData(dataArray);
        const rms = Math.sqrt(dataArray.reduce((sum, val) => sum + val * val, 0) / dataArray.length);
        setAvatarVolume(rms / 128);
        if (!audio.paused) {
          rafIdRef.current = requestAnimationFrame(updateAvatarVolume);
        } else {
          setAvatarVolume(0);
        }
      };
      audio.onplay = () => updateAvatarVolume();
      audio.onended = () => setAvatarPlaying(false);

      audio.play();
    };

    mediaRecorderRef.current.start();
    setIsRecording(true);
  };

  const stopRecording = () => {
    mediaRecorderRef.current.stop();
    setIsRecording(false);
  };

  // ------------------ Avatar pause/resume ------------------
  const toggleAvatarPlayback = () => {
    if (!avatarAudioRef.current) return;
    if (avatarPlaying) {
      avatarAudioRef.current.pause();
      setAvatarPlaying(false);
      setAvatarVolume(0);
    } else {
      avatarAudioRef.current.play();
      setAvatarPlaying(true);
    }
  };

  // ------------------ Ripple scaling helpers ------------------
  const userRippleScale = 1 + userVolume * 1.5; // scales from 1 to ~2.5
  const avatarRippleScale = 1 + avatarVolume * 1.5;

  return (
    <div className="min-h-screen bg-gradient-to-br from-emerald-100 to-stone-100 flex flex-col items-center justify-center p-4">
      <h1 className="text-3xl font-bold text-amber-700 mb-8">
        Lahn River: Voice Chat
      </h1>

      {/* User ripple */}
      <div className="mb-8 flex flex-col items-center relative">
        <motion.div
          className="w-32 h-32 rounded-full bg-lime-300 absolute"
          style={{ zIndex: 0 }}
          animate={{ scale: userRippleScale, opacity: userSpeaking ? 0.7 : 0 }}
          transition={{ duration: 0.1 }}
        />
        <div className="relative z-10 mt-20 text-center font-semibold text-stone-700">
          {userSpeaking ? "You are speaking…" : "Press mic to speak"}
        </div>
      </div>

      {/* Avatar ripple */}
      <div className="mb-8 flex flex-col items-center relative">
        <motion.div
          className="w-48 h-48 rounded-full bg-cyan-300 absolute"
          style={{ zIndex: 0 }}
          animate={{ scale: avatarRippleScale, opacity: avatarPlaying ? 0.7 : 0 }}
          transition={{ duration: 0.1 }}
        />
        {avatarAudioUrl && (
          <div className="relative z-10 flex justify-center mt-28">
            <Button onClick={toggleAvatarPlayback}>
              {avatarPlaying ? "⏸ Pause Avatar" : "▶ Resume Avatar"}
            </Button>
          </div>
        )}
      </div>

      {/* Recording button */}
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
