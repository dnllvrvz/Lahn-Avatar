import asyncio
import io
import json
import os
import re
import threading
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()
print("Loaded from .env file.")

from flask import Flask, Response, jsonify, make_response, request, send_file
from flask_cors import CORS
from llama_index.core.tools.query_engine import QueryEngineTool
from utils.llm_tooling import LLM
from utils.avatar_setup import (
    avatar_llms,
    avatar_rag_tools,
    avatar_sensor_tools,
    avatars_path,
    generate_avatars_config,
    DEFAULT_CHAT_PROVIDER,
    DEFAULT_CHAT_MODEL,
    DEFAULT_TEXT_QUERY_PROVIDER,
    DEFAULT_TEXT_QUERY_MODEL,
    DEFAULT_SENSOR_PROVIDER,
    DEFAULT_SENSOR_MODEL,
    SENSOR_SYSTEM_PROMPT,
    TEXT_QUERY_SYSTEM_PROMPT,
)
from utils.processing_pipelines import OpenAIRealtimeClient
from utils.utils import (
    RAG,
    build_or_load_index,
    detect_web_search_intent,
    extract_keywords_multilingual,
    fetch_system_prompt_from_gdoc,
    fetch_text_index_query,
    generate_context_aware_keywords_for_multilingual_text_index_search,
    format_history_as_string,
    pcm_to_wav_bytes,
    prepare_query_engines,
    transcribe_audio,
    SensorsTool,
    web_search,
)
from werkzeug.utils import secure_filename
import requests

# === Initialize Flask ===
app = Flask(__name__)
CORS(app, supports_credentials=True)

@app.errorhandler(Exception)
def handle_exception(e):
    import traceback
    from werkzeug.exceptions import HTTPException
    code = e.code if isinstance(e, HTTPException) else 500
    return jsonify({"error": str(e), "traceback": traceback.format_exc()}), code

UPLOAD_DIR = "data/uploaded_experiences"
os.makedirs(UPLOAD_DIR, exist_ok=True)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GWDG_API_KEY = os.getenv("GWDG_API_KEY")
GWDG_API_BASE = os.getenv("GWDG_API_BASE")
AGORA_APP_ID = os.getenv("AGORA_APP_ID", "")
AGORA_CUSTOMER_ID = os.getenv("AGORA_CUSTOMER_ID", "")
AGORA_CUSTOMER_SECRET = os.getenv("AGORA_CUSTOMER_SECRET", "")
BACKEND_PUBLIC_URL = os.getenv("BACKEND_PUBLIC_URL", "")
LLM_PROVIDERS_PATH = "llm_providers.json"
HEALTH_CACHE_PATH = "llm_health_cache.json"
_models_last_refreshed = None  # ISO timestamp, set after each model list refresh
_model_health_cache = json.load(open(HEALTH_CACHE_PATH)) if os.path.exists(HEALTH_CACHE_PATH) else {}

_sensor_cache = {}  # avatar_id -> {"ts": float, "summary": str}
SENSOR_CACHE_TTL = 120  # seconds

def _fetch_sensor_summary(avatar_id):
    """Fetch latest sensor readings and return a formatted text summary. Cached per avatar."""
    import time
    cached = _sensor_cache.get(avatar_id)
    if cached and (time.time() - cached["ts"]) < SENSOR_CACHE_TTL:
        return cached["summary"]

    sensor_config = avatar_sensor_tools.get(avatar_id)
    if not sensor_config:
        return None
    sensor_url = sensor_config.get("sensor_url", "")
    if not sensor_url:
        return None

    # Fetch last 10 readings
    fetch_url = sensor_url if "results=" in sensor_url else sensor_url + ("&" if "?" in sensor_url else "?") + "results=10"
    try:
        resp = requests.get(fetch_url, headers={"Accept": "application/json", "User-Agent": "Lahn-Avatar/1.0"}, timeout=8)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[sensor cache] fetch failed for avatar {avatar_id}: {e}")
        return None

    # Parse field names and most recent non-null values
    lines = []
    if "channel" in data and "feeds" in data:
        channel = data["channel"]
        field_map = {f"field{i}": channel[f"field{i}"] for i in range(1, 9) if f"field{i}" in channel}
        feeds = data["feeds"]
        # Most recent reading with at least one non-null value
        latest = next((f for f in reversed(feeds) if any(f.get(k) is not None for k in field_map)), None)
        if latest:
            lines.append(f"Latest reading ({latest.get('created_at', 'unknown time')}):")
            for field_key, field_name in field_map.items():
                val = latest.get(field_key)
                if val is not None:
                    lines.append(f"  {field_name}: {val}")
    elif "feeds" in data:
        feeds = data["feeds"]
        latest = feeds[-1] if feeds else None
        if latest:
            ts = latest.get("timestamp") or latest.get("created_at", "unknown time")
            lines.append(f"Latest reading ({ts}):")
            for k, v in latest.items():
                if k not in ("timestamp", "created_at", "entry_id") and v is not None:
                    lines.append(f"  {k}: {v}")

    if not lines:
        return None

    summary = "\n".join(lines)
    _sensor_cache[avatar_id] = {"ts": time.time(), "summary": summary}
    print(f"[sensor cache] refreshed for avatar {avatar_id}")
    return summary


def _persist_health_cache():
    try:
        json.dump(_model_health_cache, open(HEALTH_CACHE_PATH, "w"))
    except Exception as e:
        print(f"[health cache] failed to persist: {e}")

if not os.path.exists(LLM_PROVIDERS_PATH):
    json.dump([
        {"id": "openai", "name": "OpenAI", "hidden": True, "provider_key": "openai",
         "api_base": "https://api.openai.com/v1", "api_key_env": "OPENAI_API_KEY", "models": []},
        {"id": "gwdg", "name": "JLU", "provider_key": "gwdg",
         "api_base": "https://api.hrz.uni-giessen.de", "api_key_env": "GWDG_API_KEY", "models": []},
        {"id": "openrouter", "name": "OpenRouter", "provider_key": "openai",
         "api_base": "https://openrouter.ai/api/v1", "api_key_env": "OPENROUTER_API_KEY", "models": []},
        {"id": "ollama", "name": "Ollama Cloud", "provider_key": "ollama",
         "api_base": "https://ollama.com", "api_key_env": "OLLAMA_API_KEY", "models": []},
    ], open(LLM_PROVIDERS_PATH, "w"), indent=2)


# ─── Shared helpers (used by /api/chat and /api/voice/chat-completions) ───

MODEL_FAMILIES = ['gemma', 'qwen', 'llama', 'mistral', 'deepseek', 'codestral',
                  'phi', 'falcon', 'mixtral', 'command', 'claude', 'gpt',
                  'devstral', 'medgemma', 'glm', 'kimi', 'minimax']

def _extract_family(model_name):
    if not model_name:
        return None
    lower = model_name.lower()
    return next((f for f in MODEL_FAMILIES if f in lower), None)

def _is_free_tier(model_name):
    return model_name.endswith(':free') or ':free:' in model_name

def fallback_model(provider_id, model_name):
    """
    When an admin-default model is offline, find the best available substitute.
    Tier 1: same provider, same family, online.
    Tier 2: any provider, same family, online.
    Tier 3: any online model on any provider.
    Returns (provider_id, model_name) — unchanged if the model is healthy or cache is empty.
    """
    if not _model_health_cache:
        return provider_id, model_name
    if _model_health_cache.get(model_name) != 'offline':
        return provider_id, model_name

    try:
        providers = json.load(open(LLM_PROVIDERS_PATH, "r"))
    except Exception:
        return provider_id, model_name

    visible = [p for p in providers if not p.get('hidden')]
    family = _extract_family(model_name)

    def _candidate(m):
        return _model_health_cache.get(m) == 'online' and not _is_free_tier(m)

    # Tier 1: same provider, same family
    same_provider = next((p for p in visible if p['id'] == provider_id), None)
    if same_provider and family:
        t1 = next((m for m in same_provider.get('models', [])
                   if _extract_family(m) == family and _candidate(m)), None)
        if t1:
            print(f"[fallback] {model_name} offline → tier-1 fallback: {t1} ({provider_id})")
            return provider_id, t1

    # Tier 2: any provider, same family
    if family:
        for p in visible:
            t2 = next((m for m in p.get('models', [])
                       if _extract_family(m) == family and _candidate(m)), None)
            if t2:
                print(f"[fallback] {model_name} offline → tier-2 fallback: {t2} ({p['id']})")
                return p['id'], t2

    # Tier 3: any online non-free model
    for p in visible:
        t3 = next((m for m in p.get('models', []) if _candidate(m)), None)
        if t3:
            print(f"[fallback] {model_name} offline → tier-3 fallback: {t3} ({p['id']})")
            return p['id'], t3

    print(f"[fallback] {model_name} offline — no online fallback found, proceeding anyway")
    return provider_id, model_name

