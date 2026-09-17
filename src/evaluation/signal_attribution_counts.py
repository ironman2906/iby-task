"""
signal_attribution_counts.py
Numerically tallies which signal(s) fired at each detected boundary, using
the EXACT SAME compute_boundary_score logic already locked in
boundary_detection.py. This does not change detection — it just re-runs the
same scoring function per-event and records which individual signals
crossed their own firing condition at each declared boundary, for reporting.
"""

import sys
from pathlib import Path
from collections import Counter

sys.path.append(str(Path(__file__).parent.parent / "loading"))
sys.path.append(str(Path(__file__).parent.parent / "segmentation"))

from loaders import (load_session_events, get_active_app_name, get_gap_ms,
                      get_url, get_extracted_text)
import boundary_detection as bd


def which_signals_fired(prev_state, curr_event, lookahead_events):
    """
    Re-derive which individual signals fired for this event, matching
    compute_boundary_score's own logic exactly (not re-implementing new
    thresholds — just exposing what already happens inside it).
    """
    fired = []

    gap = get_gap_ms(curr_event)
    curr_app = get_active_app_name(curr_event)
    curr_url = get_url(curr_event)
    curr_text = get_extracted_text(curr_event)

    if curr_app is not None and curr_app != prev_state.get("app"):
        lookahead_apps = [get_active_app_name(e) for e in lookahead_events]
        sustained = lookahead_apps.count(curr_app) >= max(1, bd.MIN_APP_SWITCH_PERSISTENCE - 1)
        if sustained:
            fired.append("app_switch")

    if curr_url is not None and prev_state.get("url") is not None and curr_url != prev_state.get("url"):
        fired.append("url_change")

    if curr_text and prev_state.get("text"):
        if not bd.texts_are_similar(curr_text, prev_state.get("text")):
            fired.append("text_change")

    if gap > bd.GAP_THRESHOLD_MS:
        fired.append("large_gap")

    new_state = {
        "app": curr_app if curr_app else prev_state.get("app"),
        "url": curr_url if curr_url else prev_state.get("url"),
        "text": curr_text if curr_text else prev_state.get("text"),
    }
    return fired, new_state


def attribute_session(session_dir):
    events = load_session_events(session_dir)
    if not events:
        return []

    state = {
        "app": get_active_app_name(events[0]),
        "url": get_url(events[0]),
        "text": get_extracted_text(events[0]),
    }

    boundary_signal_sets = []

    for i in range(1, len(events)):
        e = events[i]
        lookahead = events[i:i + bd.MIN_APP_SWITCH_PERSISTENCE]
        score, new_state = bd.compute_boundary_score(state, e, lookahead)
        fired, _ = which_signals_fired(state, e, lookahead)  # same inputs, just re-exposed
        state = new_state

        if score >= bd.BOUNDARY_SCORE_THRESHOLD:
            boundary_signal_sets.append(tuple(sorted(fired)))

    return boundary_signal_sets


def main():
    session_name = "ses_20260701-054901-LAPTOP-R36BQBTE"
    session_dir = Path(__file__).parent.parent.parent / "data" / "dataset_a" / session_name

    signal_sets = attribute_session(session_dir)
    combo_counts = Counter(signal_sets)

    total = len(signal_sets)
    print(f"Session: {session_name}")
    print(f"Total boundaries fired: {total}\n")

    print(f"{'Signal combination':40s} {'Count':6s} {'%':6s}")
    for combo, count in combo_counts.most_common():
        combo_str = "+".join(combo) if combo else "(none — score from negative signal only)"
        print(f"{combo_str:40s} {count:6d} {100*count/total:5.1f}%")

    # Specifically report text_change-alone
    text_alone = combo_counts.get(("text_change",), 0)
    print(f"\ntext_change ALONE: {text_alone}/{total} ({100*text_alone/total:.1f}%)")
    print(f"(v1 baseline was 97/112 = 86.6%)")


if __name__ == "__main__":
    main()