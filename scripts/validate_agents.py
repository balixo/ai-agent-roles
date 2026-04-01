#!/usr/bin/env python3
"""Validate all agent configuration files for correctness and security policy compliance."""

import sys
from pathlib import Path

import yaml


REQUIRED_FIELDS = ["role", "name", "description", "persona", "model", "tools"]
MODEL_FIELDS = ["primary", "backend"]
VALID_BACKENDS = {"gx10", "minillm", "jetson"}
VALID_TOOLS = {"shell", "git", "http", "k8s-api", "rag", "ci-api", "ansible"}


def load_security_policy() -> dict | None:
    """Load security.yml if it exists. Returns None if not found."""
    security_path = Path(__file__).parent.parent / "configs" / "security.yml"
    if not security_path.exists():
        return None
    with open(security_path) as f:
        return yaml.safe_load(f)


def validate_agent(agent_path: Path, security_policy: dict | None = None) -> list[str]:
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

    # ── Security policy cross-check ─────────────────────────────────────
    if security_policy and isinstance(tools, list):
        role = config.get("role", "")
        agents_policy = security_policy.get("agents", {})
        if role and role in agents_policy:
            policy = agents_policy[role]
            allowed = set(policy.get("tools_allowed", []))
            for tool in tools:
                if tool not in allowed:
                    errors.append(
                        f"{agent_path}: tool '{tool}' not in security policy "
                        f"tools_allowed for {role}"
                    )
            # Check k8s_access consistency
            k8s_access = policy.get("k8s_access", "none")
            if k8s_access == "none" and "k8s-api" in tools:
                errors.append(
                    f"{agent_path}: has k8s-api tool but security policy "
                    f"sets k8s_access=none for {role}"
                )

    return errors


def main() -> int:
    """Validate all agents in the agents/ directory."""
    agents_dir = Path(__file__).parent.parent / "agents"
    if not agents_dir.exists():
        print(f"ERROR: agents directory not found: {agents_dir}")
        return 1

    security_policy = load_security_policy()
    if security_policy:
        print("  [INFO] security.yml loaded — cross-checking tools")
    else:
        print("  [WARN] security.yml not found — skipping policy checks")

    all_errors = []
    agent_count = 0

    for agent_dir in sorted(agents_dir.iterdir()):
        agent_file = agent_dir / "agent.yml"
        if agent_file.exists():
            agent_count += 1
            errors = validate_agent(agent_file, security_policy)
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
