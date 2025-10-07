import { Link } from 'react-router-dom';
import { useEffect, useRef, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Button } from "@/components/ui/button";
import { motion } from "framer-motion";

export default function LahnAvatarChat() {
  const [refreshPromptState, setRefreshPromptState] = useState("idle");
  const [refreshEmbeddingsState, setRefreshEmbeddingsState] = useState("idle");
  const [defaultMessages, setDefaultMessages] = useState([]);
  const [debateMessages, setDebateMessages] = useState([]);
  const [input, setInput] = useState("");
  const [defaultThinking, setDefaultThinking] = useState(false);
  const [debateThinking, setDebateThinking] = useState(false);
  const [isDebateMode, setIsDebateMode] = useState(false);
  const [topics] = useState(['Clean up Lahn', 'Reforest headwater']);
  const [selectedTopic, setSelectedTopic] = useState("");
  const [debateSummary, setDebateSummary] = useState("");
  const [hasFetchedDebateInit, setHasFetchedDebateInit] = useState(false);
  const chatEndRef = useRef(null);
  const initialFetchRef = useRef(false);

  const messages = isDebateMode ? debateMessages : defaultMessages;
  const setMessages = isDebateMode ? setDebateMessages : setDefaultMessages;
  const isThinking = isDebateMode ? debateThinking : defaultThinking;
  const setIsThinking = isDebateMode ? setDebateThinking : setDefaultThinking;

  const fetchMessage = async (prompt) => {
    if (!prompt?.trim()) {
      console.log("fetchMessage skipped due to empty prompt");
      return;
    }
    console.log("fetchMessage called with prompt:", prompt);
    setIsThinking(true);
    try {
      const resp = await fetch(
        "https://lahn-server.eastus.cloudapp.azure.com:5001/api/chat",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ prompt }),
        }
      );
      const { reply } = await resp.json();
      console.log("Received reply:", reply);
      setMessages([{ sender: "avatar", text: reply }]);
    } catch (error) {
      console.error("Failed to fetch message:", error);
    } finally {
      setIsThinking(false);
    }
  };

  useEffect(() => {
    console.log("Initial useEffect: isDebateMode=", isDebateMode);
    if (!isDebateMode && !initialFetchRef.current) {
      initialFetchRef.current = true;
      fetchMessage("__INIT__");
    }
  }, []);

  useEffect(() => {
    console.log("Debate useEffect: isDebateMode=", isDebateMode, "selectedTopic=", selectedTopic);
    if (isDebateMode && selectedTopic && !hasFetchedDebateInit) {
      fetchMessage(`Let's talk about ${selectedTopic}`);
      setHasFetchedDebateInit(true);
    }
  }, [isDebateMode, selectedTopic, hasFetchedDebateInit]);

  const handleRefreshPrompt = async () => {
    setRefreshPromptState("loading");
    try {
      await fetch("https://lahn-server.eastus.cloudapp.azure.com:5001/api/refresh-prompt", { method: "POST" });
      setRefreshPromptState("done");
      setTimeout(() => setRefreshPromptState("idle"), 1500);
    } catch {
      setRefreshPromptState("idle");
    }
  };

  const handleRefreshEmbeddings = async () => {
    setRefreshEmbeddingsState("loading");
    try {
      await fetch("https://lahn-server.eastus.cloudapp.azure.com:5001/api/refresh-embeddings", { method: "POST" });
      setRefreshEmbeddingsState("done");
      setTimeout(() => setRefreshEmbeddingsState("idle"), 1500);
    } catch {
      setRefreshEmbeddingsState("idle");
    }
  };

  const handleSubmit = async () => {
    if (!input.trim()) return;
    console.log("handleSubmit: input=", input);
    setMessages(prev => [...prev, { sender: "user", text: input }]);
    setInput("");
    setIsThinking(true);
    try {
      const resp = await fetch(
        "https://lahn-server.eastus.cloudapp.azure.com:5001/api/chat",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ history: messages, prompt: input }),
        }
      );
      const { reply } = await resp.json();
      console.log("submission reply=", reply);
      setMessages(prev => [...prev, { sender: "avatar", text: reply }]);
    } catch (error) {
      console.error("Chat submission failed:", error);
    } finally {
      setIsThinking(false);
    }
  };

  useEffect(() => {
    const last = debateMessages[debateMessages.length - 1];
    console.log("Summary effect: last=", last);
    if (isDebateMode && selectedTopic && last?.sender === 'avatar') {
      (async () => {
        try {
          const resp = await fetch(
            "https://lahn-server.eastus.cloudapp.azure.com:5001/api/debate-summary",
            {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ history: debateMessages, topic: selectedTopic }),
            }
          );
          const { summary } = await resp.json();
          console.log("Debate summary=", summary);
          setDebateSummary(summary);
        } catch (error) {
          console.error("Debate summary failed:", error);
        }
      })();
    }
  }, [debateMessages, isDebateMode, selectedTopic]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className="min-h-screen bg-gradient-to-br from-emerald-50 to-stone-100 p-4 flex flex-col items-center">
      <motion.h1 className="text-3xl font-poetic text-amber-700 mb-6" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 1 }}>
        Lahn River: Listening to the Ecosystem.
      </motion.h1>
      <motion.h3 className="text-xl font-poetic text-amber-700 italic mb-6" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 1 }}>
        Ever heard a river speak? Meet the Lahn, it has a lot to say.
      </motion.h3>

      <div className="flex items-center space-x-6 mb-4">
        <div className="flex items-center space-x-2">
          <Switch checked={isDebateMode} onCheckedChange={val => { console.log("Debate toggled=", val); setIsDebateMode(val); }} />
          <span className="font-poetic text-stone-700">Debate Mode</span>
        </div>
        <Button onClick={handleRefreshPrompt} disabled={refreshPromptState === "loading"} variant="outline">
          {refreshPromptState === "idle" ? "Refresh Prompt" : refreshPromptState === "loading" ? "Refreshing..." : "✓ Done"}
        </Button>
        <Button onClick={handleRefreshEmbeddings} disabled={refreshEmbeddingsState === "loading"} variant="outline">
          {refreshEmbeddingsState === "idle" ? "Refresh Embeddings" : refreshEmbeddingsState === "loading" ? "Refreshing..." : "✓ Done"}
        </Button>
      </div>

      {isDebateMode && (
        <div className="w-3/4 max-w-5xl mb-4 px-4">
          <label className="block mb-1 font-poetic text-stone-800">Choose a topic:</label>
          <select className="w-full p-2 rounded-md border bg-white font-poetic" value={selectedTopic} onChange={e => { console.log("Topic=", e.target.value); setSelectedTopic(e.target.value); setHasFetchedDebateInit(false); }}>
            <option value="">-- select --</option>
            {topics.map((t, i) => (<option key={i} value={t}>{t}</option>))}
          </select>
        </div>
      )}

      <motion.div className="px-4 w-full">
        <div className={`flex ${isDebateMode ? 'space-x-4' : ''}`}> 
          <div className={`${isDebateMode ? 'flex-1' : 'w-full max-w-5xl'} rounded-2xl`}>
            <Card className="shadow-lg overflow-hidden bg-white/90">
              <CardContent className="h-[60vh] overflow-y-auto px-8 py-6 space-y-4 flex flex-col">
                {messages.map((msg, i) => (
                  <motion.div key={i} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }} className={`flex ${msg.sender === 'avatar' ? 'justify-start' : 'justify-end'}`}>
                    <div className={`max-w-lg px-4 py-3 rounded-xl shadow text-base md:text-lg ${msg.sender === 'avatar' ? 'bg-lime-100 text-stone-900' : 'bg-white text-stone-800'}`}>{msg.text}</div>
                  </motion.div>
                ))}
                {isThinking && (
                  <motion.div className="text-lime-700 italic self-start" animate={{ opacity: [0.3, 1, 0.3], x: [0, 2, -2, 0] }} transition={{ repeat: Infinity, duration: 2 }}>
                    the river contemplates...
                  </motion.div>
                )}
                <div ref={chatEndRef} />
              </CardContent>
              <div className="flex items-center gap-2 px-6 py-4 border-t bg-stone-50">
                <motion.div key={input} className="flex-1" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.6 }}>
                  <Input className="w-full rounded-full font-poetic bg-white" style={{ color: '#1c1917' }} placeholder="Speak with the river..." value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleSubmit()} />
                </motion.div>
                <motion.div key={messages.length} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.6 }}>
                  <Button onClick={handleSubmit} className="rounded-full px-6 py-2 font-poetic bg-amber-600 text-white hover:bg-amber-700">
                    Flow
                  </Button>
                </motion.div>
              </div>
            </Card>
          </div>

          {isDebateMode && (
            <div className="w-1/3 bg-white rounded-2xl shadow p-4 h-[60vh] overflow-y-auto">
              <h4 className="font-poetic text-lg font-bold mb-2">Debate Summary</h4>
              <p className="text-sm text-stone-700 whitespace-pre-wrap">{debateSummary}</p>
            </div>
          )}
        </div>
      </motion.div>

      <Link to="/experience" className="text-amber-700 underline text-sm mt-4 hover:text-amber-900">
        ✍️ Share Your Experience with the Lahn
      </Link>
    </div>
  );
}
