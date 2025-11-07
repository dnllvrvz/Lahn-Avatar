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
