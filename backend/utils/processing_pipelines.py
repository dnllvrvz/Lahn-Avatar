#!/usr/bin/env python3

import os, io
import json
import time
import wave
import threading
import queue
from typing import Optional, Tuple
import numpy as np
import requests
import websocket

from .avatar import RAG, sensor_query_llm
from .utils import LahnSensorsTool

sensor_query_tool = LahnSensorsTool(sensor_query_llm)

class OpenAIRealtimeClient:
    """Client for OpenAI's Realtime API using WebSocket."""
    
    def __init__(self, api_key: str, model: str = "gpt-realtime", prompt='', streaming=False, ws_client=None):
        self.api_key = api_key
        self.model = model
        # OpenAI Realtime API WebSocket URL with model selection
        self.ws_url = f"wss://api.openai.com/v1/realtime?model={model}"
        
        # Model pricing (input/output per 1M tokens)
        self.pricing = {
            "gpt-realtime": {"input": 32.0, "output": 64.0},  # Current realtime pricing
            "gpt-4o-realtime-preview": {"input": 40.0, "output": 80.0}  # GPT-4o realtime pricing
        }
        self.response_queue = queue.Queue()
        self.ws = None
        self.session_id = None
        self.audio_buffer = bytearray()
        self.response_complete = threading.Event()
        self.input_transcript = ""
        self.output_transcript = ""
        self.awaiting_function_response = False
        self.current_response_has_function_call = False

        self.prompt = prompt + '\n Note: Always reply in the same language as the user. The language you speak, should mirror theirs. No language-choice inconsistencies. For example if the user messaged you in English, reply in English as well. Same for German, Portuguese etc.'
        self.streaming = streaming
        self.ws_client = ws_client


    def append_audio(self, base64_chunk):
        """Forward each base64 audio chunk to OpenAI if connected, else buffer."""
        try:
            if self.ws and getattr(self.ws, "sock", None) and self.ws.sock.connected:
                # 🔹 Send chunk directly to OpenAI realtime API
                self.ws.send(json.dumps({
                    "type": "input_audio_buffer.append",
                    "audio": base64_chunk
                }))
            else:
                # 🔹 No active OpenAI socket yet → buffer locally
                import base64
                decoded = base64.b64decode(base64_chunk)
                self.audio_buffer.extend(decoded)

            # Optional: let browser know chunk was received
            if self.ws_client:
                self.ws_client.send(json.dumps({"status": "audio_chunk_received"}))
        except Exception as e:
            print(f"[WARN] append_audio failed: {e}")


    def commit_audio_buffer(self):
        """Tell OpenAI that user input is finished and request a response."""
        try:
            if self.ws and getattr(self.ws, "sock", None) and self.ws.sock.connected:
                # 🔹 Finalize the current audio input buffer
                self.ws.send(json.dumps({"type": "input_audio_buffer.commit"}))

                # 🔹 Ask OpenAI to generate a response (audio + text)
                self.ws.send(json.dumps({
                    "type": "response.create",
                    "response": {
                        "modalities": ["audio"],
                        "instructions": self.prompt
                    }
                }))
            else:
                print("⚠️ No active OpenAI websocket — cannot commit.")
        except Exception as e:
            print(f"[WARN] commit_audio_buffer failed: {e}")


    def connect_to_openai(self):
        """Establish a persistent connection to the OpenAI Realtime API."""

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "OpenAI-Beta": "realtime=v1"
        }

        print("🔄 Connecting to OpenAI Realtime API...")
        self.ws = websocket.WebSocketApp(
            self.ws_url,
            header=headers,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close
        )

        ws_thread = threading.Thread(target=self.ws.run_forever, daemon=True)
        ws_thread.start()

        # Wait briefly until on_open fires
        for _ in range(20):
            if getattr(self.ws, "sock", None) and self.ws.sock.connected:
                print("✅ OpenAI realtime websocket ready.")
                return
            time.sleep(0.1)

        raise RuntimeError("Failed to connect to OpenAI realtime websocket.")






    def process_audio(self, audio_input: str) -> Tuple[Optional[bytes], float, dict]:
        """Send audio to OpenAI Realtime API and get response."""
        start_time = time.time()
        
        # Read audio file and convert to 24kHz as required by API
        # with wave.open(audio_file, 'rb') as wf:

        # Open audio
        if isinstance(audio_input, (bytes, bytearray)):
            wf = wave.open(io.BytesIO(audio_input), 'rb')
        elif hasattr(audio_input, "read"):  # file-like, e.g. BytesIO
            wf = wave.open(audio_input, 'rb')
        else:  # assume path
            wf = wave.open(audio_input, 'rb')

        frames = wf.getnframes()
        rate = wf.getframerate()
        audio_data = wf.readframes(frames)
        input_duration = frames / float(rate)
        
        # print(f"📊 Input audio: {rate}Hz, {input_duration:.2f}s, {len(audio_data)} bytes")
        
        # Convert to 24kHz if needed (API requires 24kHz)
        if rate != 24000:
            # print(f"⚠️  Converting audio from {rate}Hz to 24000Hz for Realtime API...")
            # Simple resampling - for production use scipy.signal.resample
            import numpy as np
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            # Resample to 24kHz
            resample_ratio = 24000 / rate
            new_length = int(len(audio_array) * resample_ratio)
            resampled = np.interp(
                np.linspace(0, len(audio_array) - 1, new_length),
                np.arange(len(audio_array)),
                audio_array
            ).astype(np.int16)
            pcm_data = resampled.tobytes()
        else:
            # Use the raw audio data directly
            pcm_data = audio_data
        
        # print(f"📊 PCM data ready: {len(pcm_data)} bytes")
        
        # We'll calculate actual input tokens from the transcript after processing
        # (OpenAI provides input transcript via input_audio_transcription events)
        input_tokens = 0  # Will be updated from actual transcript
        
        response_audio = None
        output_tokens = 0
        error = None
        # Initialize token counters (will be updated from transcripts)
        actual_input_tokens = 0
        actual_output_tokens = 0
        self.audio_buffer = bytearray()
        self.response_complete.clear()
        self.input_transcript = ""
        self.output_transcript = ""
        self.awaiting_function_response = False
        self.current_response_has_function_call = False
        
        try:
            # Create WebSocket connection
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "OpenAI-Beta": "realtime=v1"
            }
            
            print("🔄 Connecting to OpenAI Realtime API...")
            self.ws = websocket.WebSocketApp(
                self.ws_url,
                header=headers,
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close
            )
            
            # Start WebSocket in a separate thread
            ws_thread = threading.Thread(target=self.ws.run_forever)
            ws_thread.daemon = True
            ws_thread.start()
            
            # Wait for session to be created
            session_timeout = 5
            session_start = time.time()
            while not self.session_id and time.time() - session_start < session_timeout:
                time.sleep(0.1)
            
            if not self.session_id:
                raise Exception("Failed to establish session with Realtime API")
            
            # Send audio input
            if self.ws.sock and self.ws.sock.connected:
                # print("📤 Sending audio input...")
                
                # Convert audio to base64 (not hex!)
                import base64
                
                # Verify we have audio data
                if len(pcm_data) == 0:
                    raise Exception("No audio data to send!")
                
                # Check if audio is silent (all zeros or very low values)
                import numpy as np
                audio_check = np.frombuffer(pcm_data, dtype=np.int16)
                audio_max = np.max(np.abs(audio_check))
                # print(f"📊 Audio peak level: {audio_max} (out of 32767)")
                
                audio_base64 = base64.b64encode(pcm_data).decode('utf-8')
                
                # First, append audio to buffer
                audio_append_event = {
                    "type": "input_audio_buffer.append",
                    "audio": audio_base64  # Base64, not hex!
                }
                self.ws.send(json.dumps(audio_append_event))
                print(f"📤 Sent audio data: {len(pcm_data)} bytes as {len(audio_base64)} base64 chars")
                
                # Small delay to ensure audio is in buffer
                time.sleep(0.2)
                
                # Then commit the buffer
                commit_event = {
                    "type": "input_audio_buffer.commit"
                }
                self.ws.send(json.dumps(commit_event))
                # print("📤 Committed audio buffer")
                
                # Wait a bit for server to process the audio
                time.sleep(0.5)
                
                # Explicitly request a response
                response_event = {
                    "type": "response.create",
                    "response": {
                            "modalities": ["audio", "text"],
                            "instructions": "Function response: (What language was the user's last message to you in? Respond in precisely the same language. For example if the user messaged you in English, reply in English as well. Same for German, Portuguese etc)"
                            }
                }
                self.ws.send(json.dumps(response_event))
                print("📤 Requested response generation")
                
                print("⏳ Waiting for response...")
                
                # Wait for response completion
                if self.response_complete.wait(timeout=30):
                    # Small delay to ensure all events (including transcripts) are processed
                    time.sleep(0.2)
                    if len(self.audio_buffer) > 0:
                        response_audio = bytes(self.audio_buffer)
                        
                        # Calculate actual input tokens from transcript
                        if self.input_transcript:
                            actual_input_tokens = max(1, len(self.input_transcript) // 4)
                            # print(f"📊 Input tokens (from transcript): {actual_input_tokens}")
                            # print(f"   Input transcript: '{self.input_transcript}'")
                        else:
                            # Fallback to rough estimation if no input transcript
                            actual_input_tokens = int(input_duration * 100)
                            # print(f"📊 Input tokens (estimated - no transcript received): {actual_input_tokens}")
                            # print(f"   Warning: Input transcript was empty or not received")
                        
                        # Calculate actual output tokens from transcript
                        if self.output_transcript:
                            # Simple token estimation: ~4 characters per token (rough approximation)
                            actual_output_tokens = max(1, len(self.output_transcript) // 4)
                            # print(f"✅ Received audio response ({len(response_audio)} bytes)")
                            # print(f"   Output tokens (from transcript): {actual_output_tokens}")
                        else:
                            # Fallback to duration-based estimation if no transcript
                            output_duration = len(response_audio) / (24000 * 2)  # 24kHz, 16-bit
                            actual_output_tokens = int(output_duration * 100)
                            print(f"✅ Received audio response ({len(response_audio)} bytes)")
                            print(f"   Expected duration: {output_duration:.2f} seconds")
                            # print(f"   Output tokens (estimated from duration): {actual_output_tokens}")
                    else:
                        error = "No audio data received"
                else:
                    error = "Response timeout"
            
            # Close WebSocket with a small delay to ensure all data is received
            if self.ws:
                time.sleep(0.5)  # Small delay to ensure all audio chunks are received
                self.ws.close()
                ws_thread.join(timeout=2)
                
        except Exception as e:
            error = str(e)
            print(f"❌ OpenAI Realtime API error: {e}")
        
        # Stop timer here - before any playback
        end_time = time.time()
        elapsed_time = end_time - start_time
        print(f"⏱️  Total response time: {elapsed_time:.2f}s (playback not included)")
        
        # Prepare cost info
        # Note: Using actual transcripts for more accurate token counting
        # Input/output tokens calculated from OpenAI's provided transcripts
        model_pricing = self.pricing.get(self.model, self.pricing["gpt-realtime"])
        cost_info = {
            'input_tokens': actual_input_tokens,
            'output_tokens': actual_output_tokens,
            'input_cost': (actual_input_tokens / 1_000_000) * model_pricing["input"],
            'output_cost': (actual_output_tokens / 1_000_000) * model_pricing["output"],
            'total_cost': 0,
            'error': error,
            'model': self.model
        }
        cost_info['total_cost'] = cost_info['input_cost'] + cost_info['output_cost']
        cost_info['input_transcript'] = self.input_transcript
        cost_info['output_transcript'] = self.output_transcript
        
        return response_audio, elapsed_time, cost_info
    
    def _get_info_about_lahn(self, query: str):
        print('Function called: _get_info_about_lahn(). Query: ', query)
        print('Activating RAG...')
        context = RAG(query)

        return context

    def _get_sensor_data(self, query:str):
        print('Function called: _get_sensor_data(). Query: ', query)
        print('Calling Lahn Sensors Tool...')

        analysis = str(sensor_query_tool(query))
        print('Analysis: ', analysis)

        return analysis

    
    def _on_open(self, ws):
        """Handle WebSocket connection open."""
        print("✅ Connected to OpenAI Realtime API")

        # --- Add tool definitions ---
        tools = [
            {
                "type": "function",
                "name": "get_info_about_lahn",
                "description": (
                    "CALL THIS FUNCTION ON EVERY USER MESSAGE (except simple messages like 'Hello' which do not require a factual response). THIS IS THE AUTHORITATIVE SOURCE OF DATA ON THE LAHN. ALWAYS DEFER TO IT."
                    "Use for general factual or historical questions about the Lahn River "
                    "that do NOT involve live measurements or sensor data."
                    ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Info required"}
                    },
                    "required": ["query"]
                }
            },
            {
                "type": "function",
                "name": "get_sensor_data",
                "description": (
                    "Use ONLY for questions involving Lahn Atlas live data readings. Fetch and analyze live sensor data from the Lahn Atlas. "
                    "Use this for questions involving temperature, pH, dissolved oxygen, "
                    "electrical conductivity (water), or humidity and CO₂ (air). "
                    "The function can perform computations like averages, minimums, maximums, or trends over time."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": (
                                "Natural-language question about Lahn Atlas sensor readings, e.g. "
                                "'What was the lowest temperature last week?' or 'Show the trend in pH over the past day.'"
                            )
                        }
                    },
                    "required": ["query"]
                }
            }
        ]


        session_update = {
            "type": "session.update",
            "session": {
                "modalities": ["audio", "text"],
                "instructions": self.prompt, #"You are a helpful AI assistant. Give very short, direct answers.",
                "voice": "alloy",
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "input_audio_transcription": {"model": "whisper-1"},
                "turn_detection": None,
                "temperature": 0.7,
                "tools": tools
            }
        }
        ws.send(json.dumps(session_update))

    
    def _on_message(self, ws, message):
        """Handle incoming WebSocket messages."""
        try:
            data = json.loads(message)
            event_type = data.get('type')
            
            if event_type == 'session.created':
                self.session_id = data.get('session', {}).get('id')
                session_config = data.get('session', {})
                print(f"📋 Session created: {self.session_id}")
                # print(f"   - Voice: {session_config.get('voice', 'N/A')}")
                # print(f"   - Audio format: {session_config.get('input_audio_format', 'N/A')} -> {session_config.get('output_audio_format', 'N/A')}")
            
            elif event_type == 'response.created':
                # Reset the flag for each new response
                self.current_response_has_function_call = False
                print(f"🆕 New response created")

            elif event_type == 'response.audio.delta':
                # Accumulate audio chunks
                delta = data.get('delta', '')
                if delta:
                    if not self.streaming:
                        # Convert from base64 to bytes (not hex)
                        import base64
                        audio_chunk = base64.b64decode(delta)
                        self.audio_buffer.extend(audio_chunk)
                        # print(f"🎵 Received audio chunk: {len(audio_chunk)} bytes (total: {len(self.audio_buffer)} bytes)")
                    else:
                        self.ws_client.send(json.dumps({"delta": delta}))

            
            elif event_type == 'response.done':
                # Full response complete
                print(f"✅ Response generation complete")
                
                # If this response was a function call, wait for the next response with audio
                if self.current_response_has_function_call:
                    print("⏳ Function call response complete, waiting for audio response...")
                    # Don't set response_complete - we're waiting for the function result response
                else:
                    # This is either a direct response or the post-function-call audio response
                    if len(self.audio_buffer) == 0 and not self.awaiting_function_response:
                        print("⚠️  No audio data received in response")
                    elif len(self.audio_buffer) > 0:
                        print(f"✅ Audio response complete ({len(self.audio_buffer)} bytes)")
                    if not self.streaming:
                        self.response_complete.set()
                    self.awaiting_function_response = False
            
            elif event_type == 'response.text.delta':
                # Text response (shouldn't happen with audio modality)
                text_delta = data.get('delta', '')
                print(f"📝 Received text instead of audio: {text_delta}")
            
            elif event_type == 'response.text.done':
                # Complete text response
                text = data.get('text', '')
                print(f"📝 Complete text response: {text}")
            
            elif event_type == 'error':
                error_data = data.get('error', {})
                error_type = error_data.get('type', 'unknown_error')
                error_code = error_data.get('code', 'N/A')
                error_message = error_data.get('message', 'Unknown error')
                print(f"❌ API Error [{error_type}:{error_code}]: {error_message}")
                self.response_complete.set()
            
            elif event_type == 'input_audio_buffer.committed':
                item_id = data.get('item_id', 'unknown')
                print(f"✅ Audio buffer committed (item_id: {item_id})")
            
            elif event_type == 'conversation.item.input_audio_transcription.completed':
                # Input audio transcription
                transcript = data.get('transcript', '')
                self.input_transcript = transcript
                print(f"🎤 Input transcript: {transcript}")
            
            elif event_type == 'response.audio_transcript.delta':
                # Output audio transcript delta
                delta = data.get('delta', '')
                self.output_transcript += delta
            
            elif event_type == 'response.audio_transcript.done':
                # Output audio transcript complete
                transcript = data.get('transcript', '')
                if transcript:
                    self.output_transcript = transcript
                print(f"💬 Output transcript: {self.output_transcript}")

            #wrt function calling
            elif event_type == "response.function_call_arguments.delta":
                # The model is streaming function call arguments
                name = data.get("name", "")
                delta = data.get("delta", "")
                # print(f"🧩 Function call in progress: {name}, args delta: {delta}")
                # Mark that this response contains a function call
                self.current_response_has_function_call = True

            elif event_type == "response.function_call_arguments.done":
                # The model finished providing the arguments
                name = data.get("name")
                arguments = data.get("arguments")
                print(f"🧩 Function call requested: {name}({arguments})")
                
                # Mark that we're waiting for a function result response
                self.awaiting_function_response = True

                # Try to parse arguments safely
                try:
                    args = json.loads(arguments) if arguments else {}
                except json.JSONDecodeError:
                    args = {}

                # Route to your actual function
                result = None
                if name == "get_info_about_lahn":
                    result = self._get_info_about_lahn(**args)
                elif name == "get_sensor_data":
                    result = self._get_sensor_data(**args)

                # Send the result back to the model
                if result is not None:
                    ws.send(json.dumps({
                        "type": "response.create",
                        "response": {
                            "modalities": ["audio", "text"],
                            "instructions": "Function response: (What language was the user's last message to you in? Respond in precisely the same language. For example if the user messaged you in English, reply in English as well. Same for German, Portuguese etc)"+result
                        }
                    }))
                    print(f"📤 Sent function call response instructions for {name}")
                    print("⏳ Waiting for audio response after function call...")




            elif event_type in ['response.audio.done', 'session.updated', 'input_audio_buffer.speech_started', 'input_audio_buffer.speech_stopped', 'response.created', 'input_audio_buffer.cleared']:
                print('Event recieved: ', event_type)

            elif event_type == 'response.output_item.added':
                # Check if this output item is a function call
                item = data.get('item', {})
                item_type = item.get('type', '')
                if item_type == 'function_call':
                    self.current_response_has_function_call = True
                    print(f"🧩 Function call output item detected")
                print('Event recieved: response.output_item.added')
                        
            # Debug: print other event types
            elif event_type not in ['response.content_part.added', 
                       'conversation.item.created', 'response.content_part.done',
                       'rate_limits.updated', 'conversation.item.input_audio_transcription.delta',
                       'response.output_item.done']:
                print(f"📨 Other event: {event_type}")
                # For debugging, show more details for certain events
                if event_type in ['response.output_item.added', 'response.output_item.done']:
                    print(f"   Details: {json.dumps(data, indent=2)[:200]}...")
                    
        except Exception as e:
            print(f"❌ Error processing message: {e}")
            print(f"Raw message: {message[:200]}...")
    
    def _on_error(self, ws, error):
        """Handle WebSocket errors."""
        print(f"❌ WebSocket error: {error}")
        self.response_queue.put({'type': 'error', 'error': str(error)})
    
    def _on_close(self, ws, close_status_code, close_msg):
        """Handle WebSocket close."""
        if self.ws_client:
            try:
                self.ws_client.close()
            except:
                pass
        print("🔌 Disconnected from OpenAI Realtime API")




