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
    avatars_path,
    generate_avatars_config,
    llm_choice,
    sensor_query_tool,
    text_query_llm,
)
from utils.processing_pipelines import OpenAIRealtimeClient
from utils.utils import (
    RAG,
    build_or_load_index,
    fetch_system_prompt_from_gdoc,
    fetch_text_index_query,
    format_history_as_string,
    pcm_to_wav_bytes,
    prepare_query_engines,
    transcribe_audio,
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


@app.route("/api/health/llm", methods=["GET"])
def llm_health():
    """
    Checks the health of the LLM models by attempting a lightweight completion.
    Returns a map of model names to their status ('online' or 'offline').
    """
    gwdg_models_to_check = ["gwdg/gemma-3-27b-it", "gwdg/medgemma-27b-it", "ollama/gemma3", "mistral-large-instruct"]
    openai_models_to_check = ["gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"]
    
    health_status = {}
    health_check_timeout = 5 # seconds for a health check ping

    # Check OpenAI models
    for model_name in openai_models_to_check:
        try:
            temp_llm = LLM(
                provider='openai',
                openai_model=model_name,
                system_prompt="You are a helpful assistant.",
                openai_api_key=OPENAI_API_KEY,
                timeout=health_check_timeout
            )
            temp_llm.complete(prompt="ping")
            health_status[model_name] = "online"
        except (RuntimeError, requests.exceptions.RequestException) as e:
            print(f"OpenAI model {model_name} offline: {e}")
            health_status[model_name] = "offline"
        except Exception as e:
            print(f"OpenAI model {model_name} unknown error: {e}")
            health_status[model_name] = "offline" # Catch all other errors

    # Check GWDG models
    for model_name in gwdg_models_to_check:
        if not GWDG_API_BASE or not GWDG_API_KEY:
            health_status[model_name] = "offline"
            continue

        try:
            gwdg_params = {
                'provider': 'gwdg',
                'gwdg_model': model_name,
                'system_prompt': "You are a helpful assistant.",
                'timeout': health_check_timeout
            }
            if GWDG_API_KEY is not None:
                gwdg_params['gwdg_api_key'] = GWDG_API_KEY
            if GWDG_API_BASE is not None:
                gwdg_params['gwdg_api_base'] = GWDG_API_BASE
            
            temp_llm = LLM(**gwdg_params)
            temp_llm.complete(prompt="ping")
            health_status[model_name] = "online"
        except (RuntimeError, requests.exceptions.RequestException) as e:
            print(f"GWDG model {model_name} offline: {e}")
            health_status[model_name] = "offline"
        except Exception as e:
            print(f"GWDG model {model_name} unknown error: {e}")
            health_status[model_name] = "offline" # Catch all other errors

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
        llm, _ = generate_avatars_config(specific_avatar_id=avatar_id)
        if llm:
            avatar_llms[avatar_id] = llm
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
    print(
        "\n\n------------------------\nvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv\nChat request received."
    )
    avatar_id = request.args.get("avatar", "0")
    data = request.get_json()

    user_llm_provider = data.get("llmProvider")
    user_llm_model = data.get("llmModel")

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

    if avatar_rag_tools[avatar_id] != [None, None, None, None]:
        print("Obtaining information for the LLM...")
        # query = 'Provide context needed to address the most recent message in this conversation. Your job is not to predict what any party will say, but to provide information from the context, which is relevant for them to make their decision. That is where your job stops. : '+ format_history_as_string(conversation)
        text_index_query = fetch_text_index_query(text_query_llm, conversation)
        context = RAG(
            avatar_rag_tools[avatar_id], text_index_query, translated=True
        )  # query, text_index_query = text_index_query)

        total_context = context
        # messages_to_send = chat_history+[{'role':'assistant', 'content':'Here is relevant information about the Lahn (Sometimes the text-retrieval has relevant information that the vector-retrieval doesn\'t, or vice versa. Look through each comprehensively, to extract the information you need. Even if the Vector-retrieval says there\'s no information available, still scrutinize the Text-retrieval results to fetch relevant info (What language was the user\'s last message in? Make sure to respond in the same language.): '+total_context + ' . You can call analyze_sensor_data() if environmental data readings are relevant to the user\'s query.'}]
        chat_history[-1]["content"] += (
            "The following info is a RAG injection to provide you with helpful context. The user did not send this: Here is relevant information (Sometimes the text-retrieval has relevant information that the vector-retrieval doesn't, or vice versa. Look through each comprehensively, to extract the information you need. Even if the Vector-retrieval says there's no information available, still scrutinize the Text-retrieval results to fetch relevant info (What language was the user's last message in? Make sure to respond in the same language.): "
            + total_context
            + " . You can call analyze_sensor_data() if environmental data readings are relevant to the user's query."
        )

    messages_to_send = chat_history
    print("\n\nMessages to send: ", messages_to_send)

    # --- Instantiate LLM on-the-fly based on user's choice ---
    if user_llm_provider == 'openai':
        llm = LLM(
            provider='openai',
            openai_model=user_llm_model,
            system_prompt=system_prompt_,
            openai_api_key=OPENAI_API_KEY
        )
    elif user_llm_provider == 'gwdg':
        gwdg_params = {
            'provider': 'gwdg',
            'gwdg_model': user_llm_model,
            'system_prompt': system_prompt_
        }
        if GWDG_API_KEY is not None:
            gwdg_params['gwdg_api_key'] = GWDG_API_KEY
        if GWDG_API_BASE is not None:
            gwdg_params['gwdg_api_base'] = GWDG_API_BASE
        
        llm = LLM(**gwdg_params)
    else:
        return jsonify({"error": f"Unknown LLM provider: {user_llm_provider}"}), 400

    chat_completion = llm.complete(
        messages_to_send,
    )

    response = chat_completion.text

    print("\nAvatar response: ", response)

    if "analyze_sensor_data" in response:
        print("Analyzing sensor data...")
        response = response[response.find('user_query="') + 12 :]
        query = response[: response.find('")')]
        print("Query: ", query)
        # analysis = str(api_tool(query))
        analysis = str(sensor_query_tool(query))
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
    global system_prompt

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
                OPENAI_API_KEY, model="gpt-realtime", prompt=system_prompt_
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
    }

    avatars.append(avatar)
    print("Avatars after modification: ", avatars)
    json.dump(avatars, open(avatars_path, "w"))
    avatar_llms, avatar_rag_tools = generate_avatars_config()
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
    for field in ["name", "systemPromptUrl", "contextDocsUrl", "sensorApiUrl"]:
        if field in data and data[field] is not None:
            avatar[field] = data[field]

    print("Avatars after modification: ", avatars)
    json.dump(avatars, open(avatars_path, "w"))
    avatar_llms, avatar_rag_tools = generate_avatars_config()
    return jsonify(avatar), 200


app.register_blueprint(avatars_bp)


if __name__ == "__main__":
    app.run(debug=False, use_reloader=False, port=5001)
