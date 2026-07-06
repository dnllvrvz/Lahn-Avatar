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
  // Separate providers for each task
  const [currentUserChatProvider, setCurrentUserChatProvider] = useState('gwdg');
  const [currentUserChatModel, setCurrentUserChatModel] = useState('gwdg/gemma-3-27b-it');
  const [currentUserTextQueryProvider, setCurrentUserTextQueryProvider] = useState('gwdg');
  const [currentUserTextQueryModel, setCurrentUserTextQueryModel] = useState('gwdg/gemma-3-27b-it');
  const [currentUserSensorProvider, setCurrentUserSensorProvider] = useState('gwdg');
  const [currentUserSensorModel, setCurrentUserSensorModel] = useState('mistral-large-instruct');
  const [currentUserTemperature, setCurrentUserTemperature] = useState(0.7);
  const [currentUserTopK, setCurrentUserTopK] = useState(40);
  const [currentUserTopP, setCurrentUserTopP] = useState(1.0);
  const [modelHealth, setModelHealth] = useState({});
  const [llmOptions, setLlmOptions] = useState({});
  const [llmOptionsLastRefreshed, setLlmOptionsLastRefreshed] = useState(null);
  const [llmConfigExpanded, setLlmConfigExpanded] = useState(false);
  const [hasLlmDefaults, setHasLlmDefaults] = useState(false);
  const [adminDefaultModels, setAdminDefaultModels] = useState({ chat: null, textQuery: null, sensor: null });

  // --- backend log viewer state ---
  const [logExpanded, setLogExpanded] = useState(false);
  const [backendLog, setBackendLog] = useState("");
  const backendLogRef = useRef(null);
  const backendLogPreRef = useRef(null);
  const backendLogFirstLoadRef = useRef(true);

  // --- Integrations state ---
  const [integrationsExpanded, setIntegrationsExpanded] = useState(false);
  const [integrations, setIntegrations] = useState({});
  const [integrationEdits, setIntegrationEdits] = useState({});
  const [integrationSaving, setIntegrationSaving] = useState(false);
  const [integrationMsg, setIntegrationMsg] = useState("");

  // --- LLM provider key editing state ---
  const [llmProvidersList, setLlmProvidersList] = useState([]);
  const [providerKeyEdits, setProviderKeyEdits] = useState({});
  const [providerKeySaving, setProviderKeySaving] = useState({});

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
        setLlmOptions(data.options);
        setLlmOptionsLastRefreshed(data.last_refreshed);
        // Set initial model if available
        const firstProvider = Object.keys(data.options)[0];
        if (firstProvider && data.options[firstProvider].models.length > 0) {
          setCurrentUserChatProvider(firstProvider);
          setCurrentUserChatModel(data.options[firstProvider].models[0]);
          setCurrentUserTextQueryProvider(firstProvider);
          setCurrentUserTextQueryModel(data.options[firstProvider].models[0]);
          setCurrentUserSensorProvider(firstProvider);
          setCurrentUserSensorModel(data.options[firstProvider].models[0]);
        }
      } catch (err) {
        console.error("Error loading LLM options:", err);
      }
    })();

    // Fetch integrations
    fetch("/api/integrations")
      .then(r => r.json())
      .then(setIntegrations)
      .catch(console.error);

    // Fetch LLM providers list (includes key_set / key_last4)
    fetch("/api/llm-providers")
      .then(r => r.json())
      .then(setLlmProvidersList)
      .catch(console.error);
  }, []);

  // === Background health check (non-blocking) ===
  const healthCheckInProgress = useRef(false);

  useEffect(() => {
    // Skip if a health check is already in progress (prevents StrictMode double-invocation)
    if (healthCheckInProgress.current) {
      console.log("Health check already in progress, skipping duplicate");
      return;
    }
    healthCheckInProgress.current = true;

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

      const fetchOpenRouter = async () => {
        try {
          const resp = await fetch("/api/health/llm/openrouter");
          if (!resp.ok) throw new Error("Failed to fetch OpenRouter health");
          const data = await resp.json();
          setModelHealth(prev => ({ ...prev, ...data }));
          console.log("OpenRouter LLM health loaded:", data);
        } catch (err) {
          console.error("Error loading OpenRouter LLM health:", err);
        }
      };

      // All three run in parallel - each updates UI incrementally as it completes
      fetchFast();
      fetchSlow();
      fetchOpenRouter();
    };

    // Fetch health status in background after component mounts
    fetchHealthStatus();
  }, []);

  // === Backend log polling ===
  const fetchBackendLog = async () => {
    try {
      const resp = await fetch("/api/backend-log");
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      setBackendLog(data.log);
    } catch (e) {
      console.error("Error loading backend log:", e);
    }
  };

  useEffect(() => {
    if (!logExpanded) return;
    fetchBackendLog();
    const timer = setInterval(fetchBackendLog, 3000);
    return () => clearInterval(timer);
  }, [logExpanded]);

  useEffect(() => {
    if (backendLog.length === 0) return;
    if (backendLogFirstLoadRef.current) {
      backendLogFirstLoadRef.current = false;
      backendLogRef.current?.scrollIntoView();
      return;
    }
    const el = backendLogPreRef.current;
    if (!el) return;
    const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 50;
    if (isNearBottom) {
      backendLogRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [backendLog]);

  // === Load Admin defaults when avatar changes ===
  useEffect(() => {
    if (!selectedAvatarId || !llmOptions || Object.keys(llmOptions).length === 0) return;

    const selectedAvatar = avatars.find(a => a.id === selectedAvatarId);
    const firstProvider = Object.keys(llmOptions)[0];
    const resolveProvider = (p) => (p && llmOptions[p]) ? p : firstProvider;

    // Returns { provider, model }
    const resolveModel = (p, m) => {
      const provider = resolveProvider(p);
      const models = llmOptions[provider]?.models || [];
      return { provider, model: (m && models.includes(m)) ? m : (models[0] || '') };
    };

    if (selectedAvatar?.llmDefaults) {
      const defaults = selectedAvatar.llmDefaults;
      console.log("Loading Admin defaults for avatar:", defaults);

      // Load chat defaults
      if (defaults.chat) {
        const { provider: cp, model: cm } = resolveModel(defaults.chat.provider, defaults.chat.model);
        setCurrentUserChatProvider(cp);
        setCurrentUserChatModel(cm);
        if (defaults.chat.temperature) setCurrentUserTemperature(defaults.chat.temperature);
        if (defaults.chat.top_k) setCurrentUserTopK(defaults.chat.top_k);
        if (defaults.chat.top_p) setCurrentUserTopP(defaults.chat.top_p);
      }

      // Load text query defaults
      if (defaults.textQuery) {
        const { provider: tp, model: tm } = resolveModel(defaults.textQuery.provider, defaults.textQuery.model);
        setCurrentUserTextQueryProvider(tp);
        setCurrentUserTextQueryModel(tm);
      }

      // Load sensor defaults
      if (defaults.sensor) {
        const { provider: sp, model: sm } = resolveModel(defaults.sensor.provider, defaults.sensor.model);
        setCurrentUserSensorProvider(sp);
        setCurrentUserSensorModel(sm);
      }

      setAdminDefaultModels({
        chat: defaults.chat?.model || null,
        textQuery: defaults.textQuery?.model || null,
        sensor: defaults.sensor?.model || null,
      });
      setHasLlmDefaults(true);
    } else {
      setAdminDefaultModels({ chat: null, textQuery: null, sensor: null });
      // No Admin defaults saved, use global defaults
      const firstProvider = Object.keys(llmOptions)[0];
      if (firstProvider && llmOptions[firstProvider].models.length > 0) {
        setCurrentUserChatProvider(firstProvider);
        setCurrentUserChatModel(llmOptions[firstProvider].models[0]);
        setCurrentUserTextQueryProvider(firstProvider);
        setCurrentUserTextQueryModel(llmOptions[firstProvider].models[0]);
        setCurrentUserSensorProvider(firstProvider);
        setCurrentUserSensorModel(llmOptions[firstProvider].models[0]);
      }
      setCurrentUserTemperature(0.7);
      setCurrentUserTopK(40);
      setCurrentUserTopP(1.0);
      setHasLlmDefaults(false);
    }
  }, [selectedAvatarId, llmOptions]);

  // === Save/Clear Admin defaults ===
  const handleSaveLlmDefaults = async () => {
    if (!selectedAvatarId) return;

    try {
      const resp = await fetch(`/api/avatars/${selectedAvatarId}/llm-defaults`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          chatProvider: currentUserChatProvider,
          chatModel: currentUserChatModel,
          temperature: currentUserTemperature,
          topK: currentUserTopK,
          topP: currentUserTopP,
          textQueryProvider: currentUserTextQueryProvider,
          textQueryModel: currentUserTextQueryModel,
          sensorProvider: currentUserSensorProvider,
          sensorModel: currentUserSensorModel,
        }),
      });

      if (!resp.ok) throw new Error("Failed to save defaults");
      const updatedAvatar = await resp.json();

      // Update avatars list with the new data
      setAvatars(prev => prev.map(a => a.id === selectedAvatarId ? updatedAvatar : a));
      setHasLlmDefaults(true);
      console.log("Admin defaults saved for avatar:", selectedAvatarId);
    } catch (err) {
      console.error("Error saving Admin defaults:", err);
    }
  };

  const handleClearLlmDefaults = async () => {
    if (!selectedAvatarId) return;

    try {
      const resp = await fetch(`/api/avatars/${selectedAvatarId}/llm-defaults`, {
        method: 'DELETE',
      });

      if (!resp.ok) throw new Error("Failed to clear defaults");
      const updatedAvatar = await resp.json();

      // Update avatars list
      setAvatars(prev => prev.map(a => a.id === selectedAvatarId ? updatedAvatar : a));
      setHasLlmDefaults(false);
      console.log("Admin defaults cleared for avatar:", selectedAvatarId);
    } catch (err) {
      console.error("Error clearing Admin defaults:", err);
    }
  };

  // === Integrations save handler ===
  const handleSaveIntegrations = async () => {
    setIntegrationSaving(true);
    setIntegrationMsg("");
    try {
      const resp = await fetch("/api/integrations", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(integrationEdits),
      });
      const result = await resp.json();
      setIntegrationMsg(result.updated?.length ? `Saved: ${result.updated.join(", ")}` : "Nothing to save (fields were empty)");
      setIntegrationEdits({});
      const fresh = await fetch("/api/integrations").then(r => r.json());
      setIntegrations(fresh);
    } catch (e) {
      setIntegrationMsg("Error saving keys");
    } finally {
      setIntegrationSaving(false);
    }
  };

  // === LLM provider key save handler ===
  const handleSaveProviderKey = async (providerId) => {
    const newKey = providerKeyEdits[providerId];
    if (!newKey) return;
    setProviderKeySaving(prev => ({ ...prev, [providerId]: true }));
    try {
      const resp = await fetch(`/api/llm-providers/${providerId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ api_key: newKey }),
      });
      if (!resp.ok) throw new Error("Failed to update key");
      await resp.json();
      setProviderKeyEdits(prev => ({ ...prev, [providerId]: "" }));
      // Refresh providers list to reflect updated key status
      const optResp = await fetch("/api/llm-providers");
      if (optResp.ok) {
        const providers = await optResp.json();
        setLlmProvidersList(providers);
      }
    } catch (e) {
      console.error("Error saving provider key:", e);
    } finally {
      setProviderKeySaving(prev => ({ ...prev, [providerId]: false }));
    }
  };

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
        setLlmOptions(newOptions.options);
        setLlmOptionsLastRefreshed(newOptions.last_refreshed);
      }

      // Refresh health check to get status for new provider's models
      const healthResp = await fetch("/api/health/llm");
      if (healthResp.ok) {
        const healthData = await healthResp.json();
        setModelHealth(healthData);
      }

      setProviderFormOpen(false);

      // Select the newly created provider and its first model
      setCurrentUserChatProvider(newProvider.id);
      setCurrentUserTextQueryProvider(newProvider.id);
      setCurrentUserSensorProvider(newProvider.id);
      if (newProvider.models && newProvider.models.length > 0) {
        setCurrentUserChatModel(newProvider.models[0]);
        setCurrentUserTextQueryModel(newProvider.models[0]);
        setCurrentUserSensorModel(newProvider.models[0]);
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
            chatProvider: currentUserChatProvider,
            chatModel: currentUserChatModel,
            temperature: currentUserTemperature,
            topK: currentUserTopK,
            topP: currentUserTopP,
            textQueryProvider: currentUserTextQueryProvider,
            textQueryModel: currentUserTextQueryModel,
            sensorProvider: currentUserSensorProvider,
            sensorModel: currentUserSensorModel,
            ...(isDebateMode && selectedTopic
              ? { topic: selectedTopic }
              : {})
          }),
        }
      );
      const data = await resp.json();
      if (data.error) {
        setMessages(prev => [...prev, { sender: "avatar", text: `⚠️ ${data.error}` }]);
      } else {
        setMessages(prev => [...prev, { sender: "avatar", text: data.reply }]);
      }
    } catch (error) {
      console.error(error);
      setMessages(prev => [...prev, { sender: "avatar", text: "⚠️ An unexpected error occurred. Please try again." }]);
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

  const offlineBlockers = [
    { role: 'chat', model: currentUserChatModel },
    { role: 'text query', model: currentUserTextQueryModel },
    { role: 'sensor', model: currentUserSensorModel },
  ].filter(({ model }) => modelHealth[model] === 'offline');

  const chatDisabled = !selectedAvatar || offlineBlockers.length > 0;

  return (
    <div
      className="min-h-screen bg-gradient-to-br from-blue-100 via-sky-100 to-indigo-100 p-4 flex flex-col items-center"
      style={{ fontFamily: "'Chakra Petch', sans-serif" }}
    >
      <motion.h1
        className="text-2xl md:text-3xl font-poetic text-amber-700 mb-2"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 1 }}
      >
        Avatar Lab: Conversations with Many Voices.
      </motion.h1>
      <motion.h3
        className="text-base md:text-xl font-poetic text-amber-700 italic mb-4 text-center px-2"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 1 }}
      >
        Choose which avatar you want to speak with – or create your own.
      </motion.h3>

      {/* Avatar and LLM selection + controls */}
      <div className="w-full max-w-5xl flex flex-col gap-4 mb-4 px-4">
        <div className="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4">
          <div className="flex-1">
            <label className="block mb-1 font-poetic text-stone-800">
              Active avatar
            </label>
            <div className="flex flex-col sm:flex-row gap-2 items-stretch sm:items-center">
              <select
                className="flex-1 p-2 rounded-md border bg-white font-poetic"
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
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  className="font-poetic flex-1 sm:flex-none"
                  onClick={openCreateAvatarForm}
                >
                  + New
                </Button>
                {selectedAvatar && (
                  <Button
                    variant="outline"
                    className="font-poetic flex-1 sm:flex-none"
                    onClick={() => openEditAvatarForm(selectedAvatar)}
                  >
                    Edit
                  </Button>
                )}
              </div>
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
            <div className="mt-2 space-y-3">
              {/* Chat provider and model */}
              <div className="p-3 rounded-lg border bg-stone-50/60 space-y-2">
                  <label className="block font-poetic text-stone-800 font-semibold text-sm">Chat</label>
                  <div className="flex flex-wrap items-center gap-2">
                      <select
                          className="flex-1 min-w-[120px] p-2 rounded-md border bg-white font-poetic text-sm"
                          value={currentUserChatProvider}
                          onChange={e => {
                              setCurrentUserChatProvider(e.target.value);
                              setCurrentUserChatModel(llmOptions[e.target.value].models[0]);
                          }}
                      >
                          {Object.keys(llmOptions).map(key => (
                              <option key={key} value={key}>{llmOptions[key].name}</option>
                          ))}
                      </select>
                      <select
                          className="flex-1 min-w-[120px] p-2 rounded-md border bg-white font-poetic text-sm"
                          value={currentUserChatModel}
                          onChange={e => setCurrentUserChatModel(e.target.value)}
                      >
                          {llmOptions[currentUserChatProvider]?.models.filter(model =>
                              modelHealth[model] !== 'offline' || model === adminDefaultModels.chat
                          ).map(model => {
                              const status = modelHealth[model];
                              const indicator = status === 'online' ? '🟢' : status === 'offline' ? '🔴' : '⚪';
                              return (
                                  <option key={model} value={model} disabled={status === 'offline'}>
                                      {indicator} {model} {status === 'offline' ? '(Offline — update admin default)' : ''}
                                  </option>
                              );
                          })}
                      </select>
                  </div>
                  <div className="flex flex-wrap items-center gap-4">
                      <div className="flex items-center gap-2">
                          <label className="font-poetic text-stone-700 text-sm whitespace-nowrap">Temp:</label>
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
                      <div className="flex items-center gap-2">
                          <label className={`font-poetic text-sm whitespace-nowrap ${currentUserChatProvider === 'openai' ? 'text-stone-400' : 'text-stone-700'}`}>Top K:</label>
                          <input
                              type="range"
                              min="1"
                              max="100"
                              step="1"
                              value={currentUserTopK}
                              onChange={e => setCurrentUserTopK(parseInt(e.target.value))}
                              className="w-20"
                              disabled={currentUserChatProvider === 'openai'}
                          />
                          <span className={`text-xs w-6 ${currentUserChatProvider === 'openai' ? 'text-stone-400' : 'text-stone-600'}`}>{currentUserChatProvider === 'openai' ? '—' : currentUserTopK}</span>
                      </div>
                      <div className="flex items-center gap-2">
                          <label className="font-poetic text-stone-700 text-sm whitespace-nowrap">Top P:</label>
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
              </div>

              {/* Text Query provider and model */}
              <div className="p-3 rounded-lg border bg-stone-50/60">
                  <label className="block font-poetic text-stone-800 font-semibold text-sm mb-2">Text Query</label>
                  <div className="flex flex-wrap items-center gap-2">
                      <select
                          className="flex-1 min-w-[120px] p-2 rounded-md border bg-white font-poetic text-sm"
                          value={currentUserTextQueryProvider}
                          onChange={e => {
                              setCurrentUserTextQueryProvider(e.target.value);
                              setCurrentUserTextQueryModel(llmOptions[e.target.value].models[0]);
                          }}
                      >
                          {Object.keys(llmOptions).map(key => (
                              <option key={key} value={key}>{llmOptions[key].name}</option>
                          ))}
                      </select>
                      <select
                          className="flex-1 min-w-[120px] p-2 rounded-md border bg-white font-poetic text-sm"
                          value={currentUserTextQueryModel}
                          onChange={e => setCurrentUserTextQueryModel(e.target.value)}
                      >
                          {llmOptions[currentUserTextQueryProvider]?.models.filter(model =>
                              modelHealth[model] !== 'offline' || model === adminDefaultModels.textQuery
                          ).map(model => {
                              const status = modelHealth[model];
                              const indicator = status === 'online' ? '🟢' : status === 'offline' ? '🔴' : '⚪';
                              return (
                                  <option key={model} value={model} disabled={status === 'offline'}>
                                      {indicator} {model} {status === 'offline' ? '(Offline — update admin default)' : ''}
                                  </option>
                              );
                          })}
                      </select>
                  </div>
              </div>

              {/* Sensor provider and model */}
              <div className="p-3 rounded-lg border bg-stone-50/60">
                  <label className="block font-poetic text-stone-800 font-semibold text-sm mb-2">Sensor</label>
                  <div className="flex flex-wrap items-center gap-2">
                      <select
                          className="flex-1 min-w-[120px] p-2 rounded-md border bg-white font-poetic text-sm"
                          value={currentUserSensorProvider}
                          onChange={e => {
                              setCurrentUserSensorProvider(e.target.value);
                              setCurrentUserSensorModel(llmOptions[e.target.value].models[0]);
                          }}
                      >
                          {Object.keys(llmOptions).map(key => (
                              <option key={key} value={key}>{llmOptions[key].name}</option>
                          ))}
                      </select>
                      <select
                          className="flex-1 min-w-[120px] p-2 rounded-md border bg-white font-poetic text-sm"
                          value={currentUserSensorModel}
                          onChange={e => setCurrentUserSensorModel(e.target.value)}
                      >
                          {llmOptions[currentUserSensorProvider]?.models.filter(model =>
                              modelHealth[model] !== 'offline' || model === adminDefaultModels.sensor
                          ).map(model => {
                              const status = modelHealth[model];
                              const indicator = status === 'online' ? '🟢' : status === 'offline' ? '🔴' : '⚪';
                              return (
                                  <option key={model} value={model} disabled={status === 'offline'}>
                                      {indicator} {model} {status === 'offline' ? '(Offline — update admin default)' : ''}
                                  </option>
                              );
                          })}
                      </select>
                  </div>
              </div>

              {/* Admin defaults toggle */}
              <div className="flex items-center justify-center space-x-2 mt-2">
                  <label className="font-poetic text-stone-700 text-sm">Admin Defaults:</label>
                  <Switch
                      checked={hasLlmDefaults}
                      onCheckedChange={(checked) => {
                          if (checked) {
                              handleSaveLlmDefaults();
                          } else {
                              handleClearLlmDefaults();
                          }
                      }}
                      className="data-[state=checked]:bg-green-600"
                  />
                  <span className="text-xs text-stone-500">
                      {hasLlmDefaults ? 'Saved as Admin default' : 'Not saved'}
                  </span>
              </div>

              {/* Model list freshness */}
              <p className="text-xs text-stone-400 text-center mt-1">
                {llmOptionsLastRefreshed
                  ? <>Model list last refreshed: <span className="text-stone-500">{new Date(llmOptionsLastRefreshed).toLocaleString()}</span></>
                  : 'Model list: not yet refreshed this session'}
              </p>

              {/* Per-provider API key editing */}
              {llmProvidersList.filter(p => !p.hidden).length > 0 && (
                <div className="p-3 rounded-lg border bg-stone-50/60 space-y-2">
                  <label className="block font-poetic text-stone-800 font-semibold text-sm">Provider API Keys</label>
                  {llmProvidersList.filter(p => !p.hidden).map(p => (
                    <div key={p.id} className="flex flex-wrap items-center gap-2">
                      <span className="font-poetic text-stone-700 text-xs w-28 shrink-0">{p.name}</span>
                      <span className="text-xs">
                        {p.key_set
                          ? <span className="text-green-600">set (••••{p.key_last4})</span>
                          : <span className="text-amber-600">no key</span>}
                      </span>
                      <input
                        type="password"
                        className="flex-1 min-w-[140px] p-1 rounded border bg-white font-mono text-xs"
                        placeholder="Enter new key to update"
                        value={providerKeyEdits[p.id] || ""}
                        onChange={e => setProviderKeyEdits(prev => ({ ...prev, [p.id]: e.target.value }))}
                      />
                      <Button
                        size="sm"
                        variant="outline"
                        className="font-poetic text-xs"
                        disabled={!providerKeyEdits[p.id] || providerKeySaving[p.id]}
                        onClick={() => handleSaveProviderKey(p.id)}
                      >
                        {providerKeySaving[p.id] ? "Saving..." : "Update"}
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Horizontal separator */}
        <hr className="w-full border-stone-300" />

        {/* Collapsible Integrations Section */}
        <div className="w-full">
          <button
            className="flex items-center gap-2 font-poetic text-stone-700 cursor-pointer hover:text-stone-900"
            onClick={() => setIntegrationsExpanded(!integrationsExpanded)}
          >
            <span className="text-lg">{integrationsExpanded ? '▼' : '▶'}</span>
            <span className="font-semibold">Integrations</span>
          </button>

          {integrationsExpanded && (
            <div className="mt-2 space-y-3">
              {/* Web Search group */}
              <div className="p-3 rounded-lg border bg-stone-50/60 space-y-2">
                <label className="block font-poetic text-stone-800 font-semibold text-sm">Web Search</label>
                {[
                  { key: "BRAVE_SEARCH_API_KEY", label: "Brave Search API key" },
                ].map(({ key, label }) => {
                  const info = integrations[key] || {};
                  return (
                    <div key={key} className="flex flex-wrap items-center gap-2">
                      <span className="font-poetic text-stone-700 text-xs w-40 shrink-0">{label}</span>
                      <span className="text-xs">
                        {info.set
                          ? <span className="text-green-600">set (••••{info.last4})</span>
                          : <span className="text-red-500">not set</span>}
                      </span>
                      <input
                        type="password"
                        className="flex-1 min-w-[160px] p-1 rounded border bg-white font-mono text-xs"
                        placeholder="Enter new value to update"
                        value={integrationEdits[key] || ""}
                        onChange={e => setIntegrationEdits(prev => ({ ...prev, [key]: e.target.value }))}
                      />
                    </div>
                  );
                })}
              </div>

              {/* Voice Lab group */}
              <div className="p-3 rounded-lg border bg-stone-50/60 space-y-2">
                <label className="block font-poetic text-stone-800 font-semibold text-sm">Voice Lab</label>
                {[
                  { key: "AGORA_APP_ID", label: "Agora App ID" },
                  { key: "AGORA_APP_CERTIFICATE", label: "Agora App Certificate" },
                  { key: "AGORA_CUSTOMER_ID", label: "Agora Customer ID" },
                  { key: "AGORA_CUSTOMER_SECRET", label: "Agora Customer Secret" },
                  { key: "DEEPGRAM_API_KEY", label: "Deepgram API key" },
                  { key: "CARTESIA_API_KEY", label: "Cartesia API key" },
                ].map(({ key, label }) => {
                  const info = integrations[key] || {};
                  return (
                    <div key={key} className="flex flex-wrap items-center gap-2">
                      <span className="font-poetic text-stone-700 text-xs w-40 shrink-0">{label}</span>
                      <span className="text-xs">
                        {info.set
                          ? <span className="text-green-600">set (••••{info.last4})</span>
                          : <span className="text-red-500">not set</span>}
                      </span>
                      <input
                        type="password"
                        className="flex-1 min-w-[160px] p-1 rounded border bg-white font-mono text-xs"
                        placeholder="Enter new value to update"
                        value={integrationEdits[key] || ""}
                        onChange={e => setIntegrationEdits(prev => ({ ...prev, [key]: e.target.value }))}
                      />
                    </div>
                  );
                })}
              </div>

              {/* Save button */}
              <div className="flex items-center gap-3">
                <Button
                  className="font-poetic"
                  onClick={handleSaveIntegrations}
                  disabled={integrationSaving || Object.keys(integrationEdits).length === 0}
                >
                  {integrationSaving ? "Saving..." : "Save all changes"}
                </Button>
                {integrationMsg && (
                  <span className="text-xs text-stone-600">{integrationMsg}</span>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Horizontal separator */}
        <hr className="w-full border-stone-300" />

        {/* Collapsible Backend Log */}
        <div className="w-full">
          <button
            className="flex items-center gap-2 font-poetic text-stone-700 cursor-pointer hover:text-stone-900"
            onClick={() => setLogExpanded(!logExpanded)}
          >
            <span className="text-lg">{logExpanded ? '▼' : '▶'}</span>
            <span className="font-semibold">Backend Log</span>
          </button>

          {logExpanded && (
            <div className="mt-2">
              <Card className="bg-zinc-100 border border-zinc-300 overflow-hidden">
                <pre
                  ref={backendLogPreRef}
                  className="overflow-y-auto px-3 md:px-4 py-3 text-stone-900 text-xs leading-relaxed"
                  style={{ fontFamily: "monospace", maxHeight: "50vh", whiteSpace: "pre-wrap", wordBreak: "break-all" }}
                >
                  {backendLog || "Loading..."}
                  <div ref={backendLogRef} />
                </pre>
              </Card>
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
            <div className="mt-4 text-xs md:text-sm text-stone-700 space-y-1 break-all">
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
            <div className="mt-2 p-2 md:p-3 bg-white rounded-md border text-sm md:text-base text-stone-700 font-poetic">
              {topicDescriptions[selectedTopic]}
            </div>
          )}
        </div>
      )}

      <motion.div className="px-2 md:px-4 w-full max-w-5xl mx-auto flex-1 overflow-visible">
        <div className={`flex flex-col md:flex-row ${isDebateMode ? 'md:space-x-4' : ''} min-h-0`}>
          <div className={`${isDebateMode ? 'md:flex-1' : 'w-full'} min-h-0 rounded-2xl mb-4 md:mb-0`}>
            <Card className="flex flex-col h-full min-h-0 shadow-lg bg-white/90">
              {/* scrollable messages */}
              <div
                onWheel={e => e.stopPropagation()}
                className="flex-1 h-[60vh] md:h-[70vh] min-h-0 overflow-y-auto px-3 md:px-8 py-4 md:py-6"
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
                      className={`max-w-xs md:max-w-lg px-4 py-3 rounded-xl shadow text-sm md:text-lg whitespace-pre-wrap ${
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

              {/* offline model warning */}
              {offlineBlockers.length > 0 && (
                <div className="px-3 md:px-6 py-2 bg-red-50 border-t border-red-200 text-red-700 text-xs font-poetic">
                  ⚠️ {offlineBlockers.map(b => `${b.role} model "${b.model}"`).join(' and ')} {offlineBlockers.length > 1 ? 'are' : 'is'} offline. Open LLM Config to select an active model.
                </div>
              )}

              {/* input bar */}
              <div className="flex items-center gap-2 px-3 md:px-6 py-3 md:py-4 border-t bg-stone-50">
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ duration: 0.6 }}
                  className="flex-1"
                >
                  <Input
                    className="w-full rounded-full font-poetic bg-white text-stone-900"
                    style={{ color: '#1c1917' }}
                    placeholder={!selectedAvatar ? "Select or create an avatar to begin..." : "Speak with the avatar..."}
                    value={input}
                    onChange={e => setInput(e.target.value)}
                    onKeyDown={e => !chatDisabled && e.key === 'Enter' && handleSubmit()}
                    disabled={!selectedAvatar}
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
            <div className="w-full md:w-1/3 bg-white rounded-2xl shadow p-3 md:p-4 h-[40vh] md:h-[60vh] overflow-y-auto">
              <h4 className="font-poetic text-base md:text-lg font-bold mb-2">Debate Summary</h4>
              <div
                className="text-xs md:text-sm text-stone-700 whitespace-pre-wrap"
                dangerouslySetInnerHTML={{ __html: debateSummary }}
              />
            </div>
          )}
        </div>
      </motion.div>

      {/* Simple avatar create/edit panel (inline "modal") */}
      {avatarFormOpen && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-40 p-2">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg max-h-[90vh] overflow-y-auto p-4 md:p-6">
            <h2 className="text-lg md:text-xl font-poetic mb-4">
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
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-40 p-2">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg max-h-[90vh] overflow-y-auto p-4 md:p-6">
            <h2 className="text-lg md:text-xl font-poetic mb-4">
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
