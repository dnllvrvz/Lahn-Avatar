# ---------- standard library ----------
import os, io, re, time, wave, pickle, hashlib, datetime, subprocess, unicodedata
from pathlib import Path
from typing import Any, List
from urllib.parse import urlparse, parse_qs
from concurrent.futures import ThreadPoolExecutor, wait

# ---------- third-party ----------
import requests
import pandas as pd
import nltk
import spacy
import langid
import torch
import torchaudio

from docx import Document
from openai import OpenAI
from youtube_transcript_api import YouTubeTranscriptApi
from langdetect import detect
from deep_translator import GoogleTranslator
from nltk.tokenize import word_tokenize, sent_tokenize
from rank_bm25 import BM25Okapi

# ---------- llama-index ----------
from llama_index.core import Settings, StorageContext, load_index_from_storage
from llama_index.core.indices.vector_store import VectorStoreIndex
from llama_index.core.readers import SimpleDirectoryReader
from llama_index.core.schema import Document as LlamaDocument
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.experimental.query_engine import PandasQueryEngine
from llama_index.readers.web import SimpleWebPageReader



# === CONFIG ===
DRIVE_FOLDER_ID = "1vT4UTYHeFxS5Vy2u_OfQyQ6cQ-cP5Ywd"


# base_dir = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = "./data" #os.path.join(base_dir, "/data")

# print('Base dir: ', base_dir, 'Data dir: ', DATA_DIR)
LOG_DIR = "./chat_logs" #os.path.join(base_dir, "/chat_logs")
STORAGE_DIR = "./lahn_index"#os.path.join(base_dir, "/lahn_index")


def download_drive_folder(folder_id, output_dir="./data"):
    print('Running download_drive_folder function...')
    os.makedirs(output_dir, exist_ok=True)
    cmd = f"gdown --folder https://drive.google.com/drive/folders/{folder_id} -O {output_dir}"
    subprocess.run(cmd, shell=True)


def fetch_system_prompt_from_gdoc(avatar_id='0', system_prompt_url="https://docs.google.com/document/d/1NYOOy8KkaLDBwvHvEVg1hVDY5yvHeLACUpCEkJVM8Kw/export?format=txt" ):
    print(' Updating system prompt for avatar: ' + avatar_id + '...')
    prompt_dir = 'avatars_context/' + avatar_id+'/prompt/'
    os.makedirs(prompt_dir, exist_ok=True)
    # url = "https://docs.google.com/document/d/1NYOOy8KkaLDBwvHvEVg1hVDY5yvHeLACUpCEkJVM8Kw/export?format=txt"
    response = requests.get(system_prompt_url)
    response.raise_for_status()
    prompt = response.text.strip()
    # prompt = prompt[:prompt.find('General Internal Impressions')]

    # base_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(prompt_dir, 'system_prompt.txt')
    with open(file_path, 'w') as f:
        f.write(prompt)
    print(' Done.')


def convert_docx_to_txt_and_cleanup(folder_path):
    for root, _, files in os.walk(folder_path):
        for file in files:
            file_path = os.path.join(root, file)
            if file.endswith('.docx') or '.' not in file:
                try:
                    doc = Document(file_path)
                    text = "\n".join([para.text for para in doc.paragraphs])
                    txt_filename = os.path.splitext(file)[0] + '.txt'
                    txt_path = os.path.join(root, txt_filename)
                    with open(txt_path, 'w', encoding='utf-8') as f:
                        f.write(text)
                    os.remove(file_path)
                    print(f"✅ Converted and deleted: {file_path}")
                except Exception as e:
                    print(f"❌ Failed to convert {file_path}: {e}")


def fetch_youtube_transcript(url, languages=["de"]):
    print(f"🔗 Fetching: {url}")
    try:
        parsed = urlparse(url)

        # Handle standard and short YouTube URL formats
        if "youtube.com" in parsed.netloc:
            video_id = parse_qs(parsed.query).get("v", [None])[0]
        elif "youtu.be" in parsed.netloc:
            video_id = parsed.path.lstrip("/")
        else:
            raise ValueError("Unrecognized YouTube URL format.")

        if not video_id or len(video_id) != 11:
            raise ValueError("Invalid YouTube video ID.")

        transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=languages)
        full_text = " ".join([entry["text"] for entry in transcript])
        return LlamaDocument(text=full_text, metadata={"source": url})

    except Exception as e:
        print(f"❌ Failed to fetch {url}: {e}")
        return None


