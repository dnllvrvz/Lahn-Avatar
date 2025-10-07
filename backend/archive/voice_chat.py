import os
import json
import base64
import asyncio
from dotenv import load_dotenv
from openai import AsyncAzureOpenAI

load_dotenv()
AZURE_KEY = os.getenv("AZURE_KEY")
if not AZURE_KEY:
    raise RuntimeError("AZURE_KEY not set in .env")

DEPLOYMENT_ID = "gpt-4o-realtime-preview"
API_VERSION    = "2024-10-01-preview"
ENDPOINT       = (
    f"wss://aditu-openai-resource-2.openai.azure.com"
    f"/openai/realtime?api-version={API_VERSION}&deployment={DEPLOYMENT_ID}"
)

async def main() -> None:
    client = AsyncAzureOpenAI(
        azure_endpoint=ENDPOINT,
        api_key=AZURE_KEY,
        api_version="2025-04-01-preview",
    )

    async with client.beta.realtime.connect(model=DEPLOYMENT_ID) as connection:
        # 1) Enable both audio + text
        await connection.session.update(session={"modalities": ["text", "audio"]})

        # 2) Wait for session.updated
        print("⏳ Waiting for session.updated…")
        async for event in connection:
            print(f"EVENT: {event.type}")
            if event.type == "session.updated":
                print("✅ session.updated received")
                break

        # 3) Quick text-only ping test
        print("⏳ Sending a text-only ping…")
        await connection.conversation.item.create(item={
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "ping"}]
        })
        await connection.response.create(response={"modalities": ["text"]})

        # Capture full ping response
        ping_response = []
        async for event in connection:
            if event.type == "response.text.delta":
                print(event.delta, end="", flush=True)
                ping_response.append(event.delta)
            elif event.type == "response.done":
                full_text = "".join(ping_response)
                print(f"\n🎉 Ping response: '{full_text}'\n")
                break

        # 4) Main conversational loop
        while True:
            user_input = input("Enter a message (or q to quit): ")
            if user_input.strip().lower() == "q":
                break

            # send user prompt
            await connection.conversation.item.create(item={
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": user_input}]
            })
            # request both text+audio response
            await connection.response.create(response={"modalities": ["text", "audio"]})

            # accumulate text deltas
            response_text = []
            async for event in connection:
                # debug unexpected events
                if event.type not in {
                    "response.text.delta",
                    "response.audio.delta",
                    "response.audio_transcript.delta",
                    "response.text.done",
                    "response.done"
                }:
                    print(f"[Debug {event.type}]:", event.model_dump())

                if event.type == "response.text.delta":
                    # print and accumulate
                    print(event.delta, end="", flush=True)
                    response_text.append(event.delta)
                elif event.type == "response.audio.delta":
                    audio_bytes = base64.b64decode(event.delta)
                    print(f"🔊 Received {len(audio_bytes)} bytes of audio")
                elif event.type == "response.text.done":
                    # final text may be empty; print accumulated
                    final = "".join(response_text)
                    print(f"Assistant: {final}")
                elif event.type == "response.done":
                    print("— response complete —")
                    break

if __name__ == "__main__":
    asyncio.run(main())