# class CartesiaOpenAIPipeline:
#     """Pipeline for Cartesia STT -> OpenAI GPT-4 -> Cartesia TTS."""
    
#     def __init__(self, cartesia_api_key: str, openai_api_key: str, prompt=''):
#         self.cartesia_api_key = cartesia_api_key
#         self.openai_api_key = openai_api_key
#         self.cartesia_base_url = "https://api.cartesia.ai"
#         self.last_stt_duration = 0  # For cost calculation
#         self.prompt = prompt
        
#     def process_audio(self, audio_input) -> Tuple[Optional[bytes], float, dict]:
#         """Process audio through the Cartesia-OpenAI pipeline."""
#         start_time = time.time()
#         cost_info = {
#             'stt_cost': 0,
#             'llm_cost': 0,
#             'tts_cost': 0,
#             'total_cost': 0,
#             'stt_time': 0,
#             'llm_time': 0,
#             'tts_time': 0,
#             'transcript': '',
#             'llm_response': '',
#             'error': None
#         }
        
#         try:
#             # Step 1: Speech-to-Text with Cartesia
#             stt_start = time.time()
#             transcript = self._speech_to_text(audio_input)
#             cost_info['stt_time'] = time.time() - stt_start
#             cost_info['transcript'] = transcript
            
#             if not transcript:
#                 raise Exception("Failed to transcribe audio")
            
