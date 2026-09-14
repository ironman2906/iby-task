"""
Build an evidence table across MANY true boundaries checking which raw
signals actually fire at real boundaries vs at random midpoints (controls).
"""

import sys
from pathlib import Path
from datetime import timedelta

sys.path.append(str(Path(__file__).parent.parent / "loading"))
from loaders import (list_sessions, load_session_events, load_gt_manifest,
                      extract_true_segments, get_event_dt, get_active_app_name,
                      get_gap_ms, get_url)

from gt_imputation import impute_missing_end_ts

DATA_A = Path(__file__).parent.parent.parent / "data" / "dataset_a"


def events_in_window(events, center_dt, pad_seconds=10):
    start = center_dt - timedelta(seconds=pad_seconds)
    end = center_dt + timedelta(seconds=pad_seconds)
    return [e for e in events if start <= get_event_dt(e) <= end]


def check_signals(events, point_dt, pad_seconds=10):
    window = events_in_window(events, point_dt, pad_seconds)
    apps_before, apps_after = set(), set()
    urls_before, urls_after = set(), set()
    texts_before, texts_after = [], []
    max_gap = 0

    for e in window:
        e_dt = get_event_dt(e)
        app = get_active_app_name(e)
        url = get_url(e)
        gap = get_gap_ms(e)
        max_gap = max(max_gap, gap)
        ctx = e.get("context", {}) or {}
        text = ctx.get("extracted_text")

        if e_dt < point_dt:
            if app: apps_before.add(app)
            if url: urls_before.add(url)
            if text: texts_before.append(text)
        else:
            if app: apps_after.add(app)
            if url: urls_after.add(url)
            if text: texts_after.append(text)

    app_switch = bool(apps_before) and bool(apps_after) and apps_before != apps_after
    url_change = bool(urls_before) and bool(urls_after) and urls_before != urls_after
    large_gap = max_gap > 5000
    text_change = bool(
    texts_before
    and texts_after
    and str(texts_before) != str(texts_after)
)

    return {
        "app_switch": app_switch,
        "large_gap": large_gap,
        "max_gap_ms": max_gap,
        "url_change": url_change,
        "text_change": text_change,
    }


def print_row(session_name, point_type, code_desc, signals):
    print(f"{session_name[:20]:20s} | {point_type:18s} | {code_desc:15s} | "
          f"app={str(signals['app_switch']):5s} "
          f"gap={str(signals['large_gap']):5s}({signals['max_gap_ms']:.0f}ms) "
          f"url={str(signals['url_change']):5s} "
          f"text={str(signals['text_change']):5s}")


def inspect_suspend_resume(sessions_dir, max_examples=2):
    from loaders import load_gt_raw
    print(f"\n{'='*70}")
    print("SUSPEND/RESUME INSPECTION")
    print(f"{'='*70}")
    found = 0
    for session_dir in list_sessions(sessions_dir):
        if found >= max_examples:
            break
        gt_raw = load_gt_raw(session_dir)
        events = [e.get("event") for e in gt_raw]
        if "process_suspended" in events and "process_resumed" in events:
            print(f"\nSession: {session_dir.name}")
            for e in gt_raw:
                if e.get("event") in ("process_started", "process_switched_out",
                                       "process_suspended", "process_resumed"):
                    print(f"  {e.get('ts_utc')}  {e.get('event'):22s}  "
                          f"current={e.get('current_process')}  from={e.get('from')}  to={e.get('to')}")
            found += 1


def main():
    sessions = list_sessions(DATA_A)

    header = f"{'Session':20s} | {'Point type':18s} | {'Process':15s} | Signals"
    print(header)
    print("-" * len(header) * 2)

    inspected_sessions = 0
    total_boundaries_checked = 0

    for session_dir in sessions:
        if inspected_sessions >= 10:
            break

        gt_manifest = load_gt_manifest(session_dir)
        if gt_manifest is None:
            continue
        true_segments = extract_true_segments(gt_manifest)
        true_segments = impute_missing_end_ts(true_segments)
        if len(true_segments) < 3:
            continue

        events = load_session_events(session_dir)

        for i, seg in enumerate(true_segments[1:3], start=1):
            if seg["start_dt"]:
                signals = check_signals(events, seg["start_dt"])
                print_row(session_dir.name, "TRUE boundary", f"[{seg['process_code']}]", signals)
                total_boundaries_checked += 1

        long_seg = max(true_segments,
                        key=lambda s: (s["end_dt"] - s["start_dt"]).total_seconds()
                        if s["start_dt"] and s["end_dt"] else 0)
        if long_seg["start_dt"] and long_seg["end_dt"]:
            midpoint = long_seg["start_dt"] + (long_seg["end_dt"] - long_seg["start_dt"]) / 2
            signals = check_signals(events, midpoint)
            print_row(session_dir.name, "CONTROL (midpoint)", f"[{long_seg['process_code']}]", signals)

        inspected_sessions += 1

    print(f"\nTotal sessions inspected: {inspected_sessions}")
    print(f"Total true boundaries checked: {total_boundaries_checked}")

    inspect_suspend_resume(DATA_A)


if __name__ == "__main__":
    main()