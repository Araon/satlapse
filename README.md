<h1 align="center">satlapse</h1>
<p align="center">
  <img src="https://raw.githubusercontent.com/Araon/satlapse/master/demos/GOES19-GEOCOLOR-oct.gif" width="600">
  <br><em>GOES-19 Full Disk — GeoColor, October 2026</em>
</p>

Download geostationary satellite imagery from public sources and compile frames into timelapse videos.

**Sources:**
- **NOAA GOES** (GOES-18 West, GOES-19 East) — free, public CDN, no API key
- **MOSDAC / ISRO** (INSAT-3D, 3DR, 3DS) — Indian satellite data

### Demos

| Source | Satellite | Description |
|--------|-----------|-------------|
| <img src="https://raw.githubusercontent.com/Araon/satlapse/master/demos/GOES19-GEOCOLOR-oct.gif" width="300"> | GOES-19 (GeoColor) | Full-disk true colour / IR night composite, October 2026 |
| <img src="https://raw.githubusercontent.com/Araon/satlapse/master/demos/INSAT-3D.gif" width="300"> | INSAT-3D (IR) | Cyclone timelapse over the Indian peninsula, May 2021 |
| <img src="https://raw.githubusercontent.com/Araon/satlapse/master/demos/INSAT-3D-2.gif" width="300"> | INSAT-3D (IR) | A second pass showing twin cyclones, 550+ frames over 30 days |

---

## Setup

### Requirements

- Python **3.9+**
- [UV](https://docs.astral.sh/uv/)

```bash
# Clone the repo
git clone https://github.com/Araon/satlapse.git
cd satlapse

# Create a virtual environment and install dependencies
uv sync
```

---

## Usage

```bash
python main.py [month] [sat_id] [options]
```

### Arguments

| Argument | Description | Default |
| -------- | ----------- | ------- |
| `month`  | Month abbreviation — `jan`, `feb`, `mar`, …, `dec` | Previous month |

### Options

| Option                     | Description                                      | Default          |
| -------------------------- | ------------------------------------------------ | ---------------- |
| `--sat SATELLITE`          | Satellite name (see `--list-sats`)               | `INSAT-3D`       |
| `--img, --image-type TYPE` | Image type: `IR1` (infrared) or `BIMG` (colour)  | `IR1`            |
| `--year YEAR`              | Satellite data year                              | Current year     |
| `--fps FPS`                | Frames per second in the output video            | `25`             |
| `--output, -o FILE`        | Output filename                                  | Auto-generated   |
| `--no-progress`            | Disable progress bars                            | (enabled)        |
| `--list-sats`              | List available satellites and exit               |                  |
| `--help`                   | Show help message                                |                  |

### Examples

```bash
# Last month's data with default satellite (INSAT-3D, IR1)
python main.py

# Specific month and satellite
python main.py may --sat INSAT-3DR

# Colour blended images
python main.py may --sat INSAT-3D --img BIMG

# Custom year
python main.py jun --sat INSAT-3D --year 2021

# Slow-motion playback (lower FPS)
python main.py apr --sat INSAT-3DR --fps 10

# Custom output file
python main.py jan --sat INSAT-3DS --year 2025 -o cyclone-jan-2025.mp4

# List available satellites
python main.py --list-sats
```

> **Legacy syntax**: `python main.py may 1` (month + numeric sat ID) still works for
> backward compatibility. ID `1` = INSAT-3D, `2` = INSAT-3DR.

### Output

- Images are downloaded to `./images/` (auto-cleaned after video generation).
- Videos are saved to `./output/` as MP4 files.

---

## Satellites

Run `python main.py --list-sats` to see all available satellites and their image types:

| Satellite   | Image Types                    | Description                                  |
| ----------- | ------------------------------ | -------------------------------------------- |
| INSAT-3D    | IR1 (infrared), BIMG (colour) | Meteorological satellite with IR & visible   |
| INSAT-3DR   | IR1 (infrared), BIMG (colour) | Successor to INSAT-3D                        |
| INSAT-3DS   | IR1 (infrared), BIMG (colour) | Latest INSAT meteorological satellite (2024+) |

### Image Types

| ID     | Label               | Description                                     |
| ------ | ------------------- | ----------------------------------------------- |
| `IR1`  | `L1B_STD_IR1`       | Standard infrared channel (Level-1B)             |
| `BIMG` | `L1C_ASIA_MER_BIMG` | Asia-mercator colour blended image (Level-1C)   |

---

## How it works

1. The script builds URLs in the pattern used by MOSDAC's image gallery.
2. It iterates through every day of the given month and every 30-minute time slot (00:00–20:30 UTC), attempting to download each frame.
3. Available frames are sorted chronologically and compiled into a video with OpenCV.

If a day or time slot has no image (cloud cover, no satellite pass, data gap), it is silently skipped.

---

## Project structure

```
satlapse/
├── main.py          # CLI entry point & satellite definitions
├── helper.py        # Timestamp & date helpers
├── pyproject.toml   # Project config (UV)
├── .gitignore
├── README.md
└── demos/           # Example output GIFs
```

---

## License

MIT