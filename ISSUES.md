# Issues

Open issues to fix, roughly ranked by impact. Date = when identified.

## Open

1. **Agora fires the LLM endpoint on interim ASR transcripts** (2026-07-31)
   One long utterance triggered ~20 full RAG+LLM round-trips in 100s (see debug/1.log,
   09:54–09:55). Duplicate responses, wasted LLM calls, agent talks over itself.
   DIAGNOSIS (2026-08-11): our agent payload sets NO turn_detection block, so we run
   Agora defaults — end-of-speech via VAD with a short silence window (~640ms typical).
   Reflective speakers pause longer than that mid-thought, so Agora repeatedly
   concludes the turn ended, fires the LLM, then reissues with the extended
   transcript. Fix candidates (turn_detection.config.end_of_speech, Agora v2.4+):
   (a) mode "semantic" (Agora-recommended; judges whether the sentence is complete,
   with max_wait_ms cap) or (b) mode "vad" with silence_duration_ms raised to
   800–1000ms. Confirm exact payload field names against the join API reference at
   impl time; semantic mode may add slight response latency (watch the Agora segment
   in the latency panel). Also retest after the nova-3 ASR switch — endpointing
   behavior may already differ.
   Turn-detection reference (Agora v2.4+, restructured Feb 2026): `turn_detection`
   block = mode + config pattern. `config.end_of_speech.mode`: "vad"
   (silence_duration_ms) or "semantic" (semantic_config: silence_duration_ms,
   max_wait_ms). `config.start_of_speech.mode`: "vad" | "keywords" | "disabled",
   plus `config.speech_threshold` (VAD sensitivity) and a speaking-interrupt
   duration governing user barge-in. Old fields (interrupt_mode, interrupt_keywords)
   deprecated. Docs: docs.agora.io/en/conversational-ai/rest-api/agent/join,
   .../studio/build/customize-agent, .../overview/release-notes.

2. **Empty utterance gets RAG injection as the whole user message** (2026-07-31)
   ASR delivered an empty transcript; the context block was appended to the empty
   string and sent as the user message (debug/2.log, 09:43:15). Guard: skip RAG
   injection / skip the turn when user content is empty or whitespace.

3. **ASR language hardcoded to en-US** (2026-07-25)
   `server.py` agent start payload. Mangles Portuguese ("do Rio Sagrado" →
   "the Hilsagradu") and mishears English ("tell me" → "Tommy", which the avatar
   then adopted as its own name; "How are you" → "Are you"). Should be per-avatar
   or multilingual.
   VERIFIED FIX (2026-08-11, isolated Deepgram test): `model=nova-3&language=multi`
   → near-perfect PT/DE/code-switched transcripts, English unaffected. Current
   en-US config returned an EMPTY transcript for clean Portuguese — likely the
   mechanism behind issue 2. Residual: proper nouns ("Rio Sagrado"→"risigrado",
   "Lahn"→"Elan") — mitigated with nova-3 keyterm prompting (avatar name).
   IMPLEMENTED 2026-08-11: server.py asr params now nova-3 + multi + keyterm;
   Agora accepted the payload (agent started/stopped cleanly on a test channel).
   REMAINING: live voice session in PT/DE to confirm streaming transcription
   quality end-to-end — then close.

4. **Markdown reaches the TTS in voice responses** (2026-07-25)
   Bullet lists and `**bold**` show up in voice replies (debug/0.log "Which ones
   exactly?"; debug/2.log sensor list). Strip markdown/`|`/`*`/`#` before returning
   from /api/voice/chat-completions. Related: `RAG()` returns `" | ".join(...)` —
   pipes contaminate LLM context (return `total_context` directly instead).
   VERIFIED (2026-08-11, isolated TTS round-trip): both sonic-2 AND sonic-3
   literally speak "vertical bar" for `|` — no model upgrade fixes this; the
   server-side strip is mandatory. Bullets ("- ") and `**bold**` were handled
   gracefully by both models (list pauses, no "asterisk" spoken) — `|` is the
   uniquely toxic character, but strip all markdown anyway for safety.
   IMPLEMENTED 2026-08-11: `sanitize_for_tts()` in server.py strips links,
   bullets, markdown chars, pipes, and emojis from voice responses before the
   SSE stream; verified clean output E2E. The RAG() pipe-join context fix
   remains open (contaminates LLM context in both labs).

5. **Voice-lab Agora latency segment often hidden** (2026-07-31)
   Perceived-latency anchor slides forward on ambient mic noise, so the derived
   Agora segment clamps to ≤0 and disappears; displayed total falls back to the
   backend sum. Hysteresis detector attempt failed (never triggered — ambient floor
   above the quiet threshold). Revisit with adaptive noise floor or Agora agent
   state events (would also give the ASR/TTS split).

6. **Language flips: avatar answers in the wrong language** (2026-07-25)
   English question → German answer (debug/0.log fish question); client-reported
   English answer to Portuguese in voice. Driver: context-language dominance +
   langid misdetection on short utterances; Rio Sagrado's system prompt has no
   language-matching or no-markdown rules (client can edit the Google Doc).

7. **Corpus states conflicting river lengths** (2026-07-31)
   Responses variously say 235, 235.6, 242, 245 km (Wikipedia: 245.6 km). Source
   documents disagree; needs cleanup in the context Google Drive folder.

8. **Avatar 1 (Pathwork) chat model is slow** (2026-07-31)
   gpt-4o-mini took ~5s per voice reply vs 1.4–2.2s for avatar 0's GWDG model.
   Voice side resolved 2026-08-11 by the separate voiceChat lane (qwen3-30b).
   RESOLVED 2026-08-18: chat + sensor defaults moved to gwdg/gpt-oss-120b after
   they surfaced a UI resolution bug — the defaults pointed at the HIDDEN
   "openai" provider, which the frontend can't represent; its health-blind
   fallback silently selected gwdg's first listed model (mistral-large-instruct,
   offline) while the dropdown DISPLAYED the first online option (meta-llama-8b),
   producing "model offline" errors naming a model not visible anywhere.
   Frontend fallback is now health-aware (prefers a non-offline model) in both
   the saved-defaults and no-defaults branches. Residual config smell: the
   "openai" provider remains hidden with an empty model list — unhide or remove
   it if OpenAI models should be selectable.

