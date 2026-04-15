# RSC Mining Bot v1

An automated mining bot for ANY Runescape Classic Server. Powered by real-time YOLO object detection and OCR. Features a full Tkinter GUI, human-like mouse movement, fatigue/inventory monitoring, and extensive anti-detection measures.

![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)
![YOLO](https://img.shields.io/badge/YOLO-Ultralytics-purple)
![OpenCV](https://img.shields.io/badge/OpenCV-4.8+-green?logo=opencv)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey?logo=windows)

---

## Table of Contents

- [Features](#features)
- [Supported Ores](#supported-ores)
- [Screenshots](#screenshots)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
- [GUI Overview](#gui-overview)
- [Configuration](#configuration)
- [How It Works](#how-it-works)
- [Project Structure](#project-structure)
- [Troubleshooting](#troubleshooting)

---

## Features

### Detection
- **YOLO Object Detection** — Identifies ore rocks at ~5 FPS using YOLOv8 (`best.pt`), with an optional dedicated Adamantite model (`adamantite.pt`) for ensemble detection
- **OCR Monitoring** — Reads fatigue % and inventory count (X/30) from the game UI via EasyOCR; detects "You are too tired" messages as a fallback

### Mining
- **Fast / Lazy Modes** — Fast (100–1200ms post-click delay) or Lazy (500–2900ms) to suit different play styles
- **Powermine** — Continuous mining without stopping
- **Stop on Full Inventory** — Auto-stop when inventory hits 30/30
- **Ore Priority** — Drag-and-drop reordering to control which ores are mined first
- **Camera Rotation** — Automatically rotates camera (arrow keys or middle-mouse drag) when no ores are visible

### Anti-Detection
- **Human Mouse Curves** — Three-phase movement (overshoot → pause → correction) with easing, jitter, and variable press duration
- **Random Click Position** — Clicks a random point within the ore's bounding box (±5% variance) instead of the center, so no two clicks land in the same spot
- **Randomized Delays** — No fixed timing patterns; all intervals are randomized
- **Click Blacklisting** — Ore blacklisted for 30s after 3 failed click attempts
- **Break System** — Scheduled long breaks and micro-breaks (100–500ms) with randomized intervals
- **Failsafes** — Stops after 30 consecutive camera rotations with no ore; fatigue auto-stop at 96%

### GUI & Overlay
- **Tkinter GUI** — Live stats, debug log, ore toggles, settings, and **F6** hotkey to start/stop
- **Overlay** — In-game (transparent chroma-key) or pop-out window showing detection boxes
- **6 Themes** — Default, White+LightBlue, Magenta+Black, Red+Black, Green+Black, RSC Classic
- **Persistent Config** — All settings saved to `config.json`

---

## Supported Ores

| Ore | Color Code | Model |
|-----|-----------|-------|
| Tin | Yellow | Main |
| Copper | Orange | Main |
| Iron | White | Main |
| Coal | Gray | Main |
| Mithril | Purple | Main |
| Adamantite | Red | Main + Adamantite |

Ores are detected with colored bounding boxes in the overlay. Priority order is fully customizable via drag-and-drop in the GUI.

> **Note:** Tin, Copper, and Iron currently have the best detection accuracy and are the recommended ores to mine.

---

## Screenshots

<img width="733" height="1009" alt="imageforb0at2" src="https://github.com/user-attachments/assets/3ccd2eaa-e3e4-4319-b973-c02e413f920a" />
<img width="1362" height="781" alt="imageforb0at1" src="https://github.com/user-attachments/assets/1b323649-4212-4976-b5ab-24eee4862415" />

---

## Requirements

- **OS:** Windows 10/11
- **Python:** 3.10+
- **GPU:** Optional (CUDA-compatible GPU for faster detection; CPU fallback supported)
- **Game:** Rs-Classic Clients (Java-based)
- **Game settings:** Certain text needs to be highly visible

### Python Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `ultralytics` | ≥ 8.0.0 | YOLOv8 object detection |
| `torch` | ≥ 2.0.0 | PyTorch inference engine |
| `torchvision` | ≥ 0.15.0 | Vision utilities |
| `opencv-python` | ≥ 4.8.0 | Image processing & frame annotation |
| `numpy` | ≥ 1.24.0 | Array operations |
| `mss` | ≥ 9.0.0 | Fast screen capture |
| `easyocr` | ≥ 1.7.0 | OCR for fatigue & inventory reading |
| `Pillow` | ≥ 10.0.0 | Image manipulation |
| `pywin32` | ≥ 306 | Windows API (window management) |
| `psutil` | ≥ 5.9.0 | Process detection (Java windows) |

---

## Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/RSC-Mining-Bot.git
   cd RSC-Mining-Bot
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv my_bot_env
   my_bot_env\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Ensure model files are present**
   - `best.pt` — Main YOLO model (all ore types)
   - `adamantite.pt` — Adamantite-specific model (optional)

   These `.pt` files must be in the project root directory.

---

## Usage

### Quick Start
Double-click **`START_BOT.bat`** to launch the GUI without a console window.

### Manual Start
```bash
python main.py
```

### Basic Workflow
1. Launch the bot GUI
2. Select or auto-detect your java.exe or javaw.exe game window (Note:May be configured only to one private server at the moment)
3. Choose which ores to mine and set their priority order
4. Configure mining mode (Fast or Lazy)
5. Adjust settings as needed (confidence, breaks, mouse behavior)
6. Press **Start** or hit **F6** to begin mining
7. Press **F6** again to stop

---

## GUI Overview

The GUI has two tabs:

**Bot Tab** — Window selector (auto-detects Java processes), model toggles, ore checkboxes with drag-and-drop priority, mining mode selector, and start/stop controls on the left. Live statistics (runtime, fatigue %, inventory, last click time) and a color-coded debug log on the right.

**Settings Tab** — Confidence threshold, mouse delays & curve strength, break intervals & durations, font selection (Consolas / Segoe UI / Courier New / Fixedsys), theme picker, and antiban toggles.

---

## Configuration

All settings are saved to **`config.json`** and persist between sessions:

```jsonc
{
  "window_title": "RSC*****",
  "ore_checkboxes": { "tin_rock": true, "copper_rock": true, ... },
  "priority_order": ["iron_rock", "copper_rock", ...],
  "fast_mining_enabled": true,
  "powermine_enabled": false,
  "stop_on_full_inventory": false,
  "model_settings":     { "use_main_model": true, "use_adamantite_model": false },
  "detection_settings": { "confidence_threshold": 0.80, "update_interval_ms": 200 },
  "mouse_settings":     { "min_delay_ms": 200, "max_delay_ms": 500, "human_curve_strength": 0.7 },
  "break_settings":     { "breaks_enabled": false, "micro_breaks_enabled": true, "micro_break_min_ms": 100, "micro_break_max_ms": 500 },
  "fatigue_detection_enabled": true,
  "overlay_mode": "ingame",
  "theme": "White + Light Blue",
  "font": "Consolas"
}
```

---

## How It Works

```
Screen Capture (mss)  →  YOLO Detection (best.pt)  →  Filter & Sort by distance
       ↑                                                        ↓
   Loop / Rotate                                       Human Mouse → Click
       ↑                                                        ↓
  Check fatigue & inventory  ←  OCR reads "You obtain..." message
```

1. `mss` captures the game window at ~5 FPS
2. YOLO identifies ore rocks; results are filtered by enabled ores and sorted by proximity
3. `HumanMouse` moves to the closest ore and clicks
4. OCR waits for the "You manage to obtain" message, then reads fatigue % and inventory
5. Repeats until stopped, inventory full, or fatigue threshold reached

---

## Project Structure

```
RSC_miningbotv1/
├── main.py              # Tkinter GUI application (entry point)
├── bot.py               # Core mining bot logic & main loop
├── detector.py          # YOLO object detection wrapper
├── mouse.py             # Human-like mouse movement controller
├── overlay.py           # Legacy overlay implementation
├── drag_drop_list.py    # Drag-and-drop Tkinter listbox widget
├── config.json          # Persisted bot settings
├── best.pt              # Main YOLO model (all ores)
├── adamantite.pt        # Adamantite-specific YOLO model
├── requirements.txt     # Python dependencies
├── START_BOT.bat        # Windows launcher script
├── bot.spec             # PyInstaller build config
├── icons/               # GUI icon assets
└── Tools&Test/          # Diagnostic & testing utilities
    ├── diagnose_ocr.py
    ├── healthcheck_ocr.py
    ├── simple_ocr_test.py
    ├── test_ocr.py
    └── *.md             # Documentation & guides
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Bot can't find game window | Ensure RSC***** is running; check that the window title matches in config |
| Low detection accuracy | Lower the confidence threshold in Settings (try 0.50–0.70) |
| OCR not reading fatigue/inventory | Check `Tools&Test/` diagnostic scripts; ensure EasyOCR is installed |
| Slow detection | Install CUDA-compatible PyTorch for GPU acceleration |
| Mouse not clicking correctly | Adjust human curve strength; ensure game window is not obstructed |
| Bot stops unexpectedly | Check debug log; may be hitting fatigue threshold (96%) or consecutive failsafe (30 rotations) |
| F6 hotkey not working | Ensure the GUI window is not minimized; hotkey uses polling-based detection |

For detailed OCR troubleshooting, see [`Tools&Test/OCR_SETUP_AND_TROUBLESHOOTING.md`](Tools&Test/OCR_SETUP_AND_TROUBLESHOOTING.md).

---

## Disclaimer

This bot is intended for educational purposes and use on private servers that permit automation. Use responsibly and in accordance with the rules of the server you are playing on. The authors are not responsible for any consequences of using this software.

---

## License

This project is provided as-is for personal use. See the repository for any applicable license terms.
