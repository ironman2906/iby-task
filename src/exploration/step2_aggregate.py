"""
step2_aggregate.py

Aggregates Dataset B segments.jsonl into per-label business statistics for
Step 2 analysis. Re-derives event-count / app-diversity features by
re-slicing the raw Dataset B events for each segment's [start, end] window,
because segments.jsonl (the required deliverable format) only carries
session_id / start / end / label -- not per-event detail.

Usage:
    python step2_aggregate.py \
        --segments outputs/segments.jsonl \
        --dataset-b-dir data/dataset_b \
        --out outputs/step2_aggregation.md
"""
import argparse
import json
import sys
from pathlib import Path
from collections import defaultdict
from statistics import median, pstdev

sys.path.append(str(Path(__file__).parent.parent / "loading"))
from loaders import list_sessions, load_session_events, get_active_app_name, parse_iso


def load_segments(path):
    segs = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                segs.append(json.loads(line))
    return segs


def machine_from_session_id(session_id):
    """
    ses_<date>-<time>-<machine>. The machine token itself can contain
    hyphens (e.g. "LAPTOP-R36BQBTE"), so only split the first two dashes.
    """
    body = session_id[len("ses_"):] if session_id.startswith("ses_") else session_id
    parts = body.split("-", 2)
    return parts[2] if len(parts) == 3 else "unknown"


def index_events_by_session(dataset_b_dir):
    """Load every Dataset B session's events once, keyed by session_id."""
    cache = {}
    for session_dir in list_sessions(Path(dataset_b_dir)):
        events = load_session_events(session_dir)
        if events:
            cache[session_dir.name] = events
    return cache


def slice_events(events, start_iso, end_iso):
    start_ms = int(parse_iso(start_iso).timestamp() * 1000)
    end_ms = int(parse_iso(end_iso).timestamp() * 1000)
    return [e for e in events if start_ms <= e["timestamp_ms"] <= end_ms]


def enrich_segment(seg, events_by_session):
    events = events_by_session.get(seg["session_id"], [])
    window = slice_events(events, seg["start"], seg["end"])
    apps = {get_active_app_name(e) for e in window if get_active_app_name(e)}
    duration_s = (parse_iso(seg["end"]) - parse_iso(seg["start"])).total_seconds()
    return {
        **seg,
        "machine": machine_from_session_id(seg["session_id"]),
        "n_events": len(window),
        "apps": apps,
        "duration_s": duration_s,
    }


def aggregate(enriched):
    by_label = defaultdict(list)
    for seg in enriched:
        by_label[seg["label"]].append(seg)

    rows = []
    for label, segs in by_label.items():
        durations = [s["duration_s"] for s in segs]
        n_events = [s["n_events"] for s in segs]
        sessions = {s["session_id"] for s in segs}
        machines = {s["machine"] for s in segs}
        app_union = set()
        for s in segs:
            app_union |= s["apps"]

        mean_dur = sum(durations) / len(durations)
        cv_dur = (pstdev(durations) / mean_dur) if mean_dur > 0 and len(durations) > 1 else 0.0
        mean_ev = sum(n_events) / len(n_events)
        cv_ev = (pstdev(n_events) / mean_ev) if mean_ev > 0 and len(n_events) > 1 else 0.0

        total_time_s = sum(durations)
        # Impact (time spent) discounted by procedural inconsistency
        # (higher variation in duration/step-count => more branches =>
        # harder + riskier to automate). This is a first-pass heuristic,
        # not a validated model -- state that in the report.
        priority_score = total_time_s / (1 + cv_dur + cv_ev)

        rows.append({
            "label": label,
            "frequency": len(segs),
            "total_time_s": total_time_s,
            "median_duration_s": median(durations),
            "n_sessions": len(sessions),
            "n_machines": len(machines),
            "apps": sorted(a for a in app_union if a),
            "cv_duration": cv_dur,
            "cv_events": cv_ev,
            "priority_score": priority_score,
        })

    rows.sort(key=lambda r: r["priority_score"], reverse=True)
    return rows


def to_markdown(rows):
    lines = [
        "| label | freq | total_min | median_dur_s | sessions | machines | apps | cv_dur | cv_events | priority |",
        "|---|---:|---:|---:|---:|---:|---|---:|---:|---:|",
    ]
    for r in rows:
        lines.append(
            f"| {r['label']} | {r['frequency']} | {r['total_time_s']/60:.1f} | "
            f"{r['median_duration_s']:.1f} | {r['n_sessions']} | {r['n_machines']} | "
            f"{', '.join(r['apps'])} | {r['cv_duration']:.2f} | {r['cv_events']:.2f} | "
            f"{r['priority_score']:.0f} |"
        )
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--segments", required=True)
    ap.add_argument("--dataset-b-dir", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    segments = load_segments(args.segments)
    events_by_session = index_events_by_session(args.dataset_b_dir)
    enriched = [enrich_segment(s, events_by_session) for s in segments]
    rows = aggregate(enriched)
    md = to_markdown(rows)

    Path(args.out).write_text(md, encoding="utf-8")
    print(md)
    print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()