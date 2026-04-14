"""Extract image frames from spoof videos into a training-ready folder.

Typical use:
    python training/extract_spoof_frames.py \
        --source ./data/raw_spoof_videos \
        --output ./data/antispoof

The script walks all subfolders under `--source`, reads supported video files,
and saves every Nth frame as JPG. It can also split videos into `train/` and
`val/` automatically so you do not have to separate them by hand.
"""
from __future__ import annotations

import argparse
import random
from pathlib import Path

import cv2

VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".3gp", ".webm"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract frames from spoof videos")
    parser.add_argument("--source", type=Path, required=True, help="Folder containing spoof videos")
    parser.add_argument("--output", type=Path, required=True, help="Dataset root or direct image folder")
    parser.add_argument("--every-n-frames", type=int, default=15, help="Save one frame every N frames")
    parser.add_argument("--max-frames-per-video", type=int, default=100, help="Cap saved frames per video")
    parser.add_argument("--min-side", type=int, default=256, help="Resize so the shorter side is at least this size")
    parser.add_argument("--val-ratio", type=float, default=0.2, help="Fraction of videos to place in val split")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for train/val split")
    parser.add_argument(
        "--direct-output",
        action="store_true",
        help="Write directly to --output instead of train/val/spoof/images subfolders",
    )
    return parser.parse_args()


def resize_keep_aspect(frame, min_side: int):
    h, w = frame.shape[:2]
    short = min(h, w)
    if short >= min_side:
        return frame
    scale = float(min_side) / float(short)
    new_w = int(round(w * scale))
    new_h = int(round(h * scale))
    return cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)


def iter_videos(root: Path):
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in VIDEO_EXTS:
            yield path


def choose_split(items: list[Path], val_ratio: float, seed: int) -> dict[Path, str]:
    ordered = list(items)
    rnd = random.Random(seed)
    rnd.shuffle(ordered)

    if len(ordered) <= 1 or val_ratio <= 0:
        return {item: "train" for item in ordered}

    n_val = int(round(len(ordered) * val_ratio))
    n_val = max(1, min(n_val, len(ordered) - 1))
    val_set = set(ordered[:n_val])
    return {item: ("val" if item in val_set else "train") for item in ordered}


def resolve_output_root(base_output: Path, split: str, direct_output: bool) -> Path:
    if direct_output:
        return base_output
    return base_output / split / "spoof" / "images"


def main() -> None:
    args = parse_args()

    if not args.source.exists():
        raise FileNotFoundError(f"Source folder not found: {args.source}")
    if args.every_n_frames <= 0:
        raise ValueError("--every-n-frames must be > 0")

    videos = list(iter_videos(args.source))
    if not videos:
        print("No supported spoof videos found.")
        return

    split_map = choose_split(videos, args.val_ratio, args.seed)

    total_saved = 0
    video_count = 0

    for video_path in videos:
        video_count += 1
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            print(f"[WARN] Could not open video: {video_path}")
            continue

        split = split_map[video_path]
        output_root = resolve_output_root(args.output, split, args.direct_output)
        output_root.mkdir(parents=True, exist_ok=True)

        frame_idx = 0
        saved_for_video = 0
        stem = video_path.stem.replace(" ", "_")
        parent = video_path.parent.name.replace(" ", "_")

        while True:
            ok, frame = cap.read()
            if not ok:
                break

            if frame_idx % args.every_n_frames == 0:
                frame = resize_keep_aspect(frame, args.min_side)
                out_name = f"{parent}__{stem}__f{frame_idx:05d}.jpg"
                out_path = output_root / out_name
                cv2.imwrite(str(out_path), frame)
                saved_for_video += 1
                total_saved += 1

                if saved_for_video >= args.max_frames_per_video:
                    break

            frame_idx += 1

        cap.release()
        print(f"[OK] [{split}] {video_path.name}: saved {saved_for_video} frames")

    print(f"Done. Processed {video_count} videos, saved {total_saved} frames under {args.output}")


if __name__ == "__main__":
    main()
