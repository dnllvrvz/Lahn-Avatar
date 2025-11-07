
# #For caching translations relevant to extracting context from Text-based Index:

# import hashlib
# from deep_translator import GoogleTranslator

# # In-memory translation cache
# _trans_cache = {} #Save to file, for persistence.

# def _cache_key(word: str, target_lang: str) -> str:
#     """
#     Generate a hash key for each word-language pair.
#     """
#     key_str = f"{word.lower().strip()}::{target_lang}"
#     return hashlib.md5(key_str.encode("utf-8")).hexdigest()

# def translate_batch(words, target_lang: str):
#     """
#     Translates a list of words to target_lang, using per-word caching.
#     Only uncached words trigger API calls.
#     """
#     results = []
#     uncached_words = []
#     uncached_indices = []

#     # 1️⃣ Check cache for each word
#     for i, word in enumerate(words):
#         key = _cache_key(word, target_lang)
#         if key in _trans_cache:
#             results.append(_trans_cache[key])
#         else:
#             results.append(None)
#             uncached_words.append(word)
#             uncached_indices.append(i)

#     # 2️⃣ Translate uncached words in a batch (if API allows)
#     if uncached_words:
#         # GoogleTranslator can take a single string — we join by newline for batch translation
#         text_to_translate = "\n".join(uncached_words)
#         translated_text = GoogleTranslator(source="auto", target=target_lang).translate(text_to_translate)
        
#         # deep_translator may return one big string, so split it back
#         translated_list = [t.strip() for t in translated_text.split("\n") if t.strip()]

#         # Safety: align lengths
#         if len(translated_list) != len(uncached_words):
#             raise ValueError("Batch translation mismatch between input and output sizes.")

#         # 3️⃣ Store each translation in cache and fill results
#         for idx, word, translated in zip(uncached_indices, uncached_words, translated_list):
#             key = _cache_key(word, target_lang)
#             _trans_cache[key] = translated
#             results[idx] = translated

#             # optional reverse cache
#             reverse_key = _cache_key(translated, "en" if target_lang != "en" else "auto")
#             _trans_cache[reverse_key] = word

#     return results








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








# class GWDGEmbedding(BaseEmbedding):

#     api_key: str = Field(...)
#     api_base: str = Field(...)
#     model: str = Field(...)
#     # def __init__(self, api_key: str, api_base: str, model: str):
#     #     self.api_key = api_key
#     #     self.api_base = api_base
#     #     self.model = model

#     def _get_text_embedding(self, text: str) -> List[float]:
#         """Get embedding for a single text string."""
#         headers = {
#             "Authorization": f"Bearer {self.api_key}",
#             "Content-Type": "application/json",
#         }
#         payload = {
#             "model": self.model,
#             "input": [text],  # Important: send it as a list even for one input
#         }
#         response = requests.post(
#             f"{self.api_base}/embeddings",
#             headers=headers,
#             json=payload,
#         )
#         response.raise_for_status()
#         return response.json()["data"][0]["embedding"]

#     def _get_text_embeddings(self, texts: List[str]) -> List[List[float]]:
#         """Get embeddings for a batch of texts."""
#         headers = {
#             "Authorization": f"Bearer {self.api_key}",
#             "Content-Type": "application/json",
#         }
#         payload = {
#             "model": self.model,
#             "input": texts,
#         }
#         response = requests.post(
#             f"{self.api_base}/embeddings",
#             headers=headers,
#             json=payload,
#         )
#         response.raise_for_status()
#         return [item['embedding'] for item in response.json()["data"]]

#     # Required for newer LlamaIndex versions (>= 0.9.48)
#     def _get_query_embedding(self, query: str) -> List[float]:
#         return self._get_text_embedding(query)

#     def _aget_query_embedding(self, query: str) -> List[float]:
#         # Async version not yet implemented, fall back to sync
#         return self._get_query_embedding(query)


# class HrzOpenAI(OpenAI):
#     @property
#     def supports_function_calling_api(self) -> bool:
#         # Force‐enable tools/function‐calling for this custom model
#         return True

#     @property
#     def metadata(self) -> LLMMetadata:
#         # Return a metadata object with your real context window
#         # and whatever num_output you want.
#         return LLMMetadata(
#             context_window=8192,    # your model’s max context size
#             num_output=512,         # tokens back
#             model_name="hrz-chat-small", #hardcoded ⚠️
#         )

