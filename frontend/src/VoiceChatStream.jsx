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
  const avatarAudioRef = useRef(null);
  const nextPlayTimeRef = useRef(0);
  const avatarPlayingRef = useRef(false);

  // --- startRecording / stopRecording / handleWsMessage logic stays unchanged ---
  // (preserve everything from your existing implementation)
  // ─────────────────────────────────────────────────────────────
  // Include all the audio logic above exactly as in your version
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
        Press the microphone button below to talk to the river. Release when you’re done speaking — she’ll answer in her own voice.
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
            </DialogDescription>
          </DialogHeader>
        </DialogContent>
      </Dialog>
    </div>
  );
}
