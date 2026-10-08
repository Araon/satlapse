"""
satlapse — Satellite timelapse videos.

Downloads geostationary satellite imagery from public sources and
compiles frames into timelapse videos.

Currently supported sources:
  • NOAA GOES (GOES-18 West, GOES-19 East) — free, no API key, public CDN
  • MOSDAC/ISRO (INSAT-3D, 3DR, 3DS) — may be limited after site redesign

Usage:
    python main.py --list-sats
    python main.py --sat GOES-19 --img GEOCOLOR --size 1808
    python main.py --sat GOES-18 --img 13 --year 2026 --month sep --fps 15
"""

import argparse
import calendar
import datetime
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

import cv2
import requests
from tqdm import tqdm

from helper import last_month, timelist

# ---------------------------------------------------------------------------
# Data source configuration
# ---------------------------------------------------------------------------

_CDN = "https://cdn.star.nesdis.noaa.gov"

NOAA_GOES_CONFIGS = {
    # sat_id: (label, band_name, region, sensor, base_path)
    "GOES-19": {
        "label": "GOES-19 (GOES-East)",
        "sat_code": "GOES19",
        "sensor": "ABI",
        "region": "FD",
    },
    "GOES-18": {
        "label": "GOES-18 (GOES-West)",
        "sat_code": "GOES18",
        "sensor": "ABI",
        "region": "FD",
    },
}

NOAA_BANDS = {
    # band_id: (label, dir_name, description)
    "GEOCOLOR": ("GeoColor", "GEOCOLOR", "True colour day / IR night"),
    "13": ("Band 13", "13", "Clean longwave IR (clouds, similar to MOSDAC IR1)"),
    "02": ("Band 2", "02", "Visible red"),
    "07": ("Band 7", "07", "Shortwave IR"),
    "08": ("Band 8", "08", "Water vapour - upper"),
    "AirMass": ("Air Mass", "AirMass", "Air mass RGB composite"),
    "Sandwich": ("Sandwich", "Sandwich", "Band 3 & 13 sandwich RGB"),
}

NOAA_SIZES = {
    339: "339x339",
    678: "678x678",
    1808: "1808x1808",
    5424: "5424x5424",
    10848: "10848x10848",
    21696: "21696x21696",
}

# MOSDAC satellite definitions (original, may be limited after v3.0 redesign)
MOSDAC_BASE = "https://mosdac.gov.in"

MOSDAC_CONFIGS = {
    "INSAT-3D": {
        "label": "INSAT-3D",
        "path": "3D_IMG",
        "prefix": "3DIMG",
        "suffix": "",
        "gallery": "gallery",
    },
    "INSAT-3DR": {
        "label": "INSAT-3DR",
        "path": "3DR_IMG",
        "prefix": "3DRIMG",
        "suffix": "",
        "gallery": "gallery",
    },
    "INSAT-3DS": {
        "label": "INSAT-3DS",
        "path": "3DS_IMG",
        "prefix": "3DSIMG",
        "suffix": "_V1",
        "gallery": "gallery",
    },
}

MOSDAC_IMAGE_TYPES = {
    "IR1": ("L1B_STD_IR1", ""),
    "BIMG": ("L1C_ASIA_MER_BIMG", ""),
}

DEFAULT_SATELLITE = "GOES-19"
DEFAULT_IMAGE_TYPE = "GEOCOLOR"
DEFAULT_NOAA_SIZE = 1808
DEFAULT_FPS = 25

# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------


def days_in_month(year: int, month_abbr: str) -> int:
    """Return the number of days in a given month."""
    month_num = list(calendar.month_abbr).index(month_abbr[:3].title())
    return calendar.monthrange(year, month_num)[1]


def to_julian(year: int, month: int, day: int) -> str:
    """Return 3-digit Julian day of year."""
    return f"{datetime.date(year, month, day).timetuple().tm_yday:03d}"


def month_abbr_to_num(abbr: str) -> int:
    return list(calendar.month_abbr).index(abbr[:3].title())


# ---------------------------------------------------------------------------
# Download strategies
# ---------------------------------------------------------------------------