#             print(f"📝 Transcript: {transcript}")
            
#             # Step 2: Process with OpenAI GPT-4
#             llm_start = time.time()
#             llm_response, llm_tokens = self._process_with_gpt4(transcript)

#             cost_info['llm_time'] = time.time() - llm_start
#             cost_info['llm_response'] = llm_response
            
#             if not llm_response:
#                 raise Exception("Failed to get GPT-4 response")
            
#             print(f"🤖 GPT-4o response: {llm_response}")
            
#             # Calculate LLM cost (GPT-4o pricing)
#             cost_info['llm_input_tokens'] = llm_tokens['input']
#             cost_info['llm_output_tokens'] = llm_tokens['output']
#             cost_info['llm_cost'] = (
#                 (llm_tokens['input'] / 1_000_000) * 2.50 +  # $2.50 per 1M input tokens
#                 (llm_tokens['output'] / 1_000_000) * 10.00  # $10.00 per 1M output tokens
#             )
            
#             # Step 3: Text-to-Speech with Cartesia
#             tts_start = time.time()
#             audio_response = self._text_to_speech(llm_response)
#             cost_info['tts_time'] = time.time() - tts_start
            
#             if not audio_response:
#                 raise Exception("Failed to synthesize speech")
            
#             # Calculate Cartesia costs
#             # WARNING: These are estimates based on available pricing info
#             # STT (Ink-Whisper): 1 credit per second of audio
#             # Using Pro tier pricing: $5 for 100K credits = $0.00005 per credit
#             if hasattr(self, 'last_stt_duration'):
#                 stt_credits = self.last_stt_duration  # 1 credit per second
#                 cost_info['stt_cost'] = stt_credits * 0.00005  # Pro tier pricing
#             else:
#                 # Fallback: estimate 150 words per minute speech rate
#                 estimated_seconds = (len(transcript.split()) / 150) * 60
#                 cost_info['stt_cost'] = estimated_seconds * 0.00005
            