def create_llm_instance(provider_id, model, system_prompt, temperature=0.7,
                        top_k=40, top_p=1.0, task_name="unknown", providers=None):
    """Create an LLM instance for any task. Single source of truth for LLM construction."""
    if providers is None:
        providers = json.load(open(LLM_PROVIDERS_PATH, "r"))

    provider = next((p for p in providers if p["id"] == provider_id), None)
    if not provider:
        raise ValueError(f"Unknown LLM provider: {provider_id}")

    provider_key = provider["provider_key"]
    api_key_env = provider.get("api_key_env", "")
    api_base = provider.get("api_base", "")

    api_key = os.getenv(api_key_env, "") if api_key_env else ""
    if not api_key:
        if provider_key == "openai":
            api_key = OPENAI_API_KEY
        elif provider_key == "gwdg":
            api_key = GWDG_API_KEY
        elif provider_key == "ollama":
            api_key = os.getenv("OLLAMA_API_KEY", "")
    if not api_base and provider_key == "gwdg" and GWDG_API_BASE:
        api_base = GWDG_API_BASE

    print(f"Creating LLM for {task_name}: provider={provider_id}, model={model}, "
          f"temp={temperature}, top_k={top_k}, top_p={top_p}")

    if provider_key == "openai":
        llm_params = {
            "provider": "openai", "openai_model": model, "system_prompt": system_prompt,
            "openai_api_key": api_key, "temperature": temperature, "top_k": top_k, "top_p": top_p,
        }
        if api_base:
            llm_params["openai_api_base"] = api_base
    elif provider_key == "ollama":
        llm_params = {
            "provider": "ollama", "ollama_model": model, "system_prompt": system_prompt,
            "temperature": temperature, "top_k": top_k, "top_p": top_p,
        }
        if api_key:
            llm_params["ollama_api_key"] = api_key
        if api_base:
            llm_params["ollama_api_base"] = api_base
    else:
        llm_params = {
            "provider": "gwdg", "gwdg_model": model, "system_prompt": system_prompt,
            "temperature": temperature, "top_k": top_k, "top_p": top_p,
        }
        if api_key:
            llm_params["gwdg_api_key"] = api_key
        if api_base:
            llm_params["gwdg_api_base"] = api_base

    return LLM(**llm_params)


def resolve_llm_defaults(avatar_id, user_params=None):
    """
    Resolve LLM parameters via cascade: user request → admin defaults → global defaults.
    Returns (resolved_dict, sources_dict).
    """
    avatars = json.load(open(avatars_path, "r"))
    avatar_obj = next((a for a in avatars if a["id"] == avatar_id), None)
    admin_defaults = avatar_obj.get("llmDefaults", {}) if avatar_obj else {}

    chat_defaults = admin_defaults.get("chat", {})
    text_query_defaults = admin_defaults.get("textQuery", {})
    sensor_defaults = admin_defaults.get("sensor", {})

    if user_params is None:
        user_params = {}
    sources = {}

    def _resolve(req_val, default_val, global_val, key):
        if req_val is not None:
            if default_val is not None and default_val == req_val:
                sources[key] = "Admin defaults"
            else:
                sources[key] = "user"
            return req_val
        elif default_val is not None:
            sources[key] = "Admin defaults"
            return default_val
        else:
            sources[key] = "global defaults"
            return global_val

    resolved = {}
    resolved["chat_provider"] = _resolve(
        user_params.get("chatProvider"), chat_defaults.get("provider"), DEFAULT_CHAT_PROVIDER, "chat_provider")
    resolved["chat_model"] = _resolve(
        user_params.get("chatModel"), chat_defaults.get("model"), DEFAULT_CHAT_MODEL, "chat_model")
    resolved["temperature"] = _resolve(
        user_params.get("temperature"), chat_defaults.get("temperature"), 0.7, "temperature")
    resolved["top_k"] = _resolve(
        user_params.get("topK"), chat_defaults.get("top_k"), 40, "top_k")
    resolved["top_p"] = _resolve(
        user_params.get("topP"), chat_defaults.get("top_p"), 1.0, "top_p")

    # Text query — falls back to chat provider if unset
    resolved["text_query_provider"] = _resolve(
        user_params.get("textQueryProvider"), text_query_defaults.get("provider"), resolved["chat_provider"], "text_query_provider")
    if sources["text_query_provider"] == "global defaults":
        sources["text_query_provider"] = "inherited from chat"
    resolved["text_query_model"] = _resolve(
        user_params.get("textQueryModel"), text_query_defaults.get("model"), DEFAULT_TEXT_QUERY_MODEL, "text_query_model")

    # Sensor — falls back to chat provider if unset
    resolved["sensor_provider"] = _resolve(
        user_params.get("sensorProvider"), sensor_defaults.get("provider"), resolved["chat_provider"], "sensor_provider")
    if sources["sensor_provider"] == "global defaults":
        sources["sensor_provider"] = "inherited from chat"
    resolved["sensor_model"] = _resolve(
        user_params.get("sensorModel"), sensor_defaults.get("model"), DEFAULT_SENSOR_MODEL, "sensor_model")

    return resolved, sources


def inject_rag_context(avatar_id, chat_history, conversation_for_rag, text_query_llm,
                       verbose=True):
    """
    Inject RAG context into the last message of chat_history (in-place).
    verbose=True uses the full chat-style wrapper; False uses a compact voice wrapper.
    Returns (rag_injected: bool, web_search_query: str | None).
    The web_search_query is detected in the same LLM call as keyword generation (RAG path),
    or via a dedicated lightweight call (no-RAG path).
    """
    tools = avatar_rag_tools.get(avatar_id)
    has_rag = tools and tools[0] is not None

    if not has_rag:
        # No RAG — run a cheap dedicated web search intent check
        web_search_query = detect_web_search_intent(text_query_llm, conversation_for_rag)
        return False, web_search_query

    rag_languages = tools[4] if len(tools) > 4 else ['en', 'de']

    keywords_by_lang, web_search_query = generate_context_aware_keywords_for_multilingual_text_index_search(
        text_query_llm, conversation_for_rag, rag_languages
    )
    context = RAG(tools, None, keywords_by_lang=keywords_by_lang)

    if verbose:
        wrapper = (
            " <End of User message>.        <<IMPORTANT: The following info is a RAG injection "
            "to provide you with helpful context. The user did not send this: Here is relevant "
            "information (Sometimes the text-retrieval has relevant information that the "
            "vector-retrieval doesn't, or vice versa. Look through each comprehensively, to "
            "extract the information you need. Even if the Vector-retrieval says there's no "
            "information available, still scrutinize the Text-retrieval results to fetch relevant "
            "info (What language was the user's last message in? Make sure to respond in the same "
            "language.) This instruction is in English, but your response should be in whatever "
            "language the user messaged you in:>>  "
        )
    else:
        wrapper = " <End of User message>. <<Context from knowledge base: "

    chat_history[-1]["content"] += wrapper + context + (">>" if not verbose else "")
    return True, web_search_query


def handle_sensor_tool_call(response_text, avatar_id, sensor_provider, sensor_model,
                            llm, chat_history, providers=None):
    """
    If response_text contains analyze_sensor_data(), run the sensor tool and re-invoke LLM.
    Returns (final_response, was_handled).
    """
    sensor_config = avatar_sensor_tools.get(avatar_id)
    if not sensor_config or "analyze_sensor_data" not in response_text:
        return response_text, False

    q_start = response_text.find('user_query="') + 12
    q_end = response_text.find('")', q_start)
    query = response_text[q_start:q_end]
    if not query:
        return response_text, False

    sensor_llm = create_llm_instance(
        sensor_provider, sensor_model, SENSOR_SYSTEM_PROMPT,
        task_name="sensor", providers=providers,
    )
    sensor_tool = SensorsTool(
        sensor_llm,
        sensor_url=sensor_config["sensor_url"],
        sensor_description=sensor_config.get("sensor_description"),
    )
    analysis = str(sensor_tool(query))
    print(f"Sensor analysis: {analysis}")

    results_msg = (
        "\nHere is the output of analyze_sensor_data(): " + analysis
        + " Respond to the user accordingly. Do not provide any subjective Lahn-specific "
        "evaluation of this data, just focus on the quantitative result. And do not return "
        "a function call. What language was the user's last message in? Make sure to respond "
        "in the same language."
    )
    chat_history.append({"role": "assistant", "content": results_msg})
    final = llm.complete(chat_history).text

    # Guard against recursive function calls
    if "analyze_sensor_data" in final:
        final = analysis

    return final.replace("*", ""), True


def _build_model_checks(provider_ids_filter=None):
    """Build list of model checks, optionally filtered by provider IDs."""
    providers = json.load(open(LLM_PROVIDERS_PATH, "r"))

    model_checks = []
    for provider in providers:
        provider_key = provider["provider_key"]

        # Skip hidden providers
        if provider.get("hidden"):
            continue

        # Filter by provider id (unique per provider, unlike provider_key)
        if provider_ids_filter and provider["id"] not in provider_ids_filter:
            continue

        api_key_env = provider.get("api_key_env", "")
        api_base = provider.get("api_base", "")

        # Load API key from environment variable
        api_key = os.getenv(api_key_env, "") if api_key_env else ""

        # Special handling for legacy env vars
        if not api_key:
            if provider_key == "openai":
                api_key = OPENAI_API_KEY
            elif provider_key == "gwdg":
                api_key = GWDG_API_KEY
            elif provider_key == "ollama":
                api_key = os.getenv("OLLAMA_API_KEY", "")

        if not api_base:
            if provider_key == "gwdg" and GWDG_API_BASE:
                api_base = GWDG_API_BASE

        health_check_timeout = 15

        for model_name in provider.get("models", []):
            model_checks.append({
                "model_name": model_name,
                "provider_key": provider_key,
                "api_key": api_key,
                "api_base": api_base,
                "timeout": health_check_timeout
            })

    return model_checks