# class CustomOpenAILike(OpenAILike):
#     """
#     A custom OpenAILike subclass that mirrors your GWDGChatLLM behavior—
#     sending system prompts and messages in a single payload to a non-OpenAI endpoint,
#     with both standard and streaming chat methods.
#     """
#     model: str = Field(default="mistral-large-instruct")
#     api_base: str = Field(default="https://llm.hrz.uni-giessen.de/api")
#     api_key: str = Field(default="")
#     temperature: float = Field(default=0.1)
#     system_prompt: str = Field(default="")

#     context_window: int = 16000
#     num_output: int = 512

#     @property
#     def metadata(self) -> LLMMetadata:
#         # Report your real context window & output size
#         return LLMMetadata(
#             context_window=self.context_window,
#             num_output=self.num_output,
#             model_name="gpt-3.5-turbo",
#             is_function_calling_model=True
#         )

#     # def _get_model_name(self) -> str:
#     #     # override to match OpenAI model whitelist
#     #     return self.metadata.model_name


#     # @property
#     # def supports_function_calling_api(self) -> bool:
#     #     # force‐enable the function‐calling machinery
#     #     return True

#     @llm_chat_callback()
#     def chat(self, messages: List[dict], **kwargs: Any) -> CompletionResponse:
#         headers = {
#             "Authorization": f"Bearer {self.api_key}",
#             "Content-Type": "application/json",
#         }
#         # turn each ChatMessage (or dict) into the simple OpenAI dict form
#         serialized = []
#         for m in messages:
#             if hasattr(m, "role") and hasattr(m, "content"):
#                 # ChatMessage-like object
#                 serialized.append({"role": m.role, "content": m.content})
#             else:
#                 # assume it’s already a dict
#                 serialized.append(m)

#         payload = {
#             "model": self.model,
#             "messages": [
#                 {"role": "system", "content": self.system_prompt},
#                 *serialized
#             ],
#             "temperature": self.temperature,
#         }
#         url = f"{self.api_base}/chat/completions"
#         resp = requests.post(url, headers=headers, json=payload)
#         resp.raise_for_status()
#         data = resp.json()
#         text = data["choices"][0]["message"]["content"]
#         return ChatResponse(
#             message=ChatMessage(role="assistant", content=text)
#         )

#     @llm_chat_callback()
#     def stream_chat(self, messages: List[dict], **kwargs: Any) -> CompletionResponseGen:
#         headers = {
#             "Authorization": f"Bearer {self.api_key}",
#             "Content-Type": "application/json",
#         }
#         # payload = {
#         #     "model": self.model,
#         #     "messages": [
#         #         {"role": "system", "content": self.system_prompt},
#         #         *messages
#         #     ],
#         #     "temperature": self.temperature,
#         #     "stream": True,
#         # }

#         serialized = []
#         for m in messages:
#             if hasattr(m, "role") and hasattr(m, "content"):
#                 serialized.append({"role": m.role, "content": m.content})
#             else:
#                 serialized.append(m)

#         payload = {
#             "model": self.model,
#             "messages": [
#                 {"role": "system", "content": self.system_prompt},
#                 *serialized
#             ],
#             "temperature": self.temperature,
#             "stream": True,
#         }

#         url = f"{self.api_base}/chat/completions"
#         resp = requests.post(url, headers=headers, json=payload, stream=True)
#         resp.raise_for_status()
#         for line in resp.iter_lines(decode_unicode=True):
#             if not line or not line.startswith("data: "):
#                 continue
#             chunk = line.removeprefix("data: ")
#             if chunk.strip() == "[DONE]":
#                 break
#             data = json.loads(chunk)
#             delta = data["choices"][0]["delta"].get("content", "")
#             yield ChatResponse(text=delta, delta=delta)

# from llama_index.core.llms.function_calling import FunctionCallingLLM , LLMMetadata
# from llama_index.core.base.llms.types import ChatMessage, ChatResponse, MessageRole
# from llama_index.core.tools import BaseTool
# from llama_index.core.tools import ToolOutput
# from llama_index.core.llms.types import ToolCall  
# from llama_index.core.llms.callbacks import llm_completion_callback, llm_chat_callback
# from pydantic import Field
# from typing import Any, List, Optional, Sequence, Dict
# import requests
# import json


