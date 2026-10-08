"""
satlapse — Satellite timelapse videos from MOSDAC (ISRO).

Scrapes satellite imagery from ISRO's MOSDAC data centre and compiles
frames into timelapse videos.

Usage:
    python main.py                               # defaults
    python main.py may                           # month only
    python main.py may --sat INSAT-3D            # month + satellite
    python main.py may 2                         # sat by ID (legacy compat)
    python main.py may --year 2021               # custom year
    python main.py may --sat INSAT-3DR --fps 15
    python main.py may --list-sats               # list available satellites
"""

import argparse
import calendar
import datetime
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import cv2
import requests
from tqdm import tqdm

from helper import last_month, timelist

# ---------------------------------------------------------------------------
# Satellite definitions
# ---------------------------------------------------------------------------


@dataclass
class ImageType:
    """An image product type for a satellite (e.g. infrared, colour blend)."""

    id: str
    label: str
    url_template: str
    file_suffix: str = ""


@dataclass
class Satellite:
    """A satellite with its available image types and URL patterns."""

    id: str  # short key, e.g. "INSAT-3D"
    name: str  # human-readable
    description: str
    image_types: Dict[str, ImageType] = field(default_factory=dict)


# Each image type URL template accepts these format keys:
#   {base_url}  — the base MOSDAC URL
#   {year}      — e.g. 2026
#   {day_month} — e.g. "08OCT"
#   {day_month_year} — e.g. "08OCT2026"
#   {time}      — e.g. "0830"
#   {suffix}    — file_suffix for that image type

_BASE = "https://mosdac.gov.in"

SATELLITES: Dict[str, Satellite] = {
    "INSAT-3D": Satellite(
        id="INSAT-3D",
        name="INSAT-3D",
        description="INSAT-3D — meteorological satellite with IR and visible imaging",
        image_types={
            "IR1": ImageType(
                id="IR1",
                label="L1B_STD_IR1",
                url_template=_BASE + "/look/3D_IMG/gallery/{year}/{day_month}/3DIMG_{day_month_year}_{time}_L1B_STD_IR1.jpg",
            ),
            "BIMG": ImageType(
                id="BIMG",
                label="L1C_ASIA_MER_BIMG",
                url_template=_BASE + "/look/3D_IMG/gallery/{year}/{day_month}/3DIMG_{day_month_year}_{time}_L1C_ASIA_MER_BIMG.jpg",
            ),
        },
    ),
    "INSAT-3DR": Satellite(
        id="INSAT-3DR",
        name="INSAT-3DR",
        description="INSAT-3DR — meteorological satellite, successor to INSAT-3D",
        image_types={
            "IR1": ImageType(
                id="IR1",
                label="L1B_STD_IR1",
                url_template=_BASE + "/look/3DR_IMG/gallery/{year}/{day_month}/3DRIMG_{day_month_year}_{time}_L1B_STD_IR1.jpg",
            ),
            "BIMG": ImageType(
                id="BIMG",
                label="L1C_ASIA_MER_BIMG",
                url_template=_BASE + "/look/3DR_IMG/gallery/{year}/{day_month}/3DRIMG_{day_month_year}_{time}_L1C_ASIA_MER_BIMG.jpg",
            ),
        },
    ),
    "INSAT-3DS": Satellite(
        id="INSAT-3DS",
        name="INSAT-3DS",
        description="INSAT-3DS — latest INSAT meteorological satellite (2024+)",
        image_types={
            "IR1": ImageType(
                id="IR1",
                label="L1B_STD_IR1",
                url_template=_BASE + "/look/3DS_IMG/gallery/{year}/{day_month}/3DSIMG_{day_month_year}_{time}_L1B_STD_IR1_V1.jpg",
            ),
            "BIMG": ImageType(
                id="BIMG",
                label="L1C_ASIA_MER_BIMG",
                url_template=_BASE + "/look/3DS_IMG/gallery/{year}/{day_month}/3DSIMG_{day_month_year}_{time}_L1C_ASIA_MER_BIMG_V1.jpg",
            ),
        },
    ),
}

# Legacy numeric ID mapping (backward compat)
_LEGACY_IDS: Dict[int, str] = {
    1: "INSAT-3D",
    2: "INSAT-3DR",
}

# Legacy numeric image-type mapping (backward compat)
_LEGACY_IMAGE_TYPES: Dict[int, str] = {
    1: "IR1",
    2: "BIMG",
}

DEFAULT_SATELLITE = "INSAT-3D"
DEFAULT_IMAGE_TYPE = "IR1"
DEFAULT_FPS = 25


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------


def days_in_month(year: int, month_abbr: str) -> int:
    """Return the number of days in a given month."""
    month_num = list(calendar.month_abbr).index(month_abbr[:3].title())
    return calendar.monthrange(year, month_num)[1]


def download_images(
    image_type: ImageType,
    month: str,
    year: int,
    images_dir: Path,
    show_progress: bool = True,
) -> None:
    """Download satellite images from MOSDAC for the given month and year."""
    template = image_type.url_template
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


def list_satellites() -> str:
    """Build a formatted table of available satellites and their image types."""
    lines = []
    lines.append("")
    lines.append(f"{'Satellite':<20} {'Image Types':<40} {'Description'}")
    lines.append(f"{'─'*20} {'─'*40} {'─'*40}")
    for key, sat in SATELLITES.items():
        types = ", ".join(f"{tid} ({t.label})" for tid, t in sat.image_types.items())
        desc_short = sat.description[:50]
        lines.append(f"{key:<20} {types:<40} {desc_short}")
    lines.append("")
    lines.append("Usage:  python main.py may --sat INSAT-3DR")
    lines.append("        python main.py may --sat INSAT-3D --img BIMG")
    return "\n".join(lines)