def _health_check_reason(e):
    """Return a short human-readable reason for a failed health check."""
    msg = str(e)
    if "429" in msg:
        return "rate limited (429)"
    if "404" in msg:
        return "not a chat model (404)"
    if "400" in msg:
        return "unavailable on provider's end (400)"
    if "500" in msg:
        return "provider server error (500)"
    if isinstance(e, requests.exceptions.Timeout) or "timed out" in msg.lower() or "timeout" in msg.lower():
        return "timed out"
    return f"error ({msg[:60]})"


def _check_model(check_data):
    """Check a single model's health, with one retry on 429."""
    import time, random
    from utils.llm_tooling import LLM

    model_name = check_data["model_name"]
    provider_key = check_data["provider_key"]
    api_key = check_data["api_key"]
    api_base = check_data["api_base"]
    timeout = check_data["timeout"]

    def build_llm():
        llm_params = {
            'provider': provider_key,
            'system_prompt': "You are a helpful assistant.",
            'timeout': timeout
        }
        if provider_key == "openai":
            llm_params['openai_model'] = model_name
            llm_params['openai_api_key'] = api_key
            if api_base:
                llm_params['openai_api_base'] = api_base
        elif provider_key == "gwdg":
            llm_params['gwdg_model'] = model_name
            if api_key:
                llm_params['gwdg_api_key'] = api_key
            if api_base:
                llm_params['gwdg_api_base'] = api_base
        elif provider_key == "ollama":
            llm_params['ollama_model'] = model_name
            if api_key:
                llm_params['ollama_api_key'] = api_key
            if api_base:
                llm_params['ollama_api_base'] = api_base
        else:
            llm_params['provider'] = 'gwdg'
            llm_params['gwdg_model'] = model_name
            if api_key:
                llm_params['gwdg_api_key'] = api_key
            if api_base:
                llm_params['gwdg_api_base'] = api_base
        return LLM(**llm_params)

    MAX_RETRIES = 6
    for attempt in range(MAX_RETRIES + 1):
        try:
            build_llm().complete(prompt="ping")
            suffix = f" (after {attempt} retries)" if attempt > 0 else ""
            print(f"Health check: {model_name} ({provider_key}) -> online{suffix}")
            return (model_name, "online")
        except Exception as e:
            if "429" in str(e) and attempt < MAX_RETRIES:
                # Rate limited — backoff with jitter and try again
                delay = (attempt + 1) * 2 + random.uniform(0, 3)
                time.sleep(delay)
                continue
            reason = _health_check_reason(e)
            print(f"Health check: {model_name} ({provider_key}) -> offline ({reason})")
            return (model_name, "offline")


def _run_health_checks(model_checks, max_workers):
    """Run health checks with specified parallelism."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    health_status = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_model = {
            executor.submit(_check_model, check_data): check_data["model_name"]
            for check_data in model_checks
        }
        for future in as_completed(future_to_model):
            model_name, status = future.result()
            health_status[model_name] = status

    return health_status


@app.route("/api/health/llm/fast", methods=["GET"])
def llm_health_fast():
    """Health check for fast providers (OpenAI, GWDG) - high parallelism."""
    global _model_health_cache
    model_checks = _build_model_checks(provider_ids_filter=["openai", "gwdg"])
    results = _run_health_checks(model_checks, max_workers=10)
    _model_health_cache.update(results)
    _persist_health_cache()
    print(f"Fast health check results: {results}")
    return jsonify(results)


@app.route("/api/health/llm/slow", methods=["GET"])
def llm_health_slow():
    """Health check for slow/rate-limited providers (Ollama) - limited parallelism."""
    global _model_health_cache
    model_checks = _build_model_checks(provider_ids_filter=["ollama"])
    results = _run_health_checks(model_checks, max_workers=8)
    _model_health_cache.update(results)
    _persist_health_cache()
    print(f"Slow health check results: {results}")
    return jsonify(results)


def _check_openrouter_model(model_id, api_key):
    """Check OpenRouter model health via its endpoints metadata API (no inference needed)."""
    try:
        resp = requests.get(
            f"https://openrouter.ai/api/v1/models/{model_id}/endpoints",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        endpoints = resp.json().get("data", {}).get("endpoints", [])
        if not endpoints:
            return model_id, "offline"
        best_uptime = max((e.get("uptime_last_5m") or 0) for e in endpoints)
        status = "online" if best_uptime > 0 else "offline"
        return model_id, status
    except Exception as e:
        return model_id, "offline"


@app.route("/api/health/llm/openrouter", methods=["GET"])
def llm_health_openrouter():
    """Health check for OpenRouter using uptime metadata — no inference calls needed."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    providers = json.load(open(LLM_PROVIDERS_PATH, "r"))
    provider = next((p for p in providers if p["id"] == "openrouter"), None)
    if not provider:
        return jsonify({}), 200

    api_key = os.getenv(provider.get("api_key_env", ""), "")
    models = provider.get("models", [])

    results = {}
    with ThreadPoolExecutor(max_workers=50) as executor:
        future_to_model = {
            executor.submit(_check_openrouter_model, m, api_key): m for m in models
        }
        for future in as_completed(future_to_model):
            model_id, status = future.result()
            results[model_id] = status

    global _model_health_cache
    _model_health_cache.update(results)
    _persist_health_cache()
    online = sum(1 for s in results.values() if s == "online")
    print(f"OpenRouter health check: {online}/{len(models)} online")
    return jsonify(results)


