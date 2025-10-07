import os
import asyncio
import base64
import numpy as np
import soundfile as sf
import sounddevice as sd
from dotenv import load_dotenv
from openai import AsyncAzureOpenAI
from websockets.exceptions import ConnectionClosedOK, ConnectionClosedError

# Load Azure API key
load_dotenv()
AZURE_KEY = os.getenv("AZURE_KEY")
if not AZURE_KEY:
    raise RuntimeError("AZURE_KEY not set in environment")

# Azure OpenAI endpoint and deployment
AZURE_ENDPOINT = "https://aditu-openai-resource-2.openai.azure.com"
API_VERSION = "2024-10-01-preview"
DEPLOYMENT_ID = "gpt-4o-mini-realtime-preview"

# Audio settings
INPUT_SAMPLERATE = 16000   # Hz for recording
# Azure realtime currently outputs PCM16 at 24 kHz by default
OUTPUT_SAMPLERATE = 24000  # Hz for playback/writing WAV
DURATION = 5               # seconds to record

async def main():
    # 1) Record from microphone
    print(f"⏺️ Recording for {DURATION}s at {INPUT_SAMPLERATE}Hz...")
    audio_arr = sd.rec(int(DURATION * INPUT_SAMPLERATE), samplerate=INPUT_SAMPLERATE,
                       channels=1, dtype="int16")
    sd.wait()
    audio_bytes = audio_arr.tobytes()
    audio_b64 = base64.b64encode(audio_bytes).decode()
    print(f"Recorded {len(audio_bytes)} bytes of audio.")

    # 2) Initialize Azure client and connect
    client = AsyncAzureOpenAI(
        azure_endpoint=AZURE_ENDPOINT,
        api_key=AZURE_KEY,
        api_version=API_VERSION,
    )
    try:
        async with client.beta.realtime.connect(model=DEPLOYMENT_ID) as conn:
            # 3) Session update
            print("⏳ Sending session.update...")
            await conn.session.update(session={
                "modalities": ["text", "audio"],
                "voice": "alloy",
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16"
            })
            # Wait for confirmation
            async for ev in conn:
                if ev.type == "session.updated":
                    print("✅ session.updated received")
                    break
                elif ev.type == "error":
                    print("❌ Session error:", ev.model_dump())
                    return

            # 4) Send audio input
            print("➡️ Sending audio input...")
            await conn.conversation.item.create(item={
                "type": "message",
                "role": "user",
                "content": [{"type": "input_audio", "audio": audio_b64}]
            })
            # Drain until committed
            async for ev in conn:
                if ev.type == "conversation.item.created":
                    break

            # 5) Request assistant response
            print("➡️ Requesting assistant response...")
            await conn.response.create(response={"modalities": ["text", "audio"]})

            # 6) Stream response
            text_parts = []
            audio_buf = bytearray()
            async for ev in conn:
                if ev.type == "response.text.delta":
                    print(ev.delta, end="", flush=True)
                    text_parts.append(ev.delta)
                elif ev.type == "response.audio.delta":
                    audio_buf.extend(base64.b64decode(ev.delta))
                elif ev.type == "response.done":
                    print()  # newline
                    break

            # 7) Output results
            full_text = "".join(text_parts)
            print(f"Assistant: {full_text}")

            if audio_buf:
                # Convert to numpy array
                audio_np = np.frombuffer(audio_buf, dtype="int16")
                # Save at the correct output rate
                sf.write("output.wav", audio_np, OUTPUT_SAMPLERATE)
                # Normalize int16 to float32 [-1,1] for playback
                audio_float = audio_np.astype(np.float32) / np.iinfo(np.int16).max
                # Play at the expected output rate
                sd.play(audio_float, OUTPUT_SAMPLERATE)
                sd.wait()
            else:
                print("⚠️ No audio received.")
    except (ConnectionClosedOK, ConnectionClosedError) as e:
        print(f"⚠️ Connection closed: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
