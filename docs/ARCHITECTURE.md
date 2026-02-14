# LLM in a Box — Architecture Outline

## Overview
LLM in a Box is a portable, offline AI stack that runs directly from USB storage. The system starts a local runtime and web UI without installing software on the host.

## High-Level Components
1. **Launcher**
   - Cross-platform entry point (Windows/macOS/Linux).
   - Starts backend runtime and opens browser to local UI.
  - Quickstart guide: see [docs/QUICKSTART.md](docs/QUICKSTART.md)

2. **Backend Runtime**
   - Local model server with optional CPU/GPU acceleration.
   - Manages model loading/unloading and memory limits.
   - Stores chat sessions and logs in an encrypted store.
   - Bundles a Python virtual environment alongside the app to avoid host installation.
   - Can be powered by open source runtimes (e.g., Ollama) when suitable.

### Bundled Python Environment
- Builds include a Python virtual environment at the repo root (for example, a `.venv` folder).
- The launcher should prefer this embedded Python when starting the backend, with a fallback to the host if missing.

3. **Web UI**
   - Authenticated local web app.
   - Chat interface with model selection.
   - Model manager and system status.
   - UI skin switcher (dark + terminal).

4. **Content Library**
   - Offline ebooks in a dedicated folder.
   - Optional local search index.

5. **Security Layer**
   - Password authentication.
   - Encrypted vault for sensitive data (chat history).
   - Optional full-drive encryption guidance.

## Data Storage Layout (Proposed)
```
/LLM-in-a-Box
  /.venv  (Python virtual environment for the backend runtime)
  /app
    /backend
    /frontend
    /launcher
  /models
    /low-end
    /mid-range
    /high-end
    /survival
  /data
    /chat-history (encrypted)
    /user-vault (encrypted)
  /library
    /survival-ebooks
  /docs
    /quickstart
    /troubleshooting
    /security
```

## Model Strategy
- **3–4 LLMs** organized by hardware capability.
- **Survival model** prioritized with curated datasets or RAG over local ebooks.
- **Model manager** enforces safe memory limits and reports resource usage.

## UI Skins
- **Dark Simple:** Clean UI with muted tones.
- **Terminal:** Black background, green monospace, terminal-style UI accents.
- **Optional Third:** Light or retro theme for marketing diversity.

## Authentication
- Local user accounts.
- Passwords stored with salted hashing.
- Optional single-user mode for simplicity.

## Encryption Options
- **Per-folder encryption** for chat history and user notes.
- **Full-drive encryption** guidance (BitLocker/FileVault/VeraCrypt).

## Offline-First Constraints
- No cloud dependencies.
- All assets, fonts, and scripts served locally.
- No runtime package install required on the host.

## Future Enhancements
- Auto hardware detection for model recommendation.
- Offline updates via signed update bundles.
- Pluggable skill packs for specialized domains.
