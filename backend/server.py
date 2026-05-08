import asyncio
import io
import os
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

UPLOAD_DIR = "data/uploaded_experiences"
os.makedirs(UPLOAD_DIR, exist_ok=True)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GWDG_API_KEY = os.getenv("GWDG_API_KEY")
GWDG_API_BASE = os.getenv("GWDG_API_BASE")
LLM_PROVIDERS_PATH = "llm_providers.json"


def _build_model_checks(provider_keys_filter=None):
    """Build list of model checks, optionally filtered by provider keys."""
    providers = json.load(open(LLM_PROVIDERS_PATH, "r"))

    model_checks = []
    for provider in providers:
        provider_key = provider["provider_key"]

        # Filter by provider keys if specified
        if provider_keys_filter and provider_key not in provider_keys_filter:
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

        # Ollama models can be slower, use longer timeout
        health_check_timeout = 25 if provider_key == "ollama" else 15

        for model_name in provider.get("models", []):
            model_checks.append({
                "model_name": model_name,
                "provider_key": provider_key,
                "api_key": api_key,
                "api_base": api_base,
                "timeout": health_check_timeout
            })

    return model_checks


def _check_model(check_data):
    """Check a single model's health."""
    from utils.llm_tooling import LLM

    model_name = check_data["model_name"]
    provider_key = check_data["provider_key"]
    api_key = check_data["api_key"]
    api_base = check_data["api_base"]
    timeout = check_data["timeout"]

    try:
        llm_params = {
            'provider': provider_key,
            'system_prompt': "You are a helpful assistant.",
            'timeout': timeout
        }

        # Set provider-specific parameters
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
            # For custom providers, try to use gwdg-style interface
            llm_params['provider'] = 'gwdg'
            llm_params['gwdg_model'] = model_name
            if api_key:
                llm_params['gwdg_api_key'] = api_key
            if api_base:
                llm_params['gwdg_api_base'] = api_base

        temp_llm = LLM(**llm_params)
        temp_llm.complete(prompt="ping")
        print(f"Health check: {model_name} ({provider_key}) -> online")
        return (model_name, "online")
    except (RuntimeError, requests.exceptions.RequestException) as e:
        print(f"Health check: {model_name} ({provider_key}) -> offline ({type(e).__name__}: {str(e)[:100]})")
        return (model_name, "offline")
    except Exception as e:
        print(f"Health check: {model_name} ({provider_key}) -> offline ({type(e).__name__}: {str(e)[:100]})")
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
    # Fast providers: openai, gwdg
    model_checks = _build_model_checks(provider_keys_filter=["openai", "gwdg"])
    results = _run_health_checks(model_checks, max_workers=10)
    print(f"Fast health check results: {results}")
    return jsonify(results)