@app.route("/api/health/llm", methods=["GET"])
def llm_health():
    """
    Combined health check for all providers.
    Returns a map of model names to their status ('online' or 'offline').
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    # Build all model checks
    model_checks = _build_model_checks()

    # Separate by provider
    ollama_checks = [m for m in model_checks if m["provider_key"] == "ollama"]
    other_checks = [m for m in model_checks if m["provider_key"] != "ollama"]

    health_status = {}

    # Run both groups in parallel (but with different parallelism internally)
    with ThreadPoolExecutor(max_workers=2) as executor:
        # Submit both groups
        fast_future = executor.submit(_run_health_checks, other_checks, 10)
        slow_future = executor.submit(_run_health_checks, ollama_checks, 2)

        # Collect results
        health_status.update(fast_future.result())
        health_status.update(slow_future.result())

    return jsonify(health_status)


@app.route("/api/refresh-prompt", methods=["POST"])
def refresh_prompt():
    global avatar_llms
    data = request.get_json()
    avatar_id = data.get("avatar_id")
    if not avatar_id:
        return jsonify({"error": "avatar_id is required"}), 400

    print(f"Refresh prompt request received for avatar {avatar_id}.")

    avatars = json.load(open(avatars_path, "r"))
    avatar = next((a for a in avatars if a["id"] == avatar_id), None)
    if not avatar:
        return jsonify({"error": "Avatar not found."}), 404

    system_prompt_url = avatar.get("systemPromptUrl")
    if not system_prompt_url:
        return jsonify({"error": "Avatar does not have a systemPromptUrl."}), 400

    try:
        fetch_system_prompt_from_gdoc(avatar_id, system_prompt_url)
        # Reload the specific avatar's config
        llm, _, sensor_tool = generate_avatars_config(specific_avatar_id=avatar_id)
        if llm:
            avatar_llms[avatar_id] = llm
            avatar_sensor_tools[avatar_id] = sensor_tool
        else:
            return jsonify({"error": "Failed to reload avatar configuration."}), 500

        return jsonify({"status": "success", "message": f"Prompt for avatar {avatar_id} refreshed."})
    except Exception as e:
        print(f"Error refreshing prompt for avatar {avatar_id}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/refresh-embeddings", methods=["POST"])
def refresh_embeddings():
    global avatar_rag_tools
    data = request.get_json()
    avatar_id = data.get("avatar_id")
    if not avatar_id:
        return jsonify({"error": "avatar_id is required"}), 400

    print(f"Refresh embeddings request received for avatar {avatar_id}.")

    avatars = json.load(open(avatars_path, "r"))
    avatar = next((a for a in avatars if a["id"] == avatar_id), None)
    if not avatar:
        return jsonify({"error": "Avatar not found."}), 404

    drive_folder_id = avatar.get("driveFolderId")
    if not drive_folder_id:
        return jsonify({"error": "Avatar does not have a driveFolderId."}), 400

    try:
        # Re-build the index and get the new query engines
        rag_tools = prepare_query_engines(avatar_id, drive_folder_id, refresh=True)
        avatar_rag_tools[avatar_id] = rag_tools
        return jsonify({"status": "success", "message": f"Embeddings for avatar {avatar_id} refreshed."})
    except Exception as e:
        print(f"Error refreshing embeddings for avatar {avatar_id}: {e}")
        return jsonify({"error": str(e)}), 500


# debate_general_prompt = "Right now you are on a deliberation-centered platform, debating with the user the topic of '{topic}'. In this mode you should always consider the best interests of the Lahn River. You must decide what the Lahn’s best interests are based on all of your context information. You are the Lahn’s advocate right now. Below is a brief description of the topic, which both you and the user have access to. You can present your position to the user as you answer questions they might have on the topic. '{description}'"
# topic_descriptions = {
#     'The Lahn should have legal personhood': "In recent years, rivers around the world have been granted legal personhood to recognize their intrinsic rights and protect their ecosystems. Granting the Lahn legal personhood would mean treating the river not merely as a resource but as a living entity with legal standing - analogous to the legal standing that a person or corporation holds. This shift could reshape how environmental protection is approached in the region, allowing for the river's interests to be formally represented in legal and political systems. And even create precedent for the river suing a company or the government, for example.",
#     'The Lahn should be able to own property': "If the Lahn were recognized as a legal person, it could theoretically hold property titles. This would allow the river to directly control land essential to its health—such as floodplains, wetlands, or riverbanks—ensuring its ecological integrity is not compromised by conflicting human interests. Property ownership could become a tool for the river to safeguard its own regeneration and future.",
#     'There should exist a “Lahn Fund”': "A dedicated “Lahn Fund” would serve as a financial mechanism to support the ongoing protection, restoration, and stewardship of the river. This fund could receive public and private contributions, fines from environmental damages, or a share of local economic activities that depend on the river. Managed in the river’s interest, the fund could finance ecological research, conservation projects, community engagement, and support the operational costs of the Avatar or legal guardianship system.",
#     'The Avatar should be able to legally speak on behalf of the Lahn': "The Lahn Avatar is envisioned as a voice for the river—an interface between natural and human systems. Allowing the Avatar to legally speak on behalf of the Lahn would formalize its role as a representative entity in decision-making processes. This could enable the river’s interests to be expressed in public hearings, governmental deliberations, and community forums, fostering a new model of ecological democracy and interspecies governance."
#   }


@app.route("/api/chat", methods=["POST"])
def chat():
    # global llm, llm_choice, system_prompt
    avatar_id = request.args.get("avatar", "0")
    data = request.get_json()

    # Load avatar to check for defaults
    avatars = json.load(open(avatars_path, "r"))
    avatar = next((a for a in avatars if a["id"] == avatar_id), None)
    avatar_name = avatar.get("name", "Unknown") if avatar else "Unknown"
    admin_defaults = avatar.get("llmDefaults", {}) if avatar else {}

    print(
        f"\n\n------------------------\nvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv\nChat request received for Avatar '{avatar_name}' (id: {avatar_id})"
    )

    # Build user request params (with backward compat)
    user_params = {
        "chatProvider": data.get("chatProvider") or data.get("llmProvider"),
        "chatModel": data.get("chatModel") or data.get("llmModel"),
        "temperature": data.get("temperature"),
        "topK": data.get("topK"),
        "topP": data.get("topP"),
        "textQueryProvider": data.get("textQueryProvider"),
        "textQueryModel": data.get("textQueryModel"),
        "sensorProvider": data.get("sensorProvider"),
        "sensorModel": data.get("sensorModel"),
    }
    # Strip None values so resolve_llm_defaults treats them as unset
    user_params = {k: v for k, v in user_params.items() if v is not None}

    resolved, sources = resolve_llm_defaults(avatar_id, user_params)
    user_chat_provider = resolved["chat_provider"]
    user_chat_model = resolved["chat_model"]
    temperature = resolved["temperature"]
    top_k = resolved["top_k"]
    top_p = resolved["top_p"]
    text_query_provider = resolved["text_query_provider"]
    text_query_model = resolved["text_query_model"]
    sensor_provider = resolved["sensor_provider"]
    sensor_model = resolved["sensor_model"]

    # Reject requests for models known to be offline
    for role, model in [("chat", user_chat_model), ("text query", text_query_model), ("sensor", sensor_model)]:
        if _model_health_cache.get(model) == "offline":
            return jsonify({"error": f"The {role} model '{model}' is currently offline. Please select a different model in Avatar Lab."}), 503

    # Log resolved parameters with sources
    print("\n=== LLM Parameters (resolved) ===")
    print(f"Chat: provider={user_chat_provider} (from: {sources['chat_provider']}), model={user_chat_model} (from: {sources['chat_model']})")
    print(f"Temperature: {temperature} (from: {sources['temperature']})")
    print(f"Top K: {top_k} (from: {sources['top_k']})")
    print(f"Top P: {top_p} (from: {sources['top_p']})")
    print(f"Text Query: provider={text_query_provider} (from: {sources['text_query_provider']}), model={text_query_model} (from: {sources['text_query_model']})")
    print(f"Sensor: provider={sensor_provider} (from: {sources['sensor_provider']}), model={sensor_model} (from: {sources['sensor_model']})")
    print("=================================\n")

    # Get the avatar's system prompt from the pre-loaded config
    system_prompt = avatar_llms[avatar_id].system_prompt


    # if topic:
    #     print(f"→ Debate topic: {topic}")
    #     debate_prompt = debate_general_prompt.format(topic=topic, description=topic_descriptions[topic])
    #     # print('Prompt: ', debate_prompt)
    #     system_prompt_= system_prompt+ '\n' + debate_prompt
    # else:
    system_prompt_ = system_prompt

    chat_history = []

    conversation = data.get("history", "")
    print("Conversation history: ", conversation)

    chat_history = [
        {
            "role": "user" if m["sender"].lower() == "user" else "assistant",
            "content": m["text"],
        }
        for m in conversation
    ]

    if len(chat_history) == 0:
        return jsonify(
            {
                "error": 'Invalid request format. Ensure your payload has "history" in the format [{"sender": "User", "text": "content"}, ...]'
            }
        )

    chat_history.insert(0, {"role": "system", "content": system_prompt_})

    # === Create task-specific LLMs ===
    providers = json.load(open(LLM_PROVIDERS_PATH, "r"))

    # Text query LLM for keyword generation
    text_query_llm = create_llm_instance(
        text_query_provider, text_query_model, TEXT_QUERY_SYSTEM_PROMPT,
        task_name="text_query", providers=providers,
    )

    # === RAG Context Injection + Web Search Intent Classification ===
    # inject_rag_context returns (rag_injected, web_search_query).
    # For RAG avatars the web search intent is detected in the same LLM call as keyword generation.
    # For no-RAG avatars a dedicated lightweight call is made instead.
    rag_injected, pre_web_search_query = inject_rag_context(
        avatar_id, chat_history, conversation, text_query_llm, verbose=True
    )
    if rag_injected:
        print("Obtaining information for the LLM...")

    # === Sensor Tool Function Schema ===
    sensor_config = avatar_sensor_tools.get(avatar_id)

    # === Build unified function schema ===
    # Both functions are listed together so model knows all available options

    if sensor_config:
        print("Adding sensor tool function schema to prompt...")
        sensor_description = sensor_config.get('sensor_description', '')
        import json as json_module
        escaped_description = json_module.dumps(sensor_description, ensure_ascii=False)

        # Sensor AND web search both available for this avatar
        function_schema = f"""
FUNCTIONS:
You have access to these functions. Call them ONLY when explicitly requested.

1. analyze_sensor_data(user_query="your question")
   - MUST call this when user asks about current sensor readings (temperature, pH, water quality, etc.)

2. web_search(query="your search query")
   - MUST call this when user says "search the web", "look up on the internet", or explicitly requests information from the web/internet

When you call a function, output ONLY the function call line, nothing else.
"""
        chat_history[0]["content"] += function_schema
    else:
        # No sensor - only web search available
        function_schema = """
FUNCTIONS:
You have access to this function. Call it ONLY when explicitly requested.

1. web_search(query="your search query")
   - MUST call this when user says "search the web", "look up on the internet", or explicitly requests information from the web/internet

