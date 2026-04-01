"""Unit tests for agent configuration validation."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.validate_agents import validate_agent, REQUIRED_FIELDS, VALID_BACKENDS


AGENTS_DIR = Path(__file__).parent.parent.parent / "agents"
CONFIGS_DIR = Path(__file__).parent.parent.parent / "configs"


class TestAgentSchemaValidation:
    """Test that all agent.yml files conform to the schema."""

    @pytest.fixture
    def agent_dirs(self):
        return sorted(d for d in AGENTS_DIR.iterdir() if d.is_dir())

    def test_all_agents_have_config(self, agent_dirs):
        """Every agent directory must have an agent.yml."""
        for agent_dir in agent_dirs:
            agent_file = agent_dir / "agent.yml"
            assert agent_file.exists(), f"{agent_dir.name} missing agent.yml"

    def test_all_agents_valid_yaml(self, agent_dirs):
        """All agent.yml files must be valid YAML."""
        for agent_dir in agent_dirs:
            agent_file = agent_dir / "agent.yml"
            if agent_file.exists():
                with open(agent_file) as f:
                    config = yaml.safe_load(f)
                assert isinstance(config, dict), f"{agent_dir.name}: root must be a mapping"

    def test_all_agents_have_required_fields(self, agent_dirs):
        """All agents must have all required fields."""
        for agent_dir in agent_dirs:
            agent_file = agent_dir / "agent.yml"
            if agent_file.exists():
                with open(agent_file) as f:
                    config = yaml.safe_load(f)
                for field in REQUIRED_FIELDS:
                    assert field in config, f"{agent_dir.name}: missing '{field}'"

    def test_all_agents_have_valid_backend(self, agent_dirs):
        """All agents must reference a valid backend."""
        for agent_dir in agent_dirs:
            agent_file = agent_dir / "agent.yml"
            if agent_file.exists():
                with open(agent_file) as f:
                    config = yaml.safe_load(f)
                model = config.get("model", {})
                backend = model.get("backend", "")
                assert backend in VALID_BACKENDS, (
                    f"{agent_dir.name}: unknown backend '{backend}'"
                )

    def test_agent_role_matches_directory(self, agent_dirs):
        """Agent role field must match directory name."""
        for agent_dir in agent_dirs:
            agent_file = agent_dir / "agent.yml"
            if agent_file.exists():
                with open(agent_file) as f:
                    config = yaml.safe_load(f)
                assert config.get("role") == agent_dir.name, (
                    f"{agent_dir.name}: role '{config.get('role')}' != dir name"
                )

    def test_agent_persona_not_empty(self, agent_dirs):
        """Agent persona must not be empty."""
        for agent_dir in agent_dirs:
            agent_file = agent_dir / "agent.yml"
            if agent_file.exists():
                with open(agent_file) as f:
                    config = yaml.safe_load(f)
                persona = config.get("persona", "")
                assert len(persona.strip()) > 10, (
                    f"{agent_dir.name}: persona too short"
                )


class TestValidateAgentFunction:
    """Test the validate_agent function directly."""

    def test_valid_agent(self, tmp_path):
        """A well-formed agent.yml passes validation."""
        agent_file = tmp_path / "agent.yml"
        agent_file.write_text(yaml.dump({
            "role": "test",
            "name": "TestBot",
            "description": "Test agent",
            "persona": "You are a test bot.",
            "model": {"primary": "qwen3-next-80b-a3b", "backend": "gx10"},
            "tools": ["shell", "git"],
        }))
        errors = validate_agent(agent_file)
        assert errors == []

    def test_missing_required_field(self, tmp_path):
        """Missing required field produces an error."""
        agent_file = tmp_path / "agent.yml"
        agent_file.write_text(yaml.dump({
            "role": "test",
            "name": "TestBot",
            # missing: description, persona, model, tools
        }))
        errors = validate_agent(agent_file)
        assert len(errors) >= 3

    def test_invalid_backend(self, tmp_path):
        """Unknown backend produces an error."""
        agent_file = tmp_path / "agent.yml"
        agent_file.write_text(yaml.dump({
            "role": "test",
            "name": "TestBot",
            "description": "Test",
            "persona": "Test persona",
            "model": {"primary": "foo", "backend": "nonexistent"},
            "tools": ["shell"],
        }))
        errors = validate_agent(agent_file)
        assert any("unknown backend" in e for e in errors)

    def test_invalid_tool(self, tmp_path):
        """Unknown tool produces an error."""
        agent_file = tmp_path / "agent.yml"
        agent_file.write_text(yaml.dump({
            "role": "test",
            "name": "TestBot",
            "description": "Test",
            "persona": "Test persona",
            "model": {"primary": "foo", "backend": "gx10"},
            "tools": ["shell", "laser_cannon"],
        }))
        errors = validate_agent(agent_file)
        assert any("unknown tool" in e for e in errors)

    def test_invalid_yaml(self, tmp_path):
        """Malformed YAML produces a parse error."""
        agent_file = tmp_path / "agent.yml"
        agent_file.write_text("role: test\n  bad indent: yes\n")
        errors = validate_agent(agent_file)
        assert any("YAML parse error" in e for e in errors)


class TestBackendsConfig:
    """Test the backends.yml configuration."""

    def test_backends_file_exists(self):
        assert (CONFIGS_DIR / "backends.yml").exists()

    def test_backends_valid_yaml(self):
        with open(CONFIGS_DIR / "backends.yml") as f:
            config = yaml.safe_load(f)
        assert "backends" in config

    def test_all_backends_have_url(self):
        with open(CONFIGS_DIR / "backends.yml") as f:
            config = yaml.safe_load(f)
        for name, backend in config["backends"].items():
            assert "url" in backend, f"Backend {name} missing 'url'"

    def test_all_backends_have_models(self):
        with open(CONFIGS_DIR / "backends.yml") as f:
            config = yaml.safe_load(f)
        for name, backend in config["backends"].items():
            assert "models" in backend, f"Backend {name} missing 'models'"
            assert len(backend["models"]) > 0, f"Backend {name} has no models"


class TestRoutingConfig:
    """Test the routing.yml configuration."""

    def test_routing_file_exists(self):
        assert (CONFIGS_DIR / "routing.yml").exists()

    def test_routing_has_default(self):
        with open(CONFIGS_DIR / "routing.yml") as f:
            config = yaml.safe_load(f)
        routing = config["routing"]
        assert "default_backend" in routing
        assert "default_model" in routing

    def test_all_agents_have_routing(self):
        """Every agent defined in agents/ must have a routing entry."""
        with open(CONFIGS_DIR / "routing.yml") as f:
            config = yaml.safe_load(f)
        routing_agents = set(config["routing"]["agents"].keys())

        for agent_dir in AGENTS_DIR.iterdir():
            if agent_dir.is_dir() and (agent_dir / "agent.yml").exists():
                assert agent_dir.name in routing_agents, (
                    f"Agent '{agent_dir.name}' has no routing entry"
                )

    def test_routing_backends_are_valid(self):
        """All backends referenced in routing must exist in backends.yml."""
        with open(CONFIGS_DIR / "backends.yml") as f:
            backends = yaml.safe_load(f)
        with open(CONFIGS_DIR / "routing.yml") as f:
            routing = yaml.safe_load(f)

        valid_backends = set(backends["backends"].keys())
        for agent, config in routing["routing"]["agents"].items():
            assert config["backend"] in valid_backends, (
                f"Agent {agent} references unknown backend '{config['backend']}'"
            )
