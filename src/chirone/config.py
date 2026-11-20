"""Runtime settings, overridable through environment variables."""
from __future__ import annotations

import os
from pathlib import Path

# Root helper installed by deploy/install.sh and whitelisted in sudoers.
HELPER = os.environ.get("CHIRONE_HELPER", "/usr/local/libexec/chirone-root-helper")
# Local llama.cpp server (llama-server), bound to 127.0.0.1.
LLM_URL = os.environ.get("CHIRONE_LLM_URL", "http://127.0.0.1:8080")
LANG = os.environ.get("CHIRONE_LANG", "it")
STATE_DIR = Path(os.environ.get("CHIRONE_STATE_DIR", Path.home() / ".local/state/chirone"))
# Budget for the diagnostics block sent to the model in step 2 (characters).
DIAG_BUDGET = int(os.environ.get("CHIRONE_DIAG_BUDGET", "1800"))
# Deterministic tool output: the model always sees English, C-locale text.
PROBE_ENV = {"LC_ALL": "C.UTF-8", "LANG": "C.UTF-8"}
