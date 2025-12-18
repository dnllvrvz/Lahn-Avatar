from typing import Any, Generator, List, Literal
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



class LLM(CustomLLM):
    # Which backend to use for THIS instance: "gwdg" or "openai"
    provider: Literal["gwdg", "openai"] = Field(default="gwdg")

    # --- shared config ---
    temperature: float = Field(default=0.1)
    system_prompt: str = Field(default="")

    context_window: int = 128000
    num_output: int = 512

    # --- GWDG config ---
    gwdg_model: str = Field(default="gemma-3-27b-it")
    gwdg_api_base: str = Field(default="https://llm.hrz.uni-giessen.de/api")
    gwdg_api_key: str = Field(default="")  # set this when using provider="gwdg"

    # --- OpenAI config ---
    openai_model: str = Field(default="gpt-4.1-mini")
    openai_api_base: str = Field(default="https://api.openai.com/v1")
    openai_api_key: str = Field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))

    @property
    def metadata(self) -> LLMMetadata:
        if self.provider == "gwdg":
            model_name = self.gwdg_model
        else:
            model_name = self.openai_model

        return LLMMetadata(
            context_window=self.context_window,
            num_output=self.num_output,
            model_name=model_name,
        )

    # ------------- helpers -------------

    def _build_messages(self, prompt: str):
        return [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": prompt},
        ]

    def _complete_gwdg(self, prompt: str) -> CompletionResponse:
        if not self.gwdg_api_key:
            raise RuntimeError("GWDG API key not set (gwdg_api_key).")

        headers = {
            "Authorization": f"Bearer {self.gwdg_api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.gwdg_model,
            "messages": self._build_messages(prompt),
            "temperature": self.temperature,
        }

        url = f"{self.gwdg_api_base.rstrip('/')}/chat/completions"
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return CompletionResponse(text=content)

    def _complete_openai(self, prompt: str) -> CompletionResponse:
        if not self.openai_api_key:
            raise RuntimeError("OpenAI API key not set (openai_api_key or OPENAI_API_KEY).")

        headers = {
            "Authorization": f"Bearer {self.openai_api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.openai_model,
            "messages": self._build_messages(prompt),
            "temperature": self.temperature,
        }

        url = f"{self.openai_api_base.rstrip('/')}/chat/completions"
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return CompletionResponse(text=content)

    # ------------- main LLM interface -------------

    @llm_completion_callback()
    def complete(self, prompt: str, **kwargs: Any) -> CompletionResponse:
        if self.provider == "gwdg":
            return self._complete_gwdg(prompt)
        elif self.provider == "openai":
            return self._complete_openai(prompt)
        else:
            raise ValueError(f"Unknown provider: {self.provider}")

    @llm_completion_callback()
    def stream_complete(self, prompt: str, **kwargs: Any) -> CompletionResponseGen:
        # Simple “fake” streaming: just call complete and yield once
        full = self.complete(prompt, **kwargs)
        yield CompletionResponse(text=full.text, delta=full.text)



# class GWDGChatLLM(CustomLLM):
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

#         # print('Payload: ', payload)

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

#                 # Otherwise continue retrying
#                 continue



#     @llm_completion_callback()
#     def stream_complete(self, prompt: str, **kwargs: Any) -> CompletionResponseGen:
#         full_response = self.complete(prompt)
#         yield CompletionResponse(text=full_response.text, delta=full_response.text)
