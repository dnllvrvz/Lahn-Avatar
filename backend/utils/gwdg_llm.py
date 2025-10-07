from typing import Any, Generator, List
from pydantic import Field
from llama_index.core.llms import (
    CustomLLM,
    ChatResponse, 
    ChatResponseGen,
    CompletionResponse,
    CompletionResponseGen,
    LLMMetadata,
    ChatMessage
)


from llama_index.core.llms.callbacks import llm_completion_callback, llm_chat_callback
import requests, json

# from llama_index.core.base.embeddings.base import BaseEmbedding
# from llama_index.llms.openai import OpenAI
# from llama_index.llms.openai_like import OpenAILike



class GWDGChatLLM(CustomLLM):
    model: str = Field(default="gemma-3-27b-it")
    api_base: str = Field(default="https://llm.hrz.uni-giessen.de/api/")
    api_key: str = Field(default="")
    temperature: float = Field(default=0.1)
    system_prompt: str = Field(default="")

    context_window: int = 128000
    num_output: int = 512

    @property
    def metadata(self) -> LLMMetadata:
        return LLMMetadata(
            context_window=self.context_window,
            num_output=self.num_output,
            model_name=self.model,
        )


    @llm_completion_callback()
    def complete(self, prompt: str, **kwargs: Any) -> CompletionResponse:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": prompt}
            ],
            "temperature": self.temperature,
        }

        # print('Payload: ', payload)

        url = f"{self.api_base}/chat/completions"
        max_retries = 5

        for attempt in range(1, max_retries + 1):
            try:
                response = requests.post(url, headers=headers, json=payload)
                response.raise_for_status()

                content = response.json()["choices"][0]["message"]["content"]
                return CompletionResponse(text=content)

            except requests.HTTPError as e:
                raw_text = response.text[:500]
                print(f"❌ HTTPError (attempt {attempt}):", e)
                print("📨 Raw content:", raw_text)
                print('Model used: ', self.model)

                if "404: Model not found" in raw_text and attempt < max_retries:
                    print(f"🔁 Retrying request (attempt {attempt + 1}/{max_retries})...")
                    continue

                try:
                    data = response.json()
                    if "choices" in data and data["choices"]:
                        fallback_text = data["choices"][0]["message"]["content"]
                        print("⚠️ Using fallback content despite HTTP error.")
                        return CompletionResponse(text=fallback_text)
                except Exception as parse_err:
                    print("❌ Failed to parse fallback content:", parse_err)

                if attempt == max_retries:
                    return CompletionResponse(
                        text="I'm currently experiencing technical issues. Please try again later."
                    )

                # Otherwise continue retrying
                continue



    @llm_completion_callback()
    def stream_complete(self, prompt: str, **kwargs: Any) -> CompletionResponseGen:
        full_response = self.complete(prompt)
        yield CompletionResponse(text=full_response.text, delta=full_response.text)


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

