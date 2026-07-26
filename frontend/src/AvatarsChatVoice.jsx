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
  const [isDisconnecting, setIsDisconnecting] = useState(false);
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
    if (!silent) setIsDisconnecting(true);
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
    setIsDisconnecting(false);
    setStatus("idle");
  }, [agentId, stopVolumePolling]);

  const connect = async () => {
    if (!selectedAvatarId || status === "connecting") return;
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

      // Listen for connection state changes
      client.on("connection-state-change", (curState, revState, reason) => {
        console.log(`[Agora] Connection: ${revState} → ${curState}, reason: ${reason}`);
      });

      client.on("exception", (evt) => {
        console.error("[Agora] Exception:", evt);
      });

      // 3. Request mic access FIRST (so we fail fast before joining channel)
      console.log("[Agora] Requesting microphone access...");
      const micTrack = await AgoraRTC.createMicrophoneAudioTrack({
        encoderConfig: "speech_low_quality",
        AEC: true,
        ANS: true,
        AGC: true,
      });
      micTrackRef.current = micTrack;
      console.log("[Agora] Mic access granted");

      // 4. Join channel
      console.log("[Agora] Joining:", { appId, channel, token: token?.slice(0, 20) + "...", uid });
      const assignedUid = await client.join(appId, channel, token ?? null, uid || null);
      console.log("[Agora] Joined successfully, assigned uid:", assignedUid);

      // 5. Publish mic track
      console.log("[Agora] Publishing mic track...");
      await client.publish([micTrack]);
      console.log("[Agora] Mic track published");
      startVolumePolling(micTrack);

      // 6. Start the AI agent on the backend (which calls Agora's REST API)
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

  // Cleanup on unmount — use ref to avoid re-triggering on every render
  const disconnectRef = useRef(disconnect);
  disconnectRef.current = disconnect;
  useEffect(() => {
    return () => { disconnectRef.current(true); };
  }, []);

  const userRippleScale = Math.min(1 + userVolume * 2, 1.6);
  const avatarRippleScale = Math.min(1 + avatarVolume * 2, 1.6);
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

      {/* Orbs — isolated in their own block, never overlap buttons below */}
      <div className="flex flex-col items-center gap-16 my-4">

        {/* User mic ripple */}
        <div className="relative flex items-center justify-center w-32 h-32">
          <motion.div
            className="absolute w-20 h-20 rounded-full bg-lime-300"
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
            className="absolute w-28 h-28 rounded-full bg-cyan-300"
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

      {/* Start / End button — always below the orbs */}
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
          disabled={isDisconnecting}
          className="bg-red-600 hover:bg-red-700 text-white rounded-full px-8 py-3 text-base font-poetic disabled:opacity-60"
        >
          {isDisconnecting ? "Ending…" : "End Conversation"}
        </Button>
      )}

      {/* Error display */}
      {error && (
        <p className="text-sm text-red-600 max-w-sm text-center font-poetic">{error}</p>
      )}

      {/* Device integration guide */}
      {!isConnected && (
        <details className="mt-4 max-w-lg w-full">
          <summary className="text-xs text-stone-400 cursor-pointer font-poetic">
            Connecting a hardware device (Raspberry Pi / ReSpeaker)
          </summary>
          <div className="mt-2 text-xs text-stone-500 space-y-3 font-mono">
            <p className="font-poetic text-stone-600">Your device joins a shared voice channel. The avatar listens, thinks, and speaks back — your device only needs to handle audio input and output.</p>
            <p className="font-poetic text-stone-500">
              Base URL: <code className="bg-stone-100 rounded px-1">https://avatars.sympoiesis.xyz</code>
            </p>

            <p className="font-poetic font-semibold text-stone-600">Requirements</p>
            <p className="font-poetic">Python 3.10 or newer. Linux or macOS (Raspberry Pi / arm64 supported, Windows is not).</p>
            <pre className="bg-stone-100 rounded p-2 overflow-x-auto whitespace-pre-wrap">{`# On Raspberry Pi, install system audio libraries first:
sudo apt-get install python3-pyaudio portaudio19-dev

# Then install Python packages:
pip install agora-python-server-sdk pyaudio requests`}</pre>

            <p className="font-poetic font-semibold text-stone-600">Step 0 — Find available avatars</p>
            <pre className="bg-stone-100 rounded p-2 overflow-x-auto whitespace-pre-wrap">{`GET /api/avatars
← [{ "id": "0", "name": "Lahn" }, { "id": "1", "name": "..." }, ...]`}</pre>

            <p className="font-poetic font-semibold text-stone-600">Step 1 — Get a channel token</p>
            <p className="font-poetic">Choose a unique name for your device's channel and any numeric user ID.</p>
            <pre className="bg-stone-100 rounded p-2 overflow-x-auto whitespace-pre-wrap">{`GET /api/voice/token?channel=my-device&uid=1
← { appId, channel, uid, token }`}</pre>

            <p className="font-poetic font-semibold text-stone-600">Step 2 — Start the avatar</p>
            <p className="font-poetic">Use the avatar <code className="bg-stone-100 rounded px-1">id</code> from Step 0 and the <code className="bg-stone-100 rounded px-1">channel</code> / <code className="bg-stone-100 rounded px-1">uid</code> from Step 1.</p>
            <pre className="bg-stone-100 rounded p-2 overflow-x-auto whitespace-pre-wrap">{`POST /api/voice/agent/start
Content-Type: application/json
{ "avatarId": "0", "channel": "my-device", "userUid": 1 }
← { agentId, channel }`}</pre>

            <p className="font-poetic font-semibold text-stone-600">Step 3 — Run the client script</p>
            <p className="font-poetic">Save the script below as <code className="bg-stone-100 rounded px-1">avatar_client.py</code>. Edit the four constants at the top, then run it. It handles Steps 1 and 2 automatically, joins the channel, streams your mic to the avatar, and plays the avatar's voice through your speaker. Press Ctrl+C to end.</p>
            <pre className="bg-stone-100 rounded p-2 overflow-x-auto whitespace-pre-wrap">{`#!/usr/bin/env python3
import asyncio, pyaudio, requests
from agora.rtc.agora_service import AgoraService, AgoraServiceConfig
from agora.rtc.rtc_connection import RTCConnConfig, RtcConnectionPublishConfig
from agora.rtc.agora_base import (
    AudioProfileType, AudioScenarioType, AudioPublishType, VideoPublishType,
    AudioSubscriptionOptions, ClientRoleType, ChannelProfileType,
)
from agora.rtc.audio_frame_observer import IAudioFrameObserver

# ── configure these ──────────────────────────────────────────────
BASE    = "https://avatars.sympoiesis.xyz"
CHANNEL = "my-device"   # unique name for this device
UID     = 1             # any integer
AVATAR  = "0"           # avatar id from GET /api/avatars
# ─────────────────────────────────────────────────────────────────

RATE, CH, CHUNK = 16000, 1, int(16000 * 0.02)  # 16 kHz mono, 20 ms frames

pa      = pyaudio.PyAudio()
speaker = pa.open(format=pyaudio.paInt16, channels=CH, rate=RATE, output=True)

class SpeakerObserver(IAudioFrameObserver):
    def on_playback_audio_frame_before_mixing(self, _lu, _cid, _uid, frame, _vs=0, _vd=None):
        speaker.write(bytes(frame.buffer))
        return 1

async def main():
    creds = requests.get(f"{BASE}/api/voice/token?channel={CHANNEL}&uid={UID}").json()
    agent = requests.post(f"{BASE}/api/voice/agent/start",
                json={"avatarId": AVATAR, "channel": CHANNEL, "userUid": UID}).json()
    agent_id = agent["agentId"]
    print(f"Avatar started — speak into your mic. Ctrl+C to end.")

    svc_cfg       = AgoraServiceConfig()
    svc_cfg.appid = creds["appId"]
    svc           = AgoraService()
    svc.initialize(svc_cfg)

    conn_cfg = RTCConnConfig(
        client_role_type=ClientRoleType.CLIENT_ROLE_BROADCASTER,
        channel_profile=ChannelProfileType.CHANNEL_PROFILE_LIVE_BROADCASTING,
        auto_subscribe_audio=1,
        auto_subscribe_video=0,
        audio_recv_media_packet=0,
        audio_subs_options=AudioSubscriptionOptions(
            packet_only=0, pcm_data_only=1,
            bytes_per_sample=2, number_of_channels=CH, sample_rate_hz=RATE,
        ),
    )
    pub_cfg = RtcConnectionPublishConfig(
        audio_profile=AudioProfileType.AUDIO_PROFILE_DEFAULT,
        audio_scenario=AudioScenarioType.AUDIO_SCENARIO_AI_SERVER,
        is_publish_audio=True, is_publish_video=False,
        audio_publish_type=AudioPublishType.AUDIO_PUBLISH_TYPE_PCM,
        video_publish_type=VideoPublishType.VIDEO_PUBLISH_TYPE_NONE,
    )
    conn = svc.create_rtc_connection(conn_cfg, pub_cfg)
    conn.connect(creds["token"], CHANNEL, str(UID))

    local_user = conn.get_local_user()
    local_user.set_playback_audio_frame_before_mixing_parameters(CH, RATE)
    conn.register_audio_frame_observer(SpeakerObserver(), 0, None)
    conn.publish_audio()

    mic  = pa.open(format=pyaudio.paInt16, channels=CH, rate=RATE,
                   input=True, frames_per_buffer=CHUNK)
    loop = asyncio.get_event_loop()
    try:
        while True:
            pcm = await loop.run_in_executor(None, mic.read, CHUNK)
            conn.push_audio_pcm_data(pcm, RATE, CH)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        mic.stop_stream(); mic.close()
        requests.post(f"{BASE}/api/voice/agent/stop", json={"agentId": agent_id})
        conn.disconnect(); conn.release()
        svc.release()
        speaker.stop_stream(); speaker.close()
        pa.terminate()
        print("Session ended.")

asyncio.run(main())`}</pre>
          </div>
        </details>
      )}
    </div>
  );
}
