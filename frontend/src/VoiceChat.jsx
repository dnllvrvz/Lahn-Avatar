import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Button } from "@/components/ui/button";

export default function VoiceChatSimple() {
  const [isRecording, setIsRecording] = useState(false);
  const [userSpeaking, setUserSpeaking] = useState(false);
  const [avatarPlaying, setAvatarPlaying] = useState(false);
  const [avatarAudioUrl, setAvatarAudioUrl] = useState(null);

  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const avatarAudioRef = useRef(null);

  // Start recording user speech
  const startRecording = async () => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorderRef.current = new MediaRecorder(stream);
    audioChunksRef.current = [];

    mediaRecorderRef.current.ondataavailable = (e) => {
      if (e.data.size > 0) audioChunksRef.current.push(e.data);
    };

    mediaRecorderRef.current.onstart = () => setUserSpeaking(true);

    mediaRecorderRef.current.onstop = async () => {
      setUserSpeaking(false);
      const blob = new Blob(audioChunksRef.current, { type: "audio/webm" });

      const resp = await fetch("/api/voice-chat", {
          method: "POST",
          body: formData,
        });

      // Get audio back as Blob
      const avatarBlob = await resp.blob();
      // Simulate sending to backend and receiving avatar audio
      // const avatarBlob = new Blob([blob], { type: "audio/webm" }); // replace with API call
      const url = URL.createObjectURL(avatarBlob);
      setAvatarAudioUrl(url);
      setAvatarPlaying(true);

      const audio = new Audio(url);
      avatarAudioRef.current = audio;
      audio.play();
      audio.onended = () => setAvatarPlaying(false);
    };

    mediaRecorderRef.current.start();
    setIsRecording(true);
  };

  const stopRecording = () => {
    mediaRecorderRef.current.stop();
    setIsRecording(false);
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

  return (
    <div className="min-h-screen bg-gradient-to-br from-emerald-100 to-stone-100 flex flex-col items-center justify-center p-4">
      <h1 className="text-3xl font-bold text-amber-700 mb-8">
        Lahn River: Voice Chat
      </h1>

      {/* User speaking ripples */}
      <div className="mb-12">
        <AnimatePresence>
          {userSpeaking && (
            <motion.div
              className="w-32 h-32 rounded-full bg-lime-300"
              initial={{ scale: 1 }}
              animate={{ scale: [1, 1.4, 1] }}
              exit={{ scale: 1 }}
              transition={{ repeat: Infinity, duration: 1 }}
            />
          )}
        </AnimatePresence>
        <div className="text-center mt-4 font-semibold text-stone-700">
          {userSpeaking ? "You are speaking…" : "Press mic to speak"}
        </div>
      </div>

      {/* Avatar response ripples */}
      <div className="mb-8 relative">
        <AnimatePresence>
          {avatarPlaying && (
            <motion.div
              className="w-48 h-48 rounded-full bg-cyan-300 mx-auto"
              initial={{ scale: 1 }}
              animate={{ scale: [1, 1.5, 1] }}
              exit={{ scale: 1 }}
              transition={{ repeat: Infinity, duration: 1 }}
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
