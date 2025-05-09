from typing import Any, Generator, List
from pydantic import Field
from llama_index.core.llms import (
    CustomLLM,
    CompletionResponse,
    CompletionResponseGen,
    LLMMetadata,
)
from llama_index.core.llms.callbacks import llm_completion_callback
from llama_index.core.base.embeddings.base import BaseEmbedding
import requests, json


class GWDGChatLLM(CustomLLM):
    model: str = Field(default="llama-3.1-8b-instruct")
    api_base: str = Field(default="https://llm.hrz.uni-giessen.de/api/")
    api_key: str = Field(default="")
    temperature: float = Field(default=0.1)
    system_prompt: str = Field(default="")

    context_window: int = 4096
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
            "messages": [{"role": "system", "content": self.system_prompt},
                         {"role": "user", "content": prompt}],
            "temperature": self.temperature,
        }

        print("📤 Sending payload:", json.dumps(payload, indent=2))
        print("📡 POST to:", f"{self.api_base}/chat/completions")

        try:
            response = requests.post(
                f"{self.api_base}/chat/completions", headers=headers, json=payload
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            return CompletionResponse(text=content)

        except requests.HTTPError as e:
            print("❌ HTTPError:", e)
            print("📨 Raw content:", response.text[:500])

            # Try to extract usable content even from failed status
            try:
                data = response.json()
                if "choices" in data and data["choices"]:
                    fallback_text = data["choices"][0]["message"]["content"]
                    print("⚠️ Using fallback content despite HTTP error.")
                    return CompletionResponse(text=f"{fallback_text}")
            except Exception as parse_err:
                print("❌ Failed to parse fallback content:", parse_err)

            # If completely unusable, re-raise
            raise e


    @llm_completion_callback()
    def stream_complete(self, prompt: str, **kwargs: Any) -> CompletionResponseGen:
        full_response = self.complete(prompt)
        yield CompletionResponse(text=full_response.text, delta=full_response.text)


class GWDGEmbedding(BaseEmbedding):

    api_key: str = Field(...)
    api_base: str = Field(...)
    model: str = Field(...)
    # def __init__(self, api_key: str, api_base: str, model: str):
    #     self.api_key = api_key
    #     self.api_base = api_base
    #     self.model = model

    def _get_text_embedding(self, text: str) -> List[float]:
        """Get embedding for a single text string."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "input": [text],  # Important: send it as a list even for one input
        }
        response = requests.post(
            f"{self.api_base}/embeddings",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        return response.json()["data"][0]["embedding"]

    def _get_text_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Get embeddings for a batch of texts."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "input": texts,
        }
        response = requests.post(
            f"{self.api_base}/embeddings",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        return [item['embedding'] for item in response.json()["data"]]

    # Required for newer LlamaIndex versions (>= 0.9.48)
    def _get_query_embedding(self, query: str) -> List[float]:
        return self._get_text_embedding(query)

    def _aget_query_embedding(self, query: str) -> List[float]:
        # Async version not yet implemented, fall back to sync
        return self._get_query_embedding(query)
