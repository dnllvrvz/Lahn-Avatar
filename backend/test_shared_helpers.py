"""
Tests for the shared helper functions extracted during the DRY refactor:
  - create_llm_instance
  - resolve_llm_defaults
  - inject_rag_context
  - handle_sensor_tool_call
"""
import json
import os
import sys
import types
from unittest.mock import MagicMock, patch, mock_open

import pytest

# ── Bootstrap: mock heavy imports so server.py can be loaded without GPU / DB ──

# Stub out modules that require external services or models
STUB_MODULES = [
    "llama_index", "llama_index.core", "llama_index.core.tools",
    "llama_index.core.tools.query_engine",
    "sentence_transformers", "spacy", "torch",
]
for mod_name in STUB_MODULES:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = types.ModuleType(mod_name)

# Provide a fake QueryEngineTool
fake_qe = types.ModuleType("llama_index.core.tools.query_engine")
fake_qe.QueryEngineTool = MagicMock
sys.modules["llama_index.core.tools.query_engine"] = fake_qe

# Ensure 'utils' parent module exists and wire submodule attrs
_utils_pkg = types.ModuleType("utils")
sys.modules["utils"] = _utils_pkg

# Stub avatar_setup so it doesn't run init logic
fake_avatar_setup = types.ModuleType("utils.avatar_setup")
fake_avatar_setup.avatar_llms = {}
fake_avatar_setup.avatar_rag_tools = {}
fake_avatar_setup.avatar_sensor_tools = {}
fake_avatar_setup.avatars_path = "avatars.json"
fake_avatar_setup.generate_avatars_config = MagicMock()
fake_avatar_setup.DEFAULT_CHAT_PROVIDER = "gwdg"
fake_avatar_setup.DEFAULT_CHAT_MODEL = "default-chat-model"
fake_avatar_setup.DEFAULT_TEXT_QUERY_PROVIDER = "gwdg"
fake_avatar_setup.DEFAULT_TEXT_QUERY_MODEL = "default-tq-model"
fake_avatar_setup.DEFAULT_SENSOR_PROVIDER = "gwdg"
fake_avatar_setup.DEFAULT_SENSOR_MODEL = "default-sensor-model"
fake_avatar_setup.SENSOR_SYSTEM_PROMPT = "You are a sensor analyst."
fake_avatar_setup.TEXT_QUERY_SYSTEM_PROMPT = "Generate keywords."
sys.modules["utils.avatar_setup"] = fake_avatar_setup

# Stub processing_pipelines
fake_pp = types.ModuleType("utils.processing_pipelines")
fake_pp.OpenAIRealtimeClient = MagicMock
sys.modules["utils.processing_pipelines"] = fake_pp

# Stub utils.utils
fake_utils = types.ModuleType("utils.utils")
fake_utils.RAG = MagicMock(return_value="some rag context")
fake_utils.build_or_load_index = MagicMock()
fake_utils.fetch_system_prompt_from_gdoc = MagicMock()
fake_utils.fetch_text_index_query = MagicMock()
fake_utils.generate_context_aware_keywords_for_multilingual_text_index_search = MagicMock(
    return_value={"en": ["keyword1"]}
)
fake_utils.format_history_as_string = MagicMock()
fake_utils.pcm_to_wav_bytes = MagicMock()
fake_utils.prepare_query_engines = MagicMock()
fake_utils.transcribe_audio = MagicMock()
fake_utils.web_search = MagicMock()

# SensorsTool mock
class FakeSensorsTool:
    def __init__(self, llm, sensor_url=None, sensor_description=None):
        self.llm = llm
    def __call__(self, query):
        return f"sensor result for: {query}"

fake_utils.SensorsTool = FakeSensorsTool
sys.modules["utils.utils"] = fake_utils

# Stub llm_tooling
fake_llm_tooling = types.ModuleType("utils.llm_tooling")

class FakeLLM:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
    def complete(self, messages):
        result = MagicMock()
        result.text = "LLM response"
        return result

fake_llm_tooling.LLM = FakeLLM
sys.modules["utils.llm_tooling"] = fake_llm_tooling

