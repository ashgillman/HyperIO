# HyperIO

HyperIO is a Python toolkit for medical physicists working with Elekta Monaco internal plan data.
It can be used to review saved plans, compare calculation settings, and prepare research and commissioning cases.
It can inspect native Monaco patient folders and ZIP archives directly.

> [!WARNING]
> This project was developed with AI tools and is not yet comprehensively validated. The outputs should not be trusted.

## Key capabilities

- **Plan review.** Inspect saved dose grid and Monte Carlo settings, beam information, density overrides, optimisation objectives and dose goals.
  Compare saved settings against a JSON profile you supply.
- **DVH analysis.** Reconstruct and plot DVHs from supported native saved dose grids and contours, overlay dose goals, and export results to Excel or CSV.
- **Relative electron density (RED).** Prepare copies of plans with different structure overrides and estimate mean RED within a contour using the applicable CT-to-ED calibration.
- **Commissioning.** Organise MPPG 5.b test cases, stage phantom plans from matching Monaco templates, and compare exports before and after controlled changes.

## Install

From the repository checkout, use Python 3.10 or later with Tk support for the desktop apps.

**Windows (PowerShell)**

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[applications]"
```

**macOS (Terminal)**

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[applications]'
```

For CLI inspection and settings checks alone, use `pip install -e .` in the virtual environment.

## Quick start

Run the desktop launchers from `.venv\Scripts\` on Windows or `.venv/bin/` on macOS.

| Launcher | Workflow |
| --- | --- |
| `hyperio-dvh-exporter` | [Plot and export DVHs](applications/README.md#dvh-spreadsheet-exporter) |
| `hyperio-red-overrides` | [Prepare RED override variants](applications/README.md#red-overrides) |
| `hyperio-commissioning` | [Build a commissioning worksheet and stage plans](applications/README.md#mppg-5b-commissioning-worksheet) |

HyperIO interacts directly with the Monaco internal stored files. Access them from your installation, something like `FocalData/installation/1~Clinic/<Patient ID>`. You should copy them out to a safe location to prevent any modification into the live environment.

Then, to inspect a plan:

```sh
hyperio inspect "/path/to/monaco-export.zip"
hyperio check "/path/to/monaco-export.zip" examples/common-settings.json
```

## What to know before using the results

- **Settings checks** compare saved values with your profile.
  The bundled example reflects a test fixture and supplies no clinical acceptance criteria.
- **Saved dose** can predate the settings in the export.
  Open generated plan copies in Monaco, verify their settings, and calculate fresh dose before evaluating the effect of an edit.
- **Reconstructed DVHs** are experimental.
  Supported layouts are based on observed Monaco and Unity exports, and results can differ from Monaco because of contour sampling and binning.
  See the [validation record](docs/validation.md).

See the [desktop guide](applications/README.md), the [MPPG 5.b plan setup guide](docs/mppg5b-plan-set.md), and the [native format notes](docs/format-notes.md).
The [code architecture guide](docs/architecture.md) maps the main workflows to their Python modules and classes.