When you call a function, output ONLY the function call line, nothing else.
"""
        chat_history[0]["content"] += function_schema

    # === Always-fetch sensor snapshot (cached, 2-min TTL) ===
    # Gives LLM current readings for simple queries without tool invocation.
    # analyze_sensor_data() tool still handles complex analytical queries.
    if sensor_config:
        sensor_summary = _fetch_sensor_summary(avatar_id)
        if sensor_summary:
            chat_history[0]["content"] += f"\n\nCURRENT SENSOR SNAPSHOT:\n{sensor_summary}\nUse this for simple current-reading questions. Call analyze_sensor_data() only for trend analysis or questions requiring historical data."

    # === Pre-fetch web search results (classifier-driven) ===
    # If the intent classifier detected a need for live data, fetch now and inject
    # into the system prompt so the main LLM never needs to emit a tool call.
    if pre_web_search_query:
        print(f"[web search] Pre-fetching for classifier query: {pre_web_search_query!r}")
        pre_search_results = web_search(pre_web_search_query, count=5)
        chat_history[0]["content"] += (
            f"\n\nWEB SEARCH RESULTS (pre-fetched for your response):\n{pre_search_results}\n"
            "Use these results to inform your answer where relevant. "
            "Respond conversationally. Use the same language as the user."
        )

    messages_to_send = chat_history

    # === Create chat LLM for main conversation ===
    llm = create_llm_instance(user_chat_provider, user_chat_model, system_prompt_,
                              temperature=temperature, top_k=top_k, top_p=top_p,
                              task_name="chat", providers=providers)

    chat_completion = llm.complete(messages_to_send)
    response = chat_completion.text

    print("\nAvatar response: ", response)

    sensor_response, sensor_handled = handle_sensor_tool_call(
        response, avatar_id, sensor_provider, sensor_model, llm, chat_history, providers=providers)
    if sensor_handled:
        print("Avatar response after getting sensor data:", sensor_response)
        return jsonify({"reply": sensor_response})

    if "analyze_sensor_data" in response and not avatar_sensor_tools.get(avatar_id):
        # Avatar has no sensor tool configured but model tried to call it
        print(f"No sensor tool available for avatar {avatar_id}")
        results = (
            "\nNote: Sensor data is not available for this avatar. "
            "Please ask about other aspects of the Lahn or choose a different avatar."
        )
        chat_completion_2 = llm.complete(
            chat_history + [{"role": "assistant", "content": results}],
        )
        return jsonify({"reply": chat_completion_2.text.replace("*", "")})

    if "web_search" in response:
        print("Performing web search...")
        # Extract query: keyword arg, JSON, or positional arg formats
        # web_search(query="..."), "query": "...", web_search("...")
        match = (re.search(r'query\s*[:=]\s*["\']([^"\']+)["\']', response) or
                 re.search(r'web_search\s*\(\s*["\']([^"\']+)["\']', response))
        query = match.group(1) if match else ""

        print(f"Web search query: {query}")

        if query:
            # Brave automatically detects query language - no need for explicit language detection
            search_results = web_search(query, count=5)
            print(f"Web search results: {search_results[:200]}...")

            results_msg = (
                "\nWEB SEARCH RESULTS - you successfully searched the web and found this information:\n"
                + search_results
                + "\n\nNow answer the user's original question using these results. Respond conversationally as the Lahn avatar. Use the same language as the user."
            )

            # Create a clean system prompt WITHOUT function schema for the follow-up
            clean_system_prompt = system_prompt_

            # Create a clean user message without RAG/function instructions
            original_user_msg = chat_history[-1]["content"].split("<End of User message>")[0].strip()

            # Build clean message history for follow-up
            clean_messages = [
                {"role": "system", "content": clean_system_prompt + results_msg},
                {"role": "user", "content": original_user_msg}
            ]

            chat_completion_2 = llm.complete(clean_messages)
            response_2 = chat_completion_2.text

            if "web_search" in response_2:
                print("Duplicate web_search call, using results directly")
                response_2 = f"Web search results for '{query}':\n{search_results}"

            response_2 = response_2.replace("*", "")
            print("Avatar response after web search:", response_2)

            return jsonify({"reply": response_2})

    response = response.replace("*", "")

    return jsonify({"reply": response})


@app.route("/api/debate-summary", methods=["POST"])
def debate_summary():
    print("Debate Summary request received.")
    data = request.get_json()
    conversation = data.get("history", "")
    topic = data.get("topic", "")
    summary = data.get("summary", "")

    formatted_history = format_history_as_string(conversation)

    prompt = f"""This is a debate between a human and an AI avatar for the Lahn river. Your job is to provide a summary outline in the format
            "Lahn:<Lahn's Central Perspective>\nPro:<Central Pro>\nCon:<Central Con of Lahn's perspective (deduced by you)>\n\nYou:<User's Central Perspective>\nPro:<Central Pro>\nCon:<Central Con of User's perspective (deduced by you)>", briefly outlining the Lahn's primary perspective, a pro and con of that perspective, the user's perspective
            and a pro and con of that as well. Keep all content very brief. You're summarizing, not re-iterating. You are provided with the most recent debate summary. If it already contains content, iterate on that content to reflect recent updates to the conversation.
            Topic being debated: {topic}

            Conversation:
            {formatted_history}

            Existing summary:
            {summary}

            Respond with an updated version of the summary in the described format. Make sure to preserve the specified formatting in the template "Lahn:\nPro:\nCon:\n\nYou:\nPro:\nCon:". No extra characters. The contents of your response should ba based purely on the given summary.
            Summaries for 'Lahn' and 'User'should be based purely on what they said. If any party is yet to contribute to the conversation, leave their summary blank, as in the template."""

    response = debate_summary_llm.complete(prompt)  # chat_engine.chat(prompt)
    # print('Summary model response: ', response)
    summary = str(response)  # .choices[0].message.content

    # chat_history = [
    #     ChatMessage(role="user" if m["sender"] == "user" else "assistant", content=m["text"])
    #     for m in conversation
    #     ]

    # print('User message:', prompt)
    # response = chat_engine.chat(messages=chat_history)
    print("Summary:", summary)

    return jsonify({"summary": summary})


# Would want to differentiate between general user and Admin uploads----
@app.route("/api/experience-upload", methods=["POST"])
def experience_upload():
    print("Experience upload received.")
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")

    os.makedirs(f"{UPLOAD_DIR}/text", exist_ok=True)

    # ---------- Save TEXT immediately ----------
    text = request.form.get("text", "")
    if text.strip():
        with open(f"{UPLOAD_DIR}/text/{timestamp}_message.txt", "w") as f:
            f.write(text.strip())

    # ---------- Save FILES (cheap, fast) ----------
    uploaded_files = request.files.getlist("files")
    saved_paths = []

    for f in uploaded_files:
        if not f or not f.filename:
            continue

        filename = secure_filename(f.filename)
        dest = os.path.join(UPLOAD_DIR, filename)
        f.save(dest)
        saved_paths.append(dest)

    # ---------- SAVE AUDIO but DO NOT TRANSCRIBE YET ----------
    audio_path = None

    if "audio" in request.files:
        audio_file = request.files["audio"]
        if audio_file and audio_file.filename:
            safe_name = secure_filename(audio_file.filename)
            ext = os.path.splitext(safe_name)[1]

            audio_path = os.path.join(UPLOAD_DIR, f"{timestamp}_audio{ext}")
            audio_file.save(audio_path)
            print("🎤 Audio saved, transcription deferred.")

    # ---------- FIRE BACKGROUND JOB ----------
    def background_job():
        try:
            if audio_path:
                transcript = transcribe_audio(audio_path)
                with open(f"{UPLOAD_DIR}/text/{timestamp}_transcript.txt", "w") as f:
                    f.write(transcript.strip())
                print("📝 Transcription saved.")

            refresh_embeddings()
            print("🔄 Embeddings refreshed.")
        except Exception as e:
            print("❌ Background job failed:", e)

    threading.Thread(target=background_job, daemon=True).start()

    # ---------- RETURN IMMEDIATELY ----------
    return jsonify(
        {"status": "success", "message": "Experience saved. Processing in background."}
    )


import subprocess

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
CARTESIA_API_KEY = os.getenv("CARTESIA_API_KEY")


# Could pass audio_data directly to bypass file processing latency
@app.post("/api/voice-chat")
def voice_chat():
    print(
        "\n\n------------------------\nvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv\nVoice Chat request received."
    )

    # Get system prompt from avatar config
    system_prompt = avatar_llms["0"].system_prompt

    # Do away with function-related instructions, for now.
    index = system_prompt.find("You also have access to sensory data")
    system_prompt_ = system_prompt[:index]

    try:
        # get uploaded file + pipeline choice
        audio_file = request.files["audio"]  # comes from FormData

        ext = audio_file.mimetype.split("/")[-1]
        audio_path = "data/temp." + ext
        audio_file.save(audio_path)

        pipeline = request.form.get("pipeline", "OpenAI gpt-realtime")

        print("Recieved voice chat request. Pipeline: ", pipeline)
        print("Audio: ", audio_path)

        output_wav = "data/temp." + ".wav"
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-i", audio_path, output_wav],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
            print(f"[Success] Converted to: {output_wav}")
        except subprocess.CalledProcessError as e:
            print("[Error] ffmpeg decoding failed:\n", e.stderr.decode())
            return None

        # read into memory
        audio_bytes = output_wav  # audio_path #audio_file.read()

        # pass raw bytes to your dispatcher
        # Dispatch
        if pipeline == "OpenAI gpt-realtime":
            client = OpenAIRealtimeClient(
                OPENAI_API_KEY, model="gpt-realtime", prompt=system_prompt_,
                sensor_tool=avatar_sensor_tools.get("0")
            )
            response_audio, elapsed, cost_info = client.process_audio(audio_bytes)
        # elif pipeline == "OpenAI gpt4o":
        #     client = OpenAIRealtimeClient(OPENAI_API_KEY, model="gpt-4o-realtime-preview", prompt = system_prompt_)
        #     response_audio, elapsed, cost_info = client.process_audio(audio_bytes)
        # elif pipeline == "Cartesia":
        #     client = CartesiaOpenAIPipeline(CARTESIA_API_KEY, OPENAI_API_KEY, prompt = system_prompt_)
        #     response_audio, elapsed, cost_info = client.process_audio(audio_bytes)
        else:
            return jsonify({"error": f"Unknown pipeline '{pipeline}'"}), 400

        print("Done processing. Info: ", elapsed, cost_info)
        # print('System prompt: ', system_prompt_)

        # Convert raw PCM to WAV
        wav_bytes = pcm_to_wav_bytes(response_audio)

        # send audio directly
        return Response(wav_bytes, mimetype="audio/wav")

    except Exception as e:
        print({"error": str(e)})
        return jsonify({"error": str(e)}), 500


import json

from flask_sock import Sock

sock = Sock(app)


@sock.route("/api/voice-chat-stream")
def stream(ws):
    print(
        "\n\n------------------------\nvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv\nStreaming Voice Chat request received."
    )

    system_prompt = avatar_llms["0"].system_prompt
    # Do away with function-related instructions, for now.
    index = system_prompt.find("You also have access to sensory data")
    system_prompt_ = system_prompt[:index]

    client = OpenAIRealtimeClient(
        OPENAI_API_KEY,
        model="gpt-realtime",
        prompt=system_prompt_,
        rag_tools=avatar_rag_tools["0"],
        sensor_tool=avatar_sensor_tools.get("0"),
        streaming=True,
        ws_client=ws,
    )
    client.connect_to_openai()

    #  gpt-4o-realtime-preview
    # Handle audio sent from frontend
    while True:
        msg = ws.receive()
        if msg is None:
            break

        try:
            data = json.loads(msg)
            if data.get("type") == "END":
                # conversation = data.get("conversation", [])
                # client.conversation_history = conversation
                client.commit_audio_buffer()
            else:
                # other control messages
                pass
        except json.JSONDecodeError:
            # raw base64 audio chunks
            client.append_audio(msg)


# Multi-Avatar Management


# avatars_api.py
from flask import Blueprint, jsonify, request

avatars_bp = Blueprint("avatars", __name__)


@avatars_bp.route("/api/avatars", methods=["GET", "POST"])
def avatars_collection():
    global avatar_llms, avatar_rag_tools
    """
    GET  /api/avatars  -> list all avatars
    POST /api/avatars  -> create a new avatar
    """

    avatars = json.load(open(avatars_path, "r"))
    print("\nAvatars: ", avatars)

    if request.method == "GET":
        # Frontend expects: [{ id, name, systemPromptUrl, contextDocsUrl, sensorApiUrl }, ...]
        return jsonify(avatars), 200

    # POST
    data = request.get_json() or {}

    name = (data.get("name") or "").strip()
    system_prompt_url = data.get("systemPromptUrl") or ""
    context_docs_url = data.get("contextDocsUrl") or ""
    sensor_api_url = data.get("sensorApiUrl") or ""
    sensor_description = data.get("sensorDescription") or ""
    rag_languages = data.get("ragLanguages") or ""

    # Parse rag_languages: comma-separated string to list
    if rag_languages:
        rag_languages_list = [lang.strip() for lang in rag_languages.split(",") if lang.strip()]
    else:
        rag_languages_list = ["en", "de"]  # Default

    if not name:
        return jsonify({"error": "Avatar 'name' is required."}), 400

    print(
        "\n\n------------------------\nvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv\nRecieved Request to Create New Avatar."
    )

    # Make id a string so it matches React's select value and find() comparison
    if len(avatars) == 0:
        next_id = "0"
    else:
        max_id = max(int(a["id"]) for a in avatars)
        next_id = str(max_id + 1)

    os.makedirs(f"avatars_context/{next_id}", exist_ok=True)

    if system_prompt_url != "":
        fetch_system_prompt_from_gdoc(next_id, system_prompt_url)

    # Run this in a thread
    # Set up RAG index for avatar
    if context_docs_url != "":
        drive_folder_id = context_docs_url.split("/folders/")[1].split("?")[0]
        print("Building Index for Avatar: " + next_id)
        # threading.Thread(target=build_or_load_index, kwargs={"avatar_id": next_id, "drive_folder_id": drive_folder_id}).start()
        results = build_or_load_index(next_id, drive_folder_id)
    else:
        drive_folder_id = None

    avatar = {
        "id": next_id,
        "name": name,
        "systemPromptUrl": system_prompt_url,
        "contextDocsUrl": context_docs_url,
        "driveFolderId": drive_folder_id,
        "sensorApiUrl": sensor_api_url,
        "sensorDescription": sensor_description,
        "ragLanguages": rag_languages_list,
    }

    avatars.append(avatar)
    print("Avatars after modification: ", avatars)
    json.dump(avatars, open(avatars_path, "w"))
    avatar_llms, avatar_rag_tools, avatar_sensor_tools = generate_avatars_config()
    # Frontend expects the created avatar object back
    return jsonify(avatar), 201


@avatars_bp.route("/api/avatars/<avatar_id>", methods=["PUT"])
def avatar_detail(avatar_id):
    """
    PUT /api/avatars/<avatar_id> -> update an existing avatar
    """
    data = request.get_json() or {}
    avatars = json.load(open(avatars_path, "r"))
    print("Avatars: ", avatars)

    # Find avatar by string id
    avatar = next((a for a in avatars if a["id"] == avatar_id), None)
    if avatar is None:
        return jsonify({"error": "Avatar not found."}), 404

    # Only update fields present in request
    for field in ["name", "systemPromptUrl", "contextDocsUrl", "sensorApiUrl", "sensorDescription"]:
        if field in data and data[field] is not None:
            avatar[field] = data[field]

    # Handle ragLanguages separately (comma-separated string to list)
    if "ragLanguages" in data and data["ragLanguages"] is not None:
        rag_languages = data["ragLanguages"]
        if rag_languages:
            avatar["ragLanguages"] = [lang.strip() for lang in rag_languages.split(",") if lang.strip()]
        else:
            avatar["ragLanguages"] = ["en", "de"]  # Default

    print("Avatars after modification: ", avatars)
    json.dump(avatars, open(avatars_path, "w"))
    avatar_llms, avatar_rag_tools, avatar_sensor_tools = generate_avatars_config()
    return jsonify(avatar), 200


@avatars_bp.route("/api/avatars/<avatar_id>/llm-defaults", methods=["POST", "DELETE"])
def avatar_llm_defaults(avatar_id):
    """
    POST   /api/avatars/<avatar_id>/llm-defaults -> save Admin defaults for avatar
    DELETE /api/avatars/<avatar_id>/llm-defaults -> clear Admin defaults for avatar
    """
    avatars = json.load(open(avatars_path, "r"))
    avatar = next((a for a in avatars if a["id"] == avatar_id), None)
    if avatar is None:
        return jsonify({"error": "Avatar not found."}), 404

    if request.method == "DELETE":
        # Clear defaults
        avatar_name = avatar.get("name", avatar_id)
        if "llmDefaults" in avatar:
            del avatar["llmDefaults"]
            print(f"\n=== Cleared Admin defaults for avatar '{avatar_name}' (id: {avatar_id}) ===\n")
        json.dump(avatars, open(avatars_path, "w"))
        return jsonify(avatar), 200

    # POST - save defaults
    data = request.get_json() or {}

    llm_defaults = {
        "chat": {
            "provider": data.get("chatProvider"),
            "model": data.get("chatModel"),
            "temperature": data.get("temperature", 0.7),
            "top_k": data.get("topK", 40),
            "top_p": data.get("topP", 1.0)
        },
        "textQuery": {
            "provider": data.get("textQueryProvider"),
            "model": data.get("textQueryModel")
        },
        "sensor": {
            "provider": data.get("sensorProvider"),
            "model": data.get("sensorModel")
        }
    }

    # Remove None values
    for task in llm_defaults:
        llm_defaults[task] = {k: v for k, v in llm_defaults[task].items() if v is not None}

    avatar["llmDefaults"] = llm_defaults
    json.dump(avatars, open(avatars_path, "w"))
    print(f"\n=== Saved Admin defaults for avatar '{avatar.get('name', avatar_id)}' (id: {avatar_id}) ===")
    print(f"{llm_defaults}")
    print("=================================\n")
    return jsonify(avatar), 200


app.register_blueprint(avatars_bp)


# LLM Providers Management
llm_providers_bp = Blueprint("llm_providers", __name__)

NON_CHAT_KEYWORDS = [
    "embed", "whisper", "tts", "rerank",       # common across providers
    "realtime", "audio", "transcribe",          # OpenAI audio/speech models
    "image", "sora",                            # OpenAI image/video generation
    "search",                                   # OpenAI search-specific models
    "codex",                                    # OpenAI code completion (non-chat API)
    "moderation",                               # OpenAI content moderation
    "computer-use",                             # OpenAI computer-use models
]

def _fetch_provider_models(provider):
    """Fetch available models from a provider's /v1/models endpoint."""
    api_base = provider.get("api_base", "").rstrip("/")
    api_key_env = provider.get("api_key_env")
    api_key = os.getenv(api_key_env) if api_key_env else None

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    # Some providers (e.g. OpenAI) already include /v1 in their api_base
    if api_base.endswith("/v1"):
        url = f"{api_base}/models"
    else:
        url = f"{api_base}/v1/models"
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()

    data = resp.json()
    models = [m["id"] for m in data.get("data", [])]
    # Filter out non-chat models (embeddings, speech, rerankers)
    return [m for m in models if not any(kw in m.lower() for kw in NON_CHAT_KEYWORDS)]