# Wire submodules as attributes on parent package
_utils_pkg.avatar_setup = fake_avatar_setup
_utils_pkg.processing_pipelines = fake_pp
_utils_pkg.utils = fake_utils
_utils_pkg.llm_tooling = fake_llm_tooling

# Now we can import the helpers from server
# But server.py runs init code on import, so we patch file reads and Flask
os.environ.setdefault("GWDG_API_KEY", "test-gwdg-key")
os.environ.setdefault("GWDG_API_BASE", "https://test-gwdg")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")

# Patch generate_avatars_config to prevent it from running
with patch("utils.avatar_setup.generate_avatars_config"):
    import server


# ─── Sample data ───

SAMPLE_PROVIDERS = [
    {
        "id": "gwdg",
        "name": "GWDG",
        "provider_key": "gwdg",
        "api_key_env": "GWDG_API_KEY",
        "api_base": "https://test-gwdg",
    },
    {
        "id": "openai",
        "name": "OpenAI",
        "provider_key": "openai",
        "api_key_env": "OPENAI_API_KEY",
        "api_base": "",
    },
    {
        "id": "ollama",
        "name": "Ollama",
        "provider_key": "ollama",
        "api_key_env": "OLLAMA_API_KEY",
        "api_base": "http://localhost:11434",
    },
]

SAMPLE_AVATARS = [
    {
        "id": "0",
        "name": "Test Avatar",
        "llmDefaults": {
            "chat": {"provider": "gwdg", "model": "admin-chat-model", "temperature": 0.5, "top_k": 30, "top_p": 0.9},
            "textQuery": {"provider": "gwdg", "model": "admin-tq-model"},
            "sensor": {"provider": "openai", "model": "admin-sensor-model"},
        },
    },
    {
        "id": "1",
        "name": "No Defaults Avatar",
    },
]


# ═══════════════════════════════════════════════════════════════════════
# Test: create_llm_instance
# ═══════════════════════════════════════════════════════════════════════

class TestCreateLLMInstance:
    def test_gwdg_provider(self):
        llm = server.create_llm_instance(
            "gwdg", "test-model", "system prompt",
            temperature=0.5, providers=SAMPLE_PROVIDERS,
        )
        assert llm.kwargs["provider"] == "gwdg"
        assert llm.kwargs["gwdg_model"] == "test-model"
        assert llm.kwargs["temperature"] == 0.5
        assert llm.kwargs["system_prompt"] == "system prompt"

    def test_openai_provider(self):
        llm = server.create_llm_instance(
            "openai", "gpt-4o", "sys",
            providers=SAMPLE_PROVIDERS,
        )
        assert llm.kwargs["provider"] == "openai"
        assert llm.kwargs["openai_model"] == "gpt-4o"
        assert "openai_api_key" in llm.kwargs

    def test_ollama_provider(self):
        llm = server.create_llm_instance(
            "ollama", "llama3", "sys",
            providers=SAMPLE_PROVIDERS,
        )
        assert llm.kwargs["provider"] == "ollama"
        assert llm.kwargs["ollama_model"] == "llama3"

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            server.create_llm_instance("nonexistent", "m", "s", providers=SAMPLE_PROVIDERS)

    def test_default_params(self):
        llm = server.create_llm_instance(
            "gwdg", "m", "s", providers=SAMPLE_PROVIDERS,
        )
        assert llm.kwargs["temperature"] == 0.7
        assert llm.kwargs["top_k"] == 40
        assert llm.kwargs["top_p"] == 1.0

    def test_api_base_set_for_gwdg(self):
        llm = server.create_llm_instance(
            "gwdg", "m", "s", providers=SAMPLE_PROVIDERS,
        )
        assert "gwdg_api_base" in llm.kwargs

    def test_api_base_set_for_ollama(self):
        llm = server.create_llm_instance(
            "ollama", "m", "s", providers=SAMPLE_PROVIDERS,
        )
        assert llm.kwargs.get("ollama_api_base") == "http://localhost:11434"


# ═══════════════════════════════════════════════════════════════════════
# Test: resolve_llm_defaults
# ═══════════════════════════════════════════════════════════════════════