#             # TTS (Sonic): 1 credit per character of INPUT text
#             # Note: It takes 750-800 credits to generate 1 minute of audio
#             tts_credits = len(llm_response)  # 1 credit per character
#             cost_info['tts_cost'] = tts_credits * 0.00005  # Pro tier pricing
            
#             # For reference: audio generation rate
#             # ~150 words/minute speaking rate, ~5 chars/word = ~750 chars/minute
#             # This aligns with Cartesia's 750-800 credits per minute of audio
            
#             # Calculate total cost
#             cost_info['total_cost'] = (
#                 cost_info['stt_cost'] + 
#                 cost_info['llm_cost'] + 
#                 cost_info['tts_cost']
#             )
            
#             # Add transcripts
#             cost_info['input_transcript'] = transcript
#             cost_info['output_transcript'] = llm_response
            
#             # Stop timer here - before any playback
#             end_time = time.time()
#             elapsed_time = end_time - start_time
#             print(f"⏱️  Total pipeline time: {elapsed_time:.2f}s (playback not included)")
            
#             return audio_response, elapsed_time, cost_info
            
#         except Exception as e:
#             cost_info['error'] = str(e)
#             print(f"❌ Pipeline error: {e}")
#             end_time = time.time()
#             elapsed_time = end_time - start_time
#             return None, elapsed_time, cost_info

