"""Organize nested live/spoof sample folders into a training-ready dataset layout.

This script is intentionally non-destructive by default: it COPIES files from a
source folder into `train/` and `val/` directories and preserves the originals.

Example:
    python training/organize_antispoof_samples.py \
        --source "C:/Users/Lam Nguyen/OneDrive/Desktop/DeepLearning_Final/samples" \
        --output "./data/antispoof"
"""
from __future__ import annotations

import argparse
import random
import shutil
from collections import Counter, defaultdict
from pathlib import Path

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
VIDEO_EXTS = {".mp4", ".mov", ".3gp", ".avi", ".mkv", ".webm"}

LIVE_KEYS = ("live", "real", "genuine", "selfie", "bonafide", "bona_fide")
SPOOF_KEYS = ("spoof", "fake", "attack", "print", "replay", "screen")


def infer_label(path: Path) -> str:
    text = str(path).lower()
    if any(key in text for key in LIVE_KEYS):
        return "live"
    if any(key in text for key in SPOOF_KEYS):
        return "spoof"
    return "unknown"


def media_kind(path: Path) -> str | None:
    ext = path.suffix.lower()
    if ext in IMAGE_EXTS:
        return "images"
    if ext in VIDEO_EXTS:
        return "videos"
    return None


def split_sessions(session_names: list[str], val_ratio: float, seed: int) -> tuple[set[str], set[str]]:
    items = list(session_names)
    rnd = random.Random(seed)
    rnd.shuffle(items)

    if len(items) <= 1 or val_ratio <= 0:
        return set(items), set()

    n_val = int(round(len(items) * val_ratio))
    n_val = max(1, min(n_val, len(items) - 1))
    val_sessions = set(items[:n_val])
    train_sessions = set(items[n_val:])
    return train_sessions, val_sessions


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Organize nested anti-spoof samples")
    parser.add_argument("--source", type=Path, required=True, help="Folder containing nested sample directories")
    parser.add_argument("--output", type=Path, required=True, help="Destination root, e.g. ai-service/data/antispoof")
    parser.add_argument("--val-ratio", type=float, default=0.2, help="Validation split ratio per label (default: 0.2)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducible splitting")
    parser.add_argument("--move", action="store_true", help="Move files instead of copying them")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not args.source.exists():
        raise FileNotFoundError(f"Source folder not found: {args.source}")

    files = [p for p in args.source.rglob("*") if p.is_file() and media_kind(p)]
    if not files:
        print("No supported media files found.")
        return

    grouped: dict[str, dict[str, list[Path]]] = defaultdict(lambda: defaultdict(list))
    counts = Counter()

    for file in files:
        label = infer_label(file)
        session = file.parent.name or "root"
        grouped[label][session].append(file)
        counts[label] += 1

    print("Detected media counts by label:")
    for label, count in sorted(counts.items()):
        print(f"  - {label}: {count}")

    copied = 0
    moved = 0

    for label, sessions in grouped.items():
        if label in {"live", "spoof"}:
            train_sessions, val_sessions = split_sessions(list(sessions.keys()), args.val_ratio, args.seed)
        else:
            train_sessions, val_sessions = set(sessions.keys()), set()

        for session_name, session_files in sessions.items():
            if label == "unknown":
                split = "unlabeled"
            elif session_name in val_sessions:
                split = "val"
            else:
                split = "train"

            for src in session_files:
                kind = media_kind(src)
                if kind is None:
                    continue

                dest_dir = args.output / split / label / kind
                dest_dir.mkdir(parents=True, exist_ok=True)

                safe_name = f"{session_name}__{src.name}"
                dest = dest_dir / safe_name

                if args.move:
                    shutil.move(str(src), str(dest))
                    moved += 1
                else:
                    shutil.copy2(src, dest)
                    copied += 1

    action = "Moved" if args.move else "Copied"
    print(f"{action} {moved if args.move else copied} files into: {args.output}")
    print("Done.")


if __name__ == "__main__":
    main()