def resolve_satellite(raw: str) -> Satellite:
    """Resolve a satellite name or numeric ID to a Satellite object."""
    # Try numeric ID first (legacy compat)
    try:
        num = int(raw)
        key = _LEGACY_IDS.get(num)
        if key:
            return SATELLITES[key]
        raise ValueError(f"Legacy satellite ID {num} not found. Use --list-sats.")
    except ValueError:
        pass

    # Try direct lookup (case-insensitive)
    for key, sat in SATELLITES.items():
        if key.lower() == raw.lower():
            return sat

    # Try partial match
    matches = [k for k in SATELLITES if raw.lower() in k.lower()]
    if len(matches) == 1:
        return SATELLITES[matches[0]]
    elif len(matches) > 1:
        print(f"Multiple satellites match '{raw}': {', '.join(matches)}")
        print("Use --list-sats to see all options.")
        sys.exit(1)

    print(f"Unknown satellite: {raw}")
    print("Use --list-sats to see available satellites.")
    sys.exit(1)


def resolve_image_type(sat: Satellite, raw: str) -> ImageType:
    """Resolve an image type name or numeric ID to an ImageType."""
    # Try numeric ID (legacy compat)
    try:
        num = int(raw)
        key = _LEGACY_IMAGE_TYPES.get(num)
        if key and key in sat.image_types:
            return sat.image_types[key]
        # fallback: try by index
        types = list(sat.image_types.values())
        if 0 <= num - 1 < len(types):
            return types[num - 1]
        raise ValueError
    except (ValueError, IndexError):
        pass

    # Try direct lookup (case-insensitive)
    for tid, img_type in sat.image_types.items():
        if tid.lower() == raw.lower() or img_type.label.lower() == raw.lower():
            return img_type

    print(f"Image type '{raw}' not found for {sat.name}.")
    print(f"Available types: {', '.join(sat.image_types.keys())}")
    sys.exit(1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="satlapse — scrape satellite images from ISRO's MOSDAC "
        "and compile them into timelapse videos.",
    )
    parser.add_argument(
        "month",
        nargs="?",
        type=str,
        help="Month abbreviation (e.g., jan, feb, mar …). Defaults to last month.",
    )
    parser.add_argument(
        "legacy_sat",
        nargs="?",
        type=str,
        help=argparse.SUPPRESS,  # hidden; legacy position arg support
    )
    parser.add_argument(
        "--sat",
        type=str,
        default=DEFAULT_SATELLITE,
        help=f"Satellite name (default: {DEFAULT_SATELLITE}). Use --list-sats to see all.",
    )
    parser.add_argument(
        "--img",
        "--image-type",
        dest="image_type",
        type=str,
        default=DEFAULT_IMAGE_TYPE,
        help=f"Image type ID (default: {DEFAULT_IMAGE_TYPE}). E.g. IR1, BIMG.",
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
        help="Output filename (default: auto-generated)",
    )
    parser.add_argument(
        "--no-progress",
        action="store_false",
        dest="progress",
        help="Disable progress bars",
    )
    parser.add_argument(
        "--list-sats",
        action="store_true",
        help="List available satellites and image types, then exit",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # --list-sats
    if args.list_sats:
        print(list_satellites())
        return

    # Resolve satellite
    sat = resolve_satellite(args.sat)

    # Legacy compat: if month arg looks like a number, treat as legacy sat_id
    month = (args.month or last_month()).upper()
    if args.month and args.month.isdigit():
        # user passed satellite ID as first positional (legacy)
        sat = resolve_satellite(args.month)
        month = last_month().upper()
        if args.legacy_sat:
            # second positional is the month
            month = args.legacy_sat.upper()

    # Legacy compat: if legacy_sat is set and month is set normally
    if args.legacy_sat and not args.legacy_sat.isdigit():
        month = args.legacy_sat.upper()

    year = args.year or datetime.datetime.now().year
    image_type = resolve_image_type(sat, args.image_type)

    # Prepare working directories
    images_dir = Path("images")
    output_dir = Path("output")

    if images_dir.exists():
        shutil.rmtree(images_dir)
    images_dir.mkdir(parents=True)
    output_dir.mkdir(exist_ok=True)

    print("═" * 50)
    print("  satlapse")
    print("═" * 50)
    print(f"  Satellite  : {sat.name}")
    print(f"  Image type : {image_type.label}")
    print(f"  Month      : {month}")
    print(f"  Year       : {year}")
    print(f"  FPS        : {args.fps}")
    print()

    # Download
    download_images(image_type, month, year, images_dir, show_progress=args.progress)
    print()

    # Generate video
    if any(images_dir.iterdir()):
        output_name = args.output or f"{sat.name} {image_type.label} {month}.mp4"
        if "." not in output_name:
            output_name += ".mp4"
        output_path = output_dir / output_name

        generate_video(images_dir, output_path, args.fps, show_progress=args.progress)
        shutil.rmtree(images_dir)
        print("\nDone!")
    else:
        print(f"No images found for {sat.name} / {month} {year}.")
        print("The data may have been archived by ISRO or the URLs may have changed.")
        shutil.rmtree(images_dir)
        sys.exit(1)


if __name__ == "__main__":
    main()