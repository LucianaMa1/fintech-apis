"""
Agent Memory — Persistent State Management
============================================
Stores catalog data, run history, retry counts, and learned patterns.
Persists to disk (data/ and memory/ directories) so state survives
across GitHub Actions runs via git commits.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger("memory")

# Paths relative to repo root
DATA_DIR = Path("data")
MEMORY_DIR = Path("memory")
CATALOG_PATH = DATA_DIR / "catalog.json"
HISTORY_PATH = MEMORY_DIR / "run_history.json"
RETRIES_PATH = MEMORY_DIR / "retries.json"
ERRORS_PATH = MEMORY_DIR / "error_log.json"


class AgentMemory:
    """
    The agent's persistent memory.

    Manages:
    - catalog.json     — the current verified API catalog
    - run_history.json — log of every agent run
    - retries.json     — per-provider retry counts
    - error_log.json   — detailed error history for debugging
    """

    def __init__(self, base_dir: Path = None):
        if base_dir:
            self.data_dir = base_dir / "data"
            self.memory_dir = base_dir / "memory"
        else:
            self.data_dir = DATA_DIR
            self.memory_dir = MEMORY_DIR

        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.memory_dir.mkdir(parents=True, exist_ok=True)

        self._catalog: list[dict] = []
        self._retries: dict[str, dict] = {}
        self._loaded = False

    def _ensure_loaded(self):
        if not self._loaded:
            self._catalog = self._load_json(
                self.data_dir / "catalog.json", default=[]
            )
            self._retries = self._load_json(
                self.memory_dir / "retries.json", default={}
            )
            self._loaded = True

    def _load_json(self, path: Path, default=None):
        if path.exists():
            try:
                return json.loads(path.read_text())
            except json.JSONDecodeError:
                log.warning(f"Corrupt JSON at {path}, using default")
                return default
        return default if default is not None else {}

    def _save_json(self, path: Path, data):
        path.write_text(json.dumps(data, indent=2, default=str))

    # ─── Catalog Operations ─────────────────────────────────────────────

    def load_catalog(self) -> list[dict]:
        self._ensure_loaded()
        return self._catalog

    def get_provider(self, provider_id: str) -> Optional[dict]:
        self._ensure_loaded()
        for entry in self._catalog:
            if entry["id"] == provider_id:
                return entry
        return None

    def save_provider(self, provider_id: str, data: dict):
        """Upsert a provider entry."""
        self._ensure_loaded()
        for i, entry in enumerate(self._catalog):
            if entry["id"] == provider_id:
                self._catalog[i] = data
                return
        # New provider
        self._catalog.append(data)

    def save_catalog(self):
        """Write catalog to disk."""
        self._ensure_loaded()
        self._save_json(self.data_dir / "catalog.json", self._catalog)
        log.info(f"   Saved catalog ({len(self._catalog)} providers)")

    # ─── Retry Tracking ─────────────────────────────────────────────────

    def get_retry_count(self, provider_id: str) -> int:
        self._ensure_loaded()
        return self._retries.get(provider_id, {}).get("count", 0)

    def get_last_error(self, provider_id: str) -> str:
        self._ensure_loaded()
        return self._retries.get(provider_id, {}).get("last_error", "")

    def increment_retries(self, provider_id: str, error: str):
        self._ensure_loaded()
        if provider_id not in self._retries:
            self._retries[provider_id] = {"count": 0, "errors": []}

        self._retries[provider_id]["count"] += 1
        self._retries[provider_id]["last_error"] = error
        self._retries[provider_id]["last_attempt"] = (
            datetime.now(timezone.utc).isoformat()
        )
        self._retries[provider_id].setdefault("errors", []).append({
            "error": error,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        # Keep only last 10 errors
        self._retries[provider_id]["errors"] = (
            self._retries[provider_id]["errors"][-10:]
        )

        self._save_json(self.memory_dir / "retries.json", self._retries)

    def reset_retries(self, provider_id: str):
        self._ensure_loaded()
        if provider_id in self._retries:
            del self._retries[provider_id]
            self._save_json(self.memory_dir / "retries.json", self._retries)

    # ─── Run History ────────────────────────────────────────────────────

    def load_run_history(self) -> list[dict]:
        return self._load_json(self.memory_dir / "run_history.json", default=[])

    def append_run_history(self, summary: dict):
        history = self.load_run_history()
        history.append(summary)
        # Keep last 100 runs
        history = history[-100:]
        self._save_json(self.memory_dir / "run_history.json", history)

    # ─── Provider Discovery (for adding new APIs) ───────────────────────

    def add_provider_seed(self, provider: dict):
        """Add a new provider to the catalog for the agent to discover."""
        self._ensure_loaded()
        existing = self.get_provider(provider["id"])
        if existing:
            log.warning(f"Provider {provider['id']} already exists, skipping")
            return
        self._catalog.append(provider)
        self.save_catalog()
        log.info(f"   Added new provider seed: {provider['id']}")
