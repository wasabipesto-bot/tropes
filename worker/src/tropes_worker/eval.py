"""`tropes-worker eval`: run the scan for a trope with its verified instances as ground truth.
Nothing is written to the site; results go to stdout and an optional JSON file."""

from __future__ import annotations

import json
import time
from typing import Any

from .client import SiteClient
from .jobs.scan_trope import scan, trope_spec_from
from .llm import LLM
from .pipeline import load_subject_text, run_async, subject_key
from .settings import Settings


def evaluate(settings: Settings, client: SiteClient, slugs: list[str] | None, out_path: str | None) -> int:
    tropes = client.tropes()
    exported = client.subjects()
    media, series = exported["media"], exported["series"]
    dossiers = {subject_key(d["subjectKind"], d["subjectId"]): d for d in client._get("/api/dossiers")["dossiers"]}
    subjects = [*media, *series]
    texts_by_media: dict[int, Any] = {}
    for m in media:
        if m.get("textSources"):
            t = load_subject_text(settings, m)
            if t:
                texts_by_media[m["id"]] = t
    chosen = [t for t in tropes if not slugs or t["slug"] in slugs]
    if not chosen:
        print("no matching tropes")
        return 2
    report = []
    for t in chosen:
        truth = {subject_key(i["kind"], i["subjectId"]) for i in t.get("instances", []) if i.get("verified")}
        if not truth:
            print(f"{t['name']}: no verified instances, skipped")
            continue
        spec, _ = trope_spec_from({"tropeId": t["id"]}, tropes, media, series)
        spec.existing = {}  # pretend nothing is attached yet so the scan has to find the truth
        llm = LLM(settings)
        started = time.monotonic()
        proposals, scores, cands = run_async(scan(None, settings, llm, spec, subjects, dossiers, texts_by_media, lambda *a: None))
        found = {subject_key(p["subject"]["kind"], p["subject"]["id"]): p["score"] for p in proposals if p["kind"] == "instance"}
        at_cut = {k for k, s in found.items() if s >= settings.unchecked_below}
        recall_any = len(truth & set(found)) / len(truth)
        recall_cut = len(truth & at_cut) / len(truth)
        precision_cut = (len(truth & at_cut) / len(at_cut)) if at_cut else 0.0
        mean_true = sum(found[k] for k in truth if k in found) / max(1, len(truth & set(found)))
        missed = sorted(truth - set(found))
        row = {
            "trope": t["name"],
            "truth": len(truth),
            "candidates": len(cands),
            "proposed": len(found),
            "recall_proposed": round(recall_any, 2),
            "recall_at_cutoff": round(recall_cut, 2),
            "precision_at_cutoff": round(precision_cut, 2),
            "mean_score_of_true": round(mean_true, 2),
            "missed": missed,
            "pass1_of_missed": {k: scores.get(k, (None, ""))[0] for k in missed},
            "seconds": round(time.monotonic() - started),
            "usage": llm.usage.as_dict(),
        }
        report.append(row)
        print(
            f"{t['name']}: truth {row['truth']}, proposed {row['proposed']} (cands {row['candidates']}), recall {row['recall_proposed']} / at cutoff {row['recall_at_cutoff']}, precision at cutoff {row['precision_at_cutoff']}, mean true score {row['mean_score_of_true']}, {row['seconds']}s, ${row['usage']['costUsd']:.4f}"  # noqa: E501
        )
        if missed:
            print(f"  missed: {', '.join(missed)} (pass 1: {row['pass1_of_missed']})")
    if out_path:
        json.dump(
            {
                "model": settings.model,
                "settings": {
                    "pass2_min_score": settings.pass2_min_score,
                    "pass2_cap": settings.pass2_cap,
                    "unchecked_below": settings.unchecked_below,
                },
                "tropes": report,
            },
            open(out_path, "w"),
            indent=1,
        )
        print(f"wrote {out_path}")
    return 0