9. **Cold RAG index load appears as unattributed "backend overhead"** (2026-07-31)
   First request to an idle avatar pays ~4s lazy index load, untimed (debug/1.log
   first Pathwork turn: 10.1s total, 4.0s overhead).
   IMPLEMENTED 2026-08-18 (both halves): per-avatar `ragPinned` toggle (Knowledge
   group in LLM config Shared section) — pinned avatars warm in a background
   thread at startup/config change and are never evicted, so their users never
   pay the cold start (verified: pinned avatar 2 request had no load segment);
   unpinned avatars now report the load as an "Index load (cold start)" segment
   in both labs' latency panels (verified: 4159ms on avatar 1). Warm/admin loads
   are excluded from request attribution. Server restart still costs one
   background warm window per pinned avatar.

10. **TTS language/voice not configured** (2026-08-11)
    Cartesia config passes no `language` param and hardcodes one `voice_id` for all
    avatars (`server.py` agent start payload, same block as issue 3). CONFIRMED
    (2026-08-11, Cartesia voices API): the production voice is "Miles - Yogi",
    language "en" — so with Cartesia's default language "en", ALL avatars synthesize
    every reply (incl. PT/DE) under English settings. Isolated test showed the same
    voice accepts language "pt"/"de" and produces audio, so config-level fix exists.
    Open questions: per-turn language switching (TTS config is set once at agent
    start but reply language varies per turn — check if sonic-2 auto-detects when
    language unset vs pinned); per-avatar voice_id (all rivers currently share one
    voice). Pronunciation quality unverified by ear — logs capture text, not audio.
    VENDOR RESEARCH (2026-08-11): sonic-2 is two generations old — Cartesia's
    current line is Sonic-3/3.5 (42 languages, emotion); model_id is passthrough,
    cheap to trial. Deepgram TTS (Aura-2) ruled out: 7 languages, no Portuguese.
    Agora TTS alternatives if Cartesia disappoints by ear: ElevenLabs (multilingual
    leader, GA on Agora, pricier) or Azure (broadest language/voice catalog, GA,
    cheap, less characterful). Cartesia is Beta on Agora. Plan: fix config first
    (per-avatar language + native voice, trial sonic-3), then A/B ElevenLabs only
    if needed.
    ISOLATED TEST (2026-08-11, TTS→Deepgram round-trip): the NATIVE VOICE is the
    decisive lever, not the model — Miles anglicizes PT proper nouns on both
    sonic-2 and sonic-3 ("Morretes"→"Moretz"/"Moritz"); native PT voice "Felipe"
    (616c64d7-f541-436b-9b8d-e79cfbe19ef9) with sonic-3 + language=pt scored 100%
    incl. proper nouns. sonic-3 and sonic-3.5 both accepted by our API key.
    Accent quality beyond proper nouns needs an ear test — clips in session
    scratchpad. Implementation: per-avatar voice_id + language; sonic-3 optional.
    PARTIALLY IMPLEMENTED 2026-08-11: server.py tts params now per-avatar
    (`ttsVoiceId`/`ttsLanguage` from avatars.json, defaults Miles/en); Rio Sagrado
    set to Felipe (native PT) + language "pt" — verified 100% round-trip on
    sonic-2, and Agora accepted agent start for both avatar 2 (Felipe/pt) and
    avatar 0 (defaults).
    FOLLOW-UP FIX (2026-08-11): first live test still sounded anglicized — the
    payload used a flat "voice_id" key, which is undocumented and silently
    ignored (Cartesia fell back to a default voice; production likely NEVER
    applied Miles either). Corrected to the documented shape
    `voice: {mode: "id", id: ...}`; Agora accepted. Agora's agent query API does
    not echo config, so voice application can only be verified by ear.
    SONIC-3 ADOPTED (2026-08-11): model_id switched sonic-2 → sonic-3 after live
    ear test confirmed Felipe/pt works (PT now good; EN from Felipe is
    PT-accented — inherent to Cartesia's accent-native voices; pinned
    language=pt compounds it). Agora accepted agent starts for avatars 2 and 0.
    CLIENT-VALIDATED (2026-08-11): the client's long session ran sonic-3 +
    Felipe and they liked it; Lahn (Miles/en/sonic-3) also confirmed speaking
    after the Cartesia credit top-up.
    REMAINING: per-avatar voices for Lahn (de-capable), Pathwork, and
    MetaRelational (all currently on the Miles/en default); if bilingual
    accent-neutrality ever matters to the client, ElevenLabs (GA on Agora,
    cross-lingual voice consistency is their differentiator) is the escalation.
    NOTE (user, 2026-08-11): cascaded TTS with manual language flags remains
    inferior to speech-native models (e.g. gpt-realtime) which speak any language
    fluently without configuration — see architectural tradeoff discussion.

