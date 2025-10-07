import React, { useRef, useEffect } from "react";
import * as tf from "@tensorflow/tfjs";
import * as bodyPix from "@tensorflow-models/body-pix";
import "@tensorflow/tfjs-backend-webgl";

export default function Mirror() {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const webcamRef = useRef(null);

  useEffect(() => {
    const loadModelAndStart = async () => {
      await tf.setBackend("webgl");
      await tf.ready();
      const net = await bodyPix.load();

      const webcamStream = await navigator.mediaDevices.getUserMedia({ video: true });
      webcamRef.current.srcObject = webcamStream;

      const drawLoop = async () => {
        if (webcamRef.current.readyState === 4) {
          const video = webcamRef.current;
          const canvas = canvasRef.current;
          const ctx = canvas.getContext("2d");

          canvas.width = video.videoWidth;
          canvas.height = video.videoHeight;

          const segmentation = await net.segmentPerson(video, {
            internalResolution: "medium",
            segmentationThreshold: 0.7,
          });

          const mask = bodyPix.toMask(segmentation);

          // Draw webcam frame first
          ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

          // Read pixels and apply mask
          const frame = ctx.getImageData(0, 0, canvas.width, canvas.height);
          for (let i = 0; i < frame.data.length; i += 4) {
            const alpha = mask.data[i + 3]; // mask alpha
            if (alpha < 128) {
              frame.data[i + 3] = 0; // transparent background
            }
          }
          ctx.putImageData(frame, 0, 0);
        }

        requestAnimationFrame(drawLoop);
      };

      drawLoop();
    };

    loadModelAndStart();
  }, []);

  return (
    <div className="relative w-full h-screen overflow-hidden">
      {/* Background looping video */}
      <video
        ref={videoRef}
        src="/video.mp4"
        autoPlay
        loop
        muted
        playsInline
        className="absolute top-0 left-0 w-full h-full object-cover z-0"
      />

      {/* Hidden webcam feed */}
      <video
        ref={webcamRef}
        autoPlay
        muted
        playsInline
        className="hidden"
      />

      {/* Canvas compositing foreground (person only) */}
      <canvas
        ref={canvasRef}
        className="absolute top-0 left-0 w-full h-full z-10"
      />
    </div>
  );
}