def sanitize_filename(url):
    domain = urlparse(url).netloc
    hashed = hashlib.md5(url.encode()).hexdigest()[:8]
    return f"{domain.replace('.', '_')}_{hashed}.txt"


# def get_llm(mode='openai',model_name=None, system_prompt=None):
#     # base_dir = os.path.dirname(os.path.abspath(__file__))
#     # file_path = os.path.join(base_dir, 'system_prompt.txt')
#     # if system_prompt == None:
#     #     system_prompt = open(file_path, 'r').read()

#     # if model_name != None:
#     if mode == 'openai':

#         llm =  OpenAI(
#             # point at your custom endpoint:
#             api_key=API_KEY,             # e.g. 'sk-…'
#             base_url=API_BASE,           # "https://llm.hrz.uni-giessen.de/api/"
#             # api_type="open_ai",          # use the “open_ai” protocol
#             # api_version=None,            # leave None unless your server needs a version
#         )


#     # else:

#     #     llm = GWDGChatLLM(
#     #             model=model_name,
#     #             api_base=API_BASE,
#     #             api_key=API_KEY,
#     #             temperature=0.5,
#     #             system_prompt=system_prompt
#     #         )

#     # print('LLM details: ', llm.model_dump())

#     # Settings.llm = llm

#     return llm #, system_prompt