@llm_providers_bp.route("/api/llm-providers", methods=["GET", "POST"])
def llm_providers_collection():
    """
    GET /api/llm-providers -> list all LLM providers
    POST /api/llm-providers -> create a new LLM provider
    """
    providers = json.load(open(LLM_PROVIDERS_PATH, "r"))

    if request.method == "GET":
        return jsonify(providers), 200

    # POST
    data = request.get_json() or {}

    provider_id = (data.get("id") or "").strip()
    name = (data.get("name") or "").strip()
    provider_key = (data.get("provider_key") or "custom").strip()
    api_base = data.get("api_base") or ""
    api_key = data.get("api_key") or ""
    models = data.get("models") or []

    if not name:
        return jsonify({"error": "Provider 'name' is required."}), 400

    if not provider_id:
        # Generate ID from name if not provided
        provider_id = name.lower().replace(" ", "-").replace("/", "-")

    # Check if ID already exists
    if any(p["id"] == provider_id for p in providers):
        return jsonify({"error": f"Provider with id '{provider_id}' already exists."}), 400

    if not models:
        return jsonify({"error": "At least one model is required."}), 400

    print(f"\n\n------------------------\nvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv\nReceived Request to Create New LLM Provider: {name}")

    # Generate env var name and write API key to .env if provided
    api_key_env = None
    if api_key:
        # Generate env var name: PROVIDER_ID_API_KEY (e.g., ANTHROPIC_API_KEY)
        api_key_env = f"{provider_id.upper().replace('-', '_')}_API_KEY"

        # Write to .env file
        env_path = ".env"
        try:
            # Read existing .env content
            env_content = ""
            if os.path.exists(env_path):
                with open(env_path, "r") as f:
                    env_content = f.read()

            # Check if env var already exists
            if f"{api_key_env}=" in env_content:
                # Update existing line
                lines = env_content.split('\n')
                lines = [line if not line.startswith(f"{api_key_env}=") else f"{api_key_env}={api_key}" for line in lines]
                env_content = '\n'.join(lines)
            else:
                # Append new line
                if env_content and not env_content.endswith('\n'):
                    env_content += '\n'
                env_content += f"{api_key_env}={api_key}\n"

            # Write back to .env
            with open(env_path, "w") as f:
                f.write(env_content)

            print(f"API key written to .env as {api_key_env}")

            # Reload environment variables
            load_dotenv(override=True)
        except Exception as e:
            print(f"Warning: Could not write to .env file: {e}")
            # Continue without storing the key
            api_key_env = None

    provider = {
        "id": provider_id,
        "name": name,
        "provider_key": provider_key,
        "api_base": api_base,
        "models": models if isinstance(models, list) else [m.strip() for m in models.split(",")],
    }

    # Only add api_key_env if a key was provided and successfully stored
    if api_key_env:
        provider["api_key_env"] = api_key_env

    providers.append(provider)
    print("LLM Providers after modification: ", providers)
    json.dump(providers, open(LLM_PROVIDERS_PATH, "w"))
    return jsonify(provider), 201


