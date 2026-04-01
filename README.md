# AI Agent Roles

> Declarative definitions for AI agent personas, tools, and routing rules.
> Used by OpenClaw (k8s) and standalone agent deployments.

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                      AI Inference Tier                            │
│                                                                   │
│  ┌─────────────┐   ┌──────────────┐   ┌───────────────────────┐  │
│  │ GX10 (.92)  │   │ minillm (.57)│   │ Jetson (.81)          │  │
│  │ vLLM        │   │ Ollama       │   │ Ollama                │  │
│  │             │   │              │   │                       │  │
│  │ Qwen3.5-32B │   │ qwen3.5:4b   │   │ snowflake-arctic-     │  │
│  │ Qwen3.5-7B  │   │ qwen3-vl:4b  │   │ embed2                │  │
│  │ Qwen3.5-3B  │   │              │   │                       │  │
│  └──────┬──────┘   └──────┬───────┘   └───────────┬───────────┘  │
│         │                 │                       │              │
│    Primary           Secondary              Embeddings           │
│    (heavy tasks)     (fast text/vision)      (RAG ingest)        │
└─────────┴─────────────────┴───────────────────────┴──────────────┘
                            │
                    ┌───────▼───────┐
                    │  Agent Router │
                    │  (gateway)    │
                    └───────┬───────┘
                            │
        ┌───────┬───────┬───┴───┬─────────┬──────────┐
        │       │       │       │         │          │
     ┌──▼──┐┌──▼──┐┌───▼──┐┌──▼───┐┌────▼───┐┌────▼────┐
     │ Dev ││ SRE ││Tester││Sr-Dev││Research││  Ops    │
     │ Bot ││ Bot ││ Bot  ││ Bot  ││  Bot   ││  Bot    │
     └─────┘└─────┘└──────┘└──────┘└────────┘└─────────┘
```

## Agent Roles

| Agent | Purpose | Model | Tools |
|-------|---------|-------|-------|
| **DevBot** | Feature implementation, branch/PR creation | Qwen3.5-32B (GX10) | shell, git, http |
| **SREBot** | Infrastructure monitoring, incident diagnosis | Qwen3.5-7B (GX10) | k8s-api, shell |
| **TesterBot** | PR review, CI triggering, test execution | Qwen3.5-7B (GX10) | git, ci-api |
| **SrDevBot** | Code review, PR approval, architecture guidance | Qwen3.5-32B (GX10) | git, http |
| **ResearchBot** | Learning companion, paper summarization | Qwen3.5-7B (GX10) | http, rag |
| **OpsBot** | Ansible playbook execution, node health | Qwen3.5-3B (GX10) | shell, ansible |

## Inference Backends

| Backend | URL | Engine | Models |
|---------|-----|--------|--------|
| **GX10** | `http://192.168.68.92:8000/v1` | vLLM | Qwen3.5-32B, 7B, 3B |
| **minillm** | `http://192.168.68.57:11434/v1` | Ollama | qwen3.5:4b, qwen3-vl:4b |
| **Jetson** | `http://192.168.68.81:11434/v1` | Ollama | snowflake-arctic-embed2 |

## Project Structure

```
ai-agent-roles/
├── README.md              # This file
├── agents/                # Agent persona definitions
│   ├── dev/               # Developer agent
│   ├── sre/               # SRE agent
│   ├── tester/            # Tester agent
│   ├── sr-dev/            # Senior developer agent
│   ├── research/          # Research/learning agent
│   └── ops/               # Operations agent
├── configs/               # Shared configuration
│   ├── backends.yml       # Inference backend definitions
│   └── routing.yml        # Model routing rules
├── scripts/               # Deployment & management scripts
│   ├── build_agents.py    # Generate k8s manifests from agent definitions
│   ├── validate_agents.py # Validate agent configs
│   └── test_backends.py   # Test connectivity to inference backends
└── tests/                 # Test suite
    ├── unit/              # Unit tests for scripts
    ├── integration/       # Integration tests (backend connectivity)
    └── e2e/               # End-to-end agent workflow tests
```

## Usage

```bash
# Validate all agent configurations
python scripts/validate_agents.py

# Test inference backend connectivity
python scripts/test_backends.py

# Generate k8s manifests from agent definitions
python scripts/build_agents.py --output /tmp/agents.yaml

# Run tests
pytest tests/
```

## Relationship to Other Projects

- **home-lab-ops**: Provisions GX10/minillm/Jetson nodes (Ansible)
- **k8s-home-lab**: Deploys OpenClaw gateway + agent pods (ArgoCD)
- **ai-agent-roles**: Defines agent personas, routing, and tools (this project)
