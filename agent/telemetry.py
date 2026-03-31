"""
Télémétrie end-to-end pour le chatbot EDAN 2025.
Chaque requête produit un RequestTrace sauvegardé de façon asynchrone
dans data/traces.jsonl (une ligne JSON par requête).
"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

_TRACES_PATH = Path(__file__).parent.parent / "data" / "traces.jsonl"
_write_lock = threading.Lock()


@dataclass
class RequestTrace:
    question:          str
    timestamp:         str           # ISO-8601 UTC, ex. "2025-12-27T14:32:11Z"
    fuzzy_corrections: list[dict]    # [{original, matched, score, entity_type}]
    route:             str           # "sql"|"rag"|"refused"|"disambiguation"|...
    sql_generated:     str | None
    sql_validated:     bool | None
    rows_returned:     int | None
    chart_type:        str | None
    latency_ms:        float
    tokens_used:       int
    error:             str | None


def _write_line(line: str) -> None:
    """Thread cible : append une ligne JSONL avec verrou fichier."""
    with _write_lock:
        _TRACES_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _TRACES_PATH.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


def save_trace(trace: RequestTrace) -> None:
    """
    Sérialise la trace en JSON et l'écrit dans data/traces.jsonl
    via un daemon thread (non-bloquant — le caller retourne immédiatement).
    """
    line = json.dumps(asdict(trace), ensure_ascii=False)
    t = threading.Thread(target=_write_line, args=(line,), daemon=True)
    t.start()


def now_iso() -> str:
    """Retourne l'heure UTC courante en ISO-8601."""
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
