# Kitsat Ground Station v2

Cross-platform satellite ground station GUI for the Kitsat CubeSat program.
Built with PySide6 (Qt for Python).

> **Status:** Beta — all core features functional. Hardware connection requires
> the `kitsat` library and a compatible modem. Mock mode works without any
> hardware.

---

## Features

| Tab | Description |
|-----|-------------|
| **Terminal** | Raw modem terminal — direct serial/BLE communication |
| **Housekeeping** | Live telemetry table from hardware packets |
| **Cmd Builder** | Hardware command builder (loaded from `sat_commands.csv`) |
| **Map** | Folium-based interactive ground track map |
| **Orbit** | pyqtgraph 3D orbit visualization |
| **Images** | Image gallery with metadata (orbit number, GPS, mode) |
| **Scripts** | Legacy script engine executor |
| **Firmware** | OTA firmware update manager |
| **Dashboard** | 6 circular gauges + 4 live strip charts + attitude/GNSS panels |
| **Commands** | Searchable list of 20 built-in commands with parameter forms and response log |
| **DSL Scripts** | DSL script editor with syntax highlighting, run/stop, and colour-coded output |
| **REPL** | Interactive single-line DSL interpreter with command history |
| **Settings** | Connection, ground station coords, TLE, firmware defaults, theme |
| **About** | Version and license information |

**Mock mode** — click **Mock: OFF** in the toolbar to start a simulated
satellite that emits 1 Hz telemetry with realistic noise, drift, and random
fault injection. No hardware required.

**Orbit simulator** — runs continuously in the background. Speed is selectable
(1× / 10× / 60× / 600×) via the toolbar dropdown. Satellite position feeds
into the mock provider when mock mode is active.

**Keyboard shortcuts** — `Alt+1` through `Alt+9` jump to Terminal, Dashboard,
Commands, DSL Scripts, REPL, Housekeeping, Map, Orbit, and Images.

---

## Requirements

| Requirement | Version |
|---|---|
| Python | 3.11 – 3.13 |
| PySide6 | ≥ 6.6 |
| sgp4 | ≥ 2.22 |
| pyqtgraph | ≥ 0.13 |
| folium | ≥ 0.15 |
| numpy | ≥ 1.24 |
| loguru | ≥ 0.7 |
| kitsat | ≥ 1.2.15 *(hardware only)* |

> **Python 3.13 note:** `PySide6-WebEngine` (used by the Map tab) does not yet
> support Python 3.13. The Map tab will be unavailable on 3.13; all other tabs
> work normally. Install with `pip install kitsat-gs[map]` on 3.11/3.12 to
> enable it.

---

## Installation

### From source (recommended for development)

```bash
# 1. Clone the repository
git clone https://github.com/nikandt/kitsat-groundstation-GUI-2.git
cd kitsat-groundstation-GUI-2

# 2. Create and activate a virtual environment
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

# 3. Install in editable mode with all dependencies
pip install -e .

# Optional: enable the Map tab (Python 3.11/3.12 only)
pip install -e ".[map]"

# Optional: install dev/test dependencies
pip install -e ".[dev]"
```

### From PyPI (when published)

```bash
pip install kitsat-gs
```

---

## Running

```bash
# After installation (any platform)
kitsat-gs

# Or directly via Python module
python -m kitsat_gs
```

### Without hardware (mock mode)

1. Launch the app — `kitsat-gs`
2. Click **Mock: OFF** in the toolbar — it turns green (**Mock: ON**)
3. Navigate to **Dashboard** to see live gauges and charts
4. Navigate to **Commands** to send simulated commands
5. Navigate to **DSL Scripts** or **REPL** to run scripts against mock telemetry

### With hardware

1. Connect your Kitsat modem via USB or Bluetooth
2. Select the port from the **port dropdown** in the toolbar
3. Click **Connect** (or **Auto** for automatic detection)
4. Navigate to **Terminal**, **Housekeeping**, or **Cmd Builder**

---

## Themes

Three themes are available via **Settings → Appearance**:

| Theme | Description |
|---|---|
| **Aerospace (Dark)** | Near-black background, cyan accent — default |
| **Dark** | Dark grey, green accent — original v2 theme |
| **Light** | Light background for bright environments |

---

## DSL Scripting

The **DSL Scripts** and **REPL** tabs use a simple domain-specific language:

```
# Example script
LOG "Starting pass sequence"
SEND PING
WAIT 2.0
GET TELEMETRY battery_percent
IF battery_percent > 20:
    SEND CAPTURE_IMAGE
    WAIT 1.0
    LOG "Image captured"
END
REPEAT 3:
    SEND BEACON
    WAIT 5.0
END
SET MODE low_power
LOG "Sequence complete"
```

**Commands:** `SEND`, `WAIT`, `GET TELEMETRY`, `SET MODE`, `LOG`, `REPEAT … END`, `IF … END`

Click **Load Example** in the DSL Scripts tab or type `HELP` in the REPL for
the full reference.

---

## Development

```bash
# Run tests
pytest tests/

# Run with offscreen rendering (CI / headless)
QT_QPA_PLATFORM=offscreen pytest tests/
```

### Project layout

```
kitsat_gs/
  app.py                     Entry point, stylesheet loader
  core/
    events.py                EventBus singleton (PySide6 Signal)
    models.py                TelemetryFrame, SatImage, CommandDef, …
    command_registry.py      20 built-in satellite commands
    modem_bridge.py          Serial/BLE hardware interface
    packet_dispatcher.py     Telemetry packet parser
    …
  providers/
    mock.py                  1 Hz simulated telemetry provider
  orbit/
    propagator.py            SGP4 + circular-orbit fallback
    ground_station.py        Elevation angle, AOS/LOS prediction
    simulator.py             Adjustable-speed orbit clock
  scripting/
    lexer.py / parser.py     DSL tokenizer and AST builder
    interpreter.py           ScriptWorker (QThread)
  ui/
    main_window.py           Application shell, sidebar, toolbar
    widgets/
      gauge.py               CircularGauge (QPainter arc)
      status_led.py          Pulsing LED indicator
      script_editor.py       QPlainTextEdit + DSL highlighter
    tabs/
      dashboard_tab.py       Gauges + charts + GNSS/IMU
      command_tab.py         Command builder + response log
      scripting_tab.py       DSL editor
      repl_tab.py            Interactive REPL
  assets/
    style.qss                Dark theme
    style_light.qss          Light theme
    style_aerospace.qss      Aerospace dark theme (default)
```

---

## License

MIT — see [LICENSE](LICENSE) or `pyproject.toml`.
