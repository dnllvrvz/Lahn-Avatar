from flask import Flask, request, jsonify, send_file, make_response, Response
from flask_cors import CORS
from werkzeug.utils import secure_filename
import os, io, asyncio
from datetime import datetime

from llama_index.core.tools.query_engine import QueryEngineTool

from utils.utils import fetch_system_prompt_from_gdoc, fetch_text_index_query, RAG, prepare_query_engines, build_or_load_index, transcribe_audio, pcm_to_wav_bytes, format_history_as_string
from utils.avatar_setup import avatars_path, avatar_llms, avatar_rag_tools, llm_choice, text_query_llm, sensor_query_tool
from utils.processing_pipelines import OpenAIRealtimeClient 

import os,threading

# === Initialize Flask ===
app = Flask(__name__)
CORS(app, supports_credentials=True)

UPLOAD_DIR = "data/uploaded_experiences"
os.makedirs(UPLOAD_DIR, exist_ok=True)












@app.route("/api/refresh-prompt", methods=["POST"])
def refresh_prompt():
    global system_prompt, llm
    print('Refresh prompt request received.')
    fetch_system_prompt_from_gdoc()
    llm,  system_prompt = get_llm('openai', llm_choice)
    return 'Done.'



@app.route("/api/refresh-embeddings", methods=["POST"])
def refresh_embeddings():
    global vector_index_query_engine, text_index_query_engine, text_index, chunks
    print('Refresh embeddings request received.')
    vector_index_query_engine, text_index_query_engine, text_index, chunks = prepare_query_engines(refresh=True)
    return 'Done'

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
    print('\n\n------------------------\nvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv\nChat request received.')
    avatar_id = request.args.get("avatar", "0")

    system_prompt = avatar_llms[avatar_id].system_prompt

    data = request.get_json()
    prompt = data.get("prompt", "")
    conversation = data.get("history", "")
    print('Conversation history: ', conversation)
    topic = data.get("topic", None)
    # if topic:
    #     print(f"→ Debate topic: {topic}")
    #     debate_prompt = debate_general_prompt.format(topic=topic, description=topic_descriptions[topic])
    #     # print('Prompt: ', debate_prompt)
    #     system_prompt_= system_prompt+ '\n' + debate_prompt
    # else:
    system_prompt_ = system_prompt


    chat_history = []

    chat_history = [
        {'role':"user" if m["sender"].lower() == "user" else "assistant", 'content':m["text"]}
        for m in conversation
        ]

    if len(chat_history) == 0:
        return jsonify({"error": 'Invalid request format. Ensure your payload has "history" in the format [{"sender": "User", "text": "content"}, ...]'})

    chat_history.insert(0, {'role':'system', 'content':system_prompt_})

    print('Obtaining information for the LLM...')

    # query = 'Provide context needed to address the most recent message in this conversation. Your job is not to predict what any party will say, but to provide information from the context, which is relevant for them to make their decision. That is where your job stops. : '+ format_history_as_string(conversation)
    text_index_query = fetch_text_index_query(text_query_llm, conversation)
    context = RAG(avatar_rag_tools[avatar_id], text_index_query, translated=True) #query, text_index_query = text_index_query)

    total_context = context 
    # messages_to_send = chat_history+[{'role':'assistant', 'content':'Here is relevant information about the Lahn (Sometimes the text-retrieval has relevant information that the vector-retrieval doesn\'t, or vice versa. Look through each comprehensively, to extract the information you need. Even if the Vector-retrieval says there\'s no information available, still scrutinize the Text-retrieval results to fetch relevant info (What language was the user\'s last message in? Make sure to respond in the same language.): '+total_context + ' . You can call analyze_sensor_data() if environmental data readings are relevant to the user\'s query.'}]
    chat_history[-1]['content'] += 'Here is relevant information about the Lahn (Sometimes the text-retrieval has relevant information that the vector-retrieval doesn\'t, or vice versa. Look through each comprehensively, to extract the information you need. Even if the Vector-retrieval says there\'s no information available, still scrutinize the Text-retrieval results to fetch relevant info (What language was the user\'s last message in? Make sure to respond in the same language.): '+total_context + ' . You can call analyze_sensor_data() if environmental data readings are relevant to the user\'s query.'
    messages_to_send = chat_history
    print("Messages to send: ", messages_to_send)

    llm = avatar_llms[avatar_id]
    
    chat_completion = llm.chat.completions.create(
          messages= messages_to_send,
          model= llm_choice,
          # temperature=0.1
          top_p=0.7
      )

    response = chat_completion.choices[0].message.content

    print('\nAvatar response: ', response)


    if 'analyze_sensor_data' in response:
        print('Analyzing sensor data...')
        response = response[response.find('user_query="')+12:]
        query = response[:response.find('")')]
        print('Query: ', query)
        # analysis = str(api_tool(query))
        analysis = str(sensor_query_tool(query))
        print('Analysis: ', analysis)
        results = '\nHere is the output of analyze_sensor_data(): '+analysis +' Respond to the user accordingly. Do not provide any subjective Lahn-specific evaluation of this data, just focus on the quantitative result. And do not return a function call. What language was the user\'s last message in? Make sure to respond in the same language.'

    # if len(results)>0:
        print('Passing analysis results to LLM..') #: ', chat_history+[{'role':'system', 'content':results}])
        chat_completion_2 = llm.chat.completions.create(
              messages=chat_history+[{'role':'assistant', 'content':results}],
              model= llm_choice,
              top_p=0.8
          )

        response_2 = chat_completion_2.choices[0].message.content
        if 'analyze_sensor_data' in response_2:
            print('Duplicate function call for some reason')
            response_2 = analysis

        response_2 = response_2.replace('*','')

        print('Avatar response after getting sensor data:', response_2)

        return jsonify({"reply": response_2})

    response = response.replace('*','')

    return jsonify({"reply": response})



