import { Link } from 'react-router-dom';
import { useEffect, useRef, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { motion } from "framer-motion";

export default function LahnAvatarChat() {
  const [refreshPromptState, setRefreshPromptState] = useState("idle");
  const [refreshEmbeddingsState, setRefreshEmbeddingsState] = useState("idle");
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [isThinking, setIsThinking] = useState(true);
  const [isDebateMode, setIsDebateMode] = useState(false);
  const [topics, setTopics] = useState([]);
  const [selectedTopic, setSelectedTopic] = useState("");
  const [debateSummary, setDebateSummary] = useState("");
  const chatEndRef = useRef(null);

  // Fetch initial chat
  useEffect(() => {
    const fetchInitialMessage = async () => {
      const response = await fetch(
        "https://lahn-server.eastus.cloudapp.azure.com:5001/api/chat",
        { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ prompt: "__INIT__" }) }
      );
      const data = await response.json();
      setMessages([{ sender: "avatar", text: data.reply }]);
      setIsThinking(false);
    };
    fetchInitialMessage();
  }, []);

  // Handle user submit
  const handleSubmit = async () => {
    if (!input.trim()) return;
    const userMessage = { sender: "user", text: input };
    setMessages(prev => [...prev, userMessage]);
    setInput("");
    setIsThinking(true);

    const response = await fetch(
      "https://lahn-server.eastus.cloudapp.azure.com:5001/api/chat",
      { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ prompt: input }) }
    );
    const data = await response.json();
    const avatarMessage = { sender: "avatar", text: data.reply };
    setMessages(prev => [...prev, avatarMessage]);
    setIsThinking(false);
  };

  // Fetch debate summary when in debate mode after each avatar response
  useEffect(() => {
    const last = messages[messages.length - 1];
    if (isDebateMode && last?.sender === 'avatar') {
      const fetchSummary = async () => {
        const resp = await fetch(
          "https://lahn-server.eastus.cloudapp.azure.com:5001/api/debate-summary",
          { method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ history: messages, topic: selectedTopic }) }
        );
        const json = await resp.json();
        setDebateSummary(json.summary);
      };
      fetchSummary();
    }
  }, [messages, isDebateMode, selectedTopic]);

  // Scroll to bottom
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleRefreshPrompt = async () => {
    setRefreshPromptState("loading");
    try {
      await fetch("https://lahn-server.eastus.cloudapp.azure.com:5001/api/refresh-prompt", {
        method: "POST",
      });
      setRefreshPromptState("done");
      setTimeout(() => setRefreshPromptState("idle"), 1500);
    } catch (err) {
      console.error("Refresh prompt failed:", err);
      setRefreshPromptState("idle");
    }
  };

  const handleRefreshEmbeddings = async () => {
    setRefreshEmbeddingsState("loading");
    try {
      await fetch("https://lahn-server.eastus.cloudapp.azure.com:5001/api/refresh-embeddings", {
        method: "POST",
      });
      setRefreshEmbeddingsState("done");
      setTimeout(() => setRefreshEmbeddingsState("idle"), 1500);
    } catch (err) {
      console.error("Refresh embeddings failed:", err);
      setRefreshEmbeddingsState("idle");
    }
  };


  return (

    // <div className="min-h-screen bg-gradient-to-br from-emerald-50 to-stone-100 p-4 flex flex-col items-center">
      
    <div className="min-h-screen bg-gradient-to-br from-emerald-50 to-stone-100 p-4 flex flex-col items-center">
      <motion.h1
        className="text-3xl font-poetic text-amber-700 mb-6"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 1 }}
      >
        Lahn River: Listening to the Ecosystem.
      </motion.h1>

      <motion.h3
        className="text-1xl font-poetic text-amber-700 italic mb-6"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 1 }}
      >
      Ever heard a river speak? Meet the Lahn, it has a lot to say.
      </motion.h3>

      {/* Controls */}
      <div className="flex items-center space-x-6 mb-4">
        <div className="flex items-center space-x-2">
          <Switch checked={isDebateMode} onCheckedChange={setIsDebateMode} />
          <span className="font-poetic text-stone-700">Debate Mode</span>
        </div>
        


        {/*<div className="flex space-x-4 mb-4">*/}
        <Button
          onClick={handleRefreshPrompt}
          disabled={refreshPromptState === "loading"}
          variant="outline"
        >
          {refreshPromptState === "idle" && "Refresh Prompt"}
          {refreshPromptState === "loading" && "Refreshing..."}
          {refreshPromptState === "done" && "✓ Done"}
        </Button>
        <Button
          onClick={handleRefreshEmbeddings}
          disabled={refreshEmbeddingsState === "loading"}
          variant="outline"
        >
          {refreshEmbeddingsState === "idle" && "Refresh Embeddings"}
          {refreshEmbeddingsState === "loading" && "Refreshing..."}
          {refreshEmbeddingsState === "done" && "✓ Done"}
        </Button>
      {/*</div>*/}




      </div>

      {/* Debate topic selector */}
      {isDebateMode && (
        <div className="w-full max-w-5xl mb-4 px-4">
          <label className="block mb-1 font-poetic text-stone-800">Choose a topic:</label>
          <select
            className="w-full p-2 rounded-md border bg-white font-poetic"
            value={selectedTopic}
            onChange={(e) => setSelectedTopic(e.target.value)}
          >
            <option value="">-- select --</option>
            {topics.map((t, idx) => (
              <option key={idx} value={t}>{t}</option>
            ))}
          </select>
        </div>
      )}

      <div className="flex w-full max-w-5xl space-x-4">
        {/* Chat Card */}
        <motion.div className="flex-1 px-4" /* animation props */>
          <Card className="rounded-2xl shadow-lg overflow-hidden bg-white/90">
            <CardContent className="h-[60vh] overflow-y-auto px-8 py-6 space-y-4 scroll-smooth flex flex-col">
              {messages.map((msg, i) => (
                <motion.div key={i} /* ... */>
                  <div /* ... */>{msg.text}</div>
                </motion.div>
              ))}
              {isThinking && <motion.div /* loading indicator */ />}
              <div ref={chatEndRef} />
            </CardContent>

            <div className="flex items-center gap-2 px-6 py-4 border-t bg-stone-50">
              <Input /* ... */ />
              <Button onClick={handleSubmit} /* ... */>Flow</Button>
            </div>
          </Card>
        </motion.div>

        {/* Debate Summary Pane */}
        {isDebateMode && (
          <div className="w-1/3 bg-white rounded-2xl shadow p-4 h-[60vh] overflow-y-auto">
            <h4 className="font-poetic text-lg mb-2">Debate Summary</h4>
            <p className="text-sm text-stone-700 whitespace-pre-wrap">{debateSummary}</p>
          </div>
        )}
      </div>

      <Link to="/experience" /* ... */>✍️ Share Your Experience with the Lahn</Link>
    </div>
  );
}
