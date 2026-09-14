"""
What does the raw event data actually look like, in aggregate?
"""

import sys
from pathlib import Path
from collections import Counter

sys.path.append(str(Path(__file__).parent.parent / "loading"))
from loaders import list_sessions, load_session_events

DATA_A = Path(__file__).parent.parent.parent / "data" / "dataset_a"


def main():
    sessions = list_sessions(DATA_A)

    event_type_counts = Counter()
    layer_counts = Counter()
    has_extracted_text = 0
    has_active_app = 0
    has_window_title = 0
    has_url = 0
    text_input_complete_total = 0
    text_input_complete_missing = 0
    total = 0

    for session_dir in sessions:
        events = load_session_events(session_dir)
        for e in events:
            total += 1
            event_type_counts[e["event_type"]] += 1
            layer_counts[e["layer"]] += 1

            ctx = e.get("context", {}) or {}
            if ctx.get("extracted_text"):
                has_extracted_text += 1
            app = ctx.get("active_app") or {}
            if app.get("app_name"):
                has_active_app += 1
            if app.get("window_title"):
                has_window_title += 1
            if (ctx.get("active_browser_tab") or {}).get("url"):
                has_url += 1

            if e["event_type"] == "text_input_complete":
                text_input_complete_total += 1
                payload = e.get("payload", {}) or {}
                if not payload.get("content") and not payload.get("text"):
                    text_input_complete_missing += 1

    print(f"Total events across all sessions: {total}\n")

    print("--- Event type distribution ---")
    for etype, count in event_type_counts.most_common():
        print(f"  {etype:25s} {count:8d}  ({100*count/total:5.1f}%)")

    print("\n--- Layer distribution ---")
    for layer, count in layer_counts.most_common():
        print(f"  {layer:10s} {count:8d}  ({100*count/total:5.1f}%)")

    print(f"\n--- Field presence ---")
    print(f"  extracted_text present: {100*has_extracted_text/total:.1f}%")
    print(f"  active_app present:     {100*has_active_app/total:.1f}%")
    print(f"  window_title present:   {100*has_window_title/total:.1f}%")
    print(f"  browser url present:    {100*has_url/total:.1f}%")

    print(f"\n--- text_input_complete reliability ---")
    print(f"  Total text_input_complete events: {text_input_complete_total}")
    if text_input_complete_total:
        print(f"  Missing content: {text_input_complete_missing} "
              f"({100*text_input_complete_missing/text_input_complete_total:.1f}%)")


if __name__ == "__main__":
    main()