@app.route("/api/debate-summary", methods=["POST"])
def debate_summary():
    print('Debate Summary request received.')
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

    response = debate_summary_llm.complete(prompt) #chat_engine.chat(prompt)
    # print('Summary model response: ', response)
    summary = str(response) #.choices[0].message.content

    # chat_history = [
    #     ChatMessage(role="user" if m["sender"] == "user" else "assistant", content=m["text"])
    #     for m in conversation
    #     ]

    # print('User message:', prompt)
    # response = chat_engine.chat(messages=chat_history)
    print('Summary:', summary)

    return jsonify({"summary": summary})


#Would want to differentiate between general user and Admin uploads----
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
    return jsonify({
        "status": "success",
        "message": "Experience saved. Processing in background."
    })



import subprocess
from dotenv import load_dotenv
load_dotenv()
print('Loaded from .env file.')

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
CARTESIA_API_KEY = os.getenv("CARTESIA_API_KEY")


# Could pass audio_data directly to bypass file processing latency
@app.post("/api/voice-chat")
def voice_chat():
    print('\n\n------------------------\nvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv\nVoice Chat request received.')
    global system_prompt

    #Do away with function-related instructions, for now.
    index = system_prompt.find('You also have access to sensory data')
    system_prompt_ = system_prompt[:index]

    try:
        # get uploaded file + pipeline choice
        audio_file = request.files["audio"]   # comes from FormData

        ext = audio_file.mimetype.split("/")[-1] 
        audio_path = 'data/temp.'+ext
        audio_file.save(audio_path)

        pipeline = request.form.get("pipeline", "OpenAI gpt-realtime")

        print('Recieved voice chat request. Pipeline: ', pipeline)
        print('Audio: ', audio_path)


        output_wav = 'data/temp.'+".wav"
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-i", audio_path, output_wav],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True
            )
            print(f"[Success] Converted to: {output_wav}")
        except subprocess.CalledProcessError as e:
            print("[Error] ffmpeg decoding failed:\n", e.stderr.decode())
            return None
        

        # read into memory
        audio_bytes = output_wav #audio_path #audio_file.read()

        # pass raw bytes to your dispatcher
        # Dispatch
        if pipeline == "OpenAI gpt-realtime":
            client = OpenAIRealtimeClient(OPENAI_API_KEY, model="gpt-realtime", prompt = system_prompt_)
            response_audio, elapsed, cost_info = client.process_audio(audio_bytes)
        # elif pipeline == "OpenAI gpt4o":
        #     client = OpenAIRealtimeClient(OPENAI_API_KEY, model="gpt-4o-realtime-preview", prompt = system_prompt_)
        #     response_audio, elapsed, cost_info = client.process_audio(audio_bytes)
        # elif pipeline == "Cartesia":
        #     client = CartesiaOpenAIPipeline(CARTESIA_API_KEY, OPENAI_API_KEY, prompt = system_prompt_)
        #     response_audio, elapsed, cost_info = client.process_audio(audio_bytes)
        else:
            return jsonify({"error": f"Unknown pipeline '{pipeline}'"}), 400

        print('Done processing. Info: ', elapsed, cost_info)
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