def download_goes(
    sat_key: str,
    band: str,
    year: int,
    month_abbr: str,
    images_dir: Path,
    size: int = DEFAULT_NOAA_SIZE,
    show_progress: bool = True,
    max_frames: int = 1000,
) -> None:
    """Download GOES images from NOAA CDN for a given month using concurrent requests."""
    sat_cfg = NOAA_GOES_CONFIGS[sat_key]
    sat_code = sat_cfg["sat_code"]
    sensor = sat_cfg["sensor"]
    region = sat_cfg["region"]
    band_dir = NOAA_BANDS[band][1]
    size_str = NOAA_SIZES[size]

    base_url = f"{_CDN}/{sat_code}/{sensor}/{region}/{band_dir}/"
    month_num = month_abbr_to_num(month_abbr)
    total_days = calendar.monthrange(year, month_num)[1]

    # GOES full disk images are every 10 minutes
    times = [f"{h:02d}{m:02d}" for h in range(24) for m in (0, 10, 20, 30, 40, 50)]

    # Build all URL + local path pairs first
    tasks: List[tuple] = []
    for day in range(1, total_days + 1):
        jday = to_julian(year, month_num, day)
        day_str = f"{day:02d}"
        for t in times:
            ts = f"{year}{jday}{t}"
            filename = f"{ts}_{sat_code}-{sensor}-{region}-{band_dir}-{size_str}.jpg"
            url = base_url + filename
            local = images_dir / f"{year}-{month_abbr}-{day_str}-{t}.jpg"
            tasks.append((url, local))

    # Limit to max_frames (0 = unlimited)
    if max_frames > 0 and len(tasks) > max_frames:
        tasks = tasks[:max_frames]

    def try_download(url: str, local: Path) -> bool:
        try:
            resp = requests.get(url, stream=True, timeout=3,
                                headers={"User-Agent": "satlapse/2.0"})
            if resp.status_code == 200:
                resp.raw.decode_content = True
                with open(local, "wb") as f:
                    shutil.copyfileobj(resp.raw, f)
                return True
        except requests.RequestException:
            pass
        return False

    downloaded = 0
    pbar = tqdm(total=len(tasks), desc="Downloading", disable=not show_progress)

    # Parallel downloads for speed
    with ThreadPoolExecutor(max_workers=16) as pool:
        futs = [pool.submit(try_download, url, local) for url, local in tasks]
        for fut in as_completed(futs):
            try:
                if fut.result():
                    downloaded += 1
            except Exception:
                pass
            pbar.update(1)

    pbar.close()
    print(f"  Downloaded {downloaded} of {len(tasks)} possible images.")


def download_mosdac(
    sat_key: str,
    image_type_id: str,
    year: int,
    month_abbr: str,
    images_dir: Path,
    show_progress: bool = True,
) -> None:
    """Download MOSDAC images (original source, may be limited)."""
    sat_cfg = MOSDAC_CONFIGS[sat_key]
    img_label, _ = MOSDAC_IMAGE_TYPES[image_type_id]

    url_path = sat_cfg["path"]
    prefix = sat_cfg["prefix"]
    suffix = sat_cfg["suffix"]

    template = (
        f"https://mosdac.gov.in/look/{url_path}/gallery/"
        f"{{year}}/{{day_month}}/{prefix}_{{{{day_month_year}}}}_{{time}}_{img_label}{suffix}.jpg"
    )

    times = timelist()
    total_days = days_in_month(year, month_abbr)
    total_attempts = total_days * len(times)
    pbar = tqdm(total=total_attempts, desc="Downloading", disable=not show_progress)

    for day in range(1, total_days + 1):
        day_str = f"{day:02d}"
        day_month = f"{day_str}{month_abbr}"
        day_month_year = f"{day_str}{month_abbr}{year}"

        found_any = False
        for t in times:
            link = template.format(
                year=year,
                day_month=day_month,
                day_month_year=day_month_year,
                time=t,
            )
            local = images_dir / f"{year}-{month_abbr}-{day_str}-{t}.jpg"

            try:
                resp = requests.get(link, stream=True, timeout=30)
                if resp.status_code == 200:
                    resp.raw.decode_content = True
                    with open(local, "wb") as f:
                        shutil.copyfileobj(resp.raw, f)
                    found_any = True
            except requests.RequestException:
                pass

            pbar.update(1)

        if not found_any:
            print(f"  No images for {year}-{month_abbr}-{day_str}")

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

    first = cv2.imread(str(files[0]))
    if first is None:
        print(f"Could not read image: {files[0]}")
        return

    height, width, _ = first.shape
    size = (width, height)

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
    """Build formatted table of available satellites and image types."""
    lines = ["\nAvailable satellites:\n"]

    lines.append("── NOAA GOES (recommended) ──────────────────────────────")
    lines.append(f"{'Key':<12} {'Satellite':<24} {'Bands'}")
    lines.append(f"{'────':<12} {'────':<24} {'─────'}")
    for key, cfg in NOAA_GOES_CONFIGS.items():
        bands = ", ".join(NOAA_BANDS.keys())
        lines.append(f"{key:<12} {cfg['label']:<24} {bands}")
    lines.append(f"  Sizes: {', '.join(str(s) for s in NOAA_SIZES)}")
    lines.append("  Examples:")
    lines.append("    python main.py --sat GOES-19 --img GEOCOLOR --size 1808")
    lines.append("    python main.py --sat GOES-18 --img 13 --size 678")
    lines.append("")

    lines.append("── MOSDAC / ISRO ────────────────────────────────────────")
    lines.append(f"{'Key':<12} {'Satellite':<24} {'Image types'}")
    lines.append(f"{'────':<12} {'────':<24} {'─────'}")
    for key, cfg in MOSDAC_CONFIGS.items():
        types = ", ".join(MOSDAC_IMAGE_TYPES.keys())
        lines.append(f"{key:<12} {cfg['label']:<24} {types}")
    lines.append("  Note: MOSDAC v3.0 redesign may limit image access.\n")

    lines.append("Usage:  python main.py --sat GOES-19 --img GEOCOLOR")
    lines.append("        python main.py --sat INSAT-3D --img IR1")
    return "\n".join(lines)


