
import numpy as np

import torch, torchaudio
import subprocess, time
from transformers import WhisperProcessor, WhisperForConditionalGeneration


import os, io, shutil
from openai import AzureOpenAI, AsyncAzureOpenAI
import base64

from dotenv import load_dotenv
from typing import Any, List


import requests
import pandas as pd
from llama_index.experimental.query_engine import PandasQueryEngine
from llama_index.core.memory.types import BaseMemory


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

    def _get_df(self):
        now = time.time()
        if self._cached_df is None or (now - self._last_fetch) > self.cache_ttl:
            print("Fetching new sensor data...")
            self._cached_df = fetch_lahn_sensors_df()
            self._last_fetch = now
        return self._cached_df

    def _repair_and_retry(self, query: str, max_retries: int = 3) -> str:
        """
        Attempts to repair and re-run a failed PandasQueryEngine query.
        The LLM is prompted with the previous error and asked to fix the code.
        """
        import traceback
        from llama_index.experimental.exec_utils import safe_exec
        import pandas as pd

        df = self._get_df()
        last_error = None
        last_code = None

        for attempt in range(max_retries):
            try:
                print(f"🧠 Repair attempt {attempt+1} for query: {query}")
                # 1️⃣ Ask the LLM to generate or repair the code
                if attempt == 0:
                    prompt = (
                        f"You are a Pandas data analysis assistant.\n"
                        f"Write correct, runnable Python code (no markdown, no comments) "
                        f"that uses the pandas DataFrame `df` to answer this question:\n\n{query}\n"
                        "Store your final answer in a variable called `result`."
                    )
                else:
                    prompt = (
                        f"The previous code failed with this error:\n{last_error}\n\n"
                        f"Previous code:\n{last_code}\n\n"
                        "Fix it and produce new valid Python code (no markdown, no comments). "
                        "Make sure to store the answer in a variable called `result`."
                    )

                response = self.llm.complete(prompt)
                response = response.text if hasattr(response, "text") else str(response)
                code = (
                    response.strip()
                    .replace("```python", "")
                    .replace("```", "")
                    .strip()
                )
                last_code = code

                print(f"🧩 Generated code:\n{code}\n")

                # 2️⃣ Attempt execution safely
                local_vars = {"df": df, "pd": pd}
                safe_exec(code, {}, local_vars)

                if "result" in local_vars:
                    print("✅ Code executed successfully after repair.")
                    return str(local_vars["result"])
                else:
                    print("⚠️ Code ran but produced no explicit result variable.")
                    return "✅ Code executed successfully (no explicit result)."

            except Exception as e:
                last_error = traceback.format_exc()
                print(f"❌ Error during repair attempt {attempt+1}:\n{last_error}\n")

        # 3️⃣ If all repair attempts failed
        return f"❌ Unable to repair query after {max_retries} attempts.\nLast error:\n{last_error}"


    def __call__(self, query: str) -> str:
        print('Calling Lahn Sensors Tool...')
        df = self._get_df()
        if self._engine is None:
            self._engine = PandasQueryEngine(df=df, llm=self.llm, verbose=True, synthesize_response=False)
        else:
            self._engine.df = df

        try:
            result = self._engine.query(query).response
            # If the response contains an embedded Pandas failure message, trigger repair
            if isinstance(result, str) and "Error message:" in result:
                print("⚠️ Detected embedded error message in response — invoking repair loop...")
                return self._repair_and_retry(query)
            return result

        except Exception as e:
            print(f"⚠️ PandasQueryEngine error: {e}")
            print("Retrying once...")
            try:
                return self._engine.query(query).response
            except Exception as e2:
                print(f"⚠️ Retry failed: {e2}")
                print("Invoking intelligent repair-and-retry loop...")
                return self._repair_and_retry(query)

    def query(self, query_str: str) -> str:
        """
        Alias so that QueryEngineTool can call .query(...)
        under the hood. Simply forwards to __call__.
        """
        return self(query_str)


# class NoMemory(BaseMemory):
#     """
#     A no-op memory implementation for LlamaIndex v0.12.35.
#     All methods are implemented but do nothing or return empty.
#     """

#     @classmethod
#     def from_defaults(cls, **kwargs: Any) -> "NoMemory":
#         # Ignoring any kwargs; just return an instance
#         return cls()

#     def put(self, message: Any) -> None:
#         # Called when the agent tries to store a message. Do nothing.
#         return

#     async def aput(self, message: Any) -> None:
#         # Async version of put. Do nothing.
#         return

#     def get(self, input=None) -> List[Any]:
#         # Called when the agent wants to retrieve “relevant” memory.
#         # Always return an empty list (no history).
#         return []

#     async def aget(self) -> List[Any]:
#         # Async version of get. Always return empty.
#         return []

#     def get_all(self) -> List[Any]:
#         # Called when the agent wants all memory. Return empty.
#         return []

#     async def aget_all(self) -> List[Any]:
#         # Async version. Return empty.
#         return []

#     def set(self, messages: List[Any]) -> None:
#         # Replace entire memory store with new messages. We ignore.
#         return

#     async def aset(self, messages: List[Any]) -> None:
#         # Async version of set. Do nothing.
#         return

#     def reset(self) -> None:
#         # Clear all memory. We have none, so do nothing.
#         return

#     async def areset(self) -> None:
#         # Async version of reset. Do nothing.
#         return

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