import { useState, useRef } from "react";
import { motion } from "framer-motion";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
// import { Select } from "@/components/ui/select"; // assuming you have this, otherwise use <select>
import { Input } from "@/components/ui/input";

export default function VoiceChat() {
  const [isRecording, setIsRecording] = useState(false);
  const [pipeline, setPipeline] = useState("pipeline1");
  const [messages, setMessages] = useState([]);
  const [isThinking, setIsThinking] = useState(false);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);

  const startRecording = async () => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorderRef.current = new MediaRecorder(stream);
    audioChunksRef.current = [];

    mediaRecorderRef.current.ondataavailable = (e) => {
      if (e.data.size > 0) audioChunksRef.current.push(e.data);
    };

    mediaRecorderRef.current.onstop = async () => {
      const blob = new Blob(audioChunksRef.current, { type: "audio/webm" });
      const formData = new FormData();
      formData.append("audio", blob, "recording.webm");
      formData.append("pipeline", pipeline);

      setIsThinking(true);

      try {
        // const resp = await fetch("/api/voice-chat", {
        //   method: "POST",
        //   body: formData,
        // });
        // const { reply } = await resp.json();
        // setMessages((prev) => [...prev, { sender: "avatar", text: reply }]);


        const resp = await fetch("/api/voice-chat", {
          method: "POST",
          body: formData,
        });

        // Get audio back as Blob
        const audioBlob = await resp.blob();
        const audioUrl = URL.createObjectURL(audioBlob);

        // Play immediately
        const audio = new Audio(audioUrl);
        audio.play();

        // (optional) Add a "message" marker so the chat shows the avatar spoke
        setMessages((prev) => [
          ...prev,
          { sender: "avatar", text: "[🎵 audio reply]" },
        ]);

      } catch (err) {
        console.error(err);
      } finally {
        setIsThinking(false);
      }
    };

    mediaRecorderRef.current.start();
    setIsRecording(true);
  };

  const stopRecording = () => {
    mediaRecorderRef.current.stop();
    setIsRecording(false);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-emerald-100 to-stone-100 p-4 flex flex-col items-center">
      <motion.h1
        className="text-3xl font-poetic text-amber-700 mb-6"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 1 }}
      >
        Lahn River: Voice Conversations
      </motion.h1>

      <div className="flex items-center space-x-4 mb-6">
        <label className="font-poetic text-stone-700">Pipeline:</label>
        <select
          value={pipeline}
          onChange={(e) => setPipeline(e.target.value)}
          className="border rounded p-2 bg-white font-poetic"
        >
          <option value="pipeline1">OpenAI gpt-realtime</option>
          <option value="pipeline2">OpenAI gpt4o</option>
          <option value="pipeline3">Cartesia</option>
        </select>
      </div>


      <Card className="w-full max-w-3xl p-6 bg-white/90 shadow-lg flex flex-col space-y-4">
        <div className="flex-1 h-[60vh] overflow-y-auto">
          {messages.map((msg, i) => (
            <div
              key={i}
              className={`mb-3 flex ${
                msg.sender === "avatar" ? "justify-start" : "justify-end"
              }`}
            >
              <div
                className={`px-4 py-2 rounded-xl shadow text-base md:text-lg whitespace-pre-wrap ${
                  msg.sender === "avatar"
                    ? "bg-lime-100 text-stone-900"
                    : "bg-white text-stone-800"
                }`}
              >
                {msg.text}
              </div>
            </div>
          ))}
          {isThinking && (
            <div className="text-lime-700 italic">the river contemplates…</div>
          )}
        </div>

        <div className="flex justify-center space-x-4">
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
      </Card>
    </div>
  );
}
