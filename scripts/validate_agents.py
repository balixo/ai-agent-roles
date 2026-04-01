#!/usr/bin/env python3
"""Validate all agent configuration files for correctness."""

import sys
from pathlib import Path

import yaml


REQUIRED_FIELDS = ["role", "name", "description", "persona", "model", "tools"]
MODEL_FIELDS = ["primary", "backend"]
VALID_BACKENDS = {"gx10", "minillm", "jetson"}
VALID_TOOLS = {"shell", "git", "http", "k8s-api", "rag", "ci-api", "ansible"}


def validate_agent(agent_path: Path) -> list[str]:
    """Validate a single agent.yml file. Returns list of errors."""
    errors = []
    try:
        with open(agent_path) as f:
            config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        return [f"{agent_path}: YAML parse error: {e}"]

    if not isinstance(config, dict):
        return [f"{agent_path}: root must be a mapping"]

    for field in REQUIRED_FIELDS:
        if field not in config:
            errors.append(f"{agent_path}: missing required field '{field}'")

    model = config.get("model", {})
    if isinstance(model, dict):
        for field in MODEL_FIELDS:
            if field not in model:
                errors.append(f"{agent_path}: model missing '{field}'")
        backend = model.get("backend", "")
        if backend and backend not in VALID_BACKENDS:
            errors.append(f"{agent_path}: unknown backend '{backend}'")
        fallback = model.get("fallback_backend", "")
        if fallback and fallback not in VALID_BACKENDS:
            errors.append(f"{agent_path}: unknown fallback_backend '{fallback}'")

    tools = config.get("tools", [])
    if isinstance(tools, list):
        for tool in tools:
            if tool not in VALID_TOOLS:
                errors.append(f"{agent_path}: unknown tool '{tool}'")

    return errors


def main() -> int:
    """Validate all agents in the agents/ directory."""
    agents_dir = Path(__file__).parent.parent / "agents"
    if not agents_dir.exists():
        print(f"ERROR: agents directory not found: {agents_dir}")
        return 1

    all_errors = []
    agent_count = 0

    for agent_dir in sorted(agents_dir.iterdir()):
        agent_file = agent_dir / "agent.yml"
        if agent_file.exists():
            agent_count += 1
            errors = validate_agent(agent_file)
            all_errors.extend(errors)
            status = "FAIL" if errors else "OK"
            print(f"  [{status}] {agent_dir.name}")

    print(f"\nValidated {agent_count} agents, {len(all_errors)} errors")

    if all_errors:
        print("\nErrors:")
        for error in all_errors:
            print(f"  - {error}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