@llm_providers_bp.route("/api/llm-providers/<provider_id>", methods=["PUT", "DELETE"])
def llm_provider_detail(provider_id):
    """
    PUT /api/llm-providers/<provider_id> -> update an existing LLM provider
    DELETE /api/llm-providers/<provider_id> -> delete an LLM provider
    """
    providers = json.load(open(LLM_PROVIDERS_PATH, "r"))
    provider = next((p for p in providers if p["id"] == provider_id), None)

    if not provider:
        return jsonify({"error": "Provider not found."}), 404

    if request.method == "DELETE":
        providers = [p for p in providers if p["id"] != provider_id]
        json.dump(providers, open(LLM_PROVIDERS_PATH, "w"))
        return jsonify({"status": "success", "message": f"Provider {provider_id} deleted."}), 200

    # PUT
    data = request.get_json() or {}

    # Handle API key update
    if "api_key" in data and data["api_key"] is not None:
        api_key = data["api_key"]

        if api_key:
            # Generate env var name
            api_key_env = f"{provider_id.upper().replace('-', '_')}_API_KEY"

            # Write to .env file
            env_path = ".env"
            try:
                # Read existing .env content
                env_content = ""
                if os.path.exists(env_path):
                    with open(env_path, "r") as f:
                        env_content = f.read()

                # Check if env var already exists
                if f"{api_key_env}=" in env_content:
                    # Update existing line
                    lines = env_content.split('\n')
                    lines = [line if not line.startswith(f"{api_key_env}=") else f"{api_key_env}={api_key}" for line in lines]
                    env_content = '\n'.join(lines)
                else:
                    # Append new line
                    if env_content and not env_content.endswith('\n'):
                        env_content += '\n'
                    env_content += f"{api_key_env}={api_key}\n"

                # Write back to .env
                with open(env_path, "w") as f:
                    f.write(env_content)

                print(f"API key updated in .env as {api_key_env}")

                # Reload environment variables
                load_dotenv(override=True)

                # Update provider with env var name
                provider["api_key_env"] = api_key_env
            except Exception as e:
                print(f"Warning: Could not write to .env file: {e}")
        else:
            # If api_key is empty string, remove the env var reference
            if "api_key_env" in provider:
                del provider["api_key_env"]

    # Update other fields (except api_key which we handle above)
    for field in ["name", "provider_key", "api_base", "models"]:
        if field in data and data[field] is not None:
            provider[field] = data[field]

    print("LLM Providers after modification: ", providers)
    json.dump(providers, open(LLM_PROVIDERS_PATH, "w"))
    return jsonify(provider), 200


@llm_providers_bp.route("/api/llm-providers/<provider_id>/refresh-models", methods=["POST"])
def refresh_provider_models(provider_id):
    """
    POST /api/llm-providers/<provider_id>/refresh-models
    Fetches the live model list from the provider's /v1/models endpoint
    and persists it to llm_providers.json.
    """
    providers = json.load(open(LLM_PROVIDERS_PATH, "r"))
    provider = next((p for p in providers if p["id"] == provider_id), None)

    if not provider:
        return jsonify({"error": "Provider not found."}), 404

    try:
        models = _fetch_provider_models(provider)
    except Exception as e:
        return jsonify({"error": f"Failed to fetch models from provider: {str(e)}"}), 502

    global _models_last_refreshed
    provider["models"] = models
    json.dump(providers, open(LLM_PROVIDERS_PATH, "w"), indent=2)
    _models_last_refreshed = datetime.now().isoformat(timespec="seconds")
    print(f"Refreshed models for provider '{provider_id}': {models}")
    return jsonify({"models": models}), 200


@llm_providers_bp.route("/api/llm-options", methods=["GET"])
def llm_options():
    """
    GET /api/llm-options -> returns providers in dropdown-friendly format
    Format: { "options": { "provider_id": { "name": "...", "models": [...] } }, "last_refreshed": "..." }
    """
    providers = json.load(open(LLM_PROVIDERS_PATH, "r"))
    options = {}
    for p in providers:
        if p.get("hidden"):
            continue
        options[p["id"]] = {
            "name": p["name"],
            "models": p["models"],
        }
    return jsonify({"options": options, "last_refreshed": _models_last_refreshed}), 200


app.register_blueprint(llm_providers_bp)


import re

ANSI_RE = re.compile(r'\x1b\[[0-9;]*[A-Za-z]')
FLASK_WARN = 'WARNING: This is a development server. Do not use it in a production deployment. Use a production WSGI server instead.'


