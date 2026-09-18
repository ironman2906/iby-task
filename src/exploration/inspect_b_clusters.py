import sys
import json
from collections import Counter
from pathlib import Path

OUTPUT_PATH = Path(__file__).parent.parent.parent / "outputs" / "segments.jsonl"

def main():
    with open(OUTPUT_PATH, encoding="utf-8") as f:
        segments = [json.loads(line) for line in f]

    label_counts = Counter(s["label"] for s in segments)
    print("Top labels by frequency:")
    for label, count in label_counts.most_common(10):
        print(f"  {label:30s} {count:4d}")

    print(f"\nTotal distinct labels: {len(label_counts)}")
    print(f"Total segments: {len(segments)}")

    # Print sample segments for top 5 labels for manual inspection
    print(f"\n{'='*80}\nSAMPLE SEGMENTS PER TOP LABEL (for manual sanity check)\n{'='*80}")
    for label, count in label_counts.most_common(5):
        print(f"\n--- {label} (n={count}) ---")
        samples = [s for s in segments if s["label"] == label][:3]
        for s in samples:
            print(f"  {s['session_id']}: {s['start']} -> {s['end']}")

if __name__ == "__main__":
    main()