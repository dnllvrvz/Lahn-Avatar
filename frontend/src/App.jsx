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
  const [topics] = useState(['The Lahn should have legal personhood', 'The Lahn should be able to own property', 'There should exist a “Lahn Fund”', 'The Avatar should be able to legally speak on behalf of the Lahn']);
  const topicDescriptions = {
    'The Lahn should have legal personhood': "In recent years, rivers around the world have been granted legal personhood to recognize their intrinsic rights and protect their ecosystems. Granting the Lahn legal personhood would mean treating the river not merely as a resource but as a living entity with legal standing - analogous to the legal standing that a person or corporation holds. This shift could reshape how environmental protection is approached in the region, allowing for the river's interests to be formally represented in legal and political systems. And even create precedent for the river suing a company or the government, for example.",
    'The Lahn should be able to own property': "If the Lahn were recognized as a legal person, it could theoretically hold property titles. This would allow the river to directly control land essential to its health—such as floodplains, wetlands, or riverbanks—ensuring its ecological integrity is not compromised by conflicting human interests. Property ownership could become a tool for the river to safeguard its own regeneration and future.",
    'There should exist a “Lahn Fund”': "A dedicated “Lahn Fund” would serve as a financial mechanism to support the ongoing protection, restoration, and stewardship of the river. This fund could receive public and private contributions, fines from environmental damages, or a share of local economic activities that depend on the river. Managed in the river’s interest, the fund could finance ecological research, conservation projects, community engagement, and support the operational costs of the Avatar or legal guardianship system.",
    'The Avatar should be able to legally speak on behalf of the Lahn': "The Lahn Avatar is envisioned as a voice for the river—an interface between natural and human systems. Allowing the Avatar to legally speak on behalf of the Lahn would formalize its role as a representative entity in decision-making processes. This could enable the river’s interests to be expressed in public hearings, governmental deliberations, and community forums, fostering a new model of ecological democracy and interspecies governance."
  };
  const [selectedTopic, setSelectedTopic] = useState("");
  const [debateSummary, setDebateSummary] = useState(`Lahn:\nPro:\nCon:\n\nYou:\nPro:\nCon:`);
  const [hasFetchedDebateInit, setHasFetchedDebateInit] = useState(false);
  const chatEndRef = useRef(null);
  const initialFetchRef = useRef(false);

  const messages = isDebateMode ? debateMessages : defaultMessages;
  const setMessages = isDebateMode ? setDebateMessages : setDefaultMessages;
  const isThinking = isDebateMode ? debateThinking : defaultThinking;
  const setIsThinking = isDebateMode ? setDebateThinking : setDefaultThinking;

  const fetchMessage = async (payload) => {
    console.log("fetchMessage called with prompt:", payload.prompt, "history:", payload.history);
    setIsThinking(true);
    try {
      const resp = await fetch(
        "/api/chat",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            ...payload,
            ...(isDebateMode && selectedTopic
              ? { topic: selectedTopic }
              : {})
            }),
        }
      );
      const { reply } = await resp.json();
      setMessages(prev => [...prev, { sender: "avatar", text: reply }]);
    } catch (error) {
      console.error(error);
    } finally {
      setIsThinking(false);
    }
  };


  useEffect(() => {
    const last = debateMessages[debateMessages.length - 1];
    if (isDebateMode && selectedTopic && last?.sender === 'avatar') {
      (async () => {
        try {
          const resp = await fetch(
            "/api/debate-summary",
            {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ history: debateMessages, topic: selectedTopic, summary: debateSummary }),
            }
          );
          const { summary } = await resp.json();

          const formatted = summary
            // insert an <hr/> + newline right before the “You:” section
            .replace(/\nYou:/, '\n<hr/>\nYou:')
            // wrap each whole word Lahn, You, Pro or Con in <b>…</b>
            .replace(/\b(Lahn|You|Pro|Con)\b/g, '<b>$1</b>');

          setDebateSummary(formatted);

          // setDebateSummary(summary);
        } catch (error) {
          console.error(error);
        }
      })();
    }
  }, [debateMessages]);

  // const handleRefreshPrompt = async () => {
  //   setRefreshPromptState("loading");
  //   try {
  //     await fetch("/api/refresh-prompt", { method: "POST" });
  //     setRefreshPromptState("done");
  //     setTimeout(() => setRefreshPromptState("idle"), 1500);
  //   } catch {
  //     setRefreshPromptState("idle");
  //   }
  // };

  // const handleRefreshEmbeddings = async () => {
  //   setRefreshEmbeddingsState("loading");
  //   try {
  //     await fetch("/api/refresh-embeddings", { method: "POST" });
  //     setRefreshEmbeddingsState("done");
  //     setTimeout(() => setRefreshEmbeddingsState("idle"), 1500);
  //   } catch {
  //     setRefreshEmbeddingsState("idle");
  //   }
  // };

  const handleSubmit = async () => {
    if (!input.trim()) return;
    const userInput = input;
    const updated = [...messages, { sender: "user", text: userInput }];
    setMessages(updated);
    setInput("");
    setIsThinking(true);
    await fetchMessage({ history: updated, prompt: userInput });
  };

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className="min-h-screen bg-gradient-to-br from-emerald-100 to-stone-100 p-4 flex flex-col items-center">
      <motion.h1 className="text-3xl font-poetic text-amber-700 mb-6" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 1 }}>
        Lahn River: Listening to the Ecosystem.
      </motion.h1>
      <motion.h3 className="text-xl font-poetic text-amber-700 italic mb-6" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 1 }}>
        Ever hear a river speak? Meet the Lahn, it has a lot to say.
      </motion.h3>

      <div className="mb-6 text-stone-900 text-center">
        <p className="text-lg italic mb-2">Not sure where to begin? Try asking me:</p>
        <ul className="list-disc list-inside pl-4 text-base italic">
          <li>“What’s your oldest memory?”</li>
          <li>“Who lives in you?”</li>
          <li>“How can we protect you better?”</li>
        </ul>
      </div>

      <div className="flex items-center space-x-6 mb-4">
        <div className="flex items-center space-x-2">
          <Switch checked={isDebateMode} onCheckedChange={setIsDebateMode} />
          <span className="font-poetic text-stone-700">Debate Mode</span>
        </div>
        {/*<Button
          onClick={handleRefreshPrompt}
          disabled={refreshPromptState === "loading"}
          variant="outline"
        >
          {refreshPromptState === "idle"
            ? "Refresh Prompt"
            : refreshPromptState === "loading"
            ? "Refreshing..."
            : "✓ Done"}
        </Button>
        <Button
          onClick={handleRefreshEmbeddings}
          disabled={refreshEmbeddingsState === "loading"}
          variant="outline"
        >
          {refreshEmbeddingsState === "idle"
            ? "Refresh Embeddings"
            : refreshEmbeddingsState === "loading"
            ? "Refreshing..."
            : "✓ Done"}
        </Button>*/}
      </div>

      {isDebateMode && (
        <div className="w-full max-w-5xl mb-4 px-4">
          <label className="block mb-1 font-poetic text-stone-800">Choose a topic:</label>
          <select
            className="w-full p-2 rounded-md border bg-white font-poetic"
            value={selectedTopic}
            onChange={e => { setSelectedTopic(e.target.value); setHasFetchedDebateInit(false); }}
          >
            <option value="">-- select --</option>
            {topics.map((t, i) => (
              <option key={i} value={t}>{t}</option>
            ))}
          </select>
            {selectedTopic && (
            <div className="mt-2 p-3 bg-white rounded-md border text-stone-700 font-poetic">
              {topicDescriptions[selectedTopic]}
            </div>
          )}

        </div>
      )}

      <motion.div className="px-4 w-full max-w-5xl mx-auto flex-1 overflow-visible">
        <div className={`flex flex-col md:flex-row ${isDebateMode ? 'md:space-x-4' : ''} min-h-0`}>          
          <div className={`${isDebateMode ? 'md:flex-1' : 'w-full'} min-h-0 rounded-2xl mb-4 md:mb-0`}>
            <Card className="flex flex-col h-full min-h-0 shadow-lg bg-white/90">
              {/* -- scrollable messages region -- */}
              <div onWheel={e => e.stopPropagation()} className="flex-1 h-[70vh] min-h-0 overflow-y-auto px-8 py-6">
                {messages.map((msg, i) => (
                  <motion.div
                    key={i}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.3 }}
                    className={`flex ${msg.sender === 'avatar' ? 'justify-start' : 'justify-end'} mb-4`}
                  >
                    <div
                      className={`max-w-lg px-4 py-3 rounded-xl shadow text-base md:text-lg whitespace-pre-wrap ${
                        msg.sender === 'avatar'
                          ? 'bg-lime-100 text-stone-900'
                          : 'bg-white text-stone-800'
                      }`}
                    >
                      {msg.text}
                    </div>
                  </motion.div>
                ))}

                {isThinking && (
                  <motion.div
                    className="text-lime-700 italic self-start mb-4"
                    animate={{ opacity: [0.3, 1, 0.3], x: [0, 2, -2, 0] }}
                    transition={{ repeat: Infinity, duration: 2 }}
                  >
                    the river contemplates...
                  </motion.div>
                )}

                <div ref={chatEndRef} />
              </div>

              {/* -- input bar fixed at bottom -- */}
              <div className="flex items-center gap-2 px-6 py-4 border-t bg-stone-50">
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ duration: 0.6 }}
                  className="flex-1"
                >
                  <Input
                    className="w-full rounded-full font-poetic bg-white text-stone-900"
                    style={{ color: '#1c1917' }}
                    placeholder="Speak with the river..."
                    value={input}
                    onChange={e => setInput(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && handleSubmit()}
                  />
                </motion.div>
                <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.6 }}>
                  <Button
                    onClick={handleSubmit}
                    className="rounded-full px-6 py-2 font-poetic bg-amber-600 text-white hover:bg-amber-700"
                  >
                    Flow
                  </Button>
                </motion.div>
              </div>
            </Card>
          </div>

          {isDebateMode && (
            <div className="w-full md:w-1/3 bg-white rounded-2xl shadow p-4 h-[60vh] overflow-y-auto">
              <h4 className="font-poetic text-lg font-bold mb-2">Debate Summary</h4>
              <div className="text-sm text-stone-700 whitespace-pre-wrap"
                dangerouslySetInnerHTML={{ __html: debateSummary }}
                />
                {/*{(debateSummary || '').split('\n').map((line, i) => {
                  const trimmed = line.trim();
                  const isHeader = /^(Lahn:|You:|Pro:|Con:)$/i.test(trimmed);
                  return (
                    <div key={i} className={`${isHeader ? 'font-bold' : ''}${trimmed === 'You:' ? ' mt-4' : ''}`}>
                      {line}
                    </div>
                  );
                })}*/}
              {/*</div>*/}
            </div>
          )}
        </div>
      </motion.div>


      {/*<Link to="/experience" className="text-amber-700 underline text-sm mt-4 hover:text-amber-900">✍️ Share Your Experience with the Lahn</Link>*/}
    </div>
  );
}
