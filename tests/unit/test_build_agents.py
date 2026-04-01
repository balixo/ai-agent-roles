"""Unit tests for build_agents.py manifest generation."""

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.build_agents import load_agent, build_configmap, build_manifests


AGENTS_DIR = Path(__file__).parent.parent.parent / "agents"
CONFIGS_DIR = Path(__file__).parent.parent.parent / "configs"


class TestLoadAgent:
    """Test agent loading from YAML files."""

    def test_load_existing_agent(self):
        """Load a known agent directory."""
        agent = load_agent(AGENTS_DIR / "dev")
        assert agent is not None
        assert agent["role"] == "dev"
        assert agent["name"] == "DevBot"

    def test_load_nonexistent_agent(self, tmp_path):
        """Loading from a dir without agent.yml returns None."""
        assert load_agent(tmp_path) is None


class TestBuildConfigMap:
    """Test ConfigMap generation."""

    def test_configmap_structure(self):
        agent = {
            "role": "dev",
            "name": "DevBot",
            "persona": "You are a developer.",
        }
        cm = build_configmap(agent)
        assert cm["apiVersion"] == "v1"
        assert cm["kind"] == "ConfigMap"
        assert cm["metadata"]["name"] == "openclaw-dev-config"
        assert cm["metadata"]["namespace"] == "automation"
        assert "PERSONA.md" in cm["data"]

    def test_configmap_has_labels(self):
        agent = {"role": "sre", "name": "SREBot", "persona": "SRE"}
        cm = build_configmap(agent)
        labels = cm["metadata"]["labels"]
        assert labels["app.kubernetes.io/component"] == "openclaw-sre"
        assert labels["app.kubernetes.io/part-of"] == "openclaw"


class TestBuildManifests:
    """Test full manifest generation."""

    def test_generates_manifests_for_all_agents(self):
        manifests = build_manifests(AGENTS_DIR, CONFIGS_DIR)
        agent_count = sum(
            1 for d in AGENTS_DIR.iterdir()
            if d.is_dir() and (d / "agent.yml").exists()
        )
        assert len(manifests) == agent_count

    def test_all_manifests_are_valid_k8s(self):
        manifests = build_manifests(AGENTS_DIR, CONFIGS_DIR)
        for m in manifests:
            assert "apiVersion" in m
            assert "kind" in m
            assert "metadata" in m

    def test_manifest_output_is_valid_yaml(self):
        manifests = build_manifests(AGENTS_DIR, CONFIGS_DIR)
        output = ""
        for i, m in enumerate(manifests):
            if i > 0:
                output += "---\n"
            output += yaml.dump(m, default_flow_style=False)
        # Should be parseable as multi-doc YAML
        docs = list(yaml.safe_load_all(output))
        assert len(docs) == len(manifests)
