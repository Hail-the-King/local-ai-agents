# Local AI Agent Suite

A growing collection of locally-hosted AI agents built with Python and Ollama (llama3.2) to automate personal computing tasks. All agents run fully offline — no cloud API required.

## Agents

### Calibre Library AI Agent (`calibre_agent.py`)
Automatically cleans and normalizes e-book metadata in a Calibre library, targeting books sourced from Royal Road where authors frequently append status tags, version numbers, and date stamps to titles.

**How it works:**
- Connects to a running Calibre instance via the calibredb content server API
- Runs each title through a regex pre-processor to strip known noise patterns
- Sends ambiguous titles to a local LLM with author and series context for intelligent judgment
- Writes cleaned titles back to Calibre without interrupting the running application

**Requirements:**
- Python 3.11+
- Ollama with llama3.2 (`ollama pull llama3.2`)
- Calibre with content server enabled (Preferences → Sharing → Sharing over the net)
- `pip install ollama`

---

### Downloads Cleanup Agent (`downloads_agent.py`)
Recursively scans a Windows Downloads directory and uses a local LLM to triage files as KEEP or JUNK, moving flagged files to a staging folder for human review before anything is permanently deleted.

**How it works:**
- Safe extensions (media, documents, books) are automatically kept without LLM calls
- Known junk formats (.tmp, .msi, .crdownload, etc.) are flagged instantly
- Ambiguous files are sent to the LLM with filename, extension, and size for a verdict and plain-English reason
- Junk is moved to a `_JUNK_REVIEW` staging folder preserving subfolder structure
- A full decision log is saved so every choice is transparent and reversible

**Requirements:**
- Python 3.11+
- Ollama with llama3.2 (`ollama pull llama3.2`)
- `pip install ollama`

---

## Philosophy
These agents are designed around three principles:
- **Local first** — everything runs on your own hardware, no data leaves your machine
- **Human in the loop** — agents flag and stage, never permanently delete or overwrite without review
- **Composable** — each agent is a standalone script, easy to trigger manually or hook into a hotkey or scheduler

## Setup
1. Install [Ollama](https://ollama.com/download/windows)
2. Run `ollama pull llama3.2`
3. Run `pip install ollama`
4. Edit the configuration block at the top of whichever script you want to use
5. Set `DRY_RUN = True` for a first pass, review the output, then set it to `False`# local-ai-agents
