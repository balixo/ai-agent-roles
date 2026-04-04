"""Unit tests for multimodal pipeline configuration."""

from pathlib import Path

import pytest
import yaml


CONFIGS_DIR = Path(__file__).parent.parent.parent / "configs"
AGENTS_DIR = Path(__file__).parent.parent.parent / "agents"

VALID_MEDIA_TYPES = {"image", "document", "spreadsheet", "video", "audio"}
VALID_PIPELINES = {"vl_then_reasoning"}


def load_multimodal_config():
    with open(CONFIGS_DIR / "multimodal.yml") as f:
        return yaml.safe_load(f)


def load_routing_config():
    with open(CONFIGS_DIR / "routing.yml") as f:
        return yaml.safe_load(f)


def load_backends_config():
    with open(CONFIGS_DIR / "backends.yml") as f:
        return yaml.safe_load(f)


def load_agent_config(agent_name):
    with open(AGENTS_DIR / agent_name / "agent.yml") as f:
        return yaml.safe_load(f)


class TestMultimodalConfig:
    """Test multimodal.yml structure and consistency."""

    @pytest.fixture
    def config(self):
        return load_multimodal_config()

    def test_pipeline_enabled(self, config):
        assert config["pipeline"]["enabled"] is True

    def test_vl_backend_configured(self, config):
        vl = config["pipeline"]["vl_backend"]
        assert vl["backend"] == "minillm"
        assert "qwen3-vl" in vl["model"]
        assert vl["url"].startswith("http://")

    def test_stt_backend_configured(self, config):
        stt = config["pipeline"]["stt_backend"]
        assert stt["backend"] == "minillm"
        assert "whisper" in stt["model"]

    def test_reasoning_backend_configured(self, config):
        reasoning = config["pipeline"]["reasoning_backend"]
        assert reasoning["backend"] == "gx10"
        assert "80b" in reasoning["model"]

    def test_all_handlers_have_extensions(self, config):
        for name, handler in config["pipeline"]["handlers"].items():
            assert "extensions" in handler, f"Handler '{name}' missing extensions"
            assert "mime_types" in handler, f"Handler '{name}' missing mime_types"
            assert "extractor" in handler, f"Handler '{name}' missing extractor"

    def test_handler_names_match_valid_types(self, config):
        for name in config["pipeline"]["handlers"]:
            assert name in VALID_MEDIA_TYPES, f"Unknown handler type '{name}'"

    def test_enabled_and_disabled_agents_are_disjoint(self, config):
        enabled = set(config["pipeline"]["enabled_agents"])
        disabled = set(config["pipeline"]["disabled_agents"])
        overlap = enabled & disabled
        assert not overlap, f"Agents in both enabled and disabled: {overlap}"

    def test_all_listed_agents_exist(self, config):
        all_agents = (
            config["pipeline"]["enabled_agents"]
            + config["pipeline"]["disabled_agents"]
        )
        for agent_name in all_agents:
            agent_dir = AGENTS_DIR / agent_name
            assert agent_dir.exists(), f"Agent '{agent_name}' directory not found"

    def test_security_limits_set(self, config):
        sec = config["pipeline"]["security"]
        assert sec["max_file_size_mb"] > 0
        assert sec["max_uploads_per_user_per_hour"] > 0
        assert sec["scan_uploads"] is True
        assert sec["reject_double_extensions"] is True

    def test_composition_has_template(self, config):
        comp = config["pipeline"]["composition"]
        assert "{filename}" in comp["extraction_prefix"]
        assert comp["max_extraction_tokens"] > 0


class TestMultimodalRouting:
    """Test that routing.yml multimodal section references valid backends."""

    @pytest.fixture
    def routing(self):
        return load_routing_config()

    @pytest.fixture
    def backends(self):
        return load_backends_config()

    def test_routing_has_multimodal_section(self, routing):
        assert "multimodal" in routing["routing"]

    def test_multimodal_enabled_in_routing(self, routing):
        assert routing["routing"]["multimodal"]["enabled"] is True

    def test_vl_backend_exists_in_backends(self, routing, backends):
        vl_backend = routing["routing"]["multimodal"]["vl_backend"]
        assert vl_backend in backends["backends"]

    def test_stt_backend_exists_in_backends(self, routing, backends):
        stt_backend = routing["routing"]["multimodal"]["stt_backend"]
        assert stt_backend in backends["backends"]

    def test_reasoning_backend_exists_in_backends(self, routing, backends):
        reasoning = routing["routing"]["multimodal"]["reasoning_backend"]
        assert reasoning in backends["backends"]


class TestAgentMultimodalDeclarations:
    """Test that agents correctly declare multimodal support."""

    @pytest.fixture
    def multimodal_config(self):
        return load_multimodal_config()

    def test_enabled_agents_have_multimodal_section(self, multimodal_config):
        """Agents listed in multimodal.yml enabled_agents must declare multimodal."""
        for agent_name in multimodal_config["pipeline"]["enabled_agents"]:
            config = load_agent_config(agent_name)
            assert "multimodal" in config, (
                f"Agent '{agent_name}' is in enabled_agents but has no multimodal section"
            )
            assert config["multimodal"]["enabled"] is True

    def test_enabled_agents_have_valid_media_types(self, multimodal_config):
        """All accepted_media types must be valid handler types."""
        for agent_name in multimodal_config["pipeline"]["enabled_agents"]:
            config = load_agent_config(agent_name)
            mm = config.get("multimodal", {})
            for media_type in mm.get("accepted_media", []):
                assert media_type in VALID_MEDIA_TYPES, (
                    f"Agent '{agent_name}' has unknown media type '{media_type}'"
                )

    def test_enabled_agents_have_valid_pipeline(self, multimodal_config):
        """Pipeline must be a known pipeline type."""
        for agent_name in multimodal_config["pipeline"]["enabled_agents"]:
            config = load_agent_config(agent_name)
            mm = config.get("multimodal", {})
            assert mm.get("pipeline") in VALID_PIPELINES, (
                f"Agent '{agent_name}' has unknown pipeline '{mm.get('pipeline')}'"
            )

    def test_disabled_agents_have_no_multimodal(self, multimodal_config):
        """Agents listed in disabled_agents should NOT have multimodal enabled."""
        for agent_name in multimodal_config["pipeline"]["disabled_agents"]:
            config = load_agent_config(agent_name)
            mm = config.get("multimodal", {})
            assert not mm.get("enabled", False), (
                f"Agent '{agent_name}' is in disabled_agents but has multimodal enabled"
            )

    def test_whisper_model_registered_in_backends(self):
        """The whisper STT model must be listed in backends.yml."""
        backends = load_backends_config()
        minillm_models = backends["backends"]["minillm"]["models"]
        model_ids = [m["id"] for m in minillm_models]
        assert any("whisper" in m for m in model_ids), (
            "whisper model not found in minillm backend models"
        )

    def test_vl_model_registered_in_backends(self):
        """The VL model must be listed in backends.yml."""
        backends = load_backends_config()
        minillm_models = backends["backends"]["minillm"]["models"]
        model_ids = [m["id"] for m in minillm_models]
        assert any("vl" in m for m in model_ids), (
            "VL model not found in minillm backend models"
        )