def create_session_log():
    os.makedirs(LOG_DIR, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return open(os.path.join(LOG_DIR, f"session_{timestamp}.txt"), "w")


def ensure_punkt_tab():
    try:
        # this will raise LookupError if not found
        nltk.data.find('tokenizers/punkt_tab')
    except LookupError:
        print("punkt_tab not found—downloading…")
        nltk.download('punkt_tab')
    else:
        print("punkt_tab already available.")


CHUNK_SIZE, OVERLAP = 200, 30
# ------------------------------------------------------------------
# 0. normalisers / helpers
# ------------------------------------------------------------------
def normalise(txt:str) -> str:
    txt = re.sub(r"\s+", " ", txt.lower().strip())
    return unicodedata.normalize("NFKD", txt)

def tokenize(text:str, lang:str) -> list[str]:
    lang_flag = "german" if lang=="de" else "english"
    return word_tokenize(text, language=lang_flag)

# ------------------------------------------------------------------
# 1. translation helper with cache
# ------------------------------------------------------------------
_trans_cache: dict[tuple[str,str], str] = {}   # (text, target_lang) → translated

def translate(text:str, target_lang:str) -> str:
    """
    Translate 'text' to target language ('de' or 'en') using deep_translator.
    Caches results to avoid hitting rate limits.
    """
    key = (text, target_lang)
    if key in _trans_cache:
        return _trans_cache[key]

    translated = GoogleTranslator(source='auto', target=target_lang).translate(text)
    _trans_cache[key] = translated
    return translated


def prepare_text_index(RAW_TEXT):
    ensure_punkt_tab()
    sentences = sent_tokenize(normalise(RAW_TEXT), language="german")
    chunks, cur, wc = [], [], 0
    for sent in sentences:
        words = tokenize(sent, "de")      # punkt model is DE but works for EN too
        cur.extend(words); wc += len(words)
        if wc >= CHUNK_SIZE:
            chunks.append(" ".join(cur))
            cur, wc = cur[-OVERLAP:], len(cur)
    if cur: chunks.append(" ".join(cur))

    print(f"➡  Raw chunks: {len(chunks)}")
    # ------------------------------------------------------------------
    # 2. Build your BM-25 index (assumes you already have 'chunks')
    # ------------------------------------------------------------------
    #   chunks = ["..."]    # list of cleaned 200-word blocks
    token_lists = [tokenize(c, detect(c)) for c in chunks]
    bm25 = BM25Okapi(token_lists)
    return bm25, chunks

# ------------------------------------------------------------------
# 3. Dual-language search
# ------------------------------------------------------------------
def search_text_index(bm25, chunks, en_keywords, de_keywords, k_each:int=5):
    # keyword_list = query.split(', ')
    query = ' '.join(en_keywords) # keyword_list[:3])
    trans_q = ' '.join(de_keywords) # keyword_list[3:])

    lang_orig  = 'en' #"de" if detect(query) == "de" else "en"
    lang_trans = 'de' #"en" if lang_orig == "de" else "de"

    # --- original language pass -----------------------------------
    q_tokens_o = tokenize(normalise(query), lang_orig)
    # print('Query recieved by Text Index searcher: ', ', '.join(en_keywords + de_keywords))
    # print('Keywords group 1: ', query)
    # print('Keywords group 2: ', trans_q)

    # print('Group 1 tokens to search with BM25: ', q_tokens_o)
    scores_o   = bm25.get_scores(q_tokens_o)
    top_o      = scores_o.argsort()[-k_each:][::-1]

    # --- translated pass ------------------------------------------
    # trans_q    = translate(query, lang_trans)
    # print('Translated query: ',trans_q)
    q_tokens_t = tokenize(normalise(trans_q), lang_trans)
    # print('Group 2 tokens to search with BM25: ', q_tokens_t)
    scores_t   = bm25.get_scores(q_tokens_t)
    top_t      = scores_t.argsort()[-k_each:][::-1]

    # --- merge, preferring best score if overlap ------------------
    seen, results = {}, []
    for idx in top_o:
        seen[idx] = ("orig", float(scores_o[idx]))
    for idx in top_t:
        if idx in seen:
            # keep the better score
            seen[idx] = ("orig+trans", max(seen[idx][1], float(scores_t[idx])))
        else:
            seen[idx] = ("trans", float(scores_t[idx]))

    # sort by score descending and trim to k_each*2
    merged = sorted(seen.items(), key=lambda kv: kv[1][1], reverse=True)[: 2*k_each]
    for idx, (tag, score) in merged[:6]:
        # results.append((tag, score, chunks[idx]))
        results.append(chunks[idx])
    return results


def translate_keywords_batch(keywords, source_lang="auto", target_lang="de"):

    if target_lang == 'de':
        prefix = 'Word: '
    elif target_lang == 'en':
        prefix = 'Wort: '

    translator = GoogleTranslator(source=source_lang, target=target_lang)
    joined = ". ".join([prefix+w for w in keywords])
    out = translator.translate(joined)
    
    # Extract translations after 'Wort:' or similar
    parts = [p.strip().replace('.','') for p in out.replace("Wort:", "Word:").split("Word:") if p.strip()]
    return parts



# Preload your NLP models
nlp_en = spacy.load("en_core_web_sm")
nlp_de = spacy.load("de_core_news_sm")
# nlp_multi = spacy.load("xx_ent_wiki_sm")  # Multilingual fallback

def extract_keywords(text):
    # Detect dominant language
    lang, confidence = langid.classify(text)
    print('Processing: ', text)
    print(f"Detected language: {lang} (confidence={confidence:.2f}). Input: {text}")

    # Decide model and translation target
    if lang.startswith("de"):
        nlp = nlp_de
        target_lang = "en"
    elif lang.startswith("en"):
        nlp = nlp_en
        target_lang = "de"
    else:
        # Multilingual or low-confidence input
        text = GoogleTranslator(source='auto', target='en').translate(text)
        nlp = nlp_en
        target_lang = "de"

    doc = nlp(text)
    print('extract_keyword doc: ', doc)
    # Extract nouns and proper nouns as keywords
    keywords = [token.text for token in doc if token.pos_ in ("NOUN", "PROPN", "X") and (not token.is_stop or token.pos_ == "PROPN")] #if (token.pos_ in ("NOUN", "PROPN", "X") or (token.text[0].isupper() and token.i != 0)) and not token.is_stop]
    keywords = list(set(keywords))  # remove duplicates
    if len(keywords) == 0:
        keywords = text.split(' ')
    print('Keywords: ', keywords)
    #Handle empty keywords ***

    translated_keywords = translate_keywords_batch(keywords, target_lang=target_lang)
    print('Translated keywords: ', translated_keywords)

    if target_lang == 'en':
        en_keywords = translated_keywords
        de_keywords = keywords
    else:
        en_keywords = keywords
        de_keywords = translated_keywords

    return en_keywords, de_keywords 







#Sensor related



# 1) Fetch & normalize your ThingSpeak data
THINGSPEAK_URL = (
    "https://api.thingspeak.com/channels/2974588/feeds.json?results=100"
)


# 2) Wrap it in a callable that runs PandasQueryEngine on demand
class LahnSensorsTool:
    name = "lahn_sensors"
    description = (
        "You can access your (the Lahn river's) temperature, ph and other live readings here. This is the single source of truth for live river readings (pH, Dissolved Oxygen, Temp, Electrical Conductivity for water parameters and Humidity and CO2 for air parameters). Some questions require analysis of the data. For example: What was the lowest temperature reading last week? Such questions require you to not just access the relevant data range, but perform a computation on it. Do what is necessary on the data, to obtain a response to the question. Input: a natural-language question about live Lahn Atlas sensor values. Output: a concise natural-language answer based on the fetched data and an analysis of it. Use this to answer analytical questions about the live Lahn Atlas sensor data (pH, Dissolved Oxygen, Temp, Electrical Conductivity for water parameters and Humidity and CO2 for air parameters) fetched from the ThingSpeak REST API."
    )

    def __init__(self, llm):
        # store whichever LLM you pass in (e.g. get_llm("mistral-large-instruct"))
        self.llm = llm
        self.cache_ttl=1800
        self._cached_df = None
        self._engine = None
        self.GENERAL_PANDAS_INSTRUCTIONS = """
            General guidance for using the DataFrame `df`:
            1. Always ensure consistent datetime handling:
               df['created_at'] = pd.to_datetime(df['created_at'])
               df['created_at'] = df['created_at'].dt.tz_localize(None)
               df = df.set_index('created_at')

            2. Never assume exact timestamp equality; use nearest lookup:
               idx = df.index.get_indexer([target_time], method='nearest')[0]

            3. Handle NaN or missing values gracefully:
               Use df.fillna(method='ffill') or df.interpolate() as needed.

            4. Guard against missing columns:
               Always check `"Temp (°C)" in df.columns` before accessing.

            5. For aggregation or change-over-time questions:
               Choose the largest of [seconds, minutes, hours, days, weeks, months, years]
               smaller than the requested interval. Use resampling accordingly.

            6. If any error occurs, adapt your next code so that it handles the failure case robustly.
            """

    def _fetch_lahn_sensors_df(self) -> pd.DataFrame:
        print('Fetching Lahn sensor data...')
        resp = requests.get(THINGSPEAK_URL)
        resp.raise_for_status()
        data = resp.json()
        # extract channel metadata → used for human‐friendly column names
        channel_meta = data["channel"]
        field_map = {
            f"field{i}": channel_meta[f"field{i}"]
            for i in range(1, 7)
        }
        # load feeds into DataFrame
        df = pd.json_normalize(data["feeds"])
        # rename columns to pH, DO (mg/L), etc.
        df = df.rename(columns=field_map)
        # parse timestamp & convert all sensor readings to numeric
        df["created_at"] = pd.to_datetime(df["created_at"])
        for col in field_map.values():
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df

    def _get_df(self):
        now = time.time()
        if self._cached_df is None or (now - self._last_fetch) > self.cache_ttl:
            print("Fetching new sensor data...")
            self._cached_df = self._fetch_lahn_sensors_df()
            self._last_fetch = now
        return self._cached_df

    def _get_df_sample(self, n=10):
        """Return a representative text sample of the dataframe for the LLM."""
        import pandas as pd
        df = self._get_df()
        sample = df.head(n).to_string(index=False)
        info = f"DataFrame columns: {', '.join(df.columns)}\nSample rows:\n{sample}"
        return info



    def __call__(self, query: str) -> str:
        print('Calling Lahn Sensors Tool...')
        n_tries = 0
        df = self._get_df()
        sample_info = self._get_df_sample()

        if self._engine is None:
            self._engine = PandasQueryEngine(df=df, llm=self.llm, verbose=True, synthesize_response=False)
        else:
            self._engine.df = df

        query = (
                f"{query}\n\n"
                f"{self.GENERAL_PANDAS_INSTRUCTIONS}\n\n"
                f"Context: here is a small sample of the dataframe you will analyze.\n"
                f"Use this to infer datetime granularity, column names, and data structure.\n"
                f"{sample_info}\n"
                # "If you need to access a specific timestamp, use the nearest available one "
                # "rather than assuming exact equality. "
                "Sometimes values are null, so take that into account as well."
            )

        result = self._engine.query(query).response

        # If the response contains an embedded Pandas failure message, trigger repair
        while (isinstance(result, str)) and ("Error message:" in result):
            if (n_tries<3):
                n_tries += 1
                print("⚠️ Detected embedded error message in response — retrying with augmented query...")
                query = f"{query}\n\nNote: the previous code failed with this error: {result}. Identify the reason for the error, and adapt your new approach to avoid that."
                print('Augmented query: ', query)
                result = self._engine.query(query).response
            else:
                print('Unable to analyze data after multiple tries.')
                return 'Technical issue with sensor data analysis. Pls try again later.'
        return result


    def query(self, query_str: str) -> str:
        """
        Alias so that QueryEngineTool can call .query(...)
        under the hood. Simply forwards to __call__.
        """
        return self(query_str)



def format_history_as_string(history):
    # print('To convert to string. Input: ', history)

    role_map = {
        "user": "User",
        "avatar": "Lahn"
    }

    result = "\n".join(f"{role_map.get(m['sender'], m['sender'])}: {m['text']}" for m in history)

    # print('Converted conversation history into string: ', result)

    return result


def convert_to_wav(input_path, output_path):
    command = [
        "ffmpeg", "-y", "-i", input_path,
        "-ar", "16000", "-ac", "1", output_path
    ]
    subprocess.run(command, check=True)


def pcm_to_wav_bytes(pcm_bytes, sample_rate=24000, n_channels=1, sampwidth=2):
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(n_channels)
        wf.setsampwidth(sampwidth)  # 2 bytes for int16
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()


    
def transcribe_audio(file_path):
    from transformers import WhisperProcessor, WhisperForConditionalGeneration
    
    whisper_device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"🔄 Loading Whisper model on {whisper_device}...")
    whisper_processor = WhisperProcessor.from_pretrained("openai/whisper-small")
    whisper_model = WhisperForConditionalGeneration.from_pretrained("openai/whisper-small").to(whisper_device)
    print("✅ Whisper model loaded.")

    temp_wav_path = file_path.rsplit(".", 1)[0] + "_converted.wav"
    convert_to_wav(file_path, temp_wav_path)

    speech, sr = torchaudio.load(temp_wav_path)
    input_features = whisper_processor(
        speech.squeeze(), sampling_rate=sr, return_tensors="pt"
    ).input_features.to(whisper_device)

    predicted_ids = whisper_model.generate(input_features)
    transcription = whisper_processor.batch_decode(predicted_ids, skip_special_tokens=True)[0]
    return transcription










