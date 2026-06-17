# Design Notes

Running log of architectural decisions, known tradeoffs, and deferred improvements.

---

## Voice RAG: keyword extraction vs. LLM-based generation

**Current (voice):** `extract_keywords_multilingual()` — spaCy POS extraction + langid language detection, runs on the user's current utterance only. No LLM call needed.

**What we gave up:** `generate_context_aware_keywords_for_multilingual_text_index_search()` uses an LLM to look at the full conversation history and generate better search terms. More accurate, especially mid-conversation when the user refers back to something said earlier.

**Why:** The LLM keyword call + main LLM call in sequence exceeded Agora's response timeout for the voice agent, causing silent failures.

**Better alternatives to revisit:**
- Run keyword generation async/in parallel with the channel join, so it's ready by the time the first utterance arrives
- Cache keywords from the previous turn and combine with current utterance extraction
- Use a fast local model (e.g. small Ollama model) for keyword generation specifically

---

## Tool invocation reliability (sensor / web search)

**Current (text chat):** The LLM is instructed via system prompt to output a specific function call syntax (`analyze_sensor_data(...)`, `web_search(...)`). The backend detects this with regex and executes the tool. Nondeterministic — the LLM sometimes outputs the call in the wrong format, wraps it in prose, or fails to call it at all.

**Better alternatives to revisit:**
- **Structured tool use / function calling**: Use the LLM provider's native tool-calling API (OpenAI, Anthropic, OpenRouter all support this). Returns a guaranteed-schema JSON tool call rather than free text. Much more reliable but requires provider-specific wiring.
- **Intent classification gate**: Before the main LLM call, run a lightweight classifier (keyword match, small model, or fast LLM call) to determine if the query needs sensor data or web search. If yes, always fetch and include in context — LLM never has to decide. Works well for sensor data (cheap to always fetch), less clean for web search.
- **Always-fetch sensor data**: For avatars with a sensor URL, always fetch current readings and append to context. Removes the tool-invocation step entirely for sensors. Downside: extra latency on every request even when sensor data isn't relevant.

**Implemented (text + voice):** Always-fetch with 2-min TTL cache per avatar. Latest reading injected into system prompt as `CURRENT SENSOR SNAPSHOT`. `analyze_sensor_data()` tool kept for complex analytical queries (trends, historical data). Cache avoids per-request HTTP cost within a session. See `_fetch_sensor_summary()` in server.py.

---
