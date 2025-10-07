from flask import Flask, request, jsonify, send_file, make_response, Response
from flask_cors import CORS
from werkzeug.utils import secure_filename
import os, io, asyncio
from datetime import datetime

from llama_index.core.tools.query_engine import QueryEngineTool

from utils.avatar import get_llm, build_index, build_or_load_index, fetch_system_prompt_from_gdoc, search_text_index
from utils.utils import whisper_processor, whisper_model, transcribe_audio, LahnSensorsTool, format_history_as_string #, azure_speech_response_func,
from utils.processing_pipelines import OpenAIRealtimeClient, CartesiaOpenAIPipeline

import os,threading
from concurrent.futures import ThreadPoolExecutor, wait

# === Initialize Flask ===
app = Flask(__name__)
CORS(app, supports_credentials=True)

UPLOAD_DIR = "data/uploaded_experiences"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# === Load LLM once at startup ===
llm_choice = "hrz-chat-small" #'mistral-large-instruct' #"hrz-chat-small" #"deepseek-r1-distill-llama-70b" #gemma-3-27b-it" #"hrz-chat-small" #"gemma-3-27b-it" #"mistral-large-instruct" #"hrz-chat-small"
llm_second_choice = "hrz-chat-small"

llm, system_prompt = get_llm('openai', llm_choice)
text_query_llm, _ = get_llm('gwdg', 'mistral-large-instruct', system_prompt= 'Context is needed to address the most recent message in this conversation (Or maybe not. Look through the given conversation and determine. If not, your query could just be "General information about the Lahn"). Return a one-line string containing 6 total keywords, each separated by a comma and space: 3 relevant keywords  (to be queried in the database) that aim to extract the needed context, and another 3 keywords corresponding to the translations (into German or English, depending on the source language) of the earlier keywords. Your job is not to predict what any party will say, but to return these keywords, so they can be used to extract information relevant for the concerned party to make their decision. That is where your job stops. Reply only with the keywords and nothing else (not even "keywords:"). The keywords should be only relevant to the most recent message, since that is what context is needed on. Double-check that your response is in the format "keyword1, keyword2, keyword3, keyword1translation, keyword2translation, keyword3translation", with the keywords being only relevant to the last message: ')

sensor_query_llm, _ = get_llm('gwdg', 'mistral-large-instruct', system_prompt= 'Provide an accurate response to the given query. Only perform calculations. Do not generate any plots or visualizations. Always include the following setup **before any resampling or time-based operations**: df[\'created_at\'] = pd.to_datetime(df[\'created_at\'])  df = df.set_index(\'created_at\') . When calculating the variation of a quantity over an interval, use the largest of [seconds, minutes, hours,days, weeks,months,years] which is smaller than the range you\'re calculating over. For example, \'How has X varied over the past week?\' should be based on a daily interval. \'How has Y varied over the past year?\' on a monthly interval etc. :')
vector_query_llm, _ = get_llm('gwdg', llm_second_choice, system_prompt= 'Provide an accurate response to the given query.:')

api_tool = QueryEngineTool.from_defaults(
        query_engine=LahnSensorsTool(sensor_query_llm),
        name=LahnSensorsTool.name,
        description=LahnSensorsTool.description,
    )


def prepare_query_engine(refresh=False):
    global vector_query_llm
    if refresh==True:
        vector_index, text_index, chunks = build_index()
    else:
        vector_index, text_index, chunks = build_or_load_index()

    # query_llm = get_llm('gwdg', "mistral-large-instruct", system_prompt= 'Provide an accurate response to the given query:')

    vector_index_query_engine = vector_index.as_query_engine(llm=vector_query_llm,similarity_top_k=10, verbose=True)
    text_index_query_engine = search_text_index

    return vector_index_query_engine, text_index_query_engine, text_index, chunks


vector_index_query_engine, text_index_query_engine, text_index, chunks = prepare_query_engine()

debate_summary_llm, _= get_llm('gwdg', "mistral-large-instruct", system_prompt= '')
print('LLM initialized.')




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
    vector_index_query_engine, text_index_query_engine, text_index, chunks = prepare_query_engine(refresh=True)
    return 'Done'

