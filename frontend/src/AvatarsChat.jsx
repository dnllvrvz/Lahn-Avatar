import { Link } from 'react-router-dom';
import { useEffect, useRef, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Button } from "@/components/ui/button";
import { motion } from "framer-motion";

import "@fontsource/chakra-petch";

export default function MultiAvatarChat() {
  // const [refreshPromptState, setRefreshPromptState] = useState("idle");
  // const [refreshEmbeddingsState, setRefreshEmbeddingsState] = useState("idle");

  // --- avatar management state ---
  const [avatars, setAvatars] = useState([]);
  const [selectedAvatarId, setSelectedAvatarId] = useState("");
  const [avatarFormOpen, setAvatarFormOpen] = useState(false);
  const [avatarFormMode, setAvatarFormMode] = useState("create"); // "create" | "edit"
  const [avatarForm, setAvatarForm] = useState({
    id: null,
    name: "",
    systemPromptUrl: "",
    contextDocsUrl: "",
    sensorApiUrl: "",
    sensorDescription: "",
    ragLanguages: "en, de",
  });
  const [avatarSaving, setAvatarSaving] = useState(false);
  const [avatarError, setAvatarError] = useState("");

  // --- chat state (same as original, just reused) ---
  const [defaultMessages, setDefaultMessages] = useState([]);
  const [debateMessages, setDebateMessages] = useState([]);
  const [input, setInput] = useState("");
  const [defaultThinking, setDefaultThinking] = useState(false);
  const [debateThinking, setDebateThinking] = useState(false);
  const [isDebateMode, setIsDebateMode] = useState(false);

  // --- LLM selection and health state ---
  const [currentUserLlmProvider, setCurrentUserLlmProvider] = useState('openai');
  const [currentUserLlmModel, setCurrentUserLlmModel] = useState('gpt-4o-mini');
  const [currentUserTextQueryModel, setCurrentUserTextQueryModel] = useState('gpt-4o-mini');
  const [currentUserSensorModel, setCurrentUserSensorModel] = useState('gpt-4o-mini');
  const [currentUserTemperature, setCurrentUserTemperature] = useState(0.7);
  const [currentUserTopK, setCurrentUserTopK] = useState(40);
  const [currentUserTopP, setCurrentUserTopP] = useState(1.0);
  const [modelHealth, setModelHealth] = useState({});
  const [llmOptions, setLlmOptions] = useState({});
  const [llmConfigExpanded, setLlmConfigExpanded] = useState(false);

  // --- LLM provider management state ---
  const [providerFormOpen, setProviderFormOpen] = useState(false);
  const [providerSaving, setProviderSaving] = useState(false);
  const [providerError, setProviderError] = useState("");
  const [providerForm, setProviderForm] = useState({
    id: "",
    name: "",
    provider_key: "custom",
    api_base: "",
    api_key: "",
    models: "",
  });

  // === Initial load ===
  useEffect(() => {
    // Fetch avatars
    (async () => {
      try {
        const resp = await fetch("/api/avatars");
        if (!resp.ok) throw new Error("Failed to fetch avatars");
        const data = await resp.json();
        setAvatars(data || []);
        if (data && data.length > 0) {
          setSelectedAvatarId(data[0].id);
        }
      } catch (err) {
        console.error("Error loading avatars:", err);
      }
    })();

    // Fetch LLM options
    (async () => {
      try {
        const resp = await fetch("/api/llm-options");
        if (!resp.ok) throw new Error("Failed to fetch LLM options");
        const data = await resp.json();
        setLlmOptions(data);
        // Set initial model if available
        const firstProvider = Object.keys(data)[0];
        if (firstProvider && data[firstProvider].models.length > 0) {
          setCurrentUserLlmProvider(firstProvider);
          setCurrentUserLlmModel(data[firstProvider].models[0]);
          setCurrentUserTextQueryModel(data[firstProvider].models[0]);
          setCurrentUserSensorModel(data[firstProvider].models[0]);
        }
      } catch (err) {
        console.error("Error loading LLM options:", err);
      }
    })();
  }, []);

  // === Background health check (non-blocking) ===
  useEffect(() => {
    const fetchHealthStatus = async () => {
      // Fetch fast and slow endpoints in parallel
      const fetchFast = async () => {
        try {
          const resp = await fetch("/api/health/llm/fast");
          if (!resp.ok) throw new Error("Failed to fetch fast health");
          const data = await resp.json();
          setModelHealth(prev => ({ ...prev, ...data }));
          console.log("Fast LLM health loaded:", data);
        } catch (err) {
          console.error("Error loading fast LLM health:", err);
        }
      };

      const fetchSlow = async () => {
        try {
          const resp = await fetch("/api/health/llm/slow");
          if (!resp.ok) throw new Error("Failed to fetch slow health");
          const data = await resp.json();
          setModelHealth(prev => ({ ...prev, ...data }));
          console.log("Slow LLM health loaded:", data);
        } catch (err) {
          console.error("Error loading slow LLM health:", err);
        }
      };

      // Run both in parallel - fast results will update UI first
      fetchFast();
      fetchSlow();
    };

    // Fetch health status in background after component mounts
    fetchHealthStatus();
  }, []);


  const [topics] = useState([
    'The River should have legal personhood',
    'The River should be able to own property',
    'There should exist a "River Fund”',
    'The Avatar should be able to legally speak on behalf of the River'
  ]);

  const topicDescriptions = {
    'The River should have legal personhood': "In recent years, rivers around the world have been granted legal personhood to recognize their intrinsic rights and protect their ecosystems. Granting the Lahn legal personhood would mean treating the river not merely as a resource but as a living entity with legal standing - analogous to the legal standing that a person or corporation holds. This shift could reshape how environmental protection is approached in the region, allowing for the river's interests to be formally represented in legal and political systems. And even create precedent for the river suing a company or the government, for example.",
    'The River should be able to own property': "If the Lahn were recognized as a legal person, it could theoretically hold property titles. This would allow the river to directly control land essential to its health—such as floodplains, wetlands, or riverbanks—ensuring its ecological integrity is not compromised by conflicting human interests. Property ownership could become a tool for the river to safeguard its own regeneration and future.",
    'There should exist a “River Fund”': "A dedicated “Lahn Fund” would serve as a financial mechanism to support the ongoing protection, restoration, and stewardship of the river. This fund could receive public and private contributions, fines from environmental damages, or a share of local economic activities that depend on the river. Managed in the river’s interest, the fund could finance ecological research, conservation projects, community engagement, and support the operational costs of the Avatar or legal guardianship system.",
    'The Avatar should be able to legally speak on behalf of the River': "The Lahn Avatar is envisioned as a voice for the river—an interface between natural and human systems. Allowing the Avatar to legally speak on behalf of the Lahn would formalize its role as a representative entity in decision-making processes. This could enable the river’s interests to be expressed in public hearings, governmental deliberations, and community forums, fostering a new model of ecological democracy and interspecies governance."
  };

  const [selectedTopic, setSelectedTopic] = useState("");
  const [debateSummary, setDebateSummary] = useState(`Avatar:\nPro:\nCon:\n\nYou:\nPro:\nCon:`);
  // const [hasFetchedDebateInit, setHasFetchedDebateInit] = useState(false);

  const chatEndRef = useRef(null);

  const [refreshState, setRefreshState] = useState({ prompt: "idle", embeddings: "idle" }); // idle, loading, success, error

  const handleRefresh = async (type) => {
    if (!selectedAvatarId) return;

    const endpoint = type === 'prompt' ? '/api/refresh-prompt' : '/api/refresh-embeddings';
    setRefreshState(prev => ({ ...prev, [type]: 'loading' }));

    try {
      const resp = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ avatar_id: selectedAvatarId }),
      });

      if (!resp.ok) {
        const errorData = await resp.json();
        throw new Error(errorData.error || `Failed to refresh ${type}`);
      }

      setRefreshState(prev => ({ ...prev, [type]: 'success' }));
      setTimeout(() => setRefreshState(prev => ({ ...prev, [type]: 'idle' })), 2000);

    } catch (err) {
      console.error(`Error refreshing ${type}:`, err);
      setRefreshState(prev => ({ ...prev, [type]: 'error' }));
      setTimeout(() => setRefreshState(prev => ({ ...prev, [type]: 'idle' })), 3000);
    }
  };

  const messages = isDebateMode ? debateMessages : defaultMessages;
  const setMessages = isDebateMode ? setDebateMessages : setDefaultMessages;
  const isThinking = isDebateMode ? debateThinking : defaultThinking;
  const setIsThinking = isDebateMode ? setDebateThinking : setDefaultThinking;

  const selectedAvatar = avatars.find(a => a.id === selectedAvatarId) || null;

  const firstRender = useRef(true);

  // === Avatar CRUD helpers ===

  const openCreateAvatarForm = () => {
    setAvatarFormMode("create");
    setAvatarForm({
      id: null,
      name: "",
      systemPromptUrl: "",
      contextDocsUrl: "",
      sensorApiUrl: "",
      sensorDescription: "",
    });
    setAvatarError("");
    setAvatarFormOpen(true);
  };

  const openEditAvatarForm = (avatar) => {
    setAvatarFormMode("edit");
    setAvatarForm({
      id: avatar.id,
      name: avatar.name || "",
      systemPromptUrl: avatar.systemPromptUrl || "",
      contextDocsUrl: avatar.contextDocsUrl || "",
      sensorApiUrl: avatar.sensorApiUrl || "",
      sensorDescription: avatar.sensorDescription || "",
      ragLanguages: Array.isArray(avatar.ragLanguages)
        ? avatar.ragLanguages.join(", ")
        : (avatar.ragLanguages || "en, de"),
    });
    setAvatarError("");
    setAvatarFormOpen(true);
  };

  const handleAvatarFormChange = (field, value) => {
    setAvatarForm(prev => ({ ...prev, [field]: value }));
  };

  const handleAvatarFormSubmit = async (e) => {
    e.preventDefault();
    setAvatarError("");

    if (!avatarForm.name.trim()) {
      setAvatarError("Avatar name is required.");
      return;
    }

    setAvatarSaving(true);
    try {
      if (avatarFormMode === "create") {
        const resp = await fetch("/api/avatars", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: avatarForm.name,
            systemPromptUrl: avatarForm.systemPromptUrl,
            contextDocsUrl: avatarForm.contextDocsUrl,
            sensorApiUrl: avatarForm.sensorApiUrl,
            sensorDescription: avatarForm.sensorDescription,
            ragLanguages: avatarForm.ragLanguages,
          }),
        });
        if (!resp.ok) throw new Error("Failed to create avatar");
        const newAvatar = await resp.json(); // expect { id, name, ... }
        setAvatars(prev => [...prev, newAvatar]);
        setSelectedAvatarId(newAvatar.id);
      } else {
        const resp = await fetch(`/api/avatars/${avatarForm.id}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: avatarForm.name,
            systemPromptUrl: avatarForm.systemPromptUrl,
            contextDocsUrl: avatarForm.contextDocsUrl,
            sensorApiUrl: avatarForm.sensorApiUrl,
            sensorDescription: avatarForm.sensorDescription,
            ragLanguages: avatarForm.ragLanguages,
          }),
        });
        if (!resp.ok) throw new Error("Failed to update avatar");
        const updated = await resp.json();
        setAvatars(prev =>
          prev.map(a => (a.id === updated.id ? updated : a))
        );
      }

      setAvatarFormOpen(false);
    } catch (err) {
      console.error(err);
      setAvatarError("Could not save avatar. Please try again.");
    } finally {
      setAvatarSaving(false);
    }
  };

  // === LLM Provider Management helpers ===

  const openCreateProviderForm = () => {
    setProviderForm({
      id: "",
      name: "",
      provider_key: "custom",
      api_base: "",
      api_key: "",
      models: "",
    });
    setProviderError("");
    setProviderFormOpen(true);
  };

  const handleProviderFormChange = (field, value) => {
    setProviderForm(prev => ({ ...prev, [field]: value }));
  };

  const handleProviderFormSubmit = async (e) => {
    e.preventDefault();
    setProviderError("");

    if (!providerForm.name.trim()) {
      setProviderError("Provider name is required.");
      return;
    }

    if (!providerForm.models.trim()) {
      setProviderError("At least one model is required (comma-separated).");
      return;
    }

    setProviderSaving(true);
    try {
      const modelsList = providerForm.models.split(",").map(m => m.trim()).filter(m => m);

      const resp = await fetch("/api/llm-providers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id: providerForm.id || undefined,
          name: providerForm.name,
          provider_key: providerForm.provider_key,
          api_base: providerForm.api_base,
          api_key: providerForm.api_key,
          models: modelsList,
        }),
      });

      if (!resp.ok) {
        const errData = await resp.json();
        throw new Error(errData.error || "Failed to create provider");
      }

      const newProvider = await resp.json();

      // Refresh LLM options from server
      const optionsResp = await fetch("/api/llm-options");
      if (optionsResp.ok) {
        const newOptions = await optionsResp.json();
        setLlmOptions(newOptions);
      }

      // Refresh health check to get status for new provider's models
      const healthResp = await fetch("/api/health/llm");
      if (healthResp.ok) {
        const healthData = await healthResp.json();
        setModelHealth(healthData);
      }

      setProviderFormOpen(false);

      // Select the newly created provider and its first model
      setCurrentUserLlmProvider(newProvider.id);
      if (newProvider.models && newProvider.models.length > 0) {
        setCurrentUserLlmModel(newProvider.models[0]);
      }
    } catch (err) {
      console.error(err);
      setProviderError(err.message || "Could not save provider. Please try again.");
    } finally {
      setProviderSaving(false);
    }
  };


  // === Chat fetch ===
  const fetchMessage = async (payload) => {
    if (!selectedAvatar) return;

    console.log("fetchMessage called with prompt:", payload.prompt, "history:", payload.history, "avatar:", selectedAvatar);

    setIsThinking(true);
    try {
      const resp = await fetch(
        "/api/chat?avatar="+selectedAvatar.id,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            ...payload,
            avatarId: selectedAvatar.id,
            avatarName: selectedAvatar.name,
            llmProvider: currentUserLlmProvider,
            llmModel: currentUserLlmModel,
            temperature: currentUserTemperature,
            topK: currentUserTopK,
            topP: currentUserTopP,
            textQueryModel: currentUserTextQueryModel,
            sensorModel: currentUserSensorModel,
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

  // === Debate summary effect ===
  useEffect(() => {
    const last = debateMessages[debateMessages.length - 1];
    if (isDebateMode && selectedTopic && last?.sender === 'avatar' && selectedAvatar) {
      (async () => {
        try {
          const resp = await fetch(
            "/api/debate-summary",
            {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                history: debateMessages,
                topic: selectedTopic,
                summary: debateSummary,
                avatarId: selectedAvatar.id,
                avatarName: selectedAvatar.name,
              }),
            }
          );
          const { summary } = await resp.json();

          const formatted = summary
            .replace(/\nYou:/, '\n<hr/>\nYou:')
            .replace(/\b(Avatar|You|Pro|Con)\b/g, '<b>$1</b>');

          setDebateSummary(formatted);
        } catch (error) {
          console.error(error);
        }
      })();
    }
  }, [debateMessages, isDebateMode, selectedTopic, selectedAvatar, debateSummary]);

  const handleSubmit = async () => {
    if (!input.trim() || !selectedAvatar) return;
    const userInput = input;
    const updated = [...messages, { sender: "user", text: userInput }];
    setMessages(updated);
    setInput("");
    setIsThinking(true);
    await fetchMessage({ history: updated, prompt: userInput });
  };

  useEffect(() => {
    // Reset chat when switching avatars
    setDefaultMessages([]);
    setDebateMessages([]);
    setInput("");

    setDefaultThinking(false);
    setDebateThinking(false);

    // Optional: reset debate UI too
    setSelectedTopic("");
    setDebateSummary(`Avatar:\nPro:\nCon:\n\nYou:\nPro:\nCon:`);

    // Optional: prevent auto-scroll jump on this reset
    firstRender.current = true;
  }, [selectedAvatarId]);


  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false;
      return; // skip scrolling on initial load
    }
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const chatDisabled = !selectedAvatar;

  return (
    <div
      className="min-h-screen bg-gradient-to-br from-blue-100 via-sky-100 to-indigo-100 p-4 flex flex-col items-center"
      style={{ fontFamily: "'Chakra Petch', sans-serif" }}
    >
      <motion.h1
        className="text-3xl font-poetic text-amber-700 mb-2"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 1 }}
      >
        Avatar Lab: Conversations with Many Voices.
      </motion.h1>
      <motion.h3
        className="text-xl font-poetic text-amber-700 italic mb-4 text-center"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 1 }}
      >
        Choose which avatar you want to speak with – or create your own.
      </motion.h3>

      {/* Avatar and LLM selection + controls */}
      <div className="w-full max-w-5xl flex flex-col gap-4 mb-4 px-4">
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
          <div className="flex-1">
            <label className="block mb-1 font-poetic text-stone-800">
              Active avatar
            </label>
            <div className="flex gap-2 items-center">
              <select
                className="w-full p-2 rounded-md border bg-white font-poetic"
                value={selectedAvatarId}
                onChange={e => setSelectedAvatarId(e.target.value)}
              >
                <option value="">-- Select an avatar --</option>
                {avatars.map(av => (
                  <option key={av.id} value={av.id}>
                    {av.name}
                  </option>
                ))}
              </select>
              <Button
                variant="outline"
                className="font-poetic"
                onClick={openCreateAvatarForm}
              >
                + New
              </Button>
              {selectedAvatar && (
                <Button
                  variant="outline"
                  className="font-poetic"
                  onClick={() => openEditAvatarForm(selectedAvatar)}
                >
                  Edit
                </Button>
              )}
            </div>
          </div>
          <div className="flex items-center space-x-4">
            <div className="flex items-center space-x-2">
              <Switch checked={isDebateMode} onCheckedChange={setIsDebateMode} />
              <span className="font-poetic text-stone-700">Debate Mode</span>
            </div>
          </div>
        </div>

        {/* Horizontal separator */}
        <hr className="w-full border-stone-300" />

        {/* Collapsible LLM Config Section */}
        <div className="w-full">
          <button
            className="flex items-center gap-2 font-poetic text-stone-700 cursor-pointer hover:text-stone-900"
            onClick={() => setLlmConfigExpanded(!llmConfigExpanded)}
          >
            <span className="text-lg">{llmConfigExpanded ? '▼' : '▶'}</span>
            <span className="font-semibold">LLM Config</span>
          </button>

          {llmConfigExpanded && (
            <div className="mt-2 space-y-2">
              <div className="flex items-center justify-center space-x-4">
                  <div className="flex items-center space-x-2">
                      <label className="font-poetic text-stone-700">Provider:</label>
                      <select
                          className="p-2 rounded-md border bg-white font-poetic"
                          value={currentUserLlmProvider}
                          onChange={e => {
                              setCurrentUserLlmProvider(e.target.value);
                              const models = llmOptions[e.target.value].models;
                              setCurrentUserLlmModel(models[0]);
                              setCurrentUserTextQueryModel(models[0]);
                              setCurrentUserSensorModel(models[0]);
                          }}
                      >
                          {Object.keys(llmOptions).map(key => (
                              <option key={key} value={key}>{llmOptions[key].name}</option>
                          ))}
                      </select>
                      <Button
                        variant="outline"
                        className="font-poetic text-xs"
                        onClick={openCreateProviderForm}
                      >
                        + New Provider
                      </Button>
                  </div>
              </div>

              <div className="flex items-center justify-center space-x-4">
                  <div className="flex items-center space-x-2">
                      <label className="font-poetic text-stone-700">Chat:</label>
                      <select
                          className="p-2 rounded-md border bg-white font-poetic"
                          value={currentUserLlmModel}
                          onChange={e => setCurrentUserLlmModel(e.target.value)}
                      >
                          {llmOptions[currentUserLlmProvider]?.models.map(model => {
                              const status = modelHealth[model];
                              let indicator = '⚪';
                              if (status === 'online') {
                                  indicator = '🟢';
                              } else if (status === 'offline') {
                                  indicator = '🔴';
                              }
                              return (
                                  <option key={model} value={model} disabled={status === 'offline'}>
                                      {indicator} {model} {status === 'offline' ? '(Offline)' : ''}
                                  </option>
                              );
                          })}
                      </select>
                  </div>
                  <div className="flex items-center space-x-2">
                      <label className="font-poetic text-stone-700 text-sm">Temp:</label>
                      <input
                          type="range"
                          min="0"
                          max="2"
                          step="0.1"
                          value={currentUserTemperature}
                          onChange={e => setCurrentUserTemperature(parseFloat(e.target.value))}
                          className="w-20"
                      />
                      <span className="text-xs text-stone-600 w-6">{currentUserTemperature}</span>
                  </div>
                  <div className="flex items-center space-x-2">
                      <label className={`font-poetic text-sm ${currentUserLlmProvider === 'openai' ? 'text-stone-400' : 'text-stone-700'}`}>Top K:</label>
                      <input
                          type="range"
                          min="1"
                          max="100"
                          step="1"
                          value={currentUserTopK}
                          onChange={e => setCurrentUserTopK(parseInt(e.target.value))}
                          className="w-20"
                          disabled={currentUserLlmProvider === 'openai'}
                      />
                      <span className={`text-xs w-6 ${currentUserLlmProvider === 'openai' ? 'text-stone-400' : 'text-stone-600'}`}>{currentUserLlmProvider === 'openai' ? '—' : currentUserTopK}</span>
                  </div>
                  <div className="flex items-center space-x-2">
                      <label className="font-poetic text-stone-700 text-sm">Top P:</label>
                      <input
                          type="range"
                          min="0"
                          max="1"
                          step="0.05"
                          value={currentUserTopP}
                          onChange={e => setCurrentUserTopP(parseFloat(e.target.value))}
                          className="w-20"
                      />
                      <span className="text-xs text-stone-600 w-8">{currentUserTopP}</span>
                  </div>
              </div>

              <div className="flex items-center justify-center space-x-4">
                  <div className="flex items-center space-x-2">
                      <label className="font-poetic text-stone-700">Text Query:</label>
                      <select
                          className="p-2 rounded-md border bg-white font-poetic"
                          value={currentUserTextQueryModel}
                          onChange={e => setCurrentUserTextQueryModel(e.target.value)}
                      >
                          {llmOptions[currentUserLlmProvider]?.models.map(model => {
                              const status = modelHealth[model];
                              let indicator = '⚪';
                              if (status === 'online') {
                                  indicator = '🟢';
                              } else if (status === 'offline') {
                                  indicator = '🔴';
                              }
                              return (
                                  <option key={model} value={model} disabled={status === 'offline'}>
                                      {indicator} {model} {status === 'offline' ? '(Offline)' : ''}
                                  </option>
                              );
                          })}
                      </select>
                  </div>
                  <div className="flex items-center space-x-2">
                      <label className="font-poetic text-stone-700">Sensor:</label>
                      <select
                          className="p-2 rounded-md border bg-white font-poetic"
                          value={currentUserSensorModel}
                          onChange={e => setCurrentUserSensorModel(e.target.value)}
                      >
                          {llmOptions[currentUserLlmProvider]?.models.map(model => {
                              const status = modelHealth[model];
                              let indicator = '⚪';
                              if (status === 'online') {
                                  indicator = '🟢';
                              } else if (status === 'offline') {
                                  indicator = '🔴';
                              }
                              return (
                                  <option key={model} value={model} disabled={status === 'offline'}>
                                      {indicator} {model} {status === 'offline' ? '(Offline)' : ''}
                                  </option>
                              );
                          })}
                      </select>
                  </div>
              </div>
            </div>
          )}
        </div>

        {/* Horizontal separator */}
        <hr className="w-full border-stone-300" />

        {selectedAvatar && (
            <div className="flex gap-2 items-center justify-center mt-2">
              <Button
                variant="outline"
                className="font-poetic"
                onClick={() => handleRefresh('prompt')}
                disabled={!selectedAvatarId || refreshState.prompt !== 'idle'}
              >
                {refreshState.prompt === 'loading' ? 'Refreshing...' : refreshState.prompt === 'success' ? 'Refreshed!' : refreshState.prompt === 'error' ? 'Error!' : 'Refresh Prompt'}
              </Button>
              <Button
                variant="outline"
                className="font-poetic"
                onClick={() => handleRefresh('embeddings')}
                disabled={!selectedAvatarId || refreshState.embeddings !== 'idle'}
              >
                {refreshState.embeddings === 'loading' ? 'Refreshing...' : refreshState.embeddings === 'success' ? 'Refreshed!' : refreshState.embeddings === 'error' ? 'Error!' : 'Refresh Avatar Context Files'}
              </Button>
            </div>
          )}

          {selectedAvatar && (
            <div className="mt-4 text-xs text-stone-700 space-y-1">
              <div><span className="font-semibold">Prompt:</span> {selectedAvatar.systemPromptUrl || "—"}</div>
              <div><span className="font-semibold">Context:</span> {selectedAvatar.contextDocsUrl || "—"}</div>
              <div><span className="font-semibold">Sensors:</span> {selectedAvatar.sensorApiUrl || "—"}</div>
              <div><span className="font-semibold">Languages in context documents:</span> {Array.isArray(selectedAvatar.ragLanguages) ? selectedAvatar.ragLanguages.join(", ") : (selectedAvatar.ragLanguages || "—")}</div>
              <div><span className="font-semibold">API:</span> https://lahn-avatar.uni-giessen.de/api/chat?avatar={selectedAvatar.id}</div>
            </div>
          )}
          {!selectedAvatar && (
            <div className="mt-2 text-xs text-red-700">
              Please select or create an avatar to start chatting.
            </div>
          )}
      </div>

      {isDebateMode && (
        <div className="w-full max-w-5xl mb-4 px-4">
          <label className="block mb-1 font-poetic text-stone-800">Choose a topic:</label>
          <select
            className="w-full p-2 rounded-md border bg-white font-poetic"
            value={selectedTopic}
            onChange={e => { setSelectedTopic(e.target.value); }}
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
              {/* scrollable messages */}
              <div
                onWheel={e => e.stopPropagation()}
                className="flex-1 h-[70vh] min-h-0 overflow-y-auto px-8 py-6"
              >
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
                    the avatar contemplates...
                  </motion.div>
                )}

                <div ref={chatEndRef} />
              </div>

              {/* input bar */}
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
                    placeholder={chatDisabled ? "Select or create an avatar to begin..." : "Speak with the avatar..."}
                    value={input}
                    onChange={e => setInput(e.target.value)}
                    onKeyDown={e => !chatDisabled && e.key === 'Enter' && handleSubmit()}
                    disabled={chatDisabled}
                  />
                </motion.div>
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ duration: 0.6 }}
                >
                  <Button
                    onClick={handleSubmit}
                    className="rounded-full px-6 py-2 font-poetic bg-amber-600 text-white hover:bg-amber-700 disabled:opacity-50"
                    disabled={chatDisabled}
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
              <div
                className="text-sm text-stone-700 whitespace-pre-wrap"
                dangerouslySetInnerHTML={{ __html: debateSummary }}
              />
            </div>
          )}
        </div>
      </motion.div>

      {/* Simple avatar create/edit panel (inline "modal") */}
      {avatarFormOpen && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-40">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg p-6">
            <h2 className="text-xl font-poetic mb-4">
              {avatarFormMode === "create" ? "Create New Avatar" : "Edit Avatar"}
            </h2>
            <form onSubmit={handleAvatarFormSubmit} className="space-y-4">
              <div>
                <label className="block text-sm font-semibold mb-1">Avatar name</label>
                <Input
                  className="border border-gray-300 rounded-md px-3 py-2 placeholder:text-gray-400"
                  style={{
                    backgroundColor: '#f9fafb',
                    color: '#000000',
                  }}
                  value={avatarForm.name}
                  onChange={e => handleAvatarFormChange("name", e.target.value)}
                  placeholder="e.g. Lahn River, Forest Spirit..."
                />
              </div>
              <div>
                <label className="block text-sm font-semibold mb-1">
                  Link to system prompt
                </label>
                <Input
                  className="border border-gray-300 rounded-md px-3 py-2 placeholder:text-gray-400"
                  style={{
                    backgroundColor: '#f9fafb',
                    color: '#000000',
                  }}
                  value={avatarForm.systemPromptUrl}
                  onChange={e => handleAvatarFormChange("systemPromptUrl", e.target.value)}
                  placeholder="Google Docs Link (e.g., https://docs.google.com/...)"
                />
              </div>
              <div>
                <label className="block text-sm font-semibold mb-1">
                  Link to context documents
                </label>
                <Input
                  className="border border-gray-300 rounded-md px-3 py-2 placeholder:text-gray-400"
                  style={{
                    backgroundColor: '#f9fafb',
                    color: '#000000',
                  }}
                  value={avatarForm.contextDocsUrl}
                  onChange={e => handleAvatarFormChange("contextDocsUrl", e.target.value)}
                  placeholder="Google Drive Folder Link (e.g., https://drive.google.com/drive/folders/...)"
                />
              </div>
              <div>
                <label className="block text-sm font-semibold mb-1">
                  Link to sensor data API
                </label>
                <Input
                  className="border border-gray-300 rounded-md px-3 py-2 placeholder:text-gray-400"
                  style={{
                    backgroundColor: '#f9fafb',
                    color: '#000000',
                  }}
                  value={avatarForm.sensorApiUrl}
                  onChange={e => handleAvatarFormChange("sensorApiUrl", e.target.value)}
                  placeholder="https://…/sensors"
                />
              </div>
              <div>
                <label className="block text-sm font-semibold mb-1">
                  Sensor data description
                </label>
                <Input
                  className="border border-gray-300 rounded-md px-3 py-2 placeholder:text-gray-400"
                  style={{
                    backgroundColor: '#f9fafb',
                    color: '#000000',
                  }}
                  value={avatarForm.sensorDescription}
                  onChange={e => handleAvatarFormChange("sensorDescription", e.target.value)}
                  placeholder="e.g. Provides live pH, temperature, dissolved oxygen, and conductivity data"
                />
              </div>
              <div>
                <label className="block text-sm font-semibold mb-1">
                  What languages are your context documents in?
                </label>
                <Input
                  className="border border-gray-300 rounded-md px-3 py-2 placeholder:text-gray-400"
                  style={{
                    backgroundColor: '#f9fafb',
                    color: '#000000',
                  }}
                  value={avatarForm.ragLanguages}
                  onChange={e => handleAvatarFormChange("ragLanguages", e.target.value)}
                  placeholder="en, de, fr, pt"
                />
                <p className="text-xs text-gray-500 mt-1">
                  Enter language codes separated by commas. This helps optimize RAG queries for your document languages.
                </p>
              </div>

              {avatarError && (
                <div className="text-sm text-red-600">{avatarError}</div>
              )}

              <div className="flex justify-end gap-2 mt-4">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setAvatarFormOpen(false)}
                  disabled={avatarSaving}
                >
                  Cancel
                </Button>
                <Button type="submit" disabled={avatarSaving}>
                  {avatarSaving
                    ? avatarFormMode === "create"
                      ? "Saving... (Might take a few minutes to prepare your context data)"
                      : "Saving..."
                    : avatarFormMode === "create"
                      ? "Create"
                      : "Save changes"}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* LLM Provider create/edit panel */}
      {providerFormOpen && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-40">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg p-6">
            <h2 className="text-xl font-poetic mb-4">
              Add New LLM Provider
            </h2>
            <form onSubmit={handleProviderFormSubmit} className="space-y-4">
              <div>
                <label className="block text-sm font-semibold mb-1">Provider name</label>
                <Input
                  className="border border-gray-300 rounded-md px-3 py-2 placeholder:text-gray-400"
                  style={{
                    backgroundColor: '#f9fafb',
                    color: '#000000',
                  }}
                  value={providerForm.name}
                  onChange={e => handleProviderFormChange("name", e.target.value)}
                  placeholder="e.g. Anthropic, Azure OpenAI, HuggingFace..."
                />
              </div>
              <div>
                <label className="block text-sm font-semibold mb-1">
                  API base URL
                </label>
                <Input
                  className="border border-gray-300 rounded-md px-3 py-2 placeholder:text-gray-400"
                  style={{
                    backgroundColor: '#f9fafb',
                    color: '#000000',
                  }}
                  value={providerForm.api_base}
                  onChange={e => handleProviderFormChange("api_base", e.target.value)}
                  placeholder="https://api.example.com/v1"
                />
              </div>
              <div>
                <label className="block text-sm font-semibold mb-1">
                  API key
                </label>
                <Input
                  type="password"
                  className="border border-gray-300 rounded-md px-3 py-2 placeholder:text-gray-400"
                  style={{
                    backgroundColor: '#f9fafb',
                    color: '#000000',
                  }}
                  value={providerForm.api_key}
                  onChange={e => handleProviderFormChange("api_key", e.target.value)}
                  placeholder="sk-..."
                />
              </div>
              <div>
                <label className="block text-sm font-semibold mb-1">
                  Models (comma-separated)
                </label>
                <Input
                  className="border border-gray-300 rounded-md px-3 py-2 placeholder:text-gray-400"
                  style={{
                    backgroundColor: '#f9fafb',
                    color: '#000000',
                  }}
                  value={providerForm.models}
                  onChange={e => handleProviderFormChange("models", e.target.value)}
                  placeholder="claude-3-opus, claude-3-sonnet, claude-3-haiku"
                />
              </div>

              {providerError && (
                <div className="text-sm text-red-600">{providerError}</div>
              )}

              <div className="flex justify-end gap-2 mt-4">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setProviderFormOpen(false)}
                  disabled={providerSaving}
                >
                  Cancel
                </Button>
                <Button type="submit" disabled={providerSaving}>
                  {providerSaving ? "Adding..." : "Add Provider"}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
