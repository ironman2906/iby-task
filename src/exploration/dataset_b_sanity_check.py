import sys
from pathlib import Path
from collections import Counter

sys.path.append(str(Path(__file__).parent.parent / "loading"))
from loaders import list_sessions, load_session_events, get_active_app_name, get_url, get_extracted_text

DATA_B = Path(__file__).parent.parent.parent / "data" / "dataset_b"

def main():
    sessions = list_sessions(DATA_B)
    print(f"Dataset B sessions: {len(sessions)}")

    total_events = 0
    event_type_counts = Counter()
    layer_counts = Counter()
    app_counts = Counter()
    has_url = 0
    has_text = 0

    for session_dir in sessions:
        events = load_session_events(session_dir)
        total_events += len(events)
        for e in events:
            event_type_counts[e["event_type"]] += 1
            layer_counts[e["layer"]] += 1
            app = get_active_app_name(e)
            if app:
                app_counts[app] += 1
            if get_url(e):
                has_url += 1
            if get_extracted_text(e):
                has_text += 1

    print(f"Total events: {total_events}")
    print(f"\n--- Event type distribution ---")
    for etype, count in event_type_counts.most_common(15):
        print(f"  {etype:25s} {count:8d}  ({100*count/total_events:.1f}%)")
    print(f"\n--- Layer distribution ---")
    for layer, count in layer_counts.most_common():
        print(f"  {layer:10s} {count:8d}  ({100*count/total_events:.1f}%)")
    print(f"\n--- Top apps used ---")
    for app, count in app_counts.most_common(15):
        print(f"  {app:30s} {count:8d}")
    print(f"\nurl present: {100*has_url/total_events:.1f}%  (Dataset A was 52.6%)")
    print(f"extracted_text present: {100*has_text/total_events:.1f}%  (Dataset A was 4.5%)")

if __name__ == "__main__":
    main()