debate_general_prompt = "Right now you are on a deliberation-centered platform, debating with the user the topic of '{topic}'. In this mode you should always consider the best interests of the Lahn River. You must decide what the Lahn’s best interests are based on all of your context information. You are the Lahn’s advocate right now. Below is a brief description of the topic, which both you and the user have access to. You can present your position to the user as you answer questions they might have on the topic. '{description}'"
topic_descriptions = {
    'The Lahn should have legal personhood': "In recent years, rivers around the world have been granted legal personhood to recognize their intrinsic rights and protect their ecosystems. Granting the Lahn legal personhood would mean treating the river not merely as a resource but as a living entity with legal standing - analogous to the legal standing that a person or corporation holds. This shift could reshape how environmental protection is approached in the region, allowing for the river's interests to be formally represented in legal and political systems. And even create precedent for the river suing a company or the government, for example.",
    'The Lahn should be able to own property': "If the Lahn were recognized as a legal person, it could theoretically hold property titles. This would allow the river to directly control land essential to its health—such as floodplains, wetlands, or riverbanks—ensuring its ecological integrity is not compromised by conflicting human interests. Property ownership could become a tool for the river to safeguard its own regeneration and future.",
    'There should exist a “Lahn Fund”': "A dedicated “Lahn Fund” would serve as a financial mechanism to support the ongoing protection, restoration, and stewardship of the river. This fund could receive public and private contributions, fines from environmental damages, or a share of local economic activities that depend on the river. Managed in the river’s interest, the fund could finance ecological research, conservation projects, community engagement, and support the operational costs of the Avatar or legal guardianship system.",
    'The Avatar should be able to legally speak on behalf of the Lahn': "The Lahn Avatar is envisioned as a voice for the river—an interface between natural and human systems. Allowing the Avatar to legally speak on behalf of the Lahn would formalize its role as a representative entity in decision-making processes. This could enable the river’s interests to be expressed in public hearings, governmental deliberations, and community forums, fostering a new model of ecological democracy and interspecies governance."
  }


def fetch_text_index_context(conversation, text_query_llm, text_index_query_engine):
    print('Fetching context from text index...')
    query_prompt = 'Here is the conversation: ' + format_history_as_string(conversation) #+ '\nUser: '+prompt #response[:response.find('")')]
    # print('Query prompt: ', query_prompt)

    query = str(text_query_llm.complete(query_prompt))
    # print('Crafted Query: ', query)
    context_from_text_index = text_index_query_engine(text_index, chunks, query)
    print('\n\nContext from text index: ', context_from_text_index)
    context_from_text_index = '\n'.join(context_from_text_index)

    print('Done fetching context from text index...')

    return context_from_text_index


def fetch_vector_index_context(query):
    print('Fetching context from vector index...')
    response =  vector_index_query_engine.query(query)
    print('\n\nContext from vector index: ', response)

    print('Done fetching context from vector index...')
    return response



