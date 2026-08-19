import os, json, threading, time
from dotenv import load_dotenv

from .llm_tooling import LLM
from .utils import prepare_query_engines, SensorsTool, fetch_system_prompt_from_gdoc


load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY") #("GWDG_API_KEY")
API_BASE = None #os.getenv("GWDG_API_BASE")


# Default LLM choices for each task (used when not specified in request).
# Keep these on a provider with working credentials — they are the last-resort
# fallback when an avatar has no admin defaults (see ISSUES.md 13).
DEFAULT_CHAT_PROVIDER = "gwdg"
DEFAULT_CHAT_MODEL = "gwdg/openai-gpt-oss-120b"

DEFAULT_TEXT_QUERY_PROVIDER = "gwdg"
DEFAULT_TEXT_QUERY_MODEL = "meta-llama-3.1-8b-instruct"

DEFAULT_SENSOR_PROVIDER = "gwdg"
DEFAULT_SENSOR_MODEL = "gwdg/openai-gpt-oss-120b"

# System prompts for different tasks
SENSOR_SYSTEM_PROMPT = 'Provide an accurate response to the given query. Only perform calculations. Do not generate any plots or visualizations. Always include the following setup **before any resampling or time-based operations**: df[\'created_at\'] = pd.to_datetime(df[\'created_at\');  df = df.set_index(\'created_at\') . When calculating the variation of a quantity over an interval, use the largest of [seconds, minutes, hours,days, weeks,months,years] which is smaller than the range you\'re calculating over. For example, \'How has X varied over the past week?\' should be based on a daily interval. \'How has Y varied over the past year?\' on a monthly interval etc. :'

TEXT_QUERY_SYSTEM_PROMPT = 'Context is needed to address the most recent message in the conversation (NOTE: EMPHASIS ON THE USER\'S LAST MESSAGE. INFO IS NEEDED TO RESPOND TO THE USER\'S LAST MESSAGE) (Or maybe not. Look through the given conversation and determine. If not, your query could just be "General information about the Lahn"). Return a one-line string containing 6 total keywords, each separated by a comma and space: 3 relevant English keywords  (to be queried in the database) that aim to extract the needed context, a "|" divider, and another 3 keywords corresponding to the German translations of the earlier keywords. Your job is not to predict what any party will say, but to return these keywords, so they can be used to extract information relevant for the concerned party to make their decision. That is where your job stops. Reply only with the keywords and nothing else (not even "keywords:"). The keywords should be only relevant to the most recent message, since that is what context is needed on. Double-check that your response is in the format "keyword1, keyword2, keyword3 | keyword1translation, keyword2translation, keyword3translation", with the keywords being only relevant to the last message: :'

RAG_EVICT_AFTER = 30 * 60  # seconds of inactivity before evicting an avatar's index


class AvatarConfig:
    def __init__(self, system_prompt):
        self.system_prompt = system_prompt


class LazyAvatarRAGTools:
    """
    Drop-in replacement for a plain dict of avatar RAG tools.
    Avatars with a drive folder have their vector/text indices loaded on first
    access and evicted after RAG_EVICT_AFTER seconds of inactivity.
    Avatars without a drive folder return a no-op sentinel immediately.
    """

    def __init__(self):
        self._meta = {}       # avatar_id -> {drive_folder_id, rag_languages, pinned}
        self._loaded = {}     # avatar_id -> (tools, last_access_ts)
        self._no_rag = {}     # avatar_id -> [None, None, None, None, rag_languages]
        self._last_load_ms = {}  # avatar_id -> duration of the most recent cold load
        self._lock = threading.Lock()
        t = threading.Thread(target=self._eviction_loop, daemon=True)
        t.start()

    # ── dict-like interface ──────────────────────────────────────────────────

    def __contains__(self, avatar_id):
        return avatar_id in self._meta or avatar_id in self._no_rag

    def get(self, avatar_id, default=None):
        try:
            return self[avatar_id]
        except KeyError:
            return default

    def __getitem__(self, avatar_id):
        if avatar_id in self._no_rag:
            return self._no_rag[avatar_id]

        if avatar_id not in self._meta:
            raise KeyError(avatar_id)

        with self._lock:
            if avatar_id in self._loaded:
                tools, _ = self._loaded[avatar_id]
                self._loaded[avatar_id] = (tools, time.time())
                return tools

        # Load outside the lock so other avatars aren't blocked
        meta = self._meta[avatar_id]
        print(f"[RAG cache] Loading index for avatar {avatar_id}...")
        t0 = time.time()
        tools = prepare_query_engines(
            avatar_id=avatar_id,
            drive_folder_id=meta['drive_folder_id'],
            rag_languages=meta['rag_languages'],
        )
        load_ms = round((time.time() - t0) * 1000)
        with self._lock:
            self._loaded[avatar_id] = (tools, time.time())
            self._last_load_ms[avatar_id] = load_ms
        print(f"[RAG cache] Avatar {avatar_id} index loaded and cached ({load_ms}ms)")
        return tools

    def __setitem__(self, avatar_id, value):
        """
        Support direct assignment used by refresh endpoints and generate_avatars_config.
        If value looks like loaded tools (list starting with a non-None), cache it.
        If value is a no-rag sentinel, store in _no_rag.
        """
        if isinstance(value, list) and (not value or value[0] is None):
            self._no_rag[avatar_id] = value
            with self._lock:
                self._loaded.pop(avatar_id, None)
        else:
            with self._lock:
                self._loaded[avatar_id] = (value, time.time())

    def register(self, avatar_id, drive_folder_id, rag_languages, pinned=False):
        """Register an avatar for lazy loading without loading its index yet."""
        self._meta[avatar_id] = {
            'drive_folder_id': drive_folder_id,
            'rag_languages': rag_languages,
            'pinned': pinned,
        }

    def invalidate(self, avatar_id):
        """Force eviction so the next access reloads from disk."""
        with self._lock:
            self._loaded.pop(avatar_id, None)

    def consume_load_ms(self, avatar_id):
        """
        Return-and-clear the duration of the last cold load for this avatar, so
        the request that triggered it can report it as its own latency segment
        (and later requests don't).
        """
        with self._lock:
            return self._last_load_ms.pop(avatar_id, 0)

    def warm_pinned(self):
        """
        Load pinned avatars' indexes in a background thread so their users never
        pay the cold start. Called at startup and after avatar config changes;
        already-loaded indexes are a no-op.
        """
        pinned = [aid for aid, m in self._meta.items() if m.get('pinned')]
        if not pinned:
            return
        def _warm():
            for aid in pinned:
                try:
                    _ = self[aid]
                    # Discard the load record — this load wasn't paid by a user
                    # request, so no request should report it as its cold start.
                    self.consume_load_ms(aid)
                except Exception as e:
                    print(f"[RAG cache] warm failed for pinned avatar {aid}: {e}")
        threading.Thread(target=_warm, daemon=True).start()
        print(f"[RAG cache] warming pinned avatars in background: {pinned}")

    # ── background eviction ──────────────────────────────────────────────────

    def _eviction_loop(self):
        while True:
            time.sleep(60)
            cutoff = time.time() - RAG_EVICT_AFTER
            with self._lock:
                stale = [aid for aid, (_, ts) in self._loaded.items()
                         if ts < cutoff and not self._meta.get(aid, {}).get('pinned')]
                for aid in stale:
                    del self._loaded[aid]
                    print(f"[RAG cache] Evicted avatar {aid} index (inactive for 30 min)")


