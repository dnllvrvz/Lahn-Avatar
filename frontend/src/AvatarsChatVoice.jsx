import { useState, useRef, useEffect, useCallback } from "react";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import AgoraRTC from "agora-rtc-sdk-ng";

AgoraRTC.setLogLevel(3); // warn only

const STATUS_LABEL = {
  idle: "Press to start conversation",
  connecting: "Connecting…",
  listening: "Listening…",
  thinking: "The river contemplates…",
  speaking: "The river speaks…",
  error: "Connection error",
};

export default function AvatarsChatVoice() {
  const [status, setStatus] = useState("idle");
  const [isConnected, setIsConnected] = useState(false);
  const [userVolume, setUserVolume] = useState(0);
  const [avatarVolume, setAvatarVolume] = useState(0);
  const [avatars, setAvatars] = useState([]);
  const [selectedAvatarId, setSelectedAvatarId] = useState(null);
  const [agentId, setAgentId] = useState(null);
  const [error, setError] = useState(null);

  const clientRef = useRef(null);
  const micTrackRef = useRef(null);
  const volumeRafRef = useRef(null);
  // Unique channel per session so multiple browser tabs don't collide
  const channelRef = useRef(`avatar-lab-${Date.now()}`);

  // Load avatar list on mount
  useEffect(() => {
    fetch("/api/avatars")
      .then(r => r.json())
      .then(data => {
        setAvatars(data);
        if (data.length > 0) setSelectedAvatarId(data[0].id);
      })
      .catch(e => console.error("Failed to load avatars:", e));
  }, []);

  // Poll mic volume for user ripple
  const startVolumePolling = useCallback((micTrack) => {
    const poll = () => {
      if (!micTrack) return;
      setUserVolume((micTrack.getVolumeLevel?.() ?? 0));
      volumeRafRef.current = requestAnimationFrame(poll);
    };
    poll();
  }, []);

  const stopVolumePolling = useCallback(() => {
    if (volumeRafRef.current) {
      cancelAnimationFrame(volumeRafRef.current);
      volumeRafRef.current = null;
    }
    setUserVolume(0);
    setAvatarVolume(0);
  }, []);

  const disconnect = useCallback(async (silent = false) => {
    stopVolumePolling();

    if (agentId) {
      try {
        await fetch("/api/voice/agent/stop", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ agentId }),
        });
      } catch (e) {
        if (!silent) console.error("Stop agent error:", e);
      }
      setAgentId(null);
    }

    if (micTrackRef.current) {
      micTrackRef.current.close();
      micTrackRef.current = null;
    }

    if (clientRef.current) {
      try { await clientRef.current.leave(); } catch (_e) { /* ignore */ }
      clientRef.current = null;
    }

    setIsConnected(false);
    setStatus("idle");
  }, [agentId, stopVolumePolling]);

  const connect = async () => {
    if (!selectedAvatarId) return;
    setError(null);
    setStatus("connecting");

    try {
      // 1. Get Agora credentials from backend
      const tokenResp = await fetch(`/api/voice/token?channel=${channelRef.current}`);
      const { appId, token, channel, uid } = await tokenResp.json();

      if (!appId) throw new Error("AGORA_APP_ID is not configured on the backend.");

      // 2. Create Agora RTC client
      const client = AgoraRTC.createClient({ mode: "rtc", codec: "vp8" });
      clientRef.current = client;

      // When the AI agent publishes its audio response, play it
      client.on("user-published", async (user, mediaType) => {
        await client.subscribe(user, mediaType);
        if (mediaType === "audio") {
          user.audioTrack.play();
          setStatus("speaking");

          // Poll avatar track volume for ripple animation
          const pollAvatar = () => {
            setAvatarVolume(user.audioTrack.getVolumeLevel?.() ?? 0);
            volumeRafRef.current = requestAnimationFrame(pollAvatar);
          };
          pollAvatar();
        }
      });

      client.on("user-unpublished", (_user, mediaType) => {
        if (mediaType === "audio") {
          setAvatarVolume(0);
          setStatus("listening");
        }
      });

      client.on("user-left", () => {
        setAvatarVolume(0);
        setStatus("listening");
      });

      // 3. Join channel
      await client.join(appId, channel, token ?? null, uid || null);

      // 4. Capture and publish microphone
      const micTrack = await AgoraRTC.createMicrophoneAudioTrack({
        encoderConfig: "speech_low_quality",
        AEC: true,
        ANS: true,
        AGC: true,
      });
      micTrackRef.current = micTrack;
      await client.publish([micTrack]);
      startVolumePolling(micTrack);

      // 5. Start the AI agent on the backend (which calls Agora's REST API)
      const agentResp = await fetch("/api/voice/agent/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          avatarId: selectedAvatarId,
          channel,
          userUid: uid || 0,
        }),
      });

      if (!agentResp.ok) {
        const err = await agentResp.json();
        throw new Error(typeof err.error === "string" ? err.error : JSON.stringify(err.error));
      }

      const { agentId: id } = await agentResp.json();
      setAgentId(id);
      setIsConnected(true);
      setStatus("listening");

    } catch (e) {
      console.error("Voice connection failed:", e);
      setError(e.message);
      setStatus("error");
      await disconnect(true);
    }
  };

  // Cleanup on unmount
  useEffect(() => {
    return () => { disconnect(true); };
  }, [disconnect]);

  const userRippleScale = 1 + userVolume * 2;
  const avatarRippleScale = 1 + avatarVolume * 2;
  const selectedAvatar = avatars.find(a => a.id === selectedAvatarId);

  return (
    <div className="min-h-screen bg-gradient-to-br from-emerald-100 to-stone-100 flex flex-col items-center justify-center p-6 gap-6">

      <h1 className="text-3xl font-poetic text-amber-700">Voice Avatar Lab</h1>

      {/* Avatar selector — only shown when not connected */}
      {!isConnected && avatars.length > 0 && (
        <div className="flex items-center gap-3">
          <label className="font-poetic text-stone-600 text-sm">Avatar:</label>
          <select
            className="p-2 rounded-md border bg-white font-poetic text-sm"
            value={selectedAvatarId ?? ""}
            onChange={e => setSelectedAvatarId(e.target.value)}
          >
            {avatars.map(a => (
              <option key={a.id} value={a.id}>{a.name}</option>
            ))}
          </select>
        </div>
      )}

      {isConnected && selectedAvatar && (
        <p className="font-poetic text-stone-500 text-sm">
          Speaking with: <span className="text-stone-700 font-semibold">{selectedAvatar.name}</span>
        </p>
      )}

      {/* Ripple visualisers */}
      <div className="relative flex flex-col items-center gap-16 my-4">

        {/* User mic ripple */}
        <div className="relative flex items-center justify-center w-32 h-32">
          <motion.div
            className="absolute w-32 h-32 rounded-full bg-lime-300"
            animate={{ scale: isConnected ? userRippleScale : 1, opacity: isConnected ? 0.55 : 0.15 }}
            transition={{ duration: 0.08 }}
          />
          <span className="relative z-10 text-xs font-poetic text-stone-600 text-center px-2">
            {isConnected ? "You" : ""}
          </span>
        </div>

        {/* Avatar audio ripple */}
        <div className="relative flex items-center justify-center w-48 h-48">
          <motion.div
            className="absolute w-48 h-48 rounded-full bg-cyan-300"
            animate={{
              scale: status === "speaking" ? avatarRippleScale : 1,
              opacity: status === "speaking" ? 0.55 : 0.1,
            }}
            transition={{ duration: 0.08 }}
          />
          <span className="relative z-10 text-xs font-poetic text-stone-600 text-center px-4">
            {isConnected ? "Avatar" : ""}
          </span>
        </div>
      </div>

      {/* Status label */}
      <p className="font-poetic text-stone-500 text-sm italic min-h-[1.25rem]">
        {STATUS_LABEL[status] ?? ""}
      </p>

      {/* Main action button */}
      {!isConnected ? (
        <Button
          onClick={connect}
          disabled={status === "connecting" || !selectedAvatarId}
          className="bg-amber-600 hover:bg-amber-700 text-white rounded-full px-8 py-3 text-base font-poetic"
        >
          {status === "connecting" ? "Connecting…" : "🎤 Start Conversation"}
        </Button>
      ) : (
        <Button
          onClick={() => disconnect()}
          className="bg-red-600 hover:bg-red-700 text-white rounded-full px-8 py-3 text-base font-poetic"
        >
          End Conversation
        </Button>
      )}

      {/* Error display */}
      {error && (
        <p className="text-sm text-red-600 max-w-sm text-center font-poetic">{error}</p>
      )}

      {/* Device integration guide */}
      {!isConnected && (
        <details className="mt-4 max-w-sm w-full">
          <summary className="text-xs text-stone-400 cursor-pointer font-poetic">
            Connecting a hardware device (Raspberry Pi / ReSpeaker)
          </summary>
          <div className="mt-2 text-xs text-stone-500 space-y-3 font-mono">
            <p className="font-poetic text-stone-600">Your device joins a shared voice channel. The avatar listens, thinks, and speaks back — your device only needs to handle audio input and output.</p>

            <p className="font-poetic font-semibold text-stone-600">Step 1 — Request a channel token</p>
            <pre className="bg-stone-100 rounded p-2 overflow-x-auto whitespace-pre-wrap">{`GET /api/voice/token?channel=my-device&uid=1
← { appId, channel, uid, token }`}</pre>

            <p className="font-poetic font-semibold text-stone-600">Step 2 — Start the avatar</p>
            <pre className="bg-stone-100 rounded p-2 overflow-x-auto whitespace-pre-wrap">{`POST /api/voice/agent/start
{ "avatarId": "0", "channel": "my-device", "userUid": 1 }
← { agentId, channel }`}</pre>

            <p className="font-poetic font-semibold text-stone-600">Step 3 — Join the channel and talk</p>
            <p>Install Agora's Python SDK and join the channel using the credentials from Step 1. Capture mic audio and publish it; subscribe to receive the avatar's spoken responses.</p>
            <pre className="bg-stone-100 rounded p-2 overflow-x-auto whitespace-pre-wrap">{`pip install agora-python-server-sdk

# join with appId + token from step 1
# publish mic audio → avatar hears you
# subscribe to audio → play avatar's response`}</pre>

            <p className="font-poetic font-semibold text-stone-600">Step 4 — End the session</p>
            <pre className="bg-stone-100 rounded p-2 overflow-x-auto whitespace-pre-wrap">{`POST /api/voice/agent/stop
{ "agentId": "<id from step 2>" }`}</pre>
          </div>
        </details>
      )}
    </div>
  );
}
