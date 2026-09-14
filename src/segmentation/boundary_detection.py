"""
boundary_detection.py

Weighted-evidence boundary detector. Weights are NOT assumptions — they
come directly from Day 1's boundary_inspection.py tally (n=20 true
boundaries, n=10 controls):

    Signal        TRUE rate   CONTROL rate   Separation
    url_change      50%          0%           +50pp  (cleanest)
    text_change     60%         10%           +50pp
    app_switch      55%         10%           +45pp
    large_gap       10%         80%           -70pp  <- INVERTED signal!

Key finding: large gaps happen mid-process (workers pausing to read/think),
NOT at transitions (~95% of real transitions have near-zero gap). So gap
size gets a NEGATIVE weight here, not a positive one — this deliberately
contradicts the "idle time = new task" assumption common in other domains.
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent / "loading"))
from loaders import get_active_app_name, get_gap_ms, get_url

# ---- WEIGHTS FROM DAY 1 EVIDENCE TABLE ----
SIGNAL_WEIGHTS = {
    "url_change": 0.50,
    "text_change": 0.50,
    "app_switch": 0.45,
    "large_gap": -0.35,   # NEGATIVE — counter-evidence, not supporting evidence
}
GAP_THRESHOLD_MS = 5000          # matches the threshold used in Day 1's evidence table
MIN_APP_SWITCH_PERSISTENCE = 3   # app must hold for N events to count (flicker filter)
BOUNDARY_SCORE_THRESHOLD = 0.50  # minimum net score to declare a boundary
# --------------------------------------------


def compute_boundary_score(prev_state, curr_event, lookahead_events):
    """
    Compute a net weighted evidence score for whether curr_event marks
    a boundary. Returns (score, new_state).
    """
    score = 0.0
    gap = get_gap_ms(curr_event)
    curr_app = get_active_app_name(curr_event)
    curr_url = get_url(curr_event)
    ctx = curr_event.get("context", {}) or {}
    curr_text = ctx.get("extracted_text")

    # app_switch (needs sustained persistence to avoid flicker — app_switch
    # is 31% of ALL events per Day 1's data_quality.py, so raw switches alone
    # are noisy)
    if curr_app is not None and curr_app != prev_state.get("app"):
        lookahead_apps = [get_active_app_name(e) for e in lookahead_events]
        sustained = lookahead_apps.count(curr_app) >= max(1, MIN_APP_SWITCH_PERSISTENCE - 1)
        if sustained:
            score += SIGNAL_WEIGHTS["app_switch"]

    # url_change (cleanest signal, 0% false-positive rate at Day 1 controls)
    if curr_url is not None and prev_state.get("url") is not None and curr_url != prev_state.get("url"):
        score += SIGNAL_WEIGHTS["url_change"]

    # text_change (windowed accumulation handled by comparing to prev_state's
    # last-seen text, since raw extracted_text is only 4.5% present per event)
    if curr_text and prev_state.get("text") and curr_text != prev_state.get("text"):
        score += SIGNAL_WEIGHTS["text_change"]

    # large_gap — NEGATIVE evidence per Day 1 finding
    if gap > GAP_THRESHOLD_MS:
        score += SIGNAL_WEIGHTS["large_gap"]

    new_state = {
        "app": curr_app if curr_app else prev_state.get("app"),
        "url": curr_url if curr_url else prev_state.get("url"),
        "text": curr_text if curr_text else prev_state.get("text"),
    }
    return score, new_state


def detect_boundaries(events, score_threshold=BOUNDARY_SCORE_THRESHOLD):
    if not events:
        return []

    boundaries = [events[0]["timestamp_ms"]]
    state = {
        "app": get_active_app_name(events[0]),
        "url": get_url(events[0]),
        "text": (events[0].get("context", {}) or {}).get("extracted_text"),
    }

    for i in range(1, len(events)):
        e = events[i]
        lookahead = events[i:i + MIN_APP_SWITCH_PERSISTENCE]
        score, state = compute_boundary_score(state, e, lookahead)
        if score >= score_threshold:
            boundaries.append(e["timestamp_ms"])

    return sorted(set(boundaries))


def boundaries_to_raw_segments(events, boundaries):
    """
    Convention: a segment spans from its first event's timestamp through
    its last event's timestamp. Apply the SAME convention to ground truth
    in the evaluator (handled there via a small epsilon).
    """
    segments = []
    for idx in range(len(boundaries)):
        start_ms = boundaries[idx]
        end_ms = boundaries[idx + 1] if idx + 1 < len(boundaries) else events[-1]["timestamp_ms"] + 1
        seg_events = [e for e in events if start_ms <= e["timestamp_ms"] < end_ms]
        if seg_events:
            segments.append({
                "start_ms": seg_events[0]["timestamp_ms"],
                "end_ms": seg_events[-1]["timestamp_ms"],
                "start_iso": seg_events[0]["timestamp_iso"],
                "end_iso": seg_events[-1]["timestamp_iso"],
                "events": seg_events,
            })
    return segments


def merge_short_segments(segments, min_duration_ms=5000, max_gap_to_merge_ms=3000):
    """Merge trivial short fragments into a neighbor. Does not fix substantial
    (>5s) fragmentation — that needs threshold tuning, not merging."""
    if not segments:
        return segments
    merged = [segments[0]]
    for seg in segments[1:]:
        prev = merged[-1]
        duration = seg["end_ms"] - seg["start_ms"]
        gap_from_prev = seg["start_ms"] - prev["end_ms"]
        if duration < min_duration_ms and gap_from_prev < max_gap_to_merge_ms:
            prev["end_ms"] = seg["end_ms"]
            prev["end_iso"] = seg["end_iso"]
            prev["events"].extend(seg["events"])
        else:
            merged.append(seg)
    return merged


def run_segmentation(events, score_threshold=BOUNDARY_SCORE_THRESHOLD,
                      min_duration_ms=5000, max_gap_to_merge_ms=3000):
    boundaries = detect_boundaries(events, score_threshold=score_threshold)
    raw_segments = boundaries_to_raw_segments(events, boundaries)
    return merge_short_segments(raw_segments, min_duration_ms, max_gap_to_merge_ms)