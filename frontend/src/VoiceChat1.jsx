import React, { useState, useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Mic, StopCircle } from "lucide-react";

export default function VoiceChat() {
  const [recording, setRecording] = useState(false);
  const [reply, setReply] = useState("");
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const canvasRef = useRef(null);
  const animationRef = useRef(null);
  const analyserRef = useRef(null);
  const dataArrayRef = useRef(null);
  const audioCtxRef = useRef(null);

  // Initialize canvas drawing context
  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, canvas.width, canvas.height);
  }, []);

  // Draw waveform continuously
  const drawWave = () => {
    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d");
    const analyser = analyserRef.current;
    const dataArray = dataArrayRef.current;
    const bufferLength = analyser.frequencyBinCount;

    analyser.getByteTimeDomainData(dataArray);

    ctx.fillStyle = "#f3f4f6";      // light bg
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.lineWidth = 2;
    ctx.strokeStyle = recording ? "#dc2626" : "#2563eb"; // red when rec, blue when playback
    ctx.beginPath();

    const sliceWidth = canvas.width / bufferLength;
    let x = 0;
    for (let i = 0; i < bufferLength; i++) {
      const v = dataArray[i] / 128.0;   // normalized
      const y = (v * canvas.height) / 2;
      if (i === 0) ctx.moveTo(x, y);
      else        ctx.lineTo(x, y);
      x += sliceWidth;
    }

    ctx.lineTo(canvas.width, canvas.height / 2);
    ctx.stroke();

    animationRef.current = requestAnimationFrame(drawWave);
  };

  const startRecording = async () => {
    setReply("");
    // 1. get mic stream
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    audioCtxRef.current = audioCtx;

    // 2. hook up analyser
    const source = audioCtx.createMediaStreamSource(stream);
    const analyser = audioCtx.createAnalyser();
    analyser.fftSize = 2048;
    source.connect(analyser);
    analyserRef.current = analyser;

    const bufferLength = analyser.frequencyBinCount;
    dataArrayRef.current = new Uint8Array(bufferLength);

    // 3. start draw loop
    drawWave();

    // 4. set up recorder
    audioChunksRef.current = [];
    const mediaRecorder = new MediaRecorder(stream);
    mediaRecorderRef.current = mediaRecorder;
    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) audioChunksRef.current.push(e.data);
    };
    mediaRecorder.start();
    setRecording(true);
  };

  const stopRecording = async () => {
    return new Promise((resolve) => {
      const mediaRecorder = mediaRecorderRef.current;
      const audioCtx = audioCtxRef.current;

      // Close audio context and stop waveform
      audioCtx.close();
      cancelAnimationFrame(animationRef.current);
      setRecording(false);

      // On stop, assemble blob and send it
      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: "audio/webm" });

        // Upload
        const formData = new FormData();
        formData.append("audio", audioBlob, "recording.webm");

        try {
          const res = await fetch("https://lahn-server.eastus.cloudapp.azure.com:5001/api/voice-chat", { method: "POST", body: formData });
          const data = await res.json();
          setReply(data.reply_text || "(No text response)");

          if (data.reply_audio_url) {
            const audio = new Audio(data.reply_audio_url);
            await audio.play();

            // const ctx = new (window.AudioContext || window.webkitAudioContext)();
            // audioCtxRef.current = ctx;
            // const source = ctx.createMediaElementSource(audio);
            // const analyser = ctx.createAnalyser();
            // analyser.fftSize = 2048;
            // source.connect(analyser);
            // analyser.connect(ctx.destination);
            // analyserRef.current = analyser;

            // const bufferLength = analyser.frequencyBinCount;
            // dataArrayRef.current = new Uint8Array(bufferLength);
            // drawWave();

            // audio.onended = () => {
            //   cancelAnimationFrame(animationRef.current);
            //   ctx.close();
            // };
          }

          resolve();
        } catch (err) {
          console.error("Error during voice chat:", err);
          setReply("⚠️ Error during voice chat");
          resolve(); // resolve anyway to unblock UI
        }
      };

      // Actually stop
      mediaRecorder.stop();
    });
  };


  const toggleRecording = () => (recording ? stopRecording() : startRecording());

  return (
    <div className="max-w-xl mx-auto py-10 px-4 text-center space-y-6">
      <h2 className="text-2xl font-semibold">🎙️ Voice Chat with the Lahn</h2>

      <canvas
        ref={canvasRef}
        width={600}
        height={100}
        className="w-full rounded border bg-white"
      />

      <Button
        onClick={toggleRecording}
        variant={recording ? "destructive" : "primary"}
        className="flex items-center justify-center space-x-2 w-32 mx-auto"
      >
        {recording ? <StopCircle /> : <Mic />}
        <span>{recording ? "Stop" : "Speak"}</span>
      </Button>

      <p className="mt-4 text-muted-foreground">{reply}</p>
    </div>
  );
}