#     def _get_info_about_lahn(self, query: str):
#         print('Function called: _get_info_about_lahn(). Query: ', query)
#         print('Activating RAG...')
#         context = RAG(query)

#         return context

#     def _get_sensor_data(self, query:str):
#         print('Function called: _get_sensor_data(). Query: ', query)
#         print('Calling Lahn Sensors Tool...')

#         analysis = str(sensor_query_tool(query))
#         print('Analysis: ', analysis)

#         return analysis
    
#     def _speech_to_text(self, audio_input) -> Optional[str]:
#         """Convert speech to text using Cartesia."""
#         try:
#             headers = {
#                 "Cartesia-Version": "2024-06-10",
#                 "X-API-Key": self.cartesia_api_key
#             }
            
#             # with open(audio_file, 'rb') as f:
#             #     files = {'file': ('audio.wav', f, 'audio/wav')}

#             if isinstance(audio_input, (bytes, bytearray)):
#                 file_tuple = ('audio.wav', io.BytesIO(audio_input), 'audio/wav')
#             elif hasattr(audio_input, "read"):  # already file-like
#                 file_tuple = ('audio.wav', audio_input, 'audio/wav')
#             else:  # assume path
#                 file_tuple = ('audio.wav', open(audio_input, 'rb'), 'audio/wav')