@app.route("/api/backend-log", methods=["GET"])
def backend_log():
    log_path = os.path.expanduser("~/backend_log.0")
    try:
        with open(log_path, "r", errors="replace") as f:
            lines = f.readlines()
        # Keep last 4000 lines
        lines = lines[-4000:]
        # Strip ANSI escape codes for browser display
        lines = [ANSI_RE.sub("", line) for line in lines]
        # Filter out the Flask dev server warning
        lines = [line for line in lines if FLASK_WARN not in line]
        return jsonify({"log": "".join(lines)})
    except FileNotFoundError:
        return jsonify({"error": "Log file not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _auto_refresh_models():
    """Background thread: refresh all provider model lists every 24 hours."""
    import time
    global _models_last_refreshed
    REFRESH_INTERVAL = 24 * 60 * 60  # seconds

    while True:
        try:
            providers = json.load(open(LLM_PROVIDERS_PATH, "r"))
            for provider in providers:
                if provider.get("hidden"):
                    continue
                try:
                    models = _fetch_provider_models(provider)
                    provider["models"] = models
                    print(f"[model refresh] {provider['id']}: {len(models)} models")
                except Exception as e:
                    print(f"[model refresh] {provider['id']}: failed — {e}")
            json.dump(providers, open(LLM_PROVIDERS_PATH, "w"), indent=2)
            _models_last_refreshed = datetime.now().isoformat(timespec="seconds")
        except Exception as e:
            print(f"[model refresh] Could not read providers file: {e}")

        time.sleep(REFRESH_INTERVAL)


threading.Thread(target=_auto_refresh_models, daemon=True).start()


# ═══════════════════════════════════════════════════════════
# Voice Avatar Lab — Agora Conversational AI integration
# ═══════════════════════════════════════════════════════════
import uuid as _uuid
import base64 as _base64

voice_bp = Blueprint("voice", __name__)

AGORA_CONV_AI_BASE = "https://api.agora.io/api/conversational-ai-agent/v2/projects"


def _agora_auth_headers():
    creds = _base64.b64encode(f"{AGORA_CUSTOMER_ID}:{AGORA_CUSTOMER_SECRET}".encode()).decode()
    return {"Authorization": f"Basic {creds}", "Content-Type": "application/json"}


@voice_bp.route("/api/voice/token", methods=["GET"])
def get_voice_token():
    """Return Agora App ID and RTC token for the client to join a channel."""
    channel = request.args.get("channel", "avatar-lab")
    uid = int(request.args.get("uid", 0))
    # Token generation requires agora-token-builder + AGORA_APP_CERTIFICATE.
    # In dev (no certificate), pass token=None — Agora allows this in test mode.
    # TODO: install agora-token-builder and generate a real token when certificate is set.
    app_certificate = os.getenv("AGORA_APP_CERTIFICATE", "")
    token = None
    if app_certificate:
        try:
            import time as _time
            from agora_token_builder import RtcTokenBuilder
            from agora_token_builder.RtcTokenBuilder import Role_Publisher
            token = RtcTokenBuilder.buildTokenWithUid(
                AGORA_APP_ID, app_certificate,
                channel, uid, Role_Publisher,
                int(_time.time()) + 3600
            )
        except ImportError:
            print("[Voice] agora-token-builder not installed — using null token")

    return jsonify({"appId": AGORA_APP_ID, "channel": channel, "uid": uid, "token": token})


@voice_bp.route("/api/voice/agent/start", methods=["POST"])
def start_voice_agent():
    """Start an Agora Conversational AI agent for the given avatar and channel."""
    data = request.get_json() or {}
    avatar_id = str(data.get("avatarId", "0"))
    channel = data.get("channel", "avatar-lab")
    user_uid = data.get("userUid", 0)

    if avatar_id not in avatar_llms:
        return jsonify({"error": f"Unknown avatar: {avatar_id}"}), 404

    # Load admin defaults to determine TTS voice etc.
    avatars = json.load(open(avatars_path, "r"))
    avatar = next((a for a in avatars if a["id"] == avatar_id), None)

    # Use avatar system prompt — trim sensor/function instructions (handled separately)
    system_prompt = avatar_llms[avatar_id].system_prompt
    cutoff = system_prompt.find("You also have access to sensory data")
    if cutoff > 0:
        system_prompt = system_prompt[:cutoff].strip()

    # Generate RTC token for the agent's own UID so it can join the channel
    agent_uid = 999
    agent_token = ""
    app_certificate = os.getenv("AGORA_APP_CERTIFICATE", "")
    if app_certificate:
        try:
            import time as _time
            from agora_token_builder import RtcTokenBuilder
            from agora_token_builder.RtcTokenBuilder import Role_Publisher
            agent_token = RtcTokenBuilder.buildTokenWithUid(
                AGORA_APP_ID, app_certificate,
                channel, agent_uid, Role_Publisher,
                int(_time.time()) + 3600
            )
        except ImportError:
            print("[Voice] agora-token-builder not installed — agent token will be empty")

    agent_payload = {
        "name": f"lahn-avatar-{avatar_id}-{channel}",
        "properties": {
            "channel": channel,
            "token": agent_token,
            "agent_rtc_uid": str(agent_uid),
            "remote_rtc_uids": [str(user_uid)] if user_uid else ["*"],
            "idle_timeout": 120,
            "asr": {
                "vendor": "deepgram",
                "language": "en-US",
                "params": {
                    "api_key": os.getenv("DEEPGRAM_API_KEY", ""),
                }
            },
            "llm": {
                "url": f"{BACKEND_PUBLIC_URL}/api/voice/chat-completions?avatar={avatar_id}",
                "vendor": "custom",
                "style": "openai",
                "params": {"model": "avatar"},
                "system_messages": [{"role": "system", "content": system_prompt}],
                "failure_message": "I need a moment. Please hold on.",
                "max_history": 10,
                "timeout_ms": 30000,
            },
            "tts": {
                "vendor": "cartesia",
                "params": {
                    "api_key": os.getenv("CARTESIA_API_KEY", ""),
                    "model_id": "sonic-2",
                    "voice_id": "f114a467-c40a-4db8-964d-aaba89cd08fa",
                }
            }
        }
    }

    print(f"[Voice] Starting agent for avatar {avatar_id} on channel {channel}")
    resp = requests.post(
        f"{AGORA_CONV_AI_BASE}/{AGORA_APP_ID}/join",
        headers=_agora_auth_headers(),
        json=agent_payload,
        timeout=15,
    )

    if resp.status_code >= 400:
        print(f"[Voice] Agora agent start failed: {resp.status_code} — {resp.text}")
        try:
            return jsonify({"error": resp.json()}), resp.status_code
        except Exception:
            return jsonify({"error": resp.text}), resp.status_code

    agent_data = resp.json()
    agent_id = agent_data.get("agent_id") or agent_data.get("id")
    print(f"[Voice] Agent started: {agent_id}")
    return jsonify({"agentId": agent_id, "channel": channel})


@voice_bp.route("/api/voice/agent/stop", methods=["POST"])
def stop_voice_agent():
    """Stop a running Agora Conversational AI agent."""
    data = request.get_json() or {}
    agent_id = data.get("agentId")
    if not agent_id:
        return jsonify({"error": "agentId required"}), 400

    resp = requests.post(
        f"{AGORA_CONV_AI_BASE}/{AGORA_APP_ID}/agents/{agent_id}/leave",
        headers=_agora_auth_headers(),
        timeout=15,
    )
    print(f"[Voice] Agent stopped: {agent_id} (status {resp.status_code})")
    return jsonify({"status": "stopped"})


@voice_bp.route("/api/voice/chat-completions", methods=["POST"])
def voice_chat_completions():
    """
    OpenAI-compatible SSE endpoint called by the Agora Conversational AI agent.
    Runs the full RAG + sensor + LLM pipeline and streams back the response.
    """
    from flask import stream_with_context

    avatar_id = str(request.args.get("avatar", "0"))
    data = request.get_json() or {}
    messages = data.get("messages", [])

    if avatar_id not in avatar_llms:
        return jsonify({"error": f"Unknown avatar: {avatar_id}"}), 404

    # Agora includes the system prompt we configured — skip it, use ours from avatar config
    conversation_msgs = [m for m in messages if m["role"] != "system"]
    if not conversation_msgs:
        return jsonify({"error": "No conversation messages"}), 400

    print(f"\n[Voice] Chat completion — avatar={avatar_id}, turns={len(conversation_msgs)}")

    # Resolve LLM parameters from admin defaults (no user params for voice)
    resolved, _ = resolve_llm_defaults(avatar_id)
    chat_provider, chat_model = fallback_model(resolved["chat_provider"], resolved["chat_model"])
    text_query_provider_raw, text_query_model_raw = fallback_model(resolved["text_query_provider"], resolved["text_query_model"])
    temperature = resolved["temperature"]
    top_k = resolved["top_k"]
    top_p = resolved["top_p"]
    text_query_provider = text_query_provider_raw
    text_query_model = text_query_model_raw
    sensor_provider, sensor_model = fallback_model(resolved["sensor_provider"], resolved["sensor_model"])

    system_prompt = avatar_llms[avatar_id].system_prompt
    providers = json.load(open(LLM_PROVIDERS_PATH, "r"))

    # Build chat history with system prompt
    chat_history = [{"role": "system", "content": system_prompt}]
    chat_history += [
        {"role": "user" if m["role"] == "user" else "assistant", "content": m["content"]}
        for m in conversation_msgs
    ]

    # Conversation in the format RAG helpers expect
    conversation_for_rag = [
        {"sender": "user" if m["role"] == "user" else "avatar", "text": m["content"]}
        for m in conversation_msgs
    ]

    # RAG context injection
    # Voice RAG: skip LLM keyword generation — use spaCy/langid extraction directly on user utterance.
    # This avoids a full LLM round-trip that would exceed Agora's response timeout.
    # Trade-off: not context-aware across turns (only current utterance). See design notes.
    try:
        if avatar_rag_tools.get(avatar_id):
            user_query = conversation_msgs[-1]["content"]
            rag_languages = avatar_rag_tools[avatar_id][4] if len(avatar_rag_tools[avatar_id]) > 4 else ['en', 'de']
            keywords_by_lang = extract_keywords_multilingual(user_query, rag_languages)
            rag_context = RAG(avatar_rag_tools[avatar_id], keywords_by_lang=keywords_by_lang)
            if rag_context:
                chat_history[-1]["content"] += f" <End of User message>. <<Context from knowledge base: {rag_context}>>"
                print("[Voice] RAG context injected (direct keyword extraction)")
    except Exception as e:
        print(f"[Voice] RAG failed (continuing without context): {e}")

    # Sensor tool prompt injection + always-fetch snapshot
    sensor_config = avatar_sensor_tools.get(avatar_id)
    if sensor_config:
        sensor_summary = _fetch_sensor_summary(avatar_id)
        if sensor_summary:
            chat_history[0]["content"] += f"\n\nCURRENT SENSOR SNAPSHOT:\n{sensor_summary}\nUse this for simple current-reading questions. Call analyze_sensor_data() only for trend analysis or questions requiring historical data."
        else:
            chat_history[0]["content"] += (
                "\n\nIf the user asks about live sensor data (temperature, pH, water quality etc.), "
                "say you'll look it up and call: analyze_sensor_data(user_query=\"...\"). "
                "Otherwise respond normally."
            )

    # Main LLM call
    llm = create_llm_instance(chat_provider, chat_model, system_prompt,
                              temperature=temperature, top_k=top_k, top_p=top_p,
                              task_name="voice_chat", providers=providers)
    response_text = llm.complete(chat_history).text

    # Handle inline sensor call if model requested it
    response_text, sensor_handled = handle_sensor_tool_call(
        response_text, avatar_id, sensor_provider, sensor_model, llm, chat_history, providers=providers)
    if sensor_handled:
        print("[Voice] Sensor analysis complete")

    print(f"[Voice] Response: {response_text[:120]}...")

    # Stream back as SSE (single chunk — Agora accepts this)
    response_id = str(_uuid.uuid4())

    def generate():
        chunk = {
            "id": response_id,
            "object": "chat.completion.chunk",
            "choices": [{"index": 0, "delta": {"role": "assistant", "content": response_text}, "finish_reason": None}]
        }
        yield f"data: {json.dumps(chunk)}\n\n"
        done_chunk = {
            "id": response_id,
            "object": "chat.completion.chunk",
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]
        }
        yield f"data: {json.dumps(done_chunk)}\n\n"
        yield "data: [DONE]\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


app.register_blueprint(voice_bp)


if __name__ == "__main__":
    app.run(debug=False, use_reloader=False, port=5001)
