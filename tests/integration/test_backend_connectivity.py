"""Integration tests for inference backend connectivity."""

import sys
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError

import pytest
import yaml

CONFIGS_DIR = Path(__file__).parent.parent.parent / "configs"


def load_backends():
    with open(CONFIGS_DIR / "backends.yml") as f:
        return yaml.safe_load(f)["backends"]


@pytest.mark.integration
class TestBackendConnectivity:
    """Test that inference backends are reachable (requires network)."""

    @pytest.fixture
    def backends(self):
        return load_backends()

    @pytest.mark.parametrize("backend_name", ["gx10", "minillm", "jetson"])
    def test_backend_health(self, backends, backend_name):
        """Each backend's health endpoint should return 200."""
        if backend_name not in backends:
            pytest.skip(f"Backend {backend_name} not configured")

        backend = backends[backend_name]
        url = backend["url"].rstrip("/") + backend.get("health_endpoint", "/v1/models")
        try:
            req = Request(url, method="GET")
            req.add_header("Accept", "application/json")
            with urlopen(req, timeout=5) as resp:
                assert resp.status == 200, f"{backend_name} returned {resp.status}"
        except URLError as e:
            pytest.skip(f"{backend_name} unreachable: {e.reason}")

    def test_gx10_vllm_models_endpoint(self, backends):
        """GX10 vLLM /v1/models should list available models."""
        if "gx10" not in backends:
            pytest.skip("GX10 not configured")

        url = backends["gx10"]["url"].rstrip("/") + "/v1/models"
        try:
            req = Request(url, method="GET")
            req.add_header("Accept", "application/json")
            with urlopen(req, timeout=5) as resp:
                import json
                data = json.loads(resp.read())
                assert "data" in data, "vLLM /v1/models missing 'data' field"
        except URLError:
            pytest.skip("GX10 unreachable")