#             files = {'file': file_tuple}

#             data = {
#                 'model': 'ink-whisper',
#                 'language': 'en',
#                 'timestamp_granularities[]': 'word'  # Optional, for word timestamps
#             }
            
#             # Using the official Cartesia STT endpoint from docs
#             response = requests.post(
#                 f"{self.cartesia_base_url}/stt",
#                 headers=headers,
#                 files=files,
#                 data=data
#             )
            
#             if response.status_code == 200:
#                 result = response.json()
#                 # Store duration for cost calculation
#                 if hasattr(self, 'last_stt_duration'):
#                     self.last_stt_duration = result.get('duration', 0)
#                 return result.get('text', '')  # Note: API returns 'text' not 'transcript'
#             else:
#                 print(f"❌ Cartesia STT error: {response.status_code} - {response.text}")
#                 return None
                
#         except Exception as e:
#             print(f"❌ STT error: {e}")
#             return None
    
#     def _process_with_gpt4(self, text: str) -> Tuple[Optional[str], dict]:
#         """Process text with OpenAI GPT-4o."""
#         try:
#             headers = {
#                 "Authorization": f"Bearer {self.openai_api_key}",
#                 "Content-Type": "application/json"
#             }
            
#             data = {
#                 "model": "gpt-4o",
#                 "messages": [
#                     {"role": "system", "content": self.prompt}, #"You are a helpful AI assistant. Give very short, direct answers."},
#                     {"role": "user", "content": text}
#                 ],
#                 "tools": [
#                 {
#                     "type": "function",
#                     "function": {
#                         "name": "get_info_about_lahn",
#                         "description": (
#                             "Get relevant information about the Lahn"
#                             "Use for general factual or historical questions about the Lahn River "
#                             "that do NOT involve live measurements or sensor data."
#                             ),
#                         "parameters": {
#                             "type": "object",
#                             "properties": {
#                                 "query": {
#                                     "type": "string",
#                                     "description": "Info required."
#                                 }
#                             },
#                             "required": ["query"]
#                         }
#                     }
#                 },
#                 {
#                     "type": "function",
#                     "name": "get_sensor_data",
#                     "description": (
#                         "Use ONLY for questions involving Lahn Atlas live data readings. Fetch and analyze live sensor data from the Lahn Atlas. "
#                         "Use this for questions involving temperature, pH, dissolved oxygen, "
#                         "electrical conductivity (water), or humidity and CO₂ (air). "
#                         "The function can perform computations like averages, minimums, maximums, or trends over time."
#                     ),
#                     "parameters": {
#                         "type": "object",
#                         "properties": {
#                             "query": {
#                                 "type": "string",
#                                 "description": (
#                                     "Natural-language question about Lahn Atlas sensor readings, e.g. "
#                                     "'What was the lowest temperature last week?' or 'Show the trend in pH over the past day.'"
#                                 )
#                             }
#                         },
#                         "required": ["query"]
#                     }
#                 }
#             ],
#                 "temperature": 0.7
#             }
            
