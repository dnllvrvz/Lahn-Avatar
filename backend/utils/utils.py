
import numpy as np

import soundfile as sf
import torch, torchaudio
import subprocess
from transformers import WhisperProcessor, WhisperForConditionalGeneration


import os, io, shutil
from openai import AzureOpenAI, AsyncAzureOpenAI
import base64

from dotenv import load_dotenv



import requests
import pandas as pd
from llama_index.core.query_engine.pandas import PandasQueryEngine

whisper_device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"🔄 Loading Whisper model on {whisper_device}...")
whisper_processor = WhisperProcessor.from_pretrained("openai/whisper-small")
whisper_model = WhisperForConditionalGeneration.from_pretrained("openai/whisper-small").to(whisper_device)
print("✅ Whisper model loaded.")




# 1) Fetch & normalize your ThingSpeak data
THINGSPEAK_URL = (
    "https://api.thingspeak.com/channels/2974588/feeds.json?results=100"
)

def fetch_lahn_sensors_df() -> pd.DataFrame:
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

# 2) Wrap it in a callable that runs PandasQueryEngine on demand
class LahnSensorsTool:
    name = "lahn_sensors"
    description = (
        "Use this to answer analytical questions about the live Lahn Atlas sensor data "
        "(pH, DO, Temp, EC, Humidity, CO2) fetched from the ThingSpeak REST API."
    )

    def __init__(self, llm):
        # store whichever LLM you pass in (e.g. get_llm("mistral-large-instruct"))
        self.llm = llm

    def __call__(self, query: str) -> str:
        print('Calling Lahn Sensors Tool...')
        # fetch fresh data
        df = fetch_lahn_sensors_df()
        # spin up a Pandas‐powered engine on it
        engine = PandasQueryEngine(
            df=df,
            llm=self.llm,             # or your preferred LLM wrapper
            verbose=True,             # shows generated pandas code
            synthesize_response=True, # narrative answer
        )
        # run the query & return the natural‐language result
        result = engine.query(query)
        return result.response



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

    
def transcribe_audio(file_path):
    temp_wav_path = file_path.rsplit(".", 1)[0] + "_converted.wav"
    convert_to_wav(file_path, temp_wav_path)

    speech, sr = torchaudio.load(temp_wav_path)
    input_features = whisper_processor(
        speech.squeeze(), sampling_rate=sr, return_tensors="pt"
    ).input_features.to(whisper_device)

    predicted_ids = whisper_model.generate(input_features)
    transcription = whisper_processor.batch_decode(predicted_ids, skip_special_tokens=True)[0]
    return transcription




load_dotenv()
# Azure OpenAI config
AZURE_KEY = os.getenv("AZURE_KEY")
if not AZURE_KEY:
    raise RuntimeError("AZURE_KEY not set in environment")
AZURE_ENDPOINT = "https://aditu-openai-resource-2.openai.azure.com"
API_VERSION = "2024-10-01-preview"
DEPLOYMENT_ID = "gpt-4o-mini-realtime-preview"

# Audio settings
INPUT_FORMAT = 'pcm16'
OUTPUT_SAMPLERATE = 24000  # Hz for playback/writing WAV
TARGET_SR = 16000  

async def azure_speech_response_func(input_path: str) -> tuple[str, bytes]:
    wav_file = input_path.split('.')[0] + ".wav"

    # print('Input path: ', input_path, 'Output path: ', wav_file)

    subprocess.run([
        "ffmpeg", "-y", "-i", input_path,
        "-ar", str(TARGET_SR), "-ac", "1", "-f", "wav", wav_file
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 1) Read and encode input audio
    data, sr = sf.read(wav_file, dtype='int16')
    os.remove(wav_file)
    audio_b64 = base64.b64encode(data.tobytes()).decode()

    # 2) Setup Azure client and connect
    client = AsyncAzureOpenAI(
        azure_endpoint=AZURE_ENDPOINT,
        api_key=AZURE_KEY,
        api_version=API_VERSION,
    )

	# Get the directory where the current script is located
    base_dir = os.path.dirname(os.path.abspath(__file__))
    # print('Base directory: ', base_dir)

	# Build a path to the target file
    file_path = os.path.join(base_dir, 'system_prompt.txt')

    system_prompt = open(file_path, 'r').read()
    # print('System prompt: ', system_prompt[:50])

    async with client.beta.realtime.connect(model=DEPLOYMENT_ID) as conn:
        # Session update
        await conn.session.update(session={
            "modalities": ["text", "audio"],
            "instructions": system_prompt,
            "voice": "alloy",
            "input_audio_format": INPUT_FORMAT,
            "output_audio_format": INPUT_FORMAT
        })
        # wait for session.updated
        async for ev in conn:
            if ev.type == "session.updated":
                break
            if ev.type == "error":
                raise RuntimeError(f"Session error: {ev.model_dump()}")

        # Send user audio
        await conn.conversation.item.create(item={
            "type": "message",
            "role": "user",
            "content": [{"type": "input_audio", "audio": audio_b64}]
        })
        # drain until committed
        async for ev in conn:
            # print('Creating conversation item for user message...')
            if ev.type == "conversation.item.created":
                # print('Created conversation item for user message.')
                break

        # Request response
        await conn.response.create(response={"modalities": ["text", "audio"]})

        # Stream back text + collect audio
        text_parts = []
        audio_buf = bytearray()
        async for ev in conn:
            if ev.type == "response.text.delta":
                text_parts.append(ev.delta)
            elif ev.type == "response.audio.delta":
                audio_buf.extend(base64.b64decode(ev.delta))
            elif ev.type == "response.done":
                break

    # Prepare return values
    reply_text = "".join(text_parts)
    # Convert raw PCM bytes to WAV bytes
    audio_np = np.frombuffer(audio_buf, dtype='int16')
    bio = io.BytesIO()
    sf.write(bio, audio_np, OUTPUT_SAMPLERATE, format='WAV', subtype='PCM_16')
    return reply_text, bio.getvalue()