class AvatarConfig:
    def __init__(self, system_prompt):
        self.system_prompt = system_prompt


def sensor_config_from_avatar(avatar):
    """Build the runtime sensor config for an avatar record (None if no sensor URL)."""
    url = (avatar.get('sensorApiUrl') or '').strip()
    if not url:
        return None
    desc = (avatar.get('sensorDescription') or '').strip()
    return {'sensor_url': url, 'sensor_description': desc or None}


def generate_avatars_config(specific_avatar_id=None):
	global avatars_path, avatar_llms, avatar_rag_tools, avatar_sensor_tools
	avatars_path = 'avatars.json'
	avatars = json.load(open(avatars_path, 'r'))

	if specific_avatar_id is None:
		avatar_llms = {}
		avatar_rag_tools = LazyAvatarRAGTools()
		avatar_sensor_tools = {}
		avatars_to_process = avatars
	else:
		avatars_to_process = [a for a in avatars if a['id'] == specific_avatar_id]
		if not avatars_to_process:
			return None, None, None

	for avatar in avatars_to_process:
		avatar_id = avatar['id']
		print('\nWorking on Avatar: ', avatar_id)
		try:
			system_prompt = open('avatars_context/'+avatar_id+'/prompt/system_prompt.txt','r').read()
		except FileNotFoundError:
			print('System prompt not found for avatar ' + avatar_id + '. Fetching from G-Doc...')
			if avatar.get('systemPromptUrl'):
				fetch_system_prompt_from_gdoc(avatar_id, avatar['systemPromptUrl'])
				system_prompt = open('avatars_context/'+avatar_id+'/prompt/system_prompt.txt','r').read()
			else:
				system_prompt = "Default system prompt."

		avatar_config = AvatarConfig(system_prompt=system_prompt)

		rag_languages = avatar.get('ragLanguages', ['en', 'de'])
		drive_folder_id = avatar.get('driveFolderId')
		print(f"Avatar {avatar_id} RAG languages: {rag_languages}")

		if drive_folder_id:
			# Register for lazy loading — index is NOT loaded now. Pinned avatars
			# (ragPinned in avatars.json) are warmed in the background below and
			# never evicted.
			avatar_rag_tools.register(avatar_id, drive_folder_id, rag_languages,
			                          pinned=bool(avatar.get('ragPinned')))
			print(f"Avatar {avatar_id} RAG index registered for lazy loading"
			      + (" (pinned)" if avatar.get('ragPinned') else ""))
		else:
			# No RAG — store no-op sentinel immediately (cheap)
			avatar_rag_tools[avatar_id] = [None, None, None, None, rag_languages]
			print(f"Avatar {avatar_id} has no drive folder — RAG disabled")

		sensor_config = sensor_config_from_avatar(avatar)
		if sensor_config:
			print(f"Storing sensor config for avatar {avatar_id}")
		else:
			print(f"No sensor API URL for avatar {avatar_id}")
		avatar_sensor_tools[avatar_id] = sensor_config

		if specific_avatar_id:
			avatar_llms[avatar_id] = avatar_config
			# For a refresh, force-load the index immediately so it's ready
			if drive_folder_id:
				avatar_rag_tools.invalidate(avatar_id)
				_ = avatar_rag_tools[avatar_id]  # trigger load
				avatar_rag_tools.consume_load_ms(avatar_id)  # admin-triggered, not a request's cold start
			return avatar_config, avatar_rag_tools[avatar_id], avatar_sensor_tools

		avatar_llms[avatar_id] = avatar_config

	avatar_rag_tools.warm_pinned()
	return avatar_llms, avatar_rag_tools, avatar_sensor_tools


avatar_llms, avatar_rag_tools, avatar_sensor_tools = generate_avatars_config()
