"""E2E tests for agent workflow validation."""

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.validate_agents import main as validate_main
from scripts.build_agents import build_manifests


AGENTS_DIR = Path(__file__).parent.parent.parent / "agents"
CONFIGS_DIR = Path(__file__).parent.parent.parent / "configs"


@pytest.mark.e2e
class TestFullAgentPipeline:
    """Test the full pipeline: validate → build → output."""

    def test_validate_all_agents_passes(self):
        """Full validation of all agents should pass."""
        result = validate_main()
        assert result == 0, "Agent validation failed"

    def test_build_all_manifests(self):
        """Build manifests for all agents."""
        manifests = build_manifests(AGENTS_DIR, CONFIGS_DIR)
        assert len(manifests) >= 6, f"Expected >=6 agents, got {len(manifests)}"

    def test_manifests_have_unique_names(self):
        """All generated ConfigMaps must have unique names."""
        manifests = build_manifests(AGENTS_DIR, CONFIGS_DIR)
        names = [m["metadata"]["name"] for m in manifests]
        assert len(names) == len(set(names)), f"Duplicate names: {names}"

    def test_routing_covers_all_agents(self):
        """Every agent in agents/ has a routing entry."""
        with open(CONFIGS_DIR / "routing.yml") as f:
            routing = yaml.safe_load(f)

        routing_agents = set(routing["routing"]["agents"].keys())

        for agent_dir in AGENTS_DIR.iterdir():
            if agent_dir.is_dir() and (agent_dir / "agent.yml").exists():
                assert agent_dir.name in routing_agents, (
                    f"Agent {agent_dir.name} has no route"
                )

    def test_all_model_references_resolve(self):
        """Models referenced in routing must exist in backends."""
        with open(CONFIGS_DIR / "backends.yml") as f:
            backends = yaml.safe_load(f)
        with open(CONFIGS_DIR / "routing.yml") as f:
            routing = yaml.safe_load(f)

        all_aliases = set()
        for backend in backends["backends"].values():
            for model in backend.get("models", []):
                all_aliases.add(model.get("alias", model["id"]))

        for agent, config in routing["routing"]["agents"].items():
            model = config["model"]
            assert model in all_aliases, (
                f"Agent {agent} references model '{model}' not in any backend"
            )
