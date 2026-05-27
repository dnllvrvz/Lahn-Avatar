import { useEffect, useRef, useState } from "react";
import { Card } from "@/components/ui/card";

import "@fontsource/chakra-petch";

const POLL_INTERVAL_MS = 3000;

export default function BackendLog() {
  const [log, setLog] = useState("");
  const [error, setError] = useState(null);
  const bottomRef = useRef(null);
  const preRef = useRef(null);
  const stickyRef = useRef(true);

  const fetchLog = async () => {
    try {
      const resp = await fetch("/api/backend-log");
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      setLog(data.log);
      setError(null);
    } catch (e) {
      setError(e.message);
    }
  };

  useEffect(() => {
    fetchLog();
    const timer = setInterval(fetchLog, POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, []);

  // Track whether user is scrolled to the bottom
  const handleScroll = () => {
    const el = preRef.current;
    if (!el) return;
    // Within 20px of bottom = "stuck to bottom"
    stickyRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 20;
  };

  // Auto-scroll only on initial load; afterwards keep position unless already pinned
  useEffect(() => {
    const el = preRef.current;
    if (!el) return;
    // First load: always scroll to bottom
    if (stickyRef.current) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [log]);

  return (
    <div className="min-h-screen p-4 flex flex-col items-center" style={{ fontFamily: "'Chakra Petch', sans-serif" }}>
      <video
        id="bg-video"
        src="/lahn_video_stitched.mp4"
        autoPlay
        muted
        loop
        playsInline
        className="fixed top-0 left-0 w-full h-full object-cover -z-10 opacity-70"
      ></video>

      <div className="bg-white/80 p-6 rounded-lg shadow-lg relative z-10 w-full flex flex-col">
        <h1 className="text-3xl text-amber-700 mb-4">Backend Log</h1>

        {error && (
          <p className="text-red-600 mb-2">Error loading log: {error}</p>
        )}

        <Card className="flex-1 bg-black/90 overflow-hidden">
          <pre
            ref={preRef}
            onScroll={handleScroll}
            className="overflow-y-auto px-4 py-4 text-stone-900 text-sm leading-relaxed"
            style={{ fontFamily: "monospace", maxHeight: "80vh", whiteSpace: "pre-wrap", wordBreak: "break-all" }}
          >
            {log}
            <div ref={bottomRef} />
          </pre>
        </Card>
      </div>
    </div>
  );
}