# class GWDGChatLLM(FunctionCallingLLM):
#     model: str = Field(default="gemma-3-27b-it")
#     api_base: str = Field(default="https://llm.hrz.uni-giessen.de/api/")
#     api_key: str = Field(default="")
#     temperature: float = Field(default=0.1)
#     system_prompt: str = Field(default="")
#     context_window: int = 128000
#     num_output: int = 512

#     @property
#     def metadata(self) -> LLMMetadata:
#         return LLMMetadata(
#             context_window=self.context_window,
#             num_output=self.num_output,
#             model_name=self.model,
#         )

#     @llm_completion_callback()
#     def complete(self, prompt: str, **kwargs: Any) -> CompletionResponse:
#         headers = {
#             "Authorization": f"Bearer {self.api_key}",
#             "Content-Type": "application/json",
#         }
#         payload = {
#             "model": self.model,
#             "messages": [
#                 {"role": "system", "content": self.system_prompt},
#                 {"role": "user", "content": prompt}
#             ],
#             "temperature": self.temperature,
#         }
        
#         url = f"{self.api_base}/chat/completions"
#         max_retries = 5
#         for attempt in range(1, max_retries + 1):
#             try:
#                 response = requests.post(url, headers=headers, json=payload)
#                 response.raise_for_status()
#                 content = response.json()["choices"][0]["message"]["content"]
#                 return CompletionResponse(text=content)
#             except requests.HTTPError as e:
#                 raw_text = response.text[:500]
#                 print(f"❌ HTTPError (attempt {attempt}):", e)
#                 print("📨 Raw content:", raw_text)
#                 print('Model used: ', self.model)
#                 if "404: Model not found" in raw_text and attempt < max_retries:
#                     print(f"🔁 Retrying request (attempt {attempt + 1}/{max_retries})...")
#                     continue
#                 try:
#                     data = response.json()
#                     if "choices" in data and data["choices"]:
#                         fallback_text = data["choices"][0]["message"]["content"]
#                         print("⚠️ Using fallback content despite HTTP error.")
#                         return CompletionResponse(text=fallback_text)
#                 except Exception as parse_err:
#                     print("❌ Failed to parse fallback content:", parse_err)
#                 if attempt == max_retries:
#                     return CompletionResponse(
#                         text="I'm currently experiencing technical issues. Please try again later."
#                     )
#                 continue

#     @llm_chat_callback()
#     def chat(self, messages: Sequence[ChatMessage], **kwargs: Any) -> ChatResponse:
#         # Convert LlamaIndex ChatMessage to API format
#         api_messages = []
        
#         # Add system prompt if provided
#         if self.system_prompt:
#             api_messages.append({
#                 "role": "system", 
#                 "content": self.system_prompt
#             })
        
#         for msg in messages:
#             api_messages.append({
#                 "role": msg.role.value,
#                 "content": msg.content,
#                 # Include tool calls if present
#                 **({"tool_calls": msg.additional_kwargs.get("tool_calls", [])} 
#                    if msg.additional_kwargs.get("tool_calls") else {}),
#                 # Include tool call results if present  
#                 **({"tool_call_id": msg.additional_kwargs.get("tool_call_id")} 
#                    if msg.additional_kwargs.get("tool_call_id") else {})
#             })
        
#         headers = {
#             "Authorization": f"Bearer {self.api_key}",
#             "Content-Type": "application/json",
#         }
        
#         payload = {
#             "model": self.model,
#             "messages": api_messages,
#             "temperature": self.temperature,
#         }
        
#         # Add tools if provided in kwargs
#         if "tools" in kwargs and kwargs["tools"]:
#             payload["tools"] = kwargs["tools"]
#             payload["tool_choice"] = kwargs.get("tool_choice", "auto")
        
#         url = f"{self.api_base}/chat/completions"
        
#         try:
#             response = requests.post(url, headers=headers, json=payload)
#             response.raise_for_status()
#             response_data = response.json()
            
#             choice = response_data["choices"][0]
#             message = choice["message"]
            
#             # Handle tool calls
#             additional_kwargs = {}
#             if "tool_calls" in message and message["tool_calls"]:
#                 additional_kwargs["tool_calls"] = message["tool_calls"]
            