@app.route("/api/chat", methods=["POST"])
def chat():
    global llm, llm_choice, system_prompt
    print('Chat request received.')
    data = request.get_json()
    prompt = data.get("prompt", "")
    conversation = data.get("history", "")
    topic = data.get("topic", None)
    if topic:
        print(f"→ Debate topic: {topic}")
        debate_prompt = debate_general_prompt.format(topic=topic, description=topic_descriptions[topic])
        # print('Prompt: ', debate_prompt)
        system_prompt_= system_prompt+ '\n' + debate_prompt
    else:
        system_prompt_ = system_prompt

    # print('\nSystem prompt: ', system_prompt_[-300:])

    chat_history = []

    chat_history = [
        {'role':"user" if m["sender"] == "user" else "assistant", 'content':m["text"]}
        for m in conversation
        ]

    chat_history.insert(0, {'role':'system', 'content':system_prompt_})

    # print('Chat history: ', chat_history)

    # print('After adding system and user prompts: ', chat_history)

    # print('\nUser message:', prompt)

    results = ''

    print('Obtaining information for the LLM...')
    # print('Fetching context from indexes...')
    query = 'Provide context needed to address the most recent message in this conversation. Your job is not to predict what any party will say, but to provide information from the context, which is relevant for them to make their decision. That is where your job stops. : '+ format_history_as_string(conversation) #+ '\nUser: '+prompt #response[:response.find('")')]
    
    with ThreadPoolExecutor(max_workers=2) as executor:
        thread_0 = executor.submit(fetch_vector_index_context, query)
        thread_1 = executor.submit(fetch_text_index_context, conversation, text_query_llm, text_index_query_engine)

        wait([thread_0,thread_1])

        # context_from_text_index = thread_0
        context_from_vector_index =  thread_0.result().response
        context_from_text_index = thread_1.result()




    total_context = '\nContext from text-based retrieval: \n' +context_from_text_index + '\n------------\nContext from vector-based retrieval: \n' + context_from_vector_index
    # results += '\nHere is the output of get_relevant_Lahn_context(): '+context

    chat_completion = llm.chat.completions.create(
          messages=chat_history+[{'role':'system', 'content':'Here is relevant information about the Lahn (Sometimes the text-retrieval has relevant information that the vector-retrieval doesn\'t, or vice versa. Look through each comprehensively, to extract the information you need. Even if the Vector-retrieval says there\'s no information available, still scrutinize the Text-retrieval results to fetch relevant info: '+total_context + ' . You can call analyze_sensor_data() if environmental data readings are relevant to the user\'s query.'}],
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
        analysis = str(api_tool(query))
        print('Analysis: ', analysis)
        results += '\nHere is the output of analyze_sensor_data(): '+analysis +' Respond to the user accordingly. Do not provide any subjective Lahn-specific evaluation of this data, just focus on the quantitative result. And do not return a function call.'

    if len(results)>0:
        print('Passing analysis results to LLM: ', chat_history+[{'role':'system', 'content':results}])
        chat_completion_2 = llm.chat.completions.create(
              messages=chat_history+[{'role':'system', 'content':results}],
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

    # response = chat_completion.choices[0].message.content
    response = response.replace('*','')

    # print('Avatar response:', response)

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

    os.makedirs(UPLOAD_DIR+'/text', exist_ok=True)
    # Save the text message (if any)
    text = request.form.get("text", "")
    if text.strip():
        with open(os.path.join(UPLOAD_DIR+'/text', f"{timestamp}_message.txt"), "w", encoding="utf-8") as f:
            f.write(text.strip())

    uploaded_files = request.files.getlist('files')

    saved_paths = []
    for f in uploaded_files:
        # skip empty inputs
        if not f or f.filename == '':
            continue

        # 3) Sanitize the filename
        filename = secure_filename(f.filename)

        # 4) Build the absolute path and save
        dest = os.path.join(UPLOAD_DIR, filename)
        f.save(dest)

        saved_paths.append(dest)


    # Save and transcribe the uploaded audio file
    if "audio" in request.files:
        audio_file = request.files["audio"]
        if audio_file and audio_file.filename:
            safe_name = secure_filename(audio_file.filename)
            file_ext = os.path.splitext(safe_name)[1]
            audio_path = os.path.join(UPLOAD_DIR, f"{timestamp}_audio{file_ext}")
            audio_file.save(audio_path)

            try:
                transcript = transcribe_audio(audio_path)
                with open(os.path.join(UPLOAD_DIR+'/text', f"{timestamp}_transcript.txt"), "w", encoding="utf-8") as f:
                    f.write(transcript.strip())
                print("📝 Transcription saved.")
            except Exception as e:
                print("❌ Failed to transcribe:", e)
                return jsonify({"status": "error", "message": "Audio saved, but transcription failed."}), 500
    print('Upload done...')

    refresh_embeddings_thread = threading.Thread(target=refresh_embeddings)
    print('Refreshing embeddings...')
    refresh_embeddings_thread.start()
    return jsonify({"status": "success", "message": "Experience saved."})


import subprocess
from dotenv import load_dotenv
load_dotenv()
print('Loaded from .env file.')

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
CARTESIA_API_KEY = os.getenv("CARTESIA_API_KEY")


import io
import wave

def pcm_to_wav_bytes(pcm_bytes, sample_rate=24000, n_channels=1, sampwidth=2):
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(n_channels)
        wf.setsampwidth(sampwidth)  # 2 bytes for int16
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()



# Could pass audio_data directly to bypass file processing latency
@app.post("/api/voice-chat")
def voice_chat():
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
        elif pipeline == "OpenAI gpt4o":
            client = OpenAIRealtimeClient(OPENAI_API_KEY, model="gpt-4o-realtime-preview", prompt = system_prompt_)
            response_audio, elapsed, cost_info = client.process_audio(audio_bytes)
        elif pipeline == "Cartesia":
            client = CartesiaOpenAIPipeline(CARTESIA_API_KEY, OPENAI_API_KEY, prompt = system_prompt_)
            response_audio, elapsed, cost_info = client.process_audio(audio_bytes)
        else:
            return jsonify({"error": f"Unknown pipeline '{pipeline}'"}), 400

        print('Done processing. Info: ', elapsed, cost_info)
        print('System prompt: ', system_prompt_)

        # Convert raw PCM to WAV
        wav_bytes = pcm_to_wav_bytes(response_audio)

        # send audio directly
        return Response(wav_bytes, mimetype="audio/wav")



    except Exception as e:
        print({"error": str(e)})
        return jsonify({"error": str(e)}), 500





# @app.route("/api/voice-chat", methods=["POST"])
# def voice_chat():
#     if "audio" not in request.files:
#         return jsonify({"error": "No audio uploaded"}), 400

    # audio_file = request.files["audio"]
    # ext = audio_file.mimetype.split("/")[-1] 
    # audio_path = 'data/temp.'+ext
    # audio_file.save(audio_path)

    # # audio_b64 = base64.b64encode(request.files["audio"].read()).decode()

#     try:
#         # run async function to get reply
#         reply_text, reply_wav = asyncio.run(azure_speech_response_func(audio_path))
#         # save reply to disk
#         out_path = os.path.join("data", "reply.wav")
#         with open(out_path, "wb") as f:
#             f.write(reply_wav)
#         return jsonify({
#             "reply_text": reply_text,
#             "reply_audio_url": "https://lahn-server.eastus.cloudapp.azure.com:5001/api/reply-audio"
#         })
#     except Exception as e:
#         print("❌ Voice chat error:", e)
#         return jsonify({"error": "Voice chat failed"}), 500
#     finally:
#         os.remove(audio_path)



# @app.route("/api/reply-audio")
# def reply_audio():
#     # Serve the latest reply audio file
#     audio_path = os.path.join("data", "reply.wav")
#     if not os.path.exists(audio_path):
#         return "", 404
#     # Create response with CORS headers
#     response = make_response(send_file(audio_path, mimetype="audio/wav"))
#     response.headers["Access-Control-Allow-Origin"] = "*"  # or specify frontend origin
#     response.headers["Access-Control-Allow-Headers"] = "Content-Type"
#     return response


if __name__ == "__main__":
    app.run(debug=True, use_reloader=False, port=5001)