import React, { useState, useRef } from "react";
import { Button } from "@/components/ui/button";

export default function VoiceChat() {
  const [recording, setRecording] = useState(false);
  const [reply, setReply] = useState("");
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);

  const startRecording = async () => {
    setReply("");
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mediaRecorder = new MediaRecorder(stream);
    audioChunksRef.current = [];
    mediaRecorderRef.current = mediaRecorder;

    mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > 0) {
        audioChunksRef.current.push(event.data);
      }
    };

    mediaRecorder.onstop = async () => {
      const audioBlob = new Blob(audioChunksRef.current, { type: "audio/webm" });
      const formData = new FormData();
      formData.append("audio", audioBlob, "recording.webm");

      try {
        const res = await fetch("http://127.0.0.1:5000/api/voice-chat", {
          method: "POST",
          body: formData,
        });
        const data = await res.json();
        if (data.reply_audio_url) {
          const audio = new Audio(data.reply_audio_url);
          audio.play();
        }
        setReply(data.reply_text || "(No text response)");
      } catch (err) {
        console.error("Error during voice chat:", err);
        setReply("⚠️ Error during voice chat");
      }
    };

    mediaRecorder.start();
    setRecording(true);
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current) {
      mediaRecorderRef.current.stop();
      setRecording(false);
    }
  };

  return (
    <div className="max-w-xl mx-auto py-10 px-4 text-center">
      <h2 className="text-2xl font-semibold mb-4">🎙️ Voice Chat with the Lahn</h2>
      <div className="flex justify-center items-center space-x-4">
        <Button onClick={startRecording} disabled={recording}>Start</Button>
        <Button onClick={stopRecording} disabled={!recording}>Stop</Button>
      </div>
      <p className="mt-6 text-muted-foreground">{reply}</p>
    </div>
  );
}