@sock.route('/api/voice-chat-stream')
def stream(ws):
    print('\n\n------------------------\nvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv\nStreaming Voice Chat request received.')
    global system_prompt

    #Do away with function-related instructions, for now.
    index = system_prompt.find('You also have access to sensory data')
    system_prompt_ = system_prompt[:index]

    client = OpenAIRealtimeClient(OPENAI_API_KEY, model="gpt-realtime", prompt = system_prompt_, streaming=True, ws_client = ws)
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



#Multi-Avatar Management


# avatars_api.py
from flask import Blueprint, request, jsonify

avatars_bp = Blueprint("avatars", __name__)


@avatars_bp.route("/api/avatars", methods=["GET", "POST"])
def avatars_collection():
    global avatar_llms, avatar_rag_tools
    """
    GET  /api/avatars  -> list all avatars
    POST /api/avatars  -> create a new avatar
    """

    avatars = json.load(open(avatars_path, 'r'))
    print('\nAvatars: ', avatars)

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

    print('\n\n------------------------\nvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv\nRecieved Request to Create New Avatar.')

    # Make id a string so it matches React's select value and find() comparison
    if len(avatars) == 0:
        next_id = '0'
    else:
        max_id = max(int(a["id"]) for a in avatars)
        next_id = str(max_id + 1)

    os.makedirs(f"avatars_context/{next_id}", exist_ok=True)

    if system_prompt_url != '':
        fetch_system_prompt_from_gdoc(next_id, system_prompt_url)

    #Run this in a thread
    #Set up RAG index for avatar
    if context_docs_url != '':
        drive_folder_id = context_docs_url.split("/folders/")[1].split("?")[0]
        print('Building Index for Avatar: '+ next_id)
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
    print('Avatars after modification: ', avatars)
    json.dump(avatars, open(avatars_path, 'w'))
    avatar_llms, avatar_rag_tools = generate_avatars_config()
    # Frontend expects the created avatar object back
    return jsonify(avatar), 201


@avatars_bp.route("/api/avatars/<avatar_id>", methods=["PUT"])
def avatar_detail(avatar_id):
    """
    PUT /api/avatars/<avatar_id> -> update an existing avatar
    """
    data = request.get_json() or {}
    avatars = json.load(open(avatars_path, 'r'))
    print('Avatars: ', avatars)

    # Find avatar by string id
    avatar = next((a for a in avatars if a["id"] == avatar_id), None)
    if avatar is None:
        return jsonify({"error": "Avatar not found."}), 404

    # Only update fields present in request
    for field in ["name", "systemPromptUrl", "contextDocsUrl", "sensorApiUrl"]:
        if field in data and data[field] is not None:
            avatar[field] = data[field]

    print('Avatars after modification: ', avatars)
    json.dump(avatars, open(avatars_path, 'w'))

    return jsonify(avatar), 200


app.register_blueprint(avatars_bp)




if __name__ == "__main__":
    app.run(debug=False, use_reloader=False, port=5001)
