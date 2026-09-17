import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent / "loading"))
sys.path.append(str(Path(__file__).parent.parent / "segmentation"))

from loaders import load_session_events
from boundary_detection import compute_boundary_score_with_signals, MIN_APP_SWITCH_PERSISTENCE, BOUNDARY_SCORE_THRESHOLD

DATA_A = Path(__file__).parent.parent.parent / "data" / "dataset_a"

def attribute_boundaries(session_name, score_threshold=BOUNDARY_SCORE_THRESHOLD):
    events = load_session_events(DATA_A / session_name)
    state = {
        "app": None, "url": None, "text": None,
    }
    from collections import Counter
    signal_counts = Counter()
    boundary_log = []

    for i in range(1, len(events)):
        e = events[i]
        lookahead = events[i:i + MIN_APP_SWITCH_PERSISTENCE]
        score, state, fired = compute_boundary_score_with_signals(state, e, lookahead)
        if score >= score_threshold:
            key = tuple(sorted(fired))
            signal_counts[key] += 1
            boundary_log.append((e["timestamp_iso"], score, fired))

    print(f"Session: {session_name}")
    print(f"Total boundaries fired: {len(boundary_log)}\n")
    print("Signal combination counts:")
    for combo, count in signal_counts.most_common():
        print(f"  {combo}: {count}")

def inspect_text_change_samples(session_name, n=15):
    events = load_session_events(DATA_A / session_name)

    state = {
        "app": None,
        "url": None,
        "text": None,
    }

    samples = []

    for i in range(1, len(events)):
        e = events[i]
        lookahead = events[i:i + MIN_APP_SWITCH_PERSISTENCE]

        score, new_state, fired = compute_boundary_score_with_signals(
            state,
            e,
            lookahead,
        )

        if score >= BOUNDARY_SCORE_THRESHOLD and fired == ["text_change"]:
            samples.append({
                "ts": e["timestamp_iso"],
                "prev_text": state.get("text"),
                "curr_text": new_state.get("text"),
            })

        state = new_state

    for s in samples[:n]:
        print(f"\n--- {s['ts']} ---")
        print(f"PREV: {s['prev_text']!r}")
        print(f"CURR: {s['curr_text']!r}")


if __name__ == "__main__":
    inspect_text_change_samples(
        "ses_20260701-054901-LAPTOP-R36BQBTE"
    )