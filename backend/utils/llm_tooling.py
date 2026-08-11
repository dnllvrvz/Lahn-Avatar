import os
from typing import Any, Literal, List, Dict, Union, Optional
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


from llama_index.core.llms.callbacks import llm_completion_callback #, llm_chat_callback
import requests, json



Message = Dict[str, str]  # {"role": "...", "content": "..."}


class LLM(CustomLLM):
    provider: Literal["gwdg", "openai", "ollama"] = Field(default="gwdg")

    temperature: float = Field(default=0.1)
    top_k: int = Field(default=40)
    top_p: float = Field(default=1.0)
    system_prompt: str = Field(default="")

    context_window: int = 128000
    num_output: int = 512

    gwdg_model: str = Field(default="gemma-3-27b-it")
    gwdg_api_base: str = Field(default="https://llm.hrz.uni-giessen.de/api")
    gwdg_api_key: str = Field(default="")

    openai_model: str = Field(default="gpt-4.1-mini")
    openai_api_base: str = Field(default="https://api.openai.com/v1")
    openai_api_key: str = Field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))

    ollama_model: str = Field(default="llama3.2")
    ollama_api_base: str = Field(default="https://ollama.com")
    ollama_api_key: str = Field(default_factory=lambda: os.getenv("OLLAMA_API_KEY", ""))

    timeout: int = Field(default=60) # New timeout field

    @property
    def metadata(self) -> LLMMetadata:
        if self.provider == "gwdg":
            model_name = self.gwdg_model
        elif self.provider == "ollama":
            model_name = self.ollama_model
        else:
            model_name = self.openai_model
        return LLMMetadata(
            context_window=self.context_window,
            num_output=self.num_output,
            model_name=model_name,
        )

    # ---------- message handling ----------

    def _normalize_messages(
        self,
        prompt_or_messages: Union[str, List[Message]],
        messages: Optional[List[Message]] = None,
    ) -> List[Message]:
        """
        Accept either:
          - prompt_or_messages as str
          - prompt_or_messages as a messages list
          - or messages passed via kwargs
        """
        if messages is not None:
            final = messages
        elif isinstance(prompt_or_messages, list):
            final = prompt_or_messages
        else:
            final = [{"role": "user", "content": str(prompt_or_messages)}]

        # If caller didn't supply a system message but we have system_prompt, inject it
        has_system = any(m.get("role") == "system" for m in final)
        if self.system_prompt and not has_system:
            final = [{"role": "system", "content": self.system_prompt}] + final

        return final

    # ---------- provider calls ----------

    def _complete_gwdg(self, messages: List[Message]) -> CompletionResponse:
        if not self.gwdg_api_key:
            raise RuntimeError("GWDG API key not set (gwdg_api_key).")

        headers = {
            "Authorization": f"Bearer {self.gwdg_api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.gwdg_model,
            "messages": messages,
            "temperature": self.temperature,
            "top_k": self.top_k,
            "top_p": self.top_p,
        }

        url = f"{self.gwdg_api_base.rstrip('/')}/chat/completions"
        resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
        if resp.status_code >= 400:
            try:
                err = resp.json()
            except Exception:
                err = {"raw": resp.text[:500]}

            raise RuntimeError(
                f"{self.provider.upper()} API error {resp.status_code}: {err}"
            )
        content = resp.json()["choices"][0]["message"]["content"]
        return CompletionResponse(text=content)

    def _complete_openai(self, messages: List[Message]) -> CompletionResponse:
        if not self.openai_api_key:
            raise RuntimeError("OpenAI API key not set (openai_api_key or OPENAI_API_KEY).")

        headers = {
            "Authorization": f"Bearer {self.openai_api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.openai_model,
            "messages": messages,
            "temperature": self.temperature,
            "top_p": self.top_p,
        }

        url = f"{self.openai_api_base.rstrip('/')}/chat/completions"
        resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
        
        if resp.status_code >= 400:
            try:
                err = resp.json()
            except Exception:
                err = {"raw": resp.text[:500]}

            raise RuntimeError(
                f"{self.provider.upper()} API error {resp.status_code}: {err}"
            )


        content = resp.json()["choices"][0]["message"]["content"]
        return CompletionResponse(text=content)

    def _complete_ollama(self, messages: List[Message]) -> CompletionResponse:
        if not self.ollama_api_key:
            raise RuntimeError("Ollama API key not set (ollama_api_key or OLLAMA_API_KEY).")

        headers = {
            "Authorization": f"Bearer {self.ollama_api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.ollama_model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "top_k": self.top_k,
                "top_p": self.top_p,
            }
        }

        url = f"{self.ollama_api_base.rstrip('/')}/api/chat"
        resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)

        if resp.status_code >= 400:
            try:
                err = resp.json()
            except Exception:
                err = {"raw": resp.text[:500]}

            raise RuntimeError(
                f"OLLAMA API error {resp.status_code}: {err}"
            )

        content = resp.json()["message"]["content"]
        return CompletionResponse(text=content)

    # ---------- main LLM interface ----------

    @llm_completion_callback()
    def complete(self, prompt: Any, **kwargs: Any) -> CompletionResponse:
        # Accept messages via kwargs OR by passing a list as `prompt`
        messages = self._normalize_messages(prompt, messages=kwargs.get("messages"))

        if self.provider == "gwdg":
            return self._complete_gwdg(messages)
        if self.provider == "openai":
            return self._complete_openai(messages)
        if self.provider == "ollama":
            return self._complete_ollama(messages)
        raise ValueError(f"Unknown provider: {self.provider}")

    @llm_completion_callback()
    def stream_complete(self, prompt: Any, **kwargs: Any) -> CompletionResponseGen:
        full = self.complete(prompt, **kwargs)
        yield CompletionResponse(text=full.text, delta=full.text)

    def stream_deltas(self, prompt: Any, **kwargs: Any):
        """
        Yield raw text deltas as they arrive from the provider (true streaming,
        unlike stream_complete above which buffers). OpenAI-compatible SSE for
        gwdg/openai; NDJSON for ollama. Raises on HTTP errors so callers can
        fall back to complete().
        """
        messages = self._normalize_messages(prompt, messages=kwargs.get("messages"))

        if self.provider in ("gwdg", "openai"):
            if self.provider == "gwdg":
                api_key, api_base, model = self.gwdg_api_key, self.gwdg_api_base, self.gwdg_model
                extra = {"top_k": self.top_k}
            else:
                api_key, api_base, model = self.openai_api_key, self.openai_api_base, self.openai_model
                extra = {}
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            payload = {"model": model, "messages": messages, "temperature": self.temperature,
                       "top_p": self.top_p, "stream": True, **extra}
            url = f"{api_base.rstrip('/')}/chat/completions"
            with requests.post(url, headers=headers, json=payload, timeout=self.timeout, stream=True) as resp:
                if resp.status_code >= 400:
                    raise RuntimeError(f"{self.provider.upper()} API error {resp.status_code}: {resp.text[:300]}")
                for line in resp.iter_lines(decode_unicode=True):
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        delta = json.loads(data)["choices"][0].get("delta", {}).get("content")
                    except (KeyError, IndexError, json.JSONDecodeError):
                        continue
                    if delta:
                        yield delta

        elif self.provider == "ollama":
            headers = {"Authorization": f"Bearer {self.ollama_api_key}", "Content-Type": "application/json"}
            payload = {"model": self.ollama_model, "messages": messages, "stream": True,
                       "options": {"temperature": self.temperature, "top_k": self.top_k, "top_p": self.top_p}}
            url = f"{self.ollama_api_base.rstrip('/')}/api/chat"
            with requests.post(url, headers=headers, json=payload, timeout=self.timeout, stream=True) as resp:
                if resp.status_code >= 400:
                    raise RuntimeError(f"OLLAMA API error {resp.status_code}: {resp.text[:300]}")
                for line in resp.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if obj.get("done"):
                        break
                    delta = obj.get("message", {}).get("content")
                    if delta:
                        yield delta
        else:
            raise ValueError(f"Unknown provider: {self.provider}")



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