def resolve_satellite(raw: str):
    """Resolve satellite name to its config dict and download function."""
    # Try NOAA GOES
    if raw in NOAA_GOES_CONFIGS:
        return NOAA_GOES_CONFIGS[raw], download_goes, "noaa"
    # Try MOSDAC
    if raw in MOSDAC_CONFIGS:
        return MOSDAC_CONFIGS[raw], download_mosdac, "mosdac"
    # Case-insensitive
    for key in NOAA_GOES_CONFIGS:
        if key.lower() == raw.lower():
            return NOAA_GOES_CONFIGS[key], download_goes, "noaa"
    for key in MOSDAC_CONFIGS:
        if key.lower() == raw.lower():
            return MOSDAC_CONFIGS[key], download_mosdac, "mosdac"
    # Partial match
    for key in NOAA_GOES_CONFIGS:
        if raw.lower() in key.lower():
            return NOAA_GOES_CONFIGS[key], download_goes, "noaa"
    for key in MOSDAC_CONFIGS:
        if raw.lower() in key.lower():
            return MOSDAC_CONFIGS[key], download_mosdac, "mosdac"

    print(f"Unknown satellite: {raw}")
    print("Use --list-sats to see available satellites.")
    sys.exit(1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="satlapse — timelapse videos from satellite imagery."
    )
    parser.add_argument(
        "month",
        nargs="?",
        type=str,
        help="Month abbreviation (e.g., jan, feb, mar …). Defaults to last month.",
    )
    parser.add_argument(
        "--sat",
        type=str,
        default=DEFAULT_SATELLITE,
        help=f"Satellite (default: {DEFAULT_SATELLITE}). Use --list-sats.",
    )
    parser.add_argument(
        "--img",
        "--image-type",
        dest="image_type",
        type=str,
        default=DEFAULT_IMAGE_TYPE,
        help=f"Image type / band (default: {DEFAULT_IMAGE_TYPE}).",
    )
    parser.add_argument(
        "--size",
        type=int,
        default=DEFAULT_NOAA_SIZE,
        help=f"Image resolution in px (NOAA GOES only). Options: 339, 678, 1808, 5424, 10848, 21696. Default: {DEFAULT_NOAA_SIZE}",
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
        help=f"Frames per second (default: {DEFAULT_FPS})",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="Output filename (default: auto-generated)",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=1000,
        help="Maximum number of frames to download (default: 1000). 0 = unlimited.",
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
        help="List available satellites and exit",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.list_sats:
        print(list_satellites())
        return

    # Resolve satellite
    sat_cfg, download_fn, source_type = resolve_satellite(args.sat)

    month = (args.month or last_month()).upper()
    year = args.year or datetime.datetime.now().year

    # Build label
    sat_label = sat_cfg["label"]

    # Prepare directories
    images_dir = Path("images")
    output_dir = Path("output")

    if images_dir.exists():
        shutil.rmtree(images_dir)
    images_dir.mkdir(parents=True)
    output_dir.mkdir(exist_ok=True)

    print("═" * 50)
    print("  satlapse")
    print("═" * 50)
    print(f"  Satellite  : {sat_label}")
    print(f"  Source     : {'NOAA GOES' if source_type == 'noaa' else 'MOSDAC/ISRO'}")

    if source_type == "noaa":
        band_label = NOAA_BANDS.get(args.image_type, (args.image_type,))[0]
        print(f"  Band       : {band_label} ({args.image_type})")
        print(f"  Size       : {args.size}x{args.size}")
    else:
        img_info = MOSDAC_IMAGE_TYPES.get(args.image_type, (args.image_type, ""))
        print(f"  Image type : {img_info[0]} ({args.image_type})")

    print(f"  Month      : {month}")
    print(f"  Year       : {year}")
    print(f"  FPS        : {args.fps}")
    print()

    # Download
    if source_type == "noaa":
        download_goes(
            args.sat,
            args.image_type,
            year,
            month,
            images_dir,
            size=args.size,
            show_progress=args.progress,
            max_frames=args.max_frames,
        )
    else:
        download_mosdac(
            args.sat,
            args.image_type,
            year,
            month,
            images_dir,
            show_progress=args.progress,
        )
    print()

    # Generate video
    if any(images_dir.iterdir()):
        if source_type == "noaa":
            band_label = NOAA_BANDS.get(args.image_type, (args.image_type,))[0]
            base_name = f"{sat_label} {band_label} {month}"
        else:
            img_info = MOSDAC_IMAGE_TYPES.get(args.image_type, (args.image_type,))
            base_name = f"{sat_label} {img_info[0]} {month}"

        output_name = args.output or f"{base_name}.mp4"
        if "." not in output_name:
            output_name += ".mp4"
        output_path = output_dir / output_name

        generate_video(images_dir, output_path, args.fps, show_progress=args.progress)
        shutil.rmtree(images_dir)
        print("\nDone!")
    else:
        print(f"No images found for {sat_label} / {month} {year}.")
        shutil.rmtree(images_dir)
        sys.exit(1)


if __name__ == "__main__":
    main()