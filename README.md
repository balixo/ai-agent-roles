# AI Agent Roles

> Declarative definitions for AI agent personas, tools, and routing rules.
> Used by OpenClaw (k8s) and standalone agent deployments.

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                      AI Inference Tier                            │
│                                                                   │
│  ┌──────────────────┐ ┌──────────────┐ ┌───────────────────────┐ │
│  │ GX10 (.92)       │ │ minillm (.57)│ │ Jetson (.81)          │ │
│  │ vLLM             │ │ Ollama       │ │ Ollama                │ │
│  │                  │ │              │ │                       │ │
│  │ Qwen3-Next-80B   │ │ qwen3.5:4b   │ │ snowflake-arctic-     │ │
│  │ (MoE 3B active)  │ │ qwen3-vl:4b  │ │ embed2                │ │
│  │ NVFP4, 65K ctx   │ │              │ │                       │ │
│  └────────┬─────────┘ └──────┬───────┘ └───────────┬───────────┘ │
│           │                  │                     │             │
│      Primary            Secondary             Embeddings         │
│      (heavy tasks)      (fast text/vision)    (RAG ingest)       │
└───────────┴──────────────────┴─────────────────────┴─────────────┘
                               │
                       ┌───────▼───────┐
                       │  Agent Router │
                       │  (gateway)    │
                       └───────┬───────┘
                               │
    ┌──────┬──────┬──────┬─────┴─────┬─────────┬──────────┐
    │      │      │      │           │         │          │
 ┌──▼──┐┌──▼──┐┌─▼───┐┌─▼────┐┌────▼───┐┌────▼────┐┌────▼─────┐
 │ Dev ││ SRE ││Test ││Sr-Dev││Research││  Ops    ││ Teachers │
 │ Bot ││ Bot ││ Bot ││ Bot  ││  Bot   ││  Bot    ││ + Family │
 └─────┘└─────┘└─────┘└──────┘└────────┘└─────────┘└──────────┘
```

## Agent Roles

| Agent | Purpose | Primary Model | Backend | Tools |
|-------|---------|---------------|---------|-------|
| **DevBot** | Feature implementation, branch/PR creation | Qwen3-Next-80B | GX10 | shell, git, http |
| **SrDevBot** | Code review, PR approval, architecture guidance | Qwen3-Next-80B | GX10 | git, http |
| **SREBot** | Infrastructure monitoring, auto-recovery | qwen3.5:4b | minillm | k8s-api, shell, prometheus, loki |
| **TesterBot** | PR review, CI triggering, test execution | qwen3.5:4b | minillm | git, ci-api |
| **ResearchBot** | Learning companion, paper summarization | Qwen3-Next-80B | GX10 | http, rag |
| **OpsBot** | Ansible playbook execution, node health | qwen3.5:4b | minillm | shell, ansible |
| **JrDevBot** | Simple tasks, scaffolding, boilerplate | qwen3.5:4b | minillm | shell, git |
| **FamilyBot** | Family assistant, scheduling, reminders | qwen3.5:4b | minillm | http |
| **LearningCoach** | Multi-user learning & progress tracking | Qwen3-Next-80B | GX10 | http, rag |
| **MathTeacher** | Mathematics tutoring (Rishaan) | Qwen3-Next-80B | GX10 | http |
| **ScienceTeacher** | Science tutoring (Rishaan) | Qwen3-Next-80B | GX10 | http |
| **EnglishTeacher** | English tutoring (Rishaan) | Qwen3-Next-80B | GX10 | http |
| **ChineseTeacher** | Chinese tutoring (Rishaan) | Qwen3-Next-80B | GX10 | http |
| **HistoryTeacher** | History tutoring (Rishaan) | Qwen3-Next-80B | GX10 | http |

## Inference Backends

| Backend | URL | Engine | Model | Purpose |
|---------|-----|--------|-------|---------|
| **GX10** | `http://192.168.68.92:8000/v1` | vLLM | nvidia/Qwen3-Next-80B-A3B-Instruct-NVFP4 | Primary inference (MoE 80B, 3B active) |
| **minillm** | `http://192.168.68.57:11434/v1` | Ollama | qwen3.5:4b, qwen3-vl:4b | Fast text + vision |
| **Jetson** | `http://192.168.68.81:11434/v1` | Ollama | snowflake-arctic-embed2 | Embeddings (RAG ingest) |

> **Note:** Desktop Ollama (localhost:11434) is for Gangadhar's personal interactive use only — never used by autonomous agents.

## Project Structure

```
ai-agent-roles/
├── README.md              # This file
├── agents/                # Agent persona definitions
│   ├── dev/               # Developer agent
│   ├── sr-dev/            # Senior developer agent
│   ├── jr-dev/            # Junior developer agent
│   ├── sre/               # SRE agent (auto-recovery + monitoring)
│   ├── tester/            # Tester agent
│   ├── research/          # Research/learning agent
│   ├── ops/               # Operations agent
│   ├── family/            # Family assistant agent
│   ├── learning-coach/    # Multi-user learning coach
│   ├── math-teacher/      # Mathematics tutor
│   ├── science-teacher/   # Science tutor
│   ├── english-teacher/   # English tutor
│   ├── chinese-teacher/   # Chinese tutor
│   └── history-teacher/   # History tutor
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
