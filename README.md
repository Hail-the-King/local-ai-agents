# Local AI Agent Suite

A growing collection of locally-hosted AI agents built with Python and Ollama to automate personal computing tasks. All agents run fully offline — no cloud API, no data leaves your machine.

## Agents

| Agent | Version | Description |
|---|---|---|
| Calibre Library Agent | v1.2.0 | Cleans e-book metadata and handles Royal Road stub detection |
| Downloads Cleanup Agent | v1.1.0 | Triages Downloads folder using LLM judgment |

## Philosophy
- **Local first** — everything runs on your own hardware
- **Human in the loop** — agents flag and stage, never act destructively without approval
- **Composable** — each agent is a standalone script, easy to trigger manually or bind to a hotkey

## Requirements
- Python 3.11+
- [Ollama](https://ollama.com/download/windows) with llama3.2 (`ollama pull llama3.2`)
- `pip install ollama pandas`

## Setup
1. Install Ollama and run `ollama pull llama3.2`
2. Run `pip install ollama pandas`
3. Navigate to the agent you want and follow its README
4. Edit the configuration block at the top of the script to match your system
5. Set `DRY_RUN = True` for a first pass, review output, then set to `False`