#             response = requests.post(
#                 "https://api.openai.com/v1/chat/completions",
#                 headers=headers,
#                 json=data
#             )
            
#             if response.status_code == 200:
#                 msg = response.json()["choices"][0]["message"]

#                 if "tool_calls" in msg:
#                     print('Function call detected. Calling...')
#                     for tool_call in msg["tool_calls"]:
#                         fn_name = tool_call["function"]["name"]
#                         args = json.loads(tool_call["function"]["arguments"])
                        
#                         if fn_name == "get_info_about_lahn":
#                             result = self._get_info_about_lahn(**args)
#                         elif fn_name == "get_sensor_data":
#                             result = self._get_sensor_data(**args)
                            
#                             # Send the result back to the model
#                             followup = {
#                                 "model": "gpt-4o",
#                                 "messages": [
#                                     *data["messages"],  # include conversation so far
#                                     msg,
#                                     {
#                                         "role": "tool",
#                                         "tool_call_id": tool_call["id"],
#                                         "content": json.dumps({"result": result})
#                                     }
#                                 ]
#                             }
#                             followup_response = requests.post(
#                                 "https://api.openai.com/v1/chat/completions",
#                                 headers=headers,
#                                 json=followup
#                             )
#                             print('Follow up response from tool call: ', followup_response.json())