11. **Repetitive response formula — user-reported in session** (2026-08-11)
    Rio Sagrado opened 9 consecutive voice replies with the same "🌊 Uma gota..."
    water-drop image (debug/2.log 17:32–17:56); the user complained mid-session
    ("você está se repetindo"). Likely prompt-level fix: vary openings / instruct
    against formulaic starts. Emojis in voice replies are part of the same
    styling problem (see issue 4).

12. **PT↔ES misdetection on short greetings with ASR "multi"** (2026-08-11)
    "Bom dia" transcribed as "Hola. Buen día" → avatar replied in Spanish
    (debug/2.log 17:36, 17:42). Residual of the nova-3 multi fix (issue 3):
    short utterances land on the wrong sibling language. Possible mitigations:
    restrict Deepgram language hints per avatar if supported alongside multi,
    or prompt the LLM to prefer the avatar's configured languages when the
    transcript language is ambiguous.

13. **avatars.json llmDefaults silently wiped for avatars 0 & 2** (2026-08-11,
    18:02) — cause not confirmed; prime suspect is the Admin Defaults toggle in
    the Avatar Lab UI, whose "off" state DELETEs the avatar's llmDefaults with
    no confirmation. Consequence: resolution fell to global defaults
    (openrouter/gemma) → voice endpoint 500s (OpenRouter has no credits).
    Restored by hand. Consider: confirmation prompt on the toggle, and/or
    backups/audit logging of avatars.json writes.
    RECURRED same day (avatar 0 again + avatar 3 chat; avatar 2 chat changed to
    qwen — possibly deliberate user action, left in place). GUARDS ADDED
    2026-08-11: llm-defaults POST now merges instead of replacing (partial
    payloads can no longer wipe other tasks), and the global chat fallback moved
    off creditless OpenRouter to gwdg — a wipe now degrades instead of 500ing.
    HISTORY PERSISTENCE ADDED (2026-08-11): save_avatars() is the single write
    path for avatars.json — snapshots the previous state to avatars_history/
    (timestamped, last 100 kept) with a logged reason before every write.
    Recovery = copy a snapshot back and restart. The next wipe will identify
    its writer via the reason log. Toggle-confirmation still open.

14. **Voice endpoint buffers the full LLM response before streaming** (2026-08-11)
    IMPLEMENTED 2026-08-11: LLM.stream_deltas() (SSE for gwdg/openai, NDJSON for
    ollama); voice endpoint streams sanitize_for_tts'd sentences as generated.
    Head buffered ~48 chars to detect analyze_sensor_data() (falls back to
    buffered flow); buffered path remains automatic fallback on stream errors
    and selectable via VOICE_STREAMING. llm_first_token_ms added to timings.
    Measured warm: first sentence at 2.7s vs full response at 6.3s — TTS starts
    ~3.6s sooner. REMAINING: live ear test that Agora chunk-by-chunk TTS sounds
    natural (sentence pacing); sensor tool-call branch not yet exercised live
    (qwen answered trend question from snapshot without emitting the call).
    STATUS 2026-08-11 evening: two live streaming sessions (avatar 0) produced
    NO spoken response despite healthy 200s. Ruled out: SSE format (now matches
    Agora's custom-llm doc exactly) and nginx buffering (verified incremental
    egress through the public URL).
    RESOLVED: the silence — including on the buffered path — was CARTESIA
    CREDITS EXHAUSTED (402), not streaming. After top-up (2026-08-11), live ear
    test confirmed BOTH modes work: buffered and streaming both speak on both
    avatars. Streaming stays an opt-in voice-lab toggle, OFF by default per
    user preference while it matures. Still unexercised: sensor tool-call
    branch under streaming; sentence-pacing quality on long replies worth an
    ear-check during normal use.

## Watching

- **Cartesia credits exhausted** — 402 on all TTS (2026-08-11). ALL voice sessions
  are silent until topped up: play.cartesia.ai/subscription. Drained by the
  client's long session + test-clip generation. Consider a paid tier sized for
  real usage; TTS testing should use round-trip transcripts sparingly.
- **OpenRouter credits exhausted** — 402 on every call (2026-07-31). Anything still
  routed to OpenRouter fails.
- **Avatar 0 sensor hardware down** — ThingSpeak channel last updated 2026-02-12;
  client/hardware team to investigate.