@app.route("/api/health/llm/slow", methods=["GET"])
def llm_health_slow():
    """Health check for slow/rate-limited providers (Ollama) - limited parallelism."""
    model_checks = _build_model_checks(provider_keys_filter=["ollama"])
    results = _run_health_checks(model_checks, max_workers=2)
    print(f"Slow health check results: {results}")
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

    # Get request params (may be None if not specified)
    req_provider = data.get("llmProvider")
    req_model = data.get("llmModel")
    req_text_query_model = data.get("textQueryModel")
    req_sensor_model = data.get("sensorModel")
    req_temperature = data.get("temperature")
    req_top_k = data.get("topK")
    req_top_p = data.get("topP")

    # Extract admin defaults for each task
    chat_defaults = admin_defaults.get("chat", {})
    text_query_defaults = admin_defaults.get("textQuery", {})
    sensor_defaults = admin_defaults.get("sensor", {})

    # Track sources for logging - compare request params against admin defaults
    sources = {}

    # Resolve Provider: check if request matches admin default
    if req_provider:
        user_llm_provider = req_provider
        if chat_defaults.get("provider") == req_provider:
            sources["provider"] = "Admin defaults"
        else:
            sources["provider"] = "user"
    elif chat_defaults.get("provider"):
        user_llm_provider = chat_defaults["provider"]
        sources["provider"] = "Admin defaults"
    else:
        user_llm_provider = DEFAULT_CHAT_PROVIDER
        sources["provider"] = "global defaults"

    # Resolve Chat Model
    if req_model:
        user_llm_model = req_model
        if chat_defaults.get("model") == req_model:
            sources["chat_model"] = "Admin defaults"
        else:
            sources["chat_model"] = "user"
    elif chat_defaults.get("model"):
        user_llm_model = chat_defaults["model"]
        sources["chat_model"] = "Admin defaults"
    else:
        user_llm_model = DEFAULT_CHAT_MODEL
        sources["chat_model"] = "global defaults"

    # Resolve Temperature
    if req_temperature is not None:
        temperature = req_temperature
        if chat_defaults.get("temperature") == req_temperature:
            sources["temperature"] = "Admin defaults"
        else:
            sources["temperature"] = "user"
    elif chat_defaults.get("temperature") is not None:
        temperature = chat_defaults["temperature"]
        sources["temperature"] = "Admin defaults"
    else:
        temperature = 0.7
        sources["temperature"] = "global defaults"

    # Resolve Top K
    if req_top_k is not None:
        top_k = req_top_k
        if chat_defaults.get("top_k") == req_top_k:
            sources["top_k"] = "Admin defaults"
        else:
            sources["top_k"] = "user"
    elif chat_defaults.get("top_k") is not None:
        top_k = chat_defaults["top_k"]
        sources["top_k"] = "Admin defaults"
    else:
        top_k = 40
        sources["top_k"] = "global defaults"

    # Resolve Top P
    if req_top_p is not None:
        top_p = req_top_p
        if chat_defaults.get("top_p") == req_top_p:
            sources["top_p"] = "Admin defaults"
        else:
            sources["top_p"] = "user"
    elif chat_defaults.get("top_p") is not None:
        top_p = chat_defaults["top_p"]
        sources["top_p"] = "Admin defaults"
    else:
        top_p = 1.0
        sources["top_p"] = "global defaults"

    # Resolve Text Query LLM config
    if req_text_query_model:
        text_query_model = req_text_query_model
        text_query_provider = user_llm_provider  # Use same provider as chat
        if text_query_defaults.get("model") == req_text_query_model:
            sources["text_query_model"] = "Admin defaults"
        else:
            sources["text_query_model"] = "user"
    elif text_query_defaults.get("model"):
        text_query_model = text_query_defaults["model"]
        text_query_provider = text_query_defaults.get("provider", DEFAULT_TEXT_QUERY_PROVIDER)
        sources["text_query_model"] = "Admin defaults"
    else:
        text_query_model = DEFAULT_TEXT_QUERY_MODEL
        text_query_provider = DEFAULT_TEXT_QUERY_PROVIDER
        sources["text_query_model"] = "global defaults"

    # Resolve Sensor LLM config
    if req_sensor_model:
        sensor_model = req_sensor_model
        sensor_provider = user_llm_provider  # Use same provider as chat
        if sensor_defaults.get("model") == req_sensor_model:
            sources["sensor_model"] = "Admin defaults"
        else:
            sources["sensor_model"] = "user"
    elif sensor_defaults.get("model"):
        sensor_model = sensor_defaults["model"]
        sensor_provider = sensor_defaults.get("provider", DEFAULT_SENSOR_PROVIDER)
        sources["sensor_model"] = "Admin defaults"
    else:
        sensor_model = DEFAULT_SENSOR_MODEL
        sensor_provider = DEFAULT_SENSOR_PROVIDER
        sources["sensor_model"] = "global defaults"

    # Log resolved parameters with sources
    print("\n=== LLM Parameters (resolved) ===")
    print(f"Provider: {user_llm_provider} (from: {sources['provider']})")
    print(f"Chat Model: {user_llm_model} (from: {sources['chat_model']})")
    print(f"Temperature: {temperature} (from: {sources['temperature']})")
    print(f"Top K: {top_k} (from: {sources['top_k']})")
    print(f"Top P: {top_p} (from: {sources['top_p']})")
    print(f"Text Query Model: {text_query_model} (from: {sources['text_query_model']}, provider: {text_query_provider})")
    print(f"Sensor Model: {sensor_model} (from: {sources['sensor_model']}, provider: {sensor_provider})")
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

    # === Load provider config early (needed for all LLM instantiations) ===
    providers = json.load(open(LLM_PROVIDERS_PATH, "r"))

    # Helper function to create LLM instance for any task
    def create_llm_for_task(provider_id, model, system_prompt, temperature=0.7, top_k=40, top_p=1.0, task_name="unknown"):
        """Create an LLM instance for a specific task."""
        provider = next((p for p in providers if p["id"] == provider_id), None)
        if not provider:
            raise ValueError(f"Unknown LLM provider: {provider_id}")

        provider_key = provider["provider_key"]
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

        # Log parameters being sent to model
        print(f"Creating LLM for {task_name}: provider={provider_id}, model={model}, temp={temperature}, top_k={top_k}, top_p={top_p}")

        # Build LLM parameters based on provider type
        if provider_key == 'openai':
            llm_params = {
                'provider': 'openai',
                'openai_model': model,
                'system_prompt': system_prompt,
                'openai_api_key': api_key,
                'temperature': temperature,
                'top_k': top_k,
                'top_p': top_p
            }
            if api_base:
                llm_params['openai_api_base'] = api_base
            return LLM(**llm_params)
        elif provider_key == 'ollama':
            llm_params = {
                'provider': 'ollama',
                'ollama_model': model,
                'system_prompt': system_prompt,
                'temperature': temperature,
                'top_k': top_k,
                'top_p': top_p
            }
            if api_key:
                llm_params['ollama_api_key'] = api_key
            if api_base:
                llm_params['ollama_api_base'] = api_base
            return LLM(**llm_params)
        else:
            # For GWDG and custom providers (use GWDG-style interface)
            llm_params = {
                'provider': 'gwdg',
                'gwdg_model': model,
                'system_prompt': system_prompt,
                'temperature': temperature,
                'top_k': top_k,
                'top_p': top_p
            }
            if api_key:
                llm_params['gwdg_api_key'] = api_key
            if api_base:
                llm_params['gwdg_api_base'] = api_base
            return LLM(**llm_params)

    # === Create task-specific LLMs ===
    # Text query LLM for keyword generation
    text_query_llm = create_llm_for_task(
        text_query_provider,
        text_query_model,
        TEXT_QUERY_SYSTEM_PROMPT,
        task_name="text_query"
    )

    # === RAG Context Injection ===
    if avatar_rag_tools[avatar_id] != [None, None, None, None, ['en', 'de']]:
        print("Obtaining information for the LLM...")

        # Get RAG languages for this avatar
        rag_languages = avatar_rag_tools[avatar_id][4] if len(avatar_rag_tools[avatar_id]) > 4 else ['en', 'de']

        # Analyze conversation context and generate keywords for multilingual text-index search
        keywords_by_lang = generate_context_aware_keywords_for_multilingual_text_index_search(
            text_query_llm, conversation, rag_languages
        )

        context = RAG(avatar_rag_tools[avatar_id], None, keywords_by_lang=keywords_by_lang)

        total_context = context
        chat_history[-1]["content"] += (
            " <End of User message>.        <<IMPORTANT: If the user explicitly asked you to 'search the web', 'look up on the internet', or requested information from the web, you MUST call web_search(query=\"their search query\") instead of using this RAG data. Output ONLY the function call line. Otherwise, the following info is a RAG injection to provide you with helpful context. The user did not send this: Here is relevant information (Sometimes the text-retrieval has relevant information that the vector-retrieval doesn't, or vice versa. Look through each comprehensively, to extract the information you need. Even if the Vector-retrieval says there's no information available, still scrutinize the Text-retrieval results to fetch relevant info (What language was the user's last message in? Make sure to respond in the same language.) This instruction is in English, but your response should be in whatever language the user messaged you in:>>  "
            + total_context
        )

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

    messages_to_send = chat_history
    # print("\n\nMessages to send: ", messages_to_send)

    # === Create chat LLM for main conversation ===
    llm = create_llm_for_task(user_llm_provider, user_llm_model, system_prompt_, temperature=temperature, top_k=top_k, top_p=top_p, task_name="chat")

    # Try completion with fail-fast fallback to OpenAI if using defaults
    using_defaults = sources["provider"] != "user" and sources["chat_model"] != "user"
    try:
        chat_completion = llm.complete(messages_to_send)
        response = chat_completion.text
    except (RuntimeError, requests.exceptions.RequestException) as e:
        # If we're using defaults and GWDG fails, retry with OpenAI
        if using_defaults and user_llm_provider == 'gwdg':
            print(f"GWDG failed with error: {e}")
            print("Retrying with OpenAI fallback...")
            llm = create_llm_for_task('openai', 'gpt-4o-mini', system_prompt_, task_name="chat_fallback")
            chat_completion = llm.complete(messages_to_send)
            response = chat_completion.text
        else:
            # Re-raise if user explicitly selected this provider
            raise

    print("\nAvatar response: ", response)

    if "analyze_sensor_data" in response:
        print("Analyzing sensor data...")
        response = response[response.find('user_query="') + 12 :]
        query = response[: response.find('")')]
        print("Query: ", query)

        # Get the sensor config for this avatar and create tool on-the-fly
        sensor_config = avatar_sensor_tools.get(avatar_id)

        if sensor_config:
            # Create sensor LLM and tool on-the-fly
            sensor_llm = create_llm_for_task(
                sensor_provider,
                sensor_model,
                SENSOR_SYSTEM_PROMPT,
                task_name="sensor"
            )
            sensor_tool = SensorsTool(
                sensor_llm,
                sensor_url=sensor_config['sensor_url'],
                sensor_description=sensor_config.get('sensor_description')
            )

            analysis = str(sensor_tool(query))
            print("Analysis: ", analysis)
            results = (
                "\nHere is the output of analyze_sensor_data(): "
                + analysis
                + " Respond to the user accordingly. Do not provide any subjective Lahn-specific evaluation of this data, just focus on the quantitative result. And do not return a function call. What language was the user's last message in? Make sure to respond in the same language."
            )

            # if len(results)>0:
            print(
                "Passing analysis results to LLM.."
            )  #: ', chat_history+[{'role':'system', 'content':results}])
            chat_completion_2 = llm.complete(
                chat_history + [{"role": "assistant", "content": results}],
            )

            response_2 = chat_completion_2.text
            if "analyze_sensor_data" in response_2:
                print("Duplicate function call for some reason")
                response_2 = analysis

            response_2 = response_2.replace("*", "")

            print("Avatar response after getting sensor data:", response_2)

            return jsonify({"reply": response_2})
        else:
            # Avatar has no sensor tool configured
            print(f"No sensor tool available for avatar {avatar_id}")
            results = (
                "\nNote: Sensor data is not available for this avatar. "
                "Please ask about other aspects of the Lahn or choose a different avatar."
            )
            chat_completion_2 = llm.complete(
                chat_history + [{"role": "assistant", "content": results}],
            )
            response_2 = chat_completion_2.text.replace("*", "")
            return jsonify({"reply": response_2})

    elif "web_search" in response:
        print("Performing web search...")
        # Extract query from response: [web_search(query="...")]
        if 'query="' in response:
            query_start = response.find('query="') + 7
            query_end = response.find('"', query_start)
            query = response[query_start:query_end]
        else:
            query = ""

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


@llm_providers_bp.route("/api/llm-options", methods=["GET"])
def llm_options():
    """
    GET /api/llm-options -> returns providers in dropdown-friendly format
    Format: { "provider_id": { "name": "Display Name", "models": [...] }, ... }
    """
    providers = json.load(open(LLM_PROVIDERS_PATH, "r"))
    options = {}
    for p in providers:
        options[p["id"]] = {
            "name": p["name"],
            "models": p["models"],
        }
    return jsonify(options), 200


app.register_blueprint(llm_providers_bp)


if __name__ == "__main__":
    app.run(debug=False, use_reloader=False, port=5001)
