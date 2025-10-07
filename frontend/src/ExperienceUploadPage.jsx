import { Link } from 'react-router-dom';
import React, { useState, useRef, useEffect } from 'react';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Label } from '@/components/ui/label';

export default function ExperienceUploadPage() {
  const [text, setText] = useState('');
  const [recording, setRecording] = useState(false);
  const [audioBlob, setAudioBlob] = useState(null);
  const [audioUrl, setAudioUrl] = useState(null);
  const [submitted, setSubmitted] = useState(false);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const canvasRef = useRef(null);
  const animationIdRef = useRef(null);
  const streamRef = useRef(null);
  const analyserRef = useRef(null);
  const [files, setFiles] = useState([null]);


  const handleTextChange = (e) => setText(e.target.value);

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
      ctx.strokeStyle = '#4b5563'; // stone-700
      ctx.beginPath();

      const sliceWidth = canvas.width / bufferLength;
      let x = 0;
      for (let i = 0; i < bufferLength; i++) {
        const v = dataArray[i] / 128.0;
        const y = (v * canvas.height) / 2;
        if (i === 0) {
          ctx.moveTo(x, y);
        } else {
          ctx.lineTo(x, y);
        }
        x += sliceWidth;
      }
      ctx.lineTo(canvas.width, canvas.height / 2);
      ctx.stroke();
    };

    draw();
  };

  const stopVisualizer = () => {
    cancelAnimationFrame(animationIdRef.current);
  };


  const handleSubmit = async () => {
    const formData = new FormData();
    formData.append('text', text);
    if (audioBlob) {
      formData.append('audio', audioBlob, 'recording.webm');
    }

    files.forEach(f => {
      if (f) formData.append('files', f, f.name);
    });

    const response = await fetch('/api/experience-upload', {
      method: 'POST',
      body: formData,
    });

    if (response.ok) {
      setSubmitted(true);
    } else {
      alert('There was a problem uploading your experience.');
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-emerald-100 to-stone-100 p-6 flex flex-col items-center">
      <Link
        to="/chat"
        className="text-amber-700 underline text-sm mb-4 hover:text-amber-900 self-start max-w-2xl"
      >
        🌊 Return to the River Chat
      </Link>

      <Card className="w-full max-w-2xl bg-white/90 shadow-xl rounded-2xl">
        <CardContent className="p-6">
          <h1 className="text-2xl font-semibold mb-4 text-stone-800">
            🌊 Do you have a personal story about the Lahn river? Share it here anonymously.
          </h1>
          <ul className="mb-4 text-sm text-stone-600 list-disc pl-6">
            <li>Share a story or moment you’ll never forget that happened near the Lahn.</li>
            <li>Describe a time the river made you feel something.</li>
            <li>What does the Lahn mean to you?</li>
          </ul>

          {!submitted ? (
            <>
              <div className="mb-4">
                <Label htmlFor="experience-text" className="text-stone-700">
                  Your Message
                </Label>
                <Textarea
                  id="experience-text"
                  placeholder="Type your story or message here..."
                  value={text}
                  onChange={handleTextChange}
                  className="bg-white text-stone-800 border-stone-300"
                />
              </div>

              <div className="mb-4">
                <Label className="text-stone-700">Or record your voice</Label>
                <div className="flex items-center gap-4 mb-2">
                  <Button
                    onClick={recording ? stopRecording : startRecording}
                    className={`px-4 py-2 rounded-full text-white font-poetic ${
                      recording ? 'bg-red-600 hover:bg-red-700' : 'bg-amber-600 hover:bg-amber-700'
                    }`}
                  >
                    {recording ? 'Stop Recording' : 'Record'}
                  </Button>
                  {audioUrl && (
                    <audio controls className="mt-2">
                      <source src={audioUrl} type="audio/webm" />
                    </audio>
                  )}
                </div>
                <canvas ref={canvasRef} width="500" height="60" className="rounded bg-stone-200" />
              </div>

              {files.map((f, idx) => (
              <div key={idx} className="mb-4">
                <Label htmlFor={`experience-file-${idx}`} className="text-stone-700">
                  Upload File #{idx + 1}
                </Label>
                <input
                  id={`experience-file-${idx}`}
                  type="file"
                  onChange={e => {
                    const newFiles = [...files];
                    newFiles[idx] = e.target.files[0];
                    setFiles(newFiles);
                  }}
                  className="block w-full text-stone-800 border border-stone-300 rounded p-2 file:bg-stone-200 file:px-3 file:py-1 file:rounded"
                />
              </div>
            ))}

            <Button
              type="button"
              onClick={() => setFiles([...files, null])}
              className="block w-full mb-6 bg-stone-100 text-stone-800 hover:bg-stone-200"
              >
              Add another file
            </Button>


              <Button
                onClick={handleSubmit}
                className="bg-amber-600 text-white hover:bg-amber-700"
              >
                Submit Experience
              </Button>
            </>
          ) : (
            <p className="text-green-700 font-semibold">
              🌱 Thank you for sharing your experience with the Lahn 💚
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
