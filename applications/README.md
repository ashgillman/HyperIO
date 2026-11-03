# HyperIO desktop applications

Two Python/Tk desktop applications are available for Windows and macOS.
The reusable workflows live in `hyperio.application_io` and `hyperio.dvh_export`.
The GUI uses Tkinter, and formatted XLSX export uses openpyxl.
Excel is not required; CSV is also available using Python's standard library.
These are Python applications, not standalone bundled executables.

## Install and launch

Use Python 3.10 or later with Tk support.
The Python installers from python.org include Tk on Windows and macOS; on Windows, retain the Tcl/Tk installation option.
For other Python distributions, check their Tk installation instructions.
Run the following commands from the HyperIO repository directory.

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[applications]"
.\.venv\Scripts\hyperio-red-overrides.exe
.\.venv\Scripts\hyperio-dvh-exporter.exe
```

macOS Terminal:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[applications]'
.venv/bin/hyperio-red-overrides
.venv/bin/hyperio-dvh-exporter
```

## Run from the checkout without installing HyperIO

On macOS or Linux with Nix, enter the development shell from the repository directory:

```sh
nix develop
python applications/override_reds.py
python applications/export_dvh.py
```

The flake supplies Python, Tk, the DVH and XLSX dependencies, pydicom and pytest, and adds `src/` to `PYTHONPATH`.
Run the tests with `python -m pytest`.
On Windows, use the native Python/Tk setup above; a Linux GUI running through WSL requires its own display setup.

The launchers locate the checkout's `src/` directory automatically.
From the repository directory:

```sh
python3 applications/override_reds.py
python3 applications/export_dvh.py
```

On Windows, use `py` instead of `python3` if needed.
The RED application needs Python with Tk support only.
The DVH exporter additionally needs numpy, scipy, shapely and unlzw3, plus openpyxl for XLSX export.
These dependencies must be available in the Python environment even though HyperIO itself need not be installed.

Check Tk support with `python -m tkinter` using that same Python environment.
Both applications use native file dialogs and platform-independent paths.
Directory scanning, dose sampling and file export run in a worker thread, with Tk updates on the main thread.
Native GUI smoke testing on both Windows and macOS remains required before distribution.

## RED preset overrides

1. Choose a directory containing a Monaco patient set (or multiple patient sets), or use **Choose ZIP…** to select a patient-set archive.
2. Select a plan using its patient ID, studyset, name and member path, then choose **Load plan**.
3. Choose a CSV or TSV preset containing `structure` and `red` headers.
4. Review the table: matching structures are highlighted and show the resulting forced mode and preset RED.
5. Choose **Save modified plan copy…** and select a new output filename.

```csv
structure,red
Insert,1.1
```

This is a format example, not a recommended material-density preset.
Use your own reviewed mapping; no clinical mapping values are bundled.
Structure names match exactly, including case.
Duplicate preset names and nonfinite or out-of-range values are rejected.
The supported experimental RED range is 0.01–15, matching the existing density editor.
Unmatched preset names appear in the status message.
Unmatched plan structures keep their existing settings.
Matched records receive forced mode 2 and the requested uniform RED, preserving their fill value, layer and every other source byte.
The application refuses to overwrite the original or an existing output file.
ZIP archives are read directly without extracting or modifying them; the output remains a separate native plan file.

The output is a separate native `plan` file, not a complete independently identified Monaco plan or patient package.
Any subsequent installation into a copied patient set must preserve the required native filename and plan association.
The application does not change studyset defaults, resolve density-layer precedence, update checksums or recalculate dose.
Native edits remain experimental pending Monaco load/save and recalculation review.

## DVH spreadsheet exporter

1. Choose a directory or use **Choose ZIP…**, then select a plan.
2. Keep the default **include** contour-boundary policy, or explicitly select **exclude** for investigation.
3. Choose **Calculate DVH** to load saved `dose.1`, studyset contours and saved DVH settings.
4. Review the table, choose **xlsx** (default) or **csv**, and choose **Export spreadsheet…**.

For one plan, the suggested filename is the plan name.
Alternatively, choose **Batch export XLSX…** and an output folder to calculate every discovered plan using the selected contour-boundary policy.
Each successful workbook is named `<patient ID>-<studyset>-<plan>.xlsx`.
Invalid filename characters are replaced, existing files are never overwritten, and colliding names are reported instead of exported.
A results dialog lists plans that could not be exported; other plans continue.

The exporter calculates the structures enabled in the saved isodose configuration.
The source can be a patient directory, its parent directory, or a ZIP containing either layout.
ZIP contents are read directly without writing an extracted patient set.
It follows the structure order in that configuration and retains repeated reference requests.
Both formats follow the supplied Monaco screenshot's columns and group reference requests beneath each structure.
Matching criteria are placed beside their reference rows; remaining criteria are retained as additional rows.
Dose-at-volume and volume-at-dose criteria also populate their reference volume/dose cells, as in Monaco.
An additional **Calculated Result** column exposes the evaluated goal quantity.
Doses are cGy, volumes are cm³, relative volumes are percentage values, and HI is dimensionless.
Numbers retain full precision, and unavailable quantities are empty cells.

The XLSX **DVH Statistics** sheet uses blue structure rows, grey column headers, frozen headers, useful column widths and landscape print settings.
Doses display one decimal place, volumes three, relative volumes two, and HI two.
Reconstructed criterion results use green/yellow/red fills; unavailable results stay blank.
Names are literal text even when they begin with formula characters.
The **Provenance** sheet records the source directory, selected member path, sampling policies, dose-grid metadata and limitations.

CSV retains data and column order but does not carry Monaco's colours, column widths or number formats.
Formula-like text is prefixed with an apostrophe to keep spreadsheet applications from evaluating names as formulas.
The companion `<filename>.csv.provenance.json` records the source directory, selected member path, sampling settings, dose-grid metadata, reconstructed criterion indicators and limitations.

The calculation uses the existing experimental native-dose and contour reconstruction, not the screenshot's transcribed numerical results.
It supports the existing observed native full-grid dose profile and nonoblique WC contour layout.
Unsupported layouts, missing dose/configuration, ambiguous plan identity and existing reader diagnostics produce an error rather than a fabricated export.
Full member paths distinguish identically named plans in different patient sets.
No Monaco dose calculation is triggered, and saved dose freshness is not established.
Contour-boundary and histogram conventions remain provisional; a small OAR volume/mean residual remains in the supplied reference case.
Monaco's CI formula is unresolved, so its column remains blank.
Reconstructed criterion indicators and spreadsheet colours are not clinical approval.

The source screenshots are recorded by path and hash in `tests/fixtures/vmat-2026-10-29-ground-truth.json`.
Their raw image files remain local to the user's machine and are not application dependencies.
