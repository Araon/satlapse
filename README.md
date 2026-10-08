<h1 align="center">MOSDAC Video Generator</h1>
<p align="center">
  <img src="https://raw.githubusercontent.com/Araon/MOSDAC_Video_Generator/master/demos/INSAT-3D-2.gif">
</p>

Scrape satellite imagery from [MOSDAC](https://www.mosdac.gov.in) (ISRO's Meteorological & Oceanographic Satellite Data Archive Centre) and compile frames into timelapse videos.

**Example**: The demo above shows two cyclones hitting the Indian peninsula in May, captured by INSAT-3D across 30 days with over 550 individual images. The sun's reflection gliding across the ocean from right to left marks the passage of each day.

---

## Setup

### Requirements

- Python **3.9+**
- [UV](https://docs.astral.sh/uv/)

```bash
# Clone the repo
git clone https://github.com/Araon/MOSDAC_Video_Generator.git
cd MOSDAC_Video_Generator

# Create a virtual environment and install dependencies
uv sync
```

---

## Usage

```bash
python main.py [month] [sat_id] [options]
```

### Arguments

| Argument     | Description                                                  | Default            |
| ------------ | ------------------------------------------------------------ | ------------------ |
| `month`      | Month abbreviation — `jan`, `feb`, `mar`, …, `dec`          | Previous month     |
| `sat_id`     | Image type — `1` (L1B_STD_IR1) or `2` (L1C_ASIA_MER_BIMG)  | `1`                |

### Options

| Option                | Description                              | Default     |
| --------------------- | ---------------------------------------- | ----------- |
| `--year YEAR`         | Satellite data year                      | Current year |
| `--fps FPS`           | Frames per second in the output video    | `25`        |
| `--output, -o`        | Output filename                          | Auto-generated |
| `--no-progress`       | Disable progress bars                    | (enabled)   |
| `--help`              | Show help message                        |             |

### Examples

```bash
# Last month's data with default satellite
python main.py

# Specific month and satellite
python main.py may 2

# Custom year
python main.py jun 1 --year 2021

# Slow-motion playback (lower FPS)
python main.py apr 2 --fps 10

# Custom output file
python main.py jan 1 --year 2023 --o cyclone-jan-2023.mp4
```

### Output

- Images are downloaded to `./images/` (auto-cleaned after video generation).
- Videos are saved to `./output/` as MP4 files.

---

## Satellite Types

| ID | Type             | Description                              |
| -- | ---------------- | ---------------------------------------- |
| 1  | `L1B_STD_IR1`    | Standard infrared channel (Level-1B)     |
| 2  | `L1C_ASIA_MER_BIMG` | Asia-mercator colour blended image (Level-1C) |

---

## How it works

1. The script builds URLs in the pattern used by MOSDAC's image gallery.
2. It iterates through every day of the given month and every 30-minute time slot (00:00–20:30 UTC), attempting to download each frame.
3. Available frames are sorted chronologically and compiled into a video with OpenCV.

If a day or time slot has no image (cloud cover, no satellite pass, data gap), it is silently skipped.

---

## Project structure

```
MOSDAC_Video_Generator/
├── main.py          # CLI entry point
├── helper.py        # Timestamp & date helpers
├── pyproject.toml   # Project config (UV)
├── .gitignore
├── README.md
└── demos/           # Example output GIFs
```

---

## License

MIT