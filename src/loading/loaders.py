"""
loaders.py
Core functions to load events, ground truth, and manifests.
"""

import json
from pathlib import Path
from datetime import datetime


def parse_iso(ts):
    if ts is None:
        return None
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def load_jsonl(path):
    path = Path(path)
    if not path.exists():
        return []
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"WARNING: bad JSON at {path}:{line_num} -> {e}")
    return records


def get_chunk_dirs(session_dir):
    return sorted(Path(session_dir).glob("chunk_*"))


def load_session_events(session_dir):
    """Merge all chunks in a session into one time-sorted event list."""
    session_dir = Path(session_dir)
    all_events = []
    for chunk_dir in get_chunk_dirs(session_dir):
        chunk_events = load_jsonl(chunk_dir / "events.jsonl")
        for e in chunk_events:
            e["_chunk_dir"] = str(chunk_dir)
        all_events.extend(chunk_events)
    all_events.sort(key=lambda e: e["timestamp_ms"])
    return all_events


def load_gt_manifest(session_dir):
    path = Path(session_dir) / "gt_manifest.json"
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_gt_raw(session_dir):
    return load_jsonl(Path(session_dir) / "gt.jsonl")


def extract_true_segments(gt_manifest):
    if gt_manifest is None:
        return []
    segments = []
    for process in gt_manifest.get("processes", []):
        for ex in process.get("executions", []):
            segments.append({
                "process_code": process.get("code"),
                "family_name": process.get("family_name"),
                "domain": process.get("domain"),
                "variant": ex.get("variant"),
                "case_id": ex.get("case_id"),
                "start": ex.get("start_ts"),
                "end": ex.get("end_ts"),
                "start_dt": parse_iso(ex.get("start_ts")),
                "end_dt": parse_iso(ex.get("end_ts")),
                "apps": ex.get("apps", []),
                "phase": ex.get("phase"),
                "seq": ex.get("seq"),
                "continues_from_prev": ex.get("continues_from_prev"),
                "continues_to_next": ex.get("continues_to_next"),
            })
    return sorted(segments, key=lambda s: s["start"])


def list_sessions(dataset_dir):
    return sorted(Path(dataset_dir).glob("ses_*"))


def get_event_dt(event):
    return parse_iso(event.get("timestamp_iso"))


def get_active_app_name(event):
    ctx = event.get("context", {}) or {}
    app = ctx.get("active_app") or {}
    return app.get("app_name")


def get_gap_ms(event):
    corr = event.get("correlation", {}) or {}
    return corr.get("ms_since_last_event", 0) or 0


def get_url(event):
    ctx = event.get("context", {}) or {}
    tab = ctx.get("active_browser_tab") or {}
    return tab.get("url")

def get_extracted_text(event):
    """
    Safely extract the actual text string from context.extracted_text.
    """
    ctx = event.get("context", {}) or {}
    raw = ctx.get("extracted_text")

    if raw is None:
        return None

    if isinstance(raw, str):
        return raw

    if isinstance(raw, dict):
        return raw.get("text")

    return None