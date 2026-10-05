# Air Draw

Draw in the air with your fingers — a desktop app that turns your webcam into a canvas.
Hand tracking is done with [MediaPipe Hands](https://ai.google.dev/edge/mediapipe/solutions/vision/hand_landmarker), the UI is built with PyQt6.

![Python](https://img.shields.io/badge/python-3.10–3.12-blue)
![PyQt6](https://img.shields.io/badge/UI-PyQt6-41cd52)
![MediaPipe](https://img.shields.io/badge/hand%20tracking-MediaPipe-orange)
![Platforms](https://img.shields.io/badge/platform-macOS%20%7C%20Windows%20%7C%20Linux-lightgrey)

## Features

- **Gesture drawing** — pinch thumb and index finger to draw, pinch thumb and middle finger to clear.
- **Distance-independent gestures** — pinch thresholds scale with the size of your hand, so it works close to or far from the camera.
- **Smooth strokes** — fingertip position is smoothed with a moving average.
- **10-color palette** — pick colors with keys `0`–`9`; every color is customizable.
- **Layout-independent hotkeys** — shortcuts work on English, Russian and Kazakh keyboard layouts.
- **Localized UI** — English, Russian (Русский) and Kazakh (Қазақша).
- **Settings dialog** — camera, resolution, FPS limit, MediaPipe model, thresholds, palette; one-click reset to recommended values.
- **Save to PNG** — drawings are saved to the `air_draw_captures/` folder.
- **Ready-made builds** for Windows, macOS and Linux — no Python required.

## Download

Grab the latest build for your OS from the [**Releases**](https://github.com/kiberbus/air_draw/releases/latest) page:

| OS | File | How to run |
| --- | --- | --- |
| Windows 10/11 (x64) | `AirDraw-windows-x64.exe` | Double-click. If SmartScreen warns, click **More info → Run anyway**. |
| macOS (Apple Silicon) | `AirDraw-macos-arm64.zip` | Unzip and move `AirDraw.app` to Applications. The app is not notarized, so on first launch right-click it → **Open**, or run `xattr -cr AirDraw.app`. Allow camera access when asked. |
| Linux (x64) | `AirDraw-linux-x64.tar.gz` | `tar -xzf AirDraw-linux-x64.tar.gz && ./AirDraw`. On Ubuntu/Debian you may need `sudo apt install libxcb-cursor0`. |

Packaged builds keep settings and saved drawings in `~/AirDraw` (`%USERPROFILE%\AirDraw` on Windows).

## Run from source

Requires Python 3.10–3.12 and a webcam.

```bash
git clone https://github.com/kiberbus/air_draw.git
cd air_draw
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

On macOS, allow camera access for your terminal (or IDE) the first time you run the app.

### Command-line options

| Option | Description |
| --- | --- |
| `--camera N` | Webcam index (default `0`) |
| `--width W` / `--height H` | Capture resolution (default `960x540`) |
| `--fps N` | FPS limit, `0` = unlimited (default `30`) |
| `--lang ru\|kk\|en` | Interface language |

Example: `python main.py --camera 1 --lang en`

## Controls

### Gestures

| Gesture | Action |
| --- | --- |
| Thumb + index finger pinch | Draw |
| Thumb + middle finger pinch | Clear the canvas |

### Keyboard

| Key | Action |
| --- | --- |
| `0`–`9` | Select palette color |
| `+` / `-` | Brush thickness up / down |
| `C` | Clear the canvas |
| `S` | Save drawing as PNG |
| `D` | Toggle debug overlay (pinch distances and thresholds) |
| `H` | Toggle hand skeleton |
| `[` / `]` | Decrease / increase the clear-gesture threshold |
| `O` | Open settings |
| `F1` or `?` | Show shortcuts |
| `Q` | Quit |

Letter shortcuts use the physical key position, so they also work with a Cyrillic layout active (e.g. `Й` = `Q`, `С` = `C`).

## Configuration

Settings are stored in `config.json` — in the project folder when running from source, or in `~/AirDraw` for packaged builds. The file is created with recommended defaults on first launch and updated whenever you change something in the app. Delete it to restore the defaults.

Key parameters:

| Parameter | Default | Description |
| --- | --- | --- |
| `draw_pinch_ratio` | `17` | Draw threshold, in percent of hand size |
| `clear_pinch_ratio` | `17` | Clear threshold, in percent of hand size |
| `fps_limit` | `30` | Camera / render FPS limit (`0` = unlimited) |
| `model_complexity` | `0` | MediaPipe model: `0` = fast, `1` = accurate |
| `detection_scale` | `1.0` | Downscale factor for the frame fed to MediaPipe (lower = faster) |
| `smoothing_window` | `4` | Number of frames used to smooth the fingertip position |
| `palette` | — | Digit key → color in BGR order |

## How it works

1. `ThreadedCamera` grabs frames on a background thread so the UI never blocks on the camera.
2. On every timer tick the frame is mirrored and passed to MediaPipe Hands, which returns 21 hand landmarks.
3. The hand size is measured as the wrist → middle-finger-knuckle distance. A pinch is detected when the thumb-to-finger distance drops below `hand_size × ratio`.
4. While drawing, consecutive fingertip positions are connected with anti-aliased lines on a separate canvas.
5. The canvas is composited over the camera frame using a mask and shown in the window.

## Project structure

```
air_draw/
├── main.py                  # Entry point, CLI arguments
├── src/
│   ├── camera.py            # Threaded webcam capture
│   ├── config.py            # Settings, JSON persistence, translations
│   ├── gestures.py          # Pinch gesture classification
│   ├── key_mapper.py        # Layout-independent hotkeys
│   ├── processor_info.py    # CPU detection for the status bar
│   └── ui/
│       ├── main_window.py   # Main window and frame pipeline
│       ├── settings_dialog.py
│       └── shortcuts_dialog.py
├── tests/
│   ├── test_air_draw.py     # Unit tests
│   └── verify_full.py       # End-to-end smoke test
├── air_draw.spec            # PyInstaller build spec
├── build_exe.bat            # One-click local Windows build
└── .github/workflows/       # CI: builds for Windows, macOS, Linux + releases
```

## Tests

```bash
pip install pytest
pytest tests/test_air_draw.py
python -m tests.verify_full
```

Both run headless (`QT_QPA_PLATFORM=offscreen`). Note that they write recommended settings to `config.json`.

## Building executables

The app is packaged with [PyInstaller](https://pyinstaller.org) using [`air_draw.spec`](air_draw.spec): a single-file executable on Windows and Linux, and an `.app` bundle on macOS. Builds include Python, OpenCV, PyQt6 and the MediaPipe models.

PyInstaller cannot cross-compile, so each OS is built on its own machine. GitHub Actions does this automatically ([`build.yml`](.github/workflows/build.yml)):

- **Every push to `main`** builds all three platforms. Download the files from the run's **Artifacts** section in the **Actions** tab.
- **Pushing a version tag** publishes a GitHub Release with all three builds attached:

  ```bash
  git tag v1.0.0
  git push origin v1.0.0
  ```

To build locally for your current OS:

```bash
pip install pyinstaller
pyinstaller air_draw.spec --clean --noconfirm
```

On Windows you can also just double-click `build_exe.bat`.
