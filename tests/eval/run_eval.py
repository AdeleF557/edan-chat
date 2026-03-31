#!/usr/bin/env python3
"""
Pipeline d'évaluation offline pour le chatbot EDAN 2025.

Usage :
    python tests/eval/run_eval.py [--save]

Options :
    --save    Sauvegarde les résultats horodatés dans tests/eval/results/
"""
from __future__ import annotations

import json
import sys
import time
import statistics
from datetime import datetime
from pathlib import Path

# Racine du projet dans sys.path
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from agent.sql_agent import answer

EVAL_DIR       = Path(__file__).parent
QUESTIONS_PATH = EVAL_DIR / "questions.json"
EXPECTED_PATH  = EVAL_DIR / "expected.json"
RESULTS_DIR    = EVAL_DIR / "results"


# ── Helpers d'assertion ──────────────────────────────────────────────────────

def _check(result: dict, exp: dict) -> tuple[bool, str]:
    """
    Retourne (passed: bool, reason: str).
    `result` est le dict retourné par answer().
    `exp`    est la spec attendue depuis expected.json.
    """
    t = exp.get("type", "")
    df = result.get("dataframe")

    # Vérification d'erreur globale
    if exp.get("no_error") and result.get("error"):
        return False, f"erreur inattendue: {result['error']}"

    if t == "route":
        actual = result.get("route", "")
        expected_route = exp["route"]
        if expected_route == "refused":
            # refused correspond à plusieurs routes possibles
            ok = actual in ("refused", "sql_blocked", "adversarial")
        else:
            ok = actual == expected_route
        return ok, f"route={actual!r} (attendu {expected_route!r})"

    if t == "ambiguous":
        ok = result.get("ambiguous", False) == exp["ambiguous"]
        return ok, f"ambiguous={result.get('ambiguous')} (attendu {exp['ambiguous']})"

    if t == "value":
        if df is None or df.empty:
            return False, "dataframe vide"
        col = exp["column"]
        # Recherche de la colonne insensible à la casse
        col_match = next((c for c in df.columns if c.lower() == col.lower()), None)
        if col_match is None:
            # Essayer avec count_star() pour les COUNT(*)
            col_match = next(
                (c for c in df.columns if "count" in c.lower()),
                None
            )
        if col_match is None:
            return False, f"colonne {col!r} absente — colonnes: {list(df.columns)}"
        actual = float(df[col_match].iloc[0])
        tolerance = exp.get("tolerance", 0)
        ok = abs(actual - float(exp["value"])) <= tolerance
        return ok, f"{col_match}={actual} (attendu {exp['value']} ±{tolerance})"

    if t == "df_contains":
        if df is None or df.empty:
            return False, "dataframe vide"
        ok = True
        reasons = []
        if "candidat" in exp:
            found = any(
                exp["candidat"].upper() in str(v).upper()
                for v in df.get("candidat", [])
            )
            if not found:
                ok = False
                reasons.append(f"candidat {exp['candidat']!r} non trouvé")
        if "parti" in exp:
            found = any(
                exp["parti"].upper() in str(v).upper()
                for v in df.get("parti", [])
            )
            if not found:
                ok = False
                reasons.append(f"parti {exp['parti']!r} non trouvé")
        return ok, ", ".join(reasons) if reasons else "OK"

    if t == "df_contains_region":
        if df is None or df.empty:
            return False, "dataframe vide"
        found = any(
            exp["region"].upper() in str(v).upper()
            for v in df.get("region", [])
        )
        return found, f"region {exp['region']!r} {'trouvée' if found else 'non trouvée'}"

    if t == "min_rows":
        if df is None:
            return False, "pas de dataframe"
        ok = len(df) >= exp["min_rows"]
        return ok, f"rows={len(df)} (min {exp['min_rows']})"

    if t == "chart":
        expected_ct = exp.get("chart_type", "bar")
        actual_ct   = result.get("chart_type", "none")
        ok = actual_ct == expected_ct
        return ok, f"chart_type={actual_ct!r} (attendu {expected_ct!r})"

    if t == "no_error":
        ok = result.get("error") is None
        return ok, f"error={result.get('error')!r}"

    return False, f"type d'assertion inconnu: {t!r}"


# ── Runner principal ─────────────────────────────────────────────────────────

def run_eval(save: bool = False) -> dict:
    questions = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    expected  = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))

    rows      = []
    latencies = []

    print(f"\n{'─'*65}")
    print(f"{'ID':<6} {'Type':<22} {'Statut':<6}  {'Détail'}")
    print(f"{'─'*65}")

    for q in questions:
        q_id     = q["id"]
        question = q["question"]
        exp      = expected.get(q_id, {})

        t0 = time.monotonic()
        try:
            result = answer(question)
        except Exception as exc:
            result = {"error": str(exc), "route": "error", "dataframe": None}
        latency_ms = (time.monotonic() - t0) * 1000

        passed, reason = _check(result, exp)
        latencies.append(latency_ms)

        status = "✅ OK" if passed else "❌ FAIL"
        print(f"{q_id:<6} {q.get('type', ''):<22} {status}  {reason}  ({latency_ms:.0f}ms)")

        rows.append({
            "id":         q_id,
            "type":       q.get("type"),
            "question":   question,
            "passed":     passed,
            "reason":     reason,
            "latency_ms": round(latency_ms, 0),
            "route":      result.get("route"),
        })

    # ── Métriques récapitulatives ────────────────────────────────────────
    total  = len(rows)
    passed = sum(1 for r in rows if r["passed"])
    by_type: dict[str, list[bool]] = {}
    for r in rows:
        by_type.setdefault(r["type"] or "unknown", []).append(r["passed"])

    median_latency = statistics.median(latencies)

    print(f"\n{'─'*55}")
    print(f"{'Métrique':<35} {'Score':>8}  {'Seuil':>8}")
    print(f"{'─'*55}")
    pct_global = passed / total * 100
    seuil_ok = "✅" if pct_global >= 90 else "⚠️"
    print(f"{'Exactitude globale':<35} {pct_global:>7.1f}%  {'≥90%':>8} {seuil_ok}")
    for qtype, results in sorted(by_type.items()):
        pct = sum(results) / len(results) * 100
        print(f"  [{qtype}]{'':<{max(0,27-len(qtype))}} {pct:>7.1f}%")
    lat_ok = "✅" if median_latency < 3000 else "⚠️"
    print(f"{'Latence médiane':<35} {median_latency:>7.0f}ms  {'<3000ms':>8} {lat_ok}")
    print(f"{'─'*55}")

    summary = {
        "timestamp":        datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total":            total,
        "passed":           passed,
        "accuracy_pct":     round(pct_global, 1),
        "median_latency_ms": round(median_latency, 0),
        "by_type":          {k: round(sum(v)/len(v)*100, 1) for k, v in by_type.items()},
        "rows":             rows,
    }

    if save:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        ts       = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        out_path = RESULTS_DIR / f"eval_{ts}.json"
        out_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n💾 Résultats sauvegardés : {out_path}")

    return summary


if __name__ == "__main__":
    save    = "--save" in sys.argv
    results = run_eval(save=save)
    # Exit code 1 si accuracy < 80 %
    sys.exit(0 if results["accuracy_pct"] >= 80 else 1)
