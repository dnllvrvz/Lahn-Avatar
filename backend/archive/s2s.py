import os
import asyncio
import base64
import numpy as np
import soundfile as sf
import sounddevice as sd
from dotenv import load_dotenv
from openai import AsyncOpenAI
from websockets.exceptions import ConnectionClosedOK, ConnectionClosedError

# Load API key
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise RuntimeError("OPENAI_API_KEY not set in environment")

# Model and audio settings
MODEL_NAME = "gpt-4o-realtime-preview"
SAMPLERATE = 16000  # 16 kHz
DURATION = 5        # seconds to record

async def main():
    # 1) Record from microphone
    print(f"⏺️ Recording for {DURATION}s at {SAMPLERATE}Hz...")
    audio_arr = sd.rec(int(DURATION * SAMPLERATE), samplerate=SAMPLERATE,
                       channels=1, dtype="int16")
    sd.wait()
    audio_bytes = audio_arr.tobytes()
    audio_b64 = base64.b64encode(audio_bytes).decode()
    print(f"Recorded {len(audio_bytes)} bytes of audio.")

    # 2) Initialize client and connect
    client = AsyncOpenAI(api_key=API_KEY)
    try:
        async with client.beta.realtime.connect(model=MODEL_NAME) as conn:
            # 3) Session update with correct parameters
            print("⏳ Sending session.update...")
            await conn.session.update(session={
                "modalities": ["text", "audio"],
                "voice": "alloy",
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16"
            })
            # wait for session.updated or error
            async for ev in conn:
                print(f"EVENT: {ev.type} => {ev.model_dump()}")
                if ev.type == "session.updated":
                    print("✅ session.updated received")
                    break
                elif ev.type == "error":
                    print("❌ Session error details:", ev.model_dump())
                    return

            # 4) Send audio input and wait for server to commit it
            print("➡️ Sending audio input...")
            await conn.conversation.item.create(item={
                "type": "message",
                "role": "user",
                "content": [{"type": "input_audio", "audio": audio_b64}]
            })
            # wait for conversation.item.created event or error
            async for ev in conn:
                print(f"EVENT: {ev.type} => {ev.model_dump()}")
                if ev.type == "conversation.item.created":
                    print("✅ conversation.item.created")
                    break
                elif ev.type == "error":
                    print("❌ Audio commit error details:", ev.model_dump())
                    return

            # 5) Request both text + audio response
            print("➡️ Requesting assistant response...")
            await conn.response.create(response={"modalities": ["text", "audio"]})

            # 6) Stream the assistant response
            text_parts = []
            audio_buf = bytearray()
            async for ev in conn:
                print(f"EVENT: {ev.type} => {ev.model_dump()}")
                if ev.type == "response.text.delta":
                    print(ev.delta, end="", flush=True)
                    text_parts.append(ev.delta)
                elif ev.type == "response.audio.delta":
                    audio_buf.extend(base64.b64decode(ev.delta))
                elif ev.type == "response.done":
                    print()  # newline
                    break
                # handle any unexpected event types
                else:
                    # Already logged full ev.model_dump above
                    pass

            # 7) Output results
            full_text = "".join(text_parts)
            print(f"Assistant: {full_text}")
            if audio_buf:
                audio_np = np.frombuffer(audio_buf, dtype="int16")
                sf.write("output.wav", audio_np, SAMPLERATE)
                print("Saved audio to output.wav")
                sd.play(audio_np, SAMPLERATE)
                sd.wait()
            else:
                print("⚠️ No audio received.")
    except Exception as e:
        print(f"❌ Error establishing connection or during session: {e}")

if __name__ == "__main__":
    asyncio.run(main())