class TestResolveLLMDefaults:
    @patch("builtins.open", mock_open(read_data=json.dumps(SAMPLE_AVATARS)))
    @patch("json.load", return_value=SAMPLE_AVATARS)
    def test_admin_defaults_used_when_no_user_params(self, mock_json):
        resolved, sources = server.resolve_llm_defaults("0")
        assert resolved["chat_provider"] == "gwdg"
        assert resolved["chat_model"] == "admin-chat-model"
        assert resolved["temperature"] == 0.5
        assert resolved["top_k"] == 30
        assert resolved["top_p"] == 0.9
        assert sources["chat_provider"] == "Admin defaults"

    @patch("builtins.open", mock_open(read_data=json.dumps(SAMPLE_AVATARS)))
    @patch("json.load", return_value=SAMPLE_AVATARS)
    def test_user_params_override_admin(self, mock_json):
        user_params = {"chatProvider": "openai", "chatModel": "gpt-4o", "temperature": 0.9}
        resolved, sources = server.resolve_llm_defaults("0", user_params)
        assert resolved["chat_provider"] == "openai"
        assert resolved["chat_model"] == "gpt-4o"
        assert resolved["temperature"] == 0.9
        assert sources["chat_provider"] == "user"
        assert sources["chat_model"] == "user"
        assert sources["temperature"] == "user"

    @patch("builtins.open", mock_open(read_data=json.dumps(SAMPLE_AVATARS)))
    @patch("json.load", return_value=SAMPLE_AVATARS)
    def test_global_defaults_when_no_admin(self, mock_json):
        resolved, sources = server.resolve_llm_defaults("1")  # avatar with no defaults
        assert resolved["chat_provider"] == "gwdg"  # DEFAULT_CHAT_PROVIDER
        assert resolved["chat_model"] == "default-chat-model"
        assert sources["chat_provider"] == "global defaults"

    @patch("builtins.open", mock_open(read_data=json.dumps(SAMPLE_AVATARS)))
    @patch("json.load", return_value=SAMPLE_AVATARS)
    def test_text_query_inherits_from_chat(self, mock_json):
        resolved, sources = server.resolve_llm_defaults("1")
        assert resolved["text_query_provider"] == resolved["chat_provider"]
        assert sources["text_query_provider"] == "inherited from chat"

    @patch("builtins.open", mock_open(read_data=json.dumps(SAMPLE_AVATARS)))
    @patch("json.load", return_value=SAMPLE_AVATARS)
    def test_sensor_uses_admin_defaults(self, mock_json):
        resolved, sources = server.resolve_llm_defaults("0")
        assert resolved["sensor_provider"] == "openai"
        assert resolved["sensor_model"] == "admin-sensor-model"
        assert sources["sensor_provider"] == "Admin defaults"

    @patch("builtins.open", mock_open(read_data=json.dumps(SAMPLE_AVATARS)))
    @patch("json.load", return_value=SAMPLE_AVATARS)
    def test_user_matching_admin_shows_admin_source(self, mock_json):
        """When user sends the same value as admin default, source = Admin defaults."""
        user_params = {"chatProvider": "gwdg"}
        resolved, sources = server.resolve_llm_defaults("0", user_params)
        assert resolved["chat_provider"] == "gwdg"
        assert sources["chat_provider"] == "Admin defaults"


# ═══════════════════════════════════════════════════════════════════════
# Test: inject_rag_context
# ═══════════════════════════════════════════════════════════════════════

class TestInjectRAGContext:
    def setup_method(self):
        self.original_rag_tools = dict(server.avatar_rag_tools)

    def teardown_method(self):
        server.avatar_rag_tools.clear()
        server.avatar_rag_tools.update(self.original_rag_tools)

    def test_no_rag_tools_returns_false(self):
        server.avatar_rag_tools.clear()
        chat_history = [{"role": "user", "content": "hello"}]
        result = server.inject_rag_context("0", chat_history, [], MagicMock())
        assert result is False
        assert chat_history[-1]["content"] == "hello"  # unchanged

    def test_empty_rag_tools_returns_false(self):
        server.avatar_rag_tools["0"] = [None, None, None, None, ['en', 'de']]
        chat_history = [{"role": "user", "content": "hello"}]
        result = server.inject_rag_context("0", chat_history, [], MagicMock())
        assert result is False

    def test_rag_injection_verbose(self):
        server.avatar_rag_tools["99"] = ["engine1", "engine2", "idx", "store", ['en']]
        chat_history = [{"role": "user", "content": "What is the pH?"}]
        conversation = [{"sender": "user", "text": "What is the pH?"}]

        result = server.inject_rag_context("99", chat_history, conversation, MagicMock(), verbose=True)
        assert result is True
        assert "<End of User message>" in chat_history[-1]["content"]
        assert "IMPORTANT" in chat_history[-1]["content"]
        assert "some rag context" in chat_history[-1]["content"]

    def test_rag_injection_compact(self):
        server.avatar_rag_tools["99"] = ["engine1", "engine2", "idx", "store", ['en']]
        chat_history = [{"role": "user", "content": "hello"}]
        conversation = [{"sender": "user", "text": "hello"}]

        result = server.inject_rag_context("99", chat_history, conversation, MagicMock(), verbose=False)
        assert result is True
        assert "Context from knowledge base" in chat_history[-1]["content"]
        assert "IMPORTANT" not in chat_history[-1]["content"]


