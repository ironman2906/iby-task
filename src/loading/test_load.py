from pathlib import Path
from loaders import list_sessions, load_session_events, load_gt_manifest, extract_true_segments

DATA_A = Path(__file__).parent.parent.parent / "data" / "dataset_a"

def main():
    sessions = list_sessions(DATA_A)
    print(f"Found {len(sessions)} sessions in dataset_a")
    assert len(sessions) > 0, "No sessions found — check your data path!"

    for session_dir in sessions[:3]:
        print(f"\n--- {session_dir.name} ---")
        events = load_session_events(session_dir)
        print(f"  Total events: {len(events)}")
        if events:
            timestamps = [e["timestamp_ms"] for e in events]
            is_sorted = all(timestamps[i] <= timestamps[i+1] for i in range(len(timestamps)-1))
            print(f"  Time range: {events[0]['timestamp_iso']} -> {events[-1]['timestamp_iso']}")
            print(f"  Sorted correctly: {is_sorted}")

        gt_manifest = load_gt_manifest(session_dir)
        if gt_manifest:
            true_segments = extract_true_segments(gt_manifest)
            print(f"  True segments: {len(true_segments)}")
            for seg in true_segments[:3]:
                print(f"    [{seg['process_code']}] {seg['family_name']} | {seg['start']} -> {seg['end']}")

if __name__ == "__main__":
    main()