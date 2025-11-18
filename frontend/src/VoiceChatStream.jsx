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

  // Add near other state variables
  const [avatarPaused, setAvatarPaused] = useState(false);

  const [conversation, setConversation] = useState([]);

  const [wsConnected, setWsConnected] = useState(false);

  const recordingAudioCtxRef = useRef(null);




  // Connect once when component mounts or on first use
  const connectWebSocket = async () => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      console.log("✅ Already connected");
      return;
    }

    wsRef.current = new WebSocket("wss://" + window.location.host + "/api/voice-chat-stream");
    wsRef.current.binaryType = "arraybuffer";
    wsRef.current.onmessage = handleWsMessage;
    
    wsRef.current.onclose = () => {
      console.log("🔌 WebSocket closed");
      setWsConnected(false);
    };
    
    await new Promise((resolve) => (wsRef.current.onopen = resolve));
    setWsConnected(true);
    console.log("✅ WS connected");
  };


  // ─────────────────────────────────────────────────────────────
  // START STREAMING RECORDING
  // ─────────────────────────────────────────────────────────────
  const startRecording = async () => {
    resetAvatarAudio(); // discard any previous queued or paused audio

    // Clean up any existing recording context
    if (recordingAudioCtxRef.current) {
      try {
        recordingAudioCtxRef.current.close();
      } catch {}
    }

    // Connect if not already connected
    await connectWebSocket();

    const audioCtx = new AudioContext({ sampleRate: 24000 });
    await audioCtx.audioWorklet.addModule("/pcm-processor.js");

    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const source = audioCtx.createMediaStreamSource(stream);

    // ── Mic volume analyser for green ripple ──
    const analyser = audioCtx.createAnalyser();
    analyser.fftSize = 512;
    const dataArray = new Uint8Array(analyser.frequencyBinCount);
    source.connect(analyser);

    const updateUserVolume = () => {
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

    // const downsampleTarget = 24000;
    // const ratio = audioCtx.sampleRate / downsampleTarget;

    worklet.port.onmessage = (event) => {
      const floatChunk = event.data;
      
      // We already record at 24 kHz — NO resampling needed
      const downsampled = floatChunk;


      // Downsample from 48 kHz → 24 kHz
      // const downsampled = new Float32Array(Math.floor(floatChunk.length / ratio));
      // for (let i = 0, j = 0; i < floatChunk.length; i += ratio, j++) {
      //   downsampled[j] = floatChunk[Math.floor(i)];
      // }

      // Convert Float32 → Int16 PCM
      const pcm16 = new Int16Array(downsampled.length);
      for (let i = 0; i < downsampled.length; i++) {
        const s = Math.max(-1, Math.min(1, downsampled[i]));
        pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
      }

      if (wsRef.current.readyState === WebSocket.OPEN)
        wsRef.current.send(pcm16.buffer);

      // Base64 encode and send to backend
      // const base64Chunk = btoa(String.fromCharCode(...new Uint8Array(pcm16.buffer)));
      // if (wsRef.current.readyState === WebSocket.OPEN) wsRef.current.send(base64Chunk);
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
      wsRef.current.send(JSON.stringify({
        type: "END",
        conversation: conversation
      }));
      console.log('Conversation: ', conversation);

    }
    if (userStreamRef.current) {
      userStreamRef.current.getTracks().forEach((t) => t.stop());
      userStreamRef.current = null;
    }
    setUserSpeaking(false);
    setUserVolume(0);

    if (recordingAudioCtxRef.current) {
      try {
        recordingAudioCtxRef.current.close();
      } catch {}
      recordingAudioCtxRef.current = null;
    }

    setIsRecording(false);
  };


  const resetAvatarAudio = () => {
    const ctx = avatarAudioRef.current;
    if (ctx) {
      try {
        ctx.close(); // stop all pending buffers
      } catch {}
    }
    avatarAudioRef.current = null;
    avatarAnalyserRef.current = null;
    nextPlayTimeRef.current = 0;
    avatarPlayingRef.current = false;
    setAvatarPlaying(false);
    setAvatarPaused(false);
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

      // ⬇️ Ensure analyser exists BEFORE starting volume loop
      if (!avatarAnalyserRef.current) {
        const analyser = audioCtx.createAnalyser();
        analyser.fftSize = 256;
        avatarAnalyserRef.current = analyser;

        // NOW start the volume polling loop
        updateAvatarVolume();
      }



      const pcm16 = new Int16Array(arrayBuffer);
      const float32 = new Float32Array(pcm16.length);
      for (let i = 0; i < pcm16.length; i++) float32[i] = pcm16[i] / 32768;

      const buffer = audioCtx.createBuffer(1, float32.length, 24000);
      buffer.copyToChannel(float32, 0);
      const src = audioCtx.createBufferSource();
      src.buffer = buffer;
      src.connect(avatarAnalyserRef.current);
      avatarAnalyserRef.current.connect(audioCtx.destination);


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
    if (typeof e.data === "string") {
      try {
        const msg = JSON.parse(e.data);

        switch (msg.type) {
          case "input_transcript":
            // User said this (as detected by Whisper)
            setConversation((prev) => [...prev, { role: "user", text: msg.text }]);
            break;

          case "output_transcript":
            // Model replied with this
            setConversation((prev) => [...prev, { role: "assistant", text: msg.text }]);
            break;

          case "status":
            console.log("Status update:", msg.text);
            break;

          default:
            console.log("Unhandled WS text message:", msg);
        }
      } catch (err) {
        console.warn("Non-JSON text message:", e.data);
      }
    }
  };


  const toggleAvatarPlayback = () => {
    if (!avatarAudioRef.current) return;
    const ctx = avatarAudioRef.current;
    if (avatarPaused) {
      ctx.resume();
      setAvatarPaused(false);
      setAvatarPlaying(true);
      avatarPlayingRef.current = true;
    } else {
      ctx.suspend();
      setAvatarPaused(true);
      setAvatarPlaying(false);
      avatarPlayingRef.current = false;
    }
  };


  // ─────────────────────────────────────────────────────────────
  // Avatar ripple audio volume
  // ─────────────────────────────────────────────────────────────
  const updateAvatarVolume = () => {
    if (!avatarAnalyserRef.current) return;

    const analyser = avatarAnalyserRef.current;
    const dataArray = new Uint8Array(analyser.frequencyBinCount);

    const loop = () => {
      if (!avatarAnalyserRef.current) {
        setAvatarVolume(0);
        return;
      }

      analyser.getByteFrequencyData(dataArray);
      const rms = Math.sqrt(
        dataArray.reduce((s, v) => s + v * v, 0) / dataArray.length
      );
      setAvatarVolume(rms / 128);

      requestAnimationFrame(loop);
    };

    loop();
  };


  // ─────────────────────────────────────────────────────────────
  // UI
  // ─────────────────────────────────────────────────────────────
  const userRippleScale = 1 + userVolume * 1.5;
  const avatarRippleScale = 1 + avatarVolume * 1.5;


  useEffect(() => {
    const video = document.getElementById("bg-video");
    if (!video) return;

    video.muted = true;
    video.volume = 0;

    const tryPlay = async () => {
      try {
        await video.play();
        // Fade in volume
        let vol = 0;
        const fade = setInterval(() => {
          vol += 0.01;
          video.volume = Math.min(vol, 0.12);
          if (vol >= 0.12) clearInterval(fade);
        }, 200);
      } catch (err) {
        console.warn("⛔ Autoplay blocked, waiting for click…");
        const handleClick = async () => {
          try {
            await video.play();
            console.log("👆 User interacted → playback started");
          } catch (e) {
            console.error("Still blocked:", e);
          }
        };
        document.addEventListener("click", handleClick, { once: true });
      }
    };

    tryPlay();
  }, []);




  return (
    // bg-gradient-to-br from-emerald-100 to-stone-100
    <div
      className="relative min-h-screen  flex flex-col items-center justify-center p-4"
      style={{ fontFamily: "'Chakra Petch', sans-serif" }}
    >

    {/* BACKGROUND VIDEO */}
    <video
      id="bg-video"
      src="/lahn_video_stitched.mp4"
      autoPlay
      muted
      loop
      playsInline
      className="fixed top-0 left-0 w-full h-full object-cover -z-10 opacity-70"
    ></video>

    {/* Optional overlay for readability */}
    <div className="fixed inset-0 bg-gradient-to-b from-black/60 via-black/30 to-emerald-900/50 -z-10" />

      {/* Page Title */}
      <h1 className="text-4xl md:text-5xl font-bold text-white mb-2 text-center drop-shadow-[0_2px_6px_rgba(0,0,0,0.6)]">
        Ever heard a river speak?<br />Meet the Lahn and her Avatar.
      </h1>

      {/* Subtitle / Instructions */}
      <p className="text-white text-center mb-8 font-bold text-lg max-w-2xl drop-shadow-[0_1px_4px_rgba(0,0,0,0.6)]">
        Press the microphone button below to talk to the avatar. Press again when you’re done speaking — she’ll answer in her own voice.
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
        <div className="relative z-10 mt-20 text-lg font-bold text-white">
          {!avatarPlaying && (userSpeaking ? "You are speaking…" : "Press mic to speak")}
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
          className="w-32 h-32 rounded-full bg-cyan-300 absolute"
          style={{ zIndex: 0, pointerEvents: "none" }}
          animate={{
            scale: avatarRippleScale,
            opacity: avatarPlaying ? 0.6 : 0,
          }}
          transition={{ duration: 0.1 }}
        />
      </div>

      {avatarPlaying || avatarPaused ? (
        <div className="relative z-40 flex justify-center mt-28">
          <Button onClick={toggleAvatarPlayback}>
            {avatarPaused ? "▶ Resume Avatar" : "⏸ Pause Avatar"}
          </Button>
        </div>
      ) : null}


      {/* MIC BUTTON */}
      <div className="mt-6 relative z-50">
        {!isRecording ? (
          <Button
            onClick={startRecording}
            className="bg-amber-600 text-white rounded-full px-6 py-2"
          >
            🎤 Press to Talk
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
        <DialogContent
          className="max-w-lg text-stone-800 max-h-[80vh] overflow-y-auto rounded-2xl"
        >
          <DialogHeader>
            <DialogTitle className="font-semibold text-lg mb-2">
              About the Lahn River Avatar
            </DialogTitle>
          </DialogHeader>

          <div className="space-y-5 leading-relaxed">
            {/* Sculpture image */}
            <img
              src="/sculpture.jpg"
              alt="Lahn River Avatar sculpture"
              className="w-full rounded-2xl shadow-md border border-stone-300"
            />

            <p>
              The <strong>Lahn River Avatar</strong> is an AI-powered ecological artwork and
              research project that serves as an expression medium to the Lahn River in Germany.
              Developed by the artist-philosopher duo{" "}
              <a
                href="https://www.uni-giessen.de/en/faculties/planetarythinking/events/eventseries/conferencefinal/finalconference/#daniloolivaz"
                target="_blank"
                rel="noopener noreferrer"
                className="text-amber-700 underline hover:text-amber-800"
              >
                Danilo Olivaz
              </a>{" "}
              and{" "}
              <a
                href="https://www.uni-giessen.de/en/faculties/planetarythinking/events/eventseries/conferencefinal/finalconference/#ingvildsyntropia"
                target="_blank"
                rel="noopener noreferrer"
                className="text-amber-700 underline hover:text-amber-800"
              >
                Ingvild Syntropia
              </a>{" "}
              in context of their fellowship at the{" "}
              <a
                href="https://www.uni-giessen.de/en/faculties/planetarythinking"
                target="_blank"
                rel="noopener noreferrer"
                className="text-amber-700 underline hover:text-amber-800"
              >
                Panel on Planetary Thinking
              </a>
              , the project investigates planetary agency through the convergence of art,
              technology, and environmental ethics.
            </p>

            <p>
              <a
                href="https://lahn-avatar.uni-giessen.de/"
                target="_blank"
                rel="noopener noreferrer"
                className="text-amber-700 underline hover:text-amber-800"
              >
                https://lahn-avatar.uni-giessen.de
              </a>
            </p>

            <p>
              Embodied in a voice-activated sculpture crafted from local and upcycled materials,
              the Avatar integrates real-time environmental data, scientific research, and
              cultural knowledge specific to the Lahn.
            </p>

            <p>
              Positioned at the Lahnfenster, it serves as both a poetic and political gesture—an
              invitation to collective deliberation between humans and the river.
            </p>

            <p>
              Technical support provided by <strong>Mayowa Osibodu</strong>, the{" "}
              <a
                href="http://consider.it/"
                target="_blank"
                rel="noopener noreferrer"
                className="text-amber-700 underline hover:text-amber-800"
              >
                Consider.it
              </a>{" "}
              team, and <strong>Stanislav Hannes</strong>.
            </p>

            <div>
              <strong>Contribute to the emergence of the next Avatar:</strong>
              <br />
              A new Nature Avatar is being born, delivered by a Regenerative School at the heart
              of the Brazilian Atlantic Rainforest. They both need your support:
            </div>

            <div className="flex flex-col items-center space-y-3">
              <img
                src="/qrcode.jpg"
                alt="QR code to support next Avatar"
                className="w-40 h-40 border border-stone-400 rounded-lg shadow"
              />
              <p className="text-center text-stone-600 text-sm">
                Scan the QR code or contact us below.
              </p>
            </div>

            <p>
              Contact:{" "}
              <a
                href="mailto:hello@sympoiesis.xyz"
                className="text-amber-700 underline hover:text-amber-800"
              >
                hello@sympoiesis.xyz
              </a>
            </p>
          </div>
        </DialogContent>
      </Dialog>

    </div>
  );
}
