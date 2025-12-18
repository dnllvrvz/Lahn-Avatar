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
import base64

from .utils import RAG
from .avatar_setup import sensor_query_tool


class OpenAIRealtimeClient:
    """Client for OpenAI's Realtime API using WebSocket."""
    
    def __init__(self, api_key: str, model: str = "gpt-realtime", prompt='', rag_tools=None, streaming=False, ws_client=None):
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

        self.prompt = prompt #+ '\n Note: Always reply in the same language as the user. The language you speak, should mirror theirs. No language-choice inconsistencies. For example if the user messaged you in English, reply in English as well. Same for German, Portuguese etc.'
        self.rag_tools = rag_tools
        self.streaming = streaming
        self.ws_client = ws_client
        self.ws_thread = None

        # self.last_transcript = ""
        # self.last_language = 'en_' #None #"en"
        # self._message_queue = []

    # def update_prompt_with_last_user_language(self):
    #     index = self.prompt.find('CONTEXT INFORMATION')
    #     self.prompt = self.prompt[:index] + '\nYOU MUST RESPOND IN ' + self.last_language + '. DO NOT RESPOND IN ANY OTHER LANGUAGE. \n' + self.prompt[index:]

    #     print('Telling model to respond in ', self.last_language)



    def append_audio(self, base64_chunk):
        """Forward each base64 audio chunk to OpenAI if connected, else buffer."""
        

        try:
            if self.ws and getattr(self.ws, "sock", None) and self.ws.sock.connected:
                # 🔹 Send chunk directly to OpenAI realtime API
                self.ws.send(json.dumps({
                    "type": "input_audio_buffer.append",
                    "audio": base64_chunk
                }))

                import base64
                decoded = base64.b64decode(base64_chunk)

                import numpy as np
                arr = np.frombuffer(decoded, dtype=np.int16)
                peak = int(np.max(np.abs(arr))) if arr.size else 0
                rms = float(np.sqrt(np.mean(arr.astype(np.float32)**2))) if arr.size else 0.0
                # print(f"[AUDIO DEBUG] chunk bytes={len(decoded)}, peak={peak}, rms={rms:.2f}")

                
                # self.audio_buffer.extend(decoded)
                # 🔊 DEBUG: Write incremental audio dump
                # print("Writing debug audio...")
                # with open("/home/gm2629/input_debug.raw", "ab") as f:
                #     f.write(decoded)


            else:
                # 🔹 No active OpenAI socket yet → buffer locally
                import base64
                decoded = base64.b64decode(base64_chunk)
                self.audio_buffer.extend(decoded)


            # # Optional: let browser know chunk was received
            # if self.ws_client:
            #     self.ws_client.send(json.dumps({"status": "audio_chunk_received"}))
        except Exception as e:
            print(f"[WARN] append_audio failed: {e}")


    def commit_audio_buffer(self):
        """Tell OpenAI that user input is finished and request a response."""
        try:
            if self.ws and getattr(self.ws, "sock", None) and self.ws.sock.connected:
                # 🔹 Finalize the current audio input buffer
                self.ws.send(json.dumps({"type": "input_audio_buffer.commit"}))

                # self.update_prompt_with_last_user_language()

                # 🔹 Ask OpenAI to generate a response (audio + text)
                self.ws.send(json.dumps({
                    "type": "response.create",
                    "response": {
                        "modalities": ["audio", "text"],
                    }
                }))
            else:
                print("⚠️ No active OpenAI websocket — cannot commit.")
        except Exception as e:
            print(f"[WARN] commit_audio_buffer failed: {e}")



    def connect_to_openai(self, retries=3):
        """Establish a persistent connection to the OpenAI Realtime API with retries."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "OpenAI-Beta": "realtime=v1",
        }

        for attempt in range(1, retries + 1):
            print(f"🔄 Connecting to OpenAI Realtime API (attempt {attempt}/{retries})...")
            self.ws = websocket.WebSocketApp(
                self.ws_url,
                header=headers,
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close,
            )

            self.ws_thread = threading.Thread(target=self.ws.run_forever, daemon=True)
            self.ws_thread.start()

            for _ in range(50):  # wait up to 5 s
                if getattr(self.ws, "sock", None) and self.ws.sock.connected:
                    print("✅ OpenAI realtime websocket ready.")
                    return
                time.sleep(0.1)

            print("⚠️ Connection attempt timed out.")
            time.sleep(1)  # brief pause before retry

        raise RuntimeError("Failed to connect to OpenAI realtime websocket after retries.")







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

            self.connect_to_openai()
            
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

                # self.update_prompt_with_last_user_language()
                
                # Explicitly request a response
                response_event = {
                    "type": "response.create",
                    "response": {
                            "modalities": ["audio", "text"],
                            # "instructions": "Function response: (What language was the user's last message to you in? Respond in precisely the same language. For example if the user messaged you in English, reply in English as well. Same for German, Portuguese etc)"
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
                self.ws_thread.join(timeout=2)
                
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
        context = RAG(rag_tools, query)

        return context

    def _get_sensor_data(self, query:str):
        print('Function called: _get_sensor_data(). Query: ', query)
        print('Calling Lahn Sensors Tool...')

        analysis = 'Result for query: '+query+ ' -> ' + str(sensor_query_tool(query))
        print('Analysis: ', analysis)

        return analysis

    
    def _on_open(self, ws):
        """Handle WebSocket connection open."""
        print("✅ Connected to OpenAI Realtime API")
        # print("🔥 NEW SESSION STARTED", time.time())

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



        # self.update_prompt_with_last_user_language()

        session_update = {
            "type": "session.update",
            "session": {
                "modalities": ["audio", "text"],
                "instructions": self.prompt  + "\n\nCRITICAL LANGUAGE RULE - MUST FOLLOW: You MUST respond in the EXACT same language the user speaks to you in. | User speaks English → You respond in English | User speaks German → You respond in German | User speaks Portuguese → You respond in Portuguese | NEVER switch languages unless the user switches first", #IMPORTANT: Always respond in the same language the user speaks to you.
                "voice": "alloy",
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "input_audio_transcription": {"model": "whisper-1"},
                "turn_detection": None,
                "temperature": 0.7,
                "tools": tools
            }
        }
        #+ "\n For every reponse you give, carry out this language-consistency check: What language was the user's last message to you in? Respond in precisely the same language. For example if the user messaged you in English, reply in English as well. Same for German, Portuguese etc.", #"You are a helpful AI assistant. Give very short, direct answers.",
        ws.send(json.dumps(session_update))

        # print('\n\nSystem prompt: ', self.prompt)

    
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
                    # Convert from base64 to bytes (not hex)
                    audio_chunk = base64.b64decode(delta)
                    if not self.streaming:
                        self.audio_buffer.extend(audio_chunk)
                        # print(f"🎵 Received audio chunk: {len(audio_chunk)} bytes (total: {len(self.audio_buffer)} bytes)")
                    else:
                        try:
                            # Force bytes, avoid text encoding
                            self.ws_client.send(bytes(audio_chunk))
                        except Exception as e:
                            print(f"[WARN] failed to send binary audio: {e}")
                        # Send raw binary frame instead of JSON
                        # self.ws_client.send(audio_chunk, binary=True)
                        # self.ws_client.send(json.dumps({"delta": delta}))

            
            elif event_type == 'response.done':
                # Full response complete
                print(f"✅ Response generation complete")
                
                # If this response was a function call, wait for the next response with audio
                if self.current_response_has_function_call:
                    print("⏳ Function call response complete, waiting for audio response...")
                    # Don't set response_complete - we're waiting for the function result response
                else:
                    # This is either a direct response or the post-function-call audio response
                    if len(self.audio_buffer) == 0 and not self.awaiting_function_response and self.streaming==False:
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
                if self.ws_client:
                    self.ws_client.send(json.dumps({
                        "type": "input_transcript",
                        "text": transcript
                    }))
                print(f"🎤 Input transcript: {transcript}")

                # Debug: Print the entire event to see what Whisper returns
                # print(f"🔍 Full transcription event data: {json.dumps(data, indent=2)}")

                # metadata = data.get('metadata', {}) or {}
                # lang = metadata.get('language') or data.get('language') #or self.last_language

                # print(f"🔍 metadata: {metadata}")
                # print(f"🔍 language from metadata: {metadata.get('language')}")
                # print(f"🔍 language from data: {data.get('language')}")
                # print(f"🔍 Final lang value: {lang}")
                
                # if lang:
                #     self.last_language = lang
                #     print(f"🌍 Whisper detected language: {lang}")
                # else:
                #     print(f"⚠️ Whisper returned NULL for language, keeping previous: {self.last_language}")
                #     # Don't run langdetect on short phrases - it's unreliable
                #     if len(transcript.split()) < 3:
                #         print(f"⚠️ Transcript too short for reliable detection, keeping: {self.last_language}")
                    # else:

                        # # Only use langdetect for longer phrases
                        # try:
                        #     import langdetect
                        #     detected = langdetect.detect(transcript)
                        #     print(f"📝 langdetect says: {detected} (using as fallback)")
                        #     self.last_language = detected
                        # except:
                        #     print(f"❌ langdetect failed, keeping: {self.last_language}")

                # # 🔹 Optional: automatic detection if missing
                # if lang is None and transcript:
                #     print('Detecting language w langdetect...')
                #     import langdetect
                #     try:
                #         lang = langdetect.detect(transcript)
                #     except:
                #         lang = self.last_language or "en_"


                # self.last_language = lang

                # print(f"🌍 Detected language: {lang}")
            
            elif event_type == 'response.audio_transcript.delta':
                # Output audio transcript delta
                delta = data.get('delta', '')
                self.output_transcript += delta
            
            elif event_type == 'response.audio_transcript.done':
                # Output audio transcript complete
                transcript = data.get('transcript', '')
                if transcript:
                    self.output_transcript = transcript
                if self.ws_client:
                    self.ws_client.send(json.dumps({
                        "type": "output_transcript",
                        "text": transcript
                    }))
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
                    # self.update_prompt_with_last_user_language()
                    # print('Telling model to respond in ', self.last_language)
                    ws.send(json.dumps({
                        "type": "response.create",
                        "response": {
                            "modalities": ["audio", "text"],
                            "instructions": "Function response: "+result + '\nYOU MUST RESPOND IN THE SAME LANGUAGE AS THE USER. DO NOT RESPOND IN ANY OTHER LANGUAGE. \n'#+" Respond in "+ self.last_language #(What language was the user's last message to you in? Respond in precisely the same language. For example if the user messaged you in English, reply in English as well. Same for German, Portuguese etc)" ' + self.last_language + '.
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

