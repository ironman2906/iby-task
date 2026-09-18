import sys
from pathlib import Path
from collections import Counter

sys.path.append(str(Path(__file__).parent.parent / "loading"))

from loaders import (
    list_sessions,
    load_session_events,
    get_active_app_name,
    get_extracted_text,
    get_url,
    parse_iso,
)


DATA_B = Path(__file__).parent.parent.parent / "data" / "dataset_b"
SEGMENTS_PATH = (
    Path(__file__).parent.parent.parent
    / "outputs"
    / "segments.jsonl"
)

TARGET_LABELS = {
    "請求書承認・経費精算",
    "入社手続き",
    "経費精算・給与変更",
    "id_INV",
}


def load_segments():
    import json

    segments = []

    with open(SEGMENTS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                segments.append(json.loads(line))

    return segments


def load_events_by_session():
    events_by_session = {}

    for session_dir in list_sessions(DATA_B):
        events = load_session_events(session_dir)

        if events:
            events_by_session[session_dir.name] = events

    return events_by_session


def get_window_events(events, start, end):
    start_ms = int(parse_iso(start).timestamp() * 1000)
    end_ms = int(parse_iso(end).timestamp() * 1000)

    return [
        e
        for e in events
        if start_ms <= e["timestamp_ms"] <= end_ms
    ]


def main():

    segments = load_segments()
    events_by_session = load_events_by_session()

    targets = [
        s for s in segments
        if s["label"] in TARGET_LABELS
    ]

    print("=" * 80)
    print("STEP 2 CANDIDATE INSPECTION")
    print("=" * 80)

    print()
    print(f"Target segments found: {len(targets)}")

    counts = Counter(s["label"] for s in targets)

    print()
    print("Counts:")
    for label, count in counts.most_common():
        print(f"  {label}: {count}")

    print()

    # Show up to 5 representative examples per label
    for label in TARGET_LABELS:

        label_segments = [
            s for s in targets
            if s["label"] == label
        ]

        if not label_segments:
            continue

        print()
        print("=" * 80)
        print(f"LABEL: {label}")
        print("=" * 80)

        for i, seg in enumerate(label_segments[:5], 1):

            session_id = seg["session_id"]

            events = events_by_session.get(
                session_id,
                []
            )

            window = get_window_events(
                events,
                seg["start"],
                seg["end"]
            )

            print()
            print("-" * 80)
            print(f"Example {i}")
            print(f"Session: {session_id}")
            print(f"Start:   {seg['start']}")
            print(f"End:     {seg['end']}")
            print(f"Events:  {len(window)}")

            apps = Counter()
            event_types = Counter()
            texts = []
            urls = []

            for e in window:

                app = get_active_app_name(e)
                if app:
                    apps[app] += 1

                event_type = e.get("event_type")
                if event_type:
                    event_types[event_type] += 1

                text = get_extracted_text(e)
                if text:
                    text = str(text).strip()
                    if text:
                        texts.append(text)

                url = get_url(e)
                if url:
                    urls.append(url)

            print()
            print("Apps:")
            for app, count in apps.most_common():
                print(f"  {app}: {count}")

            print()
            print("Event types:")
            for event_type, count in event_types.most_common():
                print(f"  {event_type}: {count}")

            print()
            print("URLs:")
            for url in urls[:10]:
                print(f"  {url}")

            if len(urls) > 10:
                print(f"  ... ({len(urls) - 10} more)")

            print()
            print("Extracted text:")

            if texts:
                for text in texts[:10]:
                    print(f"  {text[:500]}")
            else:
                print("  [no extracted text]")

            if len(texts) > 10:
                print(f"  ... ({len(texts) - 10} more text records)")


if __name__ == "__main__":
    main()