# ═══════════════════════════════════════════════════════════════════════
# Test: handle_sensor_tool_call
# ═══════════════════════════════════════════════════════════════════════

class TestHandleSensorToolCall:
    def setup_method(self):
        self.original_sensor_tools = dict(server.avatar_sensor_tools)

    def teardown_method(self):
        server.avatar_sensor_tools.clear()
        server.avatar_sensor_tools.update(self.original_sensor_tools)

    def test_no_sensor_config_returns_unhandled(self):
        server.avatar_sensor_tools.clear()
        response, handled = server.handle_sensor_tool_call(
            'analyze_sensor_data(user_query="test")', "0", "gwdg", "m",
            MagicMock(), [], providers=SAMPLE_PROVIDERS,
        )
        assert handled is False

    def test_no_function_call_returns_unhandled(self):
        server.avatar_sensor_tools["0"] = {"sensor_url": "http://test", "sensor_description": "desc"}
        response, handled = server.handle_sensor_tool_call(
            "Hello, how are you?", "0", "gwdg", "m",
            MagicMock(), [], providers=SAMPLE_PROVIDERS,
        )
        assert handled is False
        assert response == "Hello, how are you?"

    def test_sensor_call_handled(self):
        server.avatar_sensor_tools["0"] = {"sensor_url": "http://test", "sensor_description": "desc"}
        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(text="The temperature is 15C")

        chat_history = [{"role": "system", "content": "sys"}, {"role": "user", "content": "what temp?"}]
        response, handled = server.handle_sensor_tool_call(
            'analyze_sensor_data(user_query="current temperature")',
            "0", "gwdg", "default-chat-model", mock_llm, chat_history,
            providers=SAMPLE_PROVIDERS,
        )
        assert handled is True
        assert "The temperature is 15C" in response

    def test_recursive_call_returns_analysis(self):
        """If the re-invoked LLM tries to call sensor again, return raw analysis."""
        server.avatar_sensor_tools["0"] = {"sensor_url": "http://test", "sensor_description": "desc"}
        mock_llm = MagicMock()
        # LLM re-invocation returns another sensor call — should be caught
        mock_llm.complete.return_value = MagicMock(text='analyze_sensor_data(user_query="again")')

        chat_history = [{"role": "system", "content": "sys"}]
        response, handled = server.handle_sensor_tool_call(
            'analyze_sensor_data(user_query="temp")',
            "0", "gwdg", "default-chat-model", mock_llm, chat_history,
            providers=SAMPLE_PROVIDERS,
        )
        assert handled is True
        assert "sensor result for: temp" in response


# ═══════════════════════════════════════════════════════════════════════
# Integration: verify both endpoints can reference the shared helpers
# ═══════════════════════════════════════════════════════════════════════

class TestEndpointIntegration:
    """Smoke tests to verify the refactored endpoints still exist and are callable."""

    def test_chat_endpoint_exists(self):
        assert hasattr(server, 'chat')

    def test_voice_chat_completions_exists(self):
        assert hasattr(server, 'voice_chat_completions')

    def test_shared_helpers_exist(self):
        assert callable(server.create_llm_instance)
        assert callable(server.resolve_llm_defaults)
        assert callable(server.inject_rag_context)
        assert callable(server.handle_sensor_tool_call)
