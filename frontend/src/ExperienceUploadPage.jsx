import { Link } from 'react-router-dom';
import React, { useState, useRef } from 'react';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Loader2 } from "lucide-react";   // 🆕 spinner icon

export default function ExperienceUploadPage() {
  const [text, setText] = useState('');
  const [recording, setRecording] = useState(false);
  const [processing, setProcessing] = useState(false);     // 🆕
  const [submitted, setSubmitted] = useState(false);
  const [audioBlob, setAudioBlob] = useState(null);
  const [audioUrl, setAudioUrl] = useState(null);
  const [files, setFiles] = useState([null]);

  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const canvasRef = useRef(null);
  const animationIdRef = useRef(null);
  const streamRef = useRef(null);
  const analyserRef = useRef(null);

  const startRecording = async () => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mediaRecorder = new MediaRecorder(stream);
    const audioChunks = [];

    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) audioChunks.push(e.data);
    };

    mediaRecorder.onstop = () => {
      const blob = new Blob(audioChunks, { type: 'audio/webm' });
      const url = URL.createObjectURL(blob);
      setAudioBlob(blob);
      setAudioUrl(url);
      stopVisualizer();
    };

    streamRef.current = stream;
    mediaRecorderRef.current = mediaRecorder;
    audioChunksRef.current = audioChunks;

    mediaRecorder.start();
    setRecording(true);
    startVisualizer(stream);
  };

  const stopRecording = () => {
    mediaRecorderRef.current?.stop();
    streamRef.current?.getTracks().forEach((track) => track.stop());
    setRecording(false);
  };

  const startVisualizer = (stream) => {
    const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const source = audioCtx.createMediaStreamSource(stream);
    const analyser = audioCtx.createAnalyser();
    source.connect(analyser);
    analyser.fftSize = 256;
    analyserRef.current = analyser;

    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    const bufferLength = analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);

    const draw = () => {
      animationIdRef.current = requestAnimationFrame(draw);
      analyser.getByteTimeDomainData(dataArray);

      ctx.fillStyle = '#ffffff';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.lineWidth = 2;
      ctx.strokeStyle = '#4b5563';
      ctx.beginPath();

      const sliceWidth = canvas.width / bufferLength;
      let x = 0;

      for (let i = 0; i < bufferLength; i++) {
        const v = dataArray[i] / 128.0;
        const y = (v * canvas.height) / 2;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
        x += sliceWidth;
      }
      ctx.stroke();
    };

    draw();
  };

  const stopVisualizer = () => cancelAnimationFrame(animationIdRef.current);

  const handleSubmit = async () => {
    if (processing) return;          // 🆕 Prevent double click
    setProcessing(true);

    const formData = new FormData();
    formData.append('text', text);
    if (audioBlob) formData.append('audio', audioBlob, 'recording.webm');
    files.forEach(f => f && formData.append('files', f, f.name));

    const res = await fetch('/api/experience-upload', {
      method: 'POST',
      body: formData
    });

    if (res.ok) {
      setSubmitted(true);
    } else {
      alert("There was a problem uploading your experience.");
    }

    setProcessing(false);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-emerald-100 to-stone-100 p-8 sm:p-12 flex flex-col items-center">

      <Link to="/chat"
        className="text-amber-700 underline text-sm mb-6 hover:text-amber-900 self-start max-w-2xl"
      >
        ◀ Return to the River Chat
      </Link>

      <Card className={`
        w-full max-w-2xl shadow-xl rounded-2xl transition-all duration-300
        ${processing ? "opacity-50 pointer-events-none" : "opacity-100"}
      `}>
        <CardContent className="p-8">

          <h1 className="text-3xl font-semibold mb-4 text-stone-800 leading-snug">
            🌊 Share Your Experience With the Lahn
          </h1>

          <p className="text-stone-600 mb-6">
            Your message becomes part of the river’s collective memory.
            You may submit text, a voice recording, and/or upload files.
          </p>

          {!submitted ? (
            <>
              <Label className="font-medium text-stone-700">Your Message</Label>
              <Textarea
                placeholder="Tell your story…"
                value={text}
                onChange={e => setText(e.target.value)}
                className="bg-white text-stone-900 border-stone-300 mb-6 min-h-[130px]"
              />

              <div className="mb-6">
                <Label className="font-medium text-stone-700">Or Record Your Voice</Label>
                <div className="flex items-center gap-4 mt-2">
                  <Button
                    onClick={recording ? stopRecording : startRecording}
                    className={`
                      px-5 rounded-full text-white font-medium
                      ${recording ? "bg-red-600" : "bg-amber-600"}
                    `}
                  >
                    {recording ? "⏹ Stop Recording" : "🎤 Record"}
                  </Button>

                  {audioUrl && (
                    <audio controls className="ml-2">
                      <source src={audioUrl} type="audio/webm" />
                    </audio>
                  )}
                </div>

                <canvas
                  ref={canvasRef}
                  width="500"
                  height="60"
                  className="rounded bg-stone-200 mt-3 shadow-inner"
                />
              </div>

              {files.map((f, idx) => (
                <div key={idx} className="mb-4">
                  <Label className="text-stone-700">
                    Upload File #{idx + 1}
                  </Label>
                  <input
                    type="file"
                    onChange={e => {
                      const newFiles = [...files];
                      newFiles[idx] = e.target.files[0];
                      setFiles(newFiles);
                    }}
                    className="block w-full text-stone-800 border border-stone-300 rounded p-2 file:bg-stone-200"
                  />
                </div>
              ))}

              <Button
                variant="outline"
                className="w-full mb-6 border-stone-400 hover:bg-stone-200"
                onClick={() => setFiles([...files, null])}
              >
                ➕ Add Another File
              </Button>

              <Button
                onClick={handleSubmit}
                disabled={processing}
                className="w-full bg-amber-600 hover:bg-amber-700 text-white font-medium py-3 rounded-xl"
              >
                {processing ? (
                  <span className="flex items-center gap-2">
                    <Loader2 className="animate-spin" size={19} />
                    Processing…
                  </span>
                ) : (
                  "Submit Experience"
                )}
              </Button>

            </>
          ) : (
            <p className="text-green-700 text-lg font-semibold text-center py-6">
              🌱 Thank you — your story now flows with the river 💚
            </p>
          )}
        </CardContent>
      </Card>

      {/* 🆕 Floating Processing Ribbon */}
      {processing && (
        <div className="
          fixed bottom-6 px-6 py-3 rounded-full shadow-xl
          bg-emerald-700 text-white font-medium
          animate-pulse
        ">
          ⏳ Upload received — processing in the background…
        </div>
      )}
    </div>
  );
}
