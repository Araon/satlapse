"""
MOSDAC Video Generator

Scrapes satellite images from MOSDAC (ISRO) and compiles them into
timelapse videos.

Usage:
    python main.py                        # default: last month, sat_id=1
    python main.py may                    # month only
    python main.py may 2                  # month + satellite ID
    python main.py may 1 --year 2021      # custom year
    python main.py may 2 --fps 15         # custom frame rate
    python main.py may 1 --output myvideo.mp4
"""

import argparse
import calendar
import datetime
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Optional

import cv2
import requests
from tqdm import tqdm

from helper import last_month, timelist

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SATELLITE_OPTIONS: Dict[int, str] = {
    1: "L1B_STD_IR1",
    2: "L1C_ASIA_MER_BIMG",
}

URL_TEMPLATES: Dict[int, str] = {
    1: "https://mosdac.gov.in/look/3D_IMG/gallery/{year}/{day_month}/3DIMG_{day_month_year}_{time}_L1B_STD_IR1.jpg",
    2: "https://mosdac.gov.in/look/3D_IMG/gallery/{year}/{day_month}/3DIMG_{day_month_year}_{time}_L1C_ASIA_MER_BIMG.jpg",
}

DEFAULT_FPS = 25

# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------


def days_in_month(year: int, month_abbr: str) -> int:
    """Return the number of days in a given month."""
    month_num = list(calendar.month_abbr).index(month_abbr[:3].title())
    return calendar.monthrange(year, month_num)[1]


def download_images(
    sat_id: int,
    month: str,
    year: int,
    images_dir: Path,
    show_progress: bool = True,
) -> None:
    """Download satellite images from MOSDAC for the given month and year."""
    template = URL_TEMPLATES[sat_id]
    times = timelist()
    total_days = days_in_month(year, month)

    total_attempts = total_days * len(times)
    pbar = tqdm(total=total_attempts, desc="Downloading", disable=not show_progress)

    for day in range(1, total_days + 1):
        day_str = f"{day:02d}"
        day_month = f"{day_str}{month}"
        day_month_year = f"{day_str}{month}{year}"

        found_any = False
        for time_slot in times:
            link = template.format(
                year=year,
                day_month=day_month,
                day_month_year=day_month_year,
                time=time_slot,
            )
            filename = images_dir / f"{year}-{month}-{day_str}-{time_slot}.jpg"

            try:
                resp = requests.get(link, stream=True, timeout=30)
                if resp.status_code == 200:
                    resp.raw.decode_content = True
                    with open(filename, "wb") as f:
                        shutil.copyfileobj(resp.raw, f)
                    found_any = True
            except requests.RequestException:
                pass  # image simply may not exist for that time slot

            pbar.update(1)

        if not found_any:
            print(f"  No images found for {year}-{month}-{day_str}")

    pbar.close()


def generate_video(
    images_dir: Path,
    output_path: Path,
    fps: int = DEFAULT_FPS,
    show_progress: bool = True,
) -> None:
    """Compile a directory of sorted images into a video file."""
    files = sorted(images_dir.iterdir())
    if not files:
        print("No images to process.")
        return

    # Determine frame size from the first image
    first = cv2.imread(str(files[0]))
    if first is None:
        print(f"Could not read image: {files[0]}")
        return

    height, width, _ = first.shape
    size = (width, height)

    # Choose codec based on output extension
    suffix = output_path.suffix.lower()
    if suffix == ".mp4":
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    elif suffix == ".avi":
        fourcc = cv2.VideoWriter_fourcc(*"DIVX")
    elif suffix == ".mov":
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    else:
        fourcc = cv2.VideoWriter_fourcc(*"DIVX")

    writer = cv2.VideoWriter(str(output_path), fourcc, fps, size)
    writer.write(first)

    for f in tqdm(files[1:], desc="Generating video", disable=not show_progress):
        img = cv2.imread(str(f))
        if img is not None:
            writer.write(img)

    writer.release()
    print(f"  Video saved → {output_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="MOSDAC Video Generator — scrape satellite images from ISRO's MOSDAC "
        "and compile them into timelapse videos.",
    )
    parser.add_argument(
        "month",
        nargs="?",
        type=str,
        help="Month abbreviation (e.g., jan, feb, mar …). Defaults to last month.",
    )
    parser.add_argument(
        "sat_id",
        nargs="?",
        type=int,
        choices=[1, 2],
        help="Satellite image type: 1 (L1B_STD_IR1) or 2 (L1C_ASIA_MER_BIMG). Defaults to 1.",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=None,
        help="Year (default: current year)",
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=DEFAULT_FPS,
        help=f"Frames per second for the output video (default: {DEFAULT_FPS})",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="Output filename (default: auto-generated as 'L1B_STD_IR1 <MONTH>.mp4')",
    )
    parser.add_argument(
        "--no-progress",
        action="store_false",
        dest="progress",
        help="Disable progress bars",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # Defaults
    month = (args.month or last_month()).upper()
    sat_id = args.sat_id or 1
    year = args.year or datetime.datetime.now().year
    sat_name = SATELLITE_OPTIONS[sat_id]

    # Prepare working directories
    images_dir = Path("images")
    output_dir = Path("output")

    if images_dir.exists():
        shutil.rmtree(images_dir)
    images_dir.mkdir(parents=True)
    output_dir.mkdir(exist_ok=True)

    print("=" * 50)
    print("  MOSDAC Video Generator")
    print("=" * 50)
    print(f"  Month     : {month}")
    print(f"  Year      : {year}")
    print(f"  Satellite : {sat_name}")
    print(f"  FPS       : {args.fps}")
    print()

    # Download
    download_images(sat_id, month, year, images_dir, show_progress=args.progress)
    print()

    # Generate video
    if any(images_dir.iterdir()):
        output_name = args.output or f"{sat_name} {month}.mp4"
        # Ensure .mp4 extension if no extension given
        if "." not in output_name:
            output_name += ".mp4"
        output_path = output_dir / output_name

        generate_video(images_dir, output_path, args.fps, show_progress=args.progress)
        shutil.rmtree(images_dir)
        print("\nDone!")
    else:
        print(f"No images were found for {month} {year}.")
        print("The data may have been archived by ISRO or the URLs may have changed.")
        shutil.rmtree(images_dir)
        sys.exit(1)


if __name__ == "__main__":
    main()