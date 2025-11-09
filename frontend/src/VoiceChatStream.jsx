import { useState, useRef, useEffect } from "react";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";

// Font import (Google)
import "@fontsource/chakra-petch"; // npm install @fontsource/chakra-petch



export default function VoiceChatStream() {
  const [isRecording, setIsRecording] = useState(false);
  const [userSpeaking, setUserSpeaking] = useState(false);
  const [userVolume, setUserVolume] = useState(0);

  const [avatarPlaying, setAvatarPlaying] = useState(false);
  const [avatarVolume, setAvatarVolume] = useState(0);
  const [avatarThinking, setAvatarThinking] = useState(false);
  const [showAbout, setShowAbout] = useState(false);

  const wsRef = useRef(null);

  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const userStreamRef = useRef(null);
  const userAnalyserRef = useRef(null);

  const avatarAudioRef = useRef(null);
  const avatarAnalyserRef = useRef(null);

  const pmBufferRef = useRef([]);
  const rafIdRef = useRef(null);

  const nextPlayTimeRef = useRef(0);

  const avatarPlayingRef = useRef(false);



  // ─────────────────────────────────────────────────────────────
  // START STREAMING RECORDING
  // ─────────────────────────────────────────────────────────────
  const startRecording = async () => {
    wsRef.current = new WebSocket("wss://" + window.location.host + "/api/voice-chat-stream");
    wsRef.current.binaryType = "arraybuffer";

    wsRef.current.onmessage = handleWsMessage;
    await new Promise((resolve) => (wsRef.current.onopen = resolve));
    console.log("✅ WS connected");

    const audioCtx = new AudioContext({ sampleRate: 48000 });
    await audioCtx.audioWorklet.addModule("/pcm-processor.js");

    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const source = audioCtx.createMediaStreamSource(stream);

    // ── Mic volume analyser for green ripple ──
    const analyser = audioCtx.createAnalyser();
    analyser.fftSize = 512;
    const dataArray = new Uint8Array(analyser.frequencyBinCount);
    source.connect(analyser);

    const updateUserVolume = () => {
      if (!isRecording) {
        requestAnimationFrame(updateUserVolume); // keep checking until active
        // setUserSpeaking(false);
        // setUserVolume(0);
        return; // stop updating if not recording
      }

      analyser.getByteFrequencyData(dataArray);
      const rms = Math.sqrt(
        dataArray.reduce((s, v) => s + v * v, 0) / dataArray.length
      );
      const normalized = rms / 128;
      setUserVolume(normalized);
      setUserSpeaking(normalized > 0.05); // threshold ≈ silence floor
      requestAnimationFrame(updateUserVolume);
    };



    const worklet = new AudioWorkletNode(audioCtx, "pcm-processor");

    const downsampleTarget = 24000;
    const ratio = audioCtx.sampleRate / downsampleTarget;

    worklet.port.onmessage = (event) => {
      const floatChunk = event.data;

      // Downsample from 48 kHz → 24 kHz
      const downsampled = new Float32Array(Math.floor(floatChunk.length / ratio));
      for (let i = 0, j = 0; i < floatChunk.length; i += ratio, j++) {
        downsampled[j] = floatChunk[Math.floor(i)];
      }

      // Convert Float32 → Int16 PCM
      const pcm16 = new Int16Array(downsampled.length);
      for (let i = 0; i < downsampled.length; i++) {
        const s = Math.max(-1, Math.min(1, downsampled[i]));
        pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
      }

      // Base64 encode and send to backend
      const base64Chunk = btoa(String.fromCharCode(...new Uint8Array(pcm16.buffer)));
      if (wsRef.current.readyState === WebSocket.OPEN) wsRef.current.send(base64Chunk);
    };

    source.connect(worklet);
    worklet.connect(audioCtx.destination);

    setIsRecording(true);
    setTimeout(() => updateUserVolume(), 50); // give React a moment to update state
    userStreamRef.current = stream;
  };



  // ─────────────────────────────────────────────────────────────
  // STOP RECORDING
  // ─────────────────────────────────────────────────────────────
  const stopRecording = () => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send("END");
    }
    if (userStreamRef.current) {
      userStreamRef.current.getTracks().forEach((t) => t.stop());
      userStreamRef.current = null;
    }
    setUserSpeaking(false);
    setUserVolume(0);

    setIsRecording(false);
  };

  // ─────────────────────────────────────────────────────────────
  // WebSocket handler (receiving streamed chunks)
  // ─────────────────────────────────────────────────────────────
  const handleWsMessage = async (e) => {
    // Case 1: Binary PCM audio frame
    if (e.data instanceof Blob || e.data instanceof ArrayBuffer) {
      const arrayBuffer = e.data instanceof Blob ? await e.data.arrayBuffer() : e.data;

      const audioCtx = avatarAudioRef.current || new AudioContext({ sampleRate: 24000 });
      if (!avatarAudioRef.current) {
        avatarAudioRef.current = audioCtx;
        nextPlayTimeRef.current = audioCtx.currentTime; // start from "now"
      }

      const pcm16 = new Int16Array(arrayBuffer);
      const float32 = new Float32Array(pcm16.length);
      for (let i = 0; i < pcm16.length; i++) float32[i] = pcm16[i] / 32768;

      const buffer = audioCtx.createBuffer(1, float32.length, 24000);
      buffer.copyToChannel(float32, 0);
      const src = audioCtx.createBufferSource();
      src.buffer = buffer;
      src.connect(audioCtx.destination);

      // schedule chunk to start sequentially
      const startAt = Math.max(nextPlayTimeRef.current, audioCtx.currentTime);
      src.start(startAt);
      nextPlayTimeRef.current = startAt + buffer.duration;

      if (!avatarPlaying) {
        setAvatarPlaying(true);
        avatarPlayingRef.current = true;
      }

      src.onended = () => {
        const now = audioCtx.currentTime;
        // if next chunk isn’t scheduled within 0.1s, assume playback done
        if (now >= nextPlayTimeRef.current - 0.1) {
          setAvatarPlaying(false);
          avatarPlayingRef.current = false;
          setAvatarVolume(0);
        }
      };

      return;
    }


    // Case 2: Text (JSON) control message
    try {
      const msg = JSON.parse(e.data);
      // console.log("Text message:", msg);
      if (msg.text) {
        // handle model text here
      }
    } catch (err) {
      console.warn("Non-JSON text message:", e.data);
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

      if (avatarPlayingRef.current) requestAnimationFrame(loop);
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
    <div
      className="min-h-screen bg-gradient-to-br from-emerald-100 to-stone-100 flex flex-col items-center justify-center p-4"
      style={{ fontFamily: "'Chakra Petch', sans-serif" }}
    >
      {/* Page Title */}
      <h1 className="text-4xl md:text-5xl font-bold text-amber-700 mb-2 text-center">
        Ever heard a river speak?<br />Meet the Lahn — she has a lot to say.
      </h1>

      {/* Subtitle / Instructions */}
      <p className="text-stone-700 text-center mb-8 max-w-lg">
        Press the microphone button below to talk to the river. Press again when you’re done speaking — she’ll answer in her own voice.
      </p>

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
      <div className="mt-6">
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

      {/* About Button */}
      <div className="mt-8">
        <Button
          variant="outline"
          className="text-amber-700 border-amber-600 hover:bg-amber-100"
          onClick={() => setShowAbout(true)}
        >
          ℹ️ About
        </Button>
      </div>

      {/* About Modal */}
      <Dialog open={showAbout} onOpenChange={setShowAbout}>
        <DialogContent className="max-w-lg text-stone-800">
          <DialogHeader>
            <DialogTitle>About the Lahn River Avatar</DialogTitle>
            <DialogDescription>
              The Lahn River Avatar is an interactive AI installation created by
              Danilo Vaz and Ingvild Syntropia, as part of the Planetary
              Thinking Fellowship at Justus Liebig University, Giessen, Germany.
              It gives the river a voice to share her stories, history, and
              ecological concerns — blending environmental science, art, and AI.
              <br /><br />
              Visitors can speak to the Lahn in real time: she listens,
              understands, and replies — inviting reflection on the relationship
              between humans and their living environment.
              <br /><br />
              Technical support provided by Mayowa Osibodu and Stanislav Hannes.
            </DialogDescription>
          </DialogHeader>
        </DialogContent>
      </Dialog>
    </div>
  );
}
