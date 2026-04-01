#!/usr/bin/env python3
"""Generate Kubernetes manifests from agent role definitions."""

import sys
from pathlib import Path

import yaml


def load_agent(agent_dir: Path) -> dict | None:
    """Load an agent definition from a directory."""
    agent_file = agent_dir / "agent.yml"
    if not agent_file.exists():
        return None
    with open(agent_file) as f:
        return yaml.safe_load(f)


def load_backends(config_dir: Path) -> dict:
    """Load backend configuration."""
    with open(config_dir / "backends.yml") as f:
        return yaml.safe_load(f)


def load_routing(config_dir: Path) -> dict:
    """Load routing configuration."""
    with open(config_dir / "routing.yml") as f:
        return yaml.safe_load(f)


def build_configmap(agent: dict) -> dict:
    """Build a ConfigMap for an agent's persona and config."""
    role = agent["role"]
    return {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {
            "name": f"openclaw-{role}-config",
            "namespace": "automation",
            "labels": {
                "app.kubernetes.io/component": f"openclaw-{role}",
                "app.kubernetes.io/part-of": "openclaw",
            },
        },
        "data": {
            "PERSONA.md": agent.get("persona", ""),
            "agent.yml": yaml.dump(agent, default_flow_style=False),
        },
    }


def build_manifests(agents_dir: Path, config_dir: Path) -> list[dict]:
    """Build all k8s manifests from agent definitions."""
    manifests = []

    for agent_dir in sorted(agents_dir.iterdir()):
        if not agent_dir.is_dir():
            continue
        agent = load_agent(agent_dir)
        if agent is None:
            continue
        manifests.append(build_configmap(agent))

    return manifests


def main() -> int:
    """Generate and output k8s manifests."""
    project_root = Path(__file__).parent.parent
    agents_dir = project_root / "agents"
    config_dir = project_root / "configs"

    if not agents_dir.exists():
        print(f"ERROR: {agents_dir} not found", file=sys.stderr)
        return 1

    manifests = build_manifests(agents_dir, config_dir)

    output = ""
    for i, manifest in enumerate(manifests):
        if i > 0:
            output += "---\n"
        output += yaml.dump(manifest, default_flow_style=False)

    # Write to stdout or file based on args
    if len(sys.argv) > 2 and sys.argv[1] == "--output":
        output_path = Path(sys.argv[2])
        output_path.write_text(output)
        print(f"Wrote {len(manifests)} manifests to {output_path}")
    else:
        print(output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