#             return ChatResponse(
#                 message=ChatMessage(
#                     role=MessageRole.ASSISTANT,
#                     content=message.get("content", "") or "",
#                     additional_kwargs=additional_kwargs
#                 )
#             )
            
#         except Exception as e:
#             print(f"❌ Error in chat: {e}")
#             return ChatResponse(
#                 message=ChatMessage(
#                     role=MessageRole.ASSISTANT,
#                     content="I'm currently experiencing technical issues. Please try again later."
#                 )
#             )

#     def get_tool_calls_from_response(
#         self,
#         response: ChatResponse,
#         error_on_no_tool_call: bool = True,
#     ) -> List[ToolCall]:
#         """Extract tool calls from the response."""
#         tool_calls = []
        
#         if response.message.additional_kwargs.get("tool_calls"):
#             for tool_call_data in response.message.additional_kwargs["tool_calls"]:
#                 try:
#                     # Parse the function call
#                     function_call = tool_call_data["function"]
#                     tool_call = ToolCall(
#                         tool_name=function_call["name"],
#                         tool_kwargs=json.loads(function_call["arguments"]),
#                         tool_id=tool_call_data.get("id", "")
#                     )
#                     tool_calls.append(tool_call)
#                 except Exception as e:
#                     print(f"Error parsing tool call: {e}")
#                     continue
        
#         if error_on_no_tool_call and not tool_calls:
#             raise ValueError("No tool calls found in response")
            
#         return tool_calls

#     def predict_and_call(
#         self,
#         tools: List[BaseTool],
#         user_msg: Optional[str] = None,
#         chat_history: Optional[List[ChatMessage]] = None,
#         verbose: bool = False,
#         **kwargs: Any,
#     ) -> ChatResponse:
#         """Predict and call tools if needed."""
        
#         # Prepare tools in OpenAI format for the API
#         tools_dict = []
#         for tool in tools:
#             tool_spec = {
#                 "type": "function",
#                 "function": {
#                     "name": tool.metadata.name,
#                     "description": tool.metadata.description,
#                     "parameters": tool.metadata.fn_schema_str
#                 }
#             }
#             # Parse the schema string if it's a string
#             if isinstance(tool.metadata.fn_schema_str, str):
#                 try:
#                     tool_spec["function"]["parameters"] = json.loads(tool.metadata.fn_schema_str)
#                 except:
#                     # Fallback to basic schema
#                     tool_spec["function"]["parameters"] = {
#                         "type": "object",
#                         "properties": {},
#                         "required": []
#                     }
#             else:
#                 tool_spec["function"]["parameters"] = tool.metadata.fn_schema_str
            
#             tools_dict.append(tool_spec)
        
#         # Prepare messages
#         messages = chat_history or []
#         if user_msg:
#             messages.append(ChatMessage(role=MessageRole.USER, content=user_msg))
        
#         # Get response with tools
#         response = self.chat(messages, tools=tools_dict, **kwargs)
        
#         # Check if model wants to call tools
#         if response.message.additional_kwargs.get("tool_calls"):
#             tool_calls = self.get_tool_calls_from_response(response, error_on_no_tool_call=False)
            
#             # Execute tool calls
#             for tool_call in tool_calls:
#                 # Find the matching tool
#                 matching_tool = None
#                 for tool in tools:
#                     if tool.metadata.name == tool_call.tool_name:
#                         matching_tool = tool
#                         break
                
#                 if matching_tool:
#                     try:
#                         # Execute the tool
#                         tool_output = matching_tool.call(**tool_call.tool_kwargs)
                        
#                         # Add tool result to messages
#                         messages.append(response.message)  # Assistant's tool call
#                         messages.append(ChatMessage(
#                             role=MessageRole.TOOL,
#                             content=str(tool_output),
#                             additional_kwargs={"tool_call_id": tool_call.tool_id}
#                         ))
                        
#                         # Get final response
#                         response = self.chat(messages)
                        
#                     except Exception as e:
#                         print(f"Error executing tool {tool_call.tool_name}: {e}")
#                         # Continue with error message
#                         messages.append(ChatMessage(
#                             role=MessageRole.TOOL,
#                             content=f"Error executing tool: {str(e)}",
#                             additional_kwargs={"tool_call_id": tool_call.tool_id}
#                         ))
#                         response = self.chat(messages)
        
#         return response