#                             response = followup_response

#                 result = response.json()
#                 message = result['choices'][0]['message']['content']
#                 print('Message: ', message)
                
#                 # For fair comparison, only count user message tokens (exclude system prompt)
#                 # The system prompt is: "You are a helpful AI assistant. Give very short, direct answers."
#                 # Estimate user tokens: ~4 characters per token
#                 user_tokens = max(1, len(text) // 4)
                
#                 tokens = {
#                     'input': user_tokens,  # Only user message tokens for fair comparison
#                     'output': result['usage']['completion_tokens']
#                 }
#                 return message, tokens
#             else:
#                 print(f"❌ GPT-4o error: {response.status_code} - {response.text}")
#                 return None, {'input': 0, 'output': 0}
                
#         except Exception as e:
#             print(f"❌ GPT-4o error: {e}")
#             return None, {'input': 0, 'output': 0}
    
#     def _text_to_speech(self, text: str) -> Optional[bytes]:
#         """Convert text to speech using Cartesia."""
#         try:
#             print("🔧 Using Cartesia direct API for TTS...")
            
#             headers = {
#                 "Cartesia-Version": "2024-06-10",
#                 "X-API-Key": self.cartesia_api_key,
#                 "Content-Type": "application/json"
#             }
            
#             data = {    
#                 "model_id": "sonic-2",
#                 "transcript": text,
#                 "voice": {
#                     "mode": "id",
#                     "id": "694f9389-aac1-45b6-b726-9d9369183238"
#                 },
#                 "output_format": {
#                     "container": "raw",
#                     "encoding": "pcm_s16le",
#                     "sample_rate": 24000
#                 },
#                 "language": "en"
#             }
            
#             response = requests.post(
#                 f"{self.cartesia_base_url}/tts/bytes",
#                 headers=headers,
#                 json=data
#             )
            
#             if response.status_code == 200:
#                 audio_data = response.content
#                 print(f"📊 Cartesia TTS response: {len(audio_data)} bytes")
#                 expected_duration = len(audio_data) / (24000 * 2)
#                 print(f"   Expected duration: {expected_duration:.2f} seconds")
#                 return audio_data
#             else:
#                 print(f"❌ Cartesia TTS error: {response.status_code} - {response.text}")
#                 return None
                    
#         except Exception as e:
#             print(f"❌ TTS error: {e}")
#             return None