#RAG related


def build_index(avatar_id='0', drive_folder_id=DRIVE_FOLDER_ID):
    index_dir = 'avatars_context/' + avatar_id+'/index'
    data_dir = 'avatars_context/' + avatar_id+'/data'

    print('Contents of ' + data_dir + ' :')
    for root, dirs, files in os.walk(data_dir):
        for name in files:
            print(os.path.join(root, name))


    print('\nRefreshing from Google Drive...')
    download_drive_folder(DRIVE_FOLDER_ID, data_dir)
    convert_docx_to_txt_and_cleanup(data_dir)

    print('\n\nCreating Context store from data sources...')

    if len(os.listdir(data_dir))>0:
        documents = SimpleDirectoryReader(data_dir, recursive=True).load_data()
        print(f"{len(documents)} documents loaded from {data_dir}")
        # for i, doc in enumerate(documents):
        #     print(f"\n--- Document {i+1} ---")
        #     print("File:", doc.metadata.get('file_path', 'Unknown'))
        #     print("Content preview:", doc.text[:300], "...\n")


    links_path = Path(data_dir) / "General_News/Online News (Links).txt"
    if links_path.exists():
        with open(links_path, "r") as f:
            urls = [line.strip() for line in f if line.strip()]

        web_reader = SimpleWebPageReader()
        for url in urls:
            try:
                print(f"🔗 Fetching: {url}")
                if "youtube.com" in url or "youtu.be" in url:
                    doc = fetch_youtube_transcript(url)
                else:
                    docs = web_reader.load_data([url])
                    full_text = "\n\n".join(doc.text for doc in docs)
                    doc = LlamaDocument(text=full_text, metadata={"source": url})

                if doc:
                    filename = sanitize_filename(url)
                    filepath = Path(DATA_DIR) / "General_News/scraped_texts" / filename
                    filepath.parent.mkdir(parents=True, exist_ok=True)
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(doc.text)
                    print(f"✅ Saved to {filepath}")
            except Exception as e:
                print(f"❌ Failed to fetch {url}: {e}")

    scraped_documents_path = Path(data_dir) / "General_News/scraped_texts"
    if  scraped_documents_path.exists() and len(os.listdir(str(scraped_documents_path)))>0:
        scraped_documents = SimpleDirectoryReader(str(Path(DATA_DIR) / "General_News/scraped_texts")).load_data()
        documents += scraped_documents

    experiences_folder_path = Path(data_dir) / "uploaded_experiences/text"
    # experiences_folder_is_empty = not os.listdir(str(Path(DATA_DIR) / "uploaded_experiences/text"))
    if experiences_folder_path.exists() and len(os.listdir(str(experiences_folder_path)))>0:
        new_uploads = SimpleDirectoryReader(str(Path(data_dir) / "uploaded_experiences"), recursive=True).load_data()
        documents += new_uploads
        #Why is this commented out? []
        # user_experiences = SimpleDirectoryReader(str(Path(DATA_DIR) / "uploaded_experiences/text")).load_data()
        # documents += user_experiences

    vector_index = VectorStoreIndex.from_documents(documents)
    vector_index.storage_context.persist(persist_dir=index_dir)


    context = '\n'.join([doc.text for doc in documents])
    text_index, chunks = prepare_text_index(context)

    pickle.dump(text_index, open(index_dir+'/text_index.pkl','wb'))
    pickle.dump(chunks, open(index_dir+'/chunks.pkl','wb'))


    print('Done')

    return vector_index, text_index, chunks



def build_or_load_index(avatar_id='0', drive_folder_id=DRIVE_FOLDER_ID, refresh=False):
    Settings.embed_model = HuggingFaceEmbedding(model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    index_dir = 'avatars_context/' + avatar_id+'/index'
    data_dir = 'avatars_context/' + avatar_id+'/data'

    index_ready = (
        os.path.exists(index_dir)

        #Vector index
        and os.path.exists(os.path.join(index_dir, "docstore.json"))
        and os.path.exists(os.path.join(index_dir, "index_store.json"))

        #Text index
        and os.path.exists(os.path.join(index_dir, "text_index.pkl"))
        and os.path.exists(os.path.join(index_dir, "chunks.pkl"))
    )

    if index_ready and not refresh:
        print('Loading index from storage...')
        storage_context = StorageContext.from_defaults(persist_dir=index_dir)
        vector_index = load_index_from_storage(storage_context)

        text_index = pickle.load(open(index_dir+'/text_index.pkl','rb'))
        chunks = pickle.load(open(index_dir+'/chunks.pkl','rb'))
        return vector_index, text_index, chunks

    #Index needs to be built and loaded
    vector_index, text_index, chunks = build_index(avatar_id, drive_folder_id)
    
    return vector_index, text_index, chunks





def prepare_query_engines(avatar_id='0', drive_folder_id=DRIVE_FOLDER_ID, refresh=False):
    if refresh==True:
        vector_index, text_index, chunks = build_index(avatar_id='0', drive_folder_id=DRIVE_FOLDER_ID)
    else:
        vector_index, text_index, chunks = build_or_load_index(avatar_id='0', drive_folder_id=DRIVE_FOLDER_ID)

    # query_llm = get_llm('gwdg', "mistral-large-instruct", system_prompt= 'Provide an accurate response to the given query:')
    vector_index_query_engine = vector_index.as_retriever(similarity_top_k=5, verbose=True)
    # vector_index_query_engine = vector_index.as_query_engine(llm=vector_query_llm,similarity_top_k=10, verbose=True)
    text_index_query_engine = search_text_index

    return vector_index_query_engine, text_index_query_engine, text_index, chunks


# vector_index_query_engine, text_index_query_engine, text_index, chunks = prepare_query_engines()




def fetch_text_index_query(conversation):
    global text_query_llm
    print('Fetching context from text index...')
    query_prompt = 'Here is the conversation: ' + format_history_as_string(conversation) #+ '\nUser: '+prompt #response[:response.find('")')]
    # print('Query prompt: ', query_prompt)

    query = str(text_query_llm.complete(query_prompt))
    # print('Crafted Query: ', query)
    return query


def fetch_vector_index_context(vector_index_query_engine, query):
    print('Fetching context from vector index...')
    v_response =  vector_index_query_engine.retrieve(query)
    response = "\n\n".join(r.node.text for r in v_response)
    # response =  vector_index_query_engine.query(query)
    # print('\n\nContext from vector index: ', response)

    response = "\n\n".join(
        "".join(ch for ch in r.node.text if 32 <= ord(ch) <= 126 or ch in "\n\r\t") #Why tf is there binary data in the results?
        for r in v_response
    )

    print('Done fetching context from vector index...')
    return response





def RAG(avatar_rag_tools, query, translated=False): #, text_index_query=None):
    # keywords_for_text_based_retrieval 
    if translated==False: #text_index_query==None:
        en_keywords, de_keywords = extract_keywords(query)
    else:
        en_keywords, de_keywords = [word.split(', ') for word in query.split('|')] #extract_keywords(text_index_query)
    print('Keywords for text-based retrieval: ', en_keywords, de_keywords)

    with ThreadPoolExecutor(max_workers=2) as executor:
        thread_0 = executor.submit(fetch_vector_index_context, avatar_rag_tools[0], ', '.join(en_keywords+de_keywords))# query)
        thread_1 = executor.submit(avatar_rag_tools[1], avatar_rag_tools[2], avatar_rag_tools[3], en_keywords, de_keywords)

        wait([thread_0,thread_1])

    # context_from_text_index = thread_0
    context_from_vector_index =  thread_0.result() #.response
    context_from_text_index = thread_1.result()
    context_from_text_index = '\n'.join(context_from_text_index)

    total_context = '\nContext from text-based retrieval: \n' +context_from_text_index + '\n------------\nContext from vector-based retrieval: \n' + context_from_vector_index

    total_context = 'Here is relevant information about the Lahn (Sometimes the text-retrieval has relevant information that the vector-retrieval doesn\'t, or vice versa. Look through each comprehensively, to extract the most relevant information you need. Even if the Vector-retrieval says there\'s no information available, still scrutinize the Text-retrieval results to fetch relevant info. Also make sure to reply in the same language the user messaged you in -not necessarily the language in which this context is expressed. If the user messaged you in English, reply in English as well, even if this context is in German. If the user messaged you in German, respond in German, if it was Portuguese, respond in Portuguese, etc.' + total_context

    printable = " | ".join(
        line.strip()
        for line in total_context.splitlines()
        if line.strip()
    )
    print('-----\n\nRAG result: ', printable)
    return printable