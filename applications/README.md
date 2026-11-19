# HyperIO desktop applications

Three Python/Tk desktop applications are available for Windows and macOS.
The RED and DVH windows live in `hyperio.desktop`, and the commissioning window lives in `hyperio.commissioning_gui`.
The headless RED and DVH export workflows are available through `hyperio.application_io` and `hyperio.dvh_export`.
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
.\.venv\Scripts\hyperio-commissioning.exe
```

macOS Terminal:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[applications]'
.venv/bin/hyperio-red-overrides
.venv/bin/hyperio-dvh-exporter
.venv/bin/hyperio-commissioning
```

## Run from the checkout without installing HyperIO

On macOS or Linux with Nix, enter the development shell from the repository directory:

```sh
nix develop
python applications/override_reds.py
python applications/dvh.py
python applications/commissioning.py
```

The flake supplies Python, Tk, the DVH and XLSX dependencies, pydicom and pytest, and adds `src/` to `PYTHONPATH`.
Run the tests with `python -m pytest`.
On Windows, use the native Python/Tk setup above; a Linux GUI running through WSL requires its own display setup.

The launchers locate the checkout's `src/` directory automatically.
From the repository directory:

```sh
python3 applications/override_reds.py
python3 applications/dvh.py
python3 applications/commissioning.py
```

On Windows, use `py` instead of `python3` if needed.
Manual RED editing and the commissioning application need Python with Tk support only.
Calculating CT mean RED also requires numpy, shapely and pydicom.
The DVH exporter additionally needs numpy, scipy, shapely and unlzw3, plus openpyxl for XLSX export.
These dependencies must be available in the Python environment even though HyperIO itself need not be installed.

Check Tk support with `python -m tkinter` using that same Python environment.
The applications use native file dialogs and platform-independent paths.
The RED and DVH applications run directory scanning, dose sampling and file export in a worker thread, with Tk updates on the main thread.
Native GUI smoke testing on both Windows and macOS remains required before distribution.

## MPPG 5.b commissioning worksheet

Use **Open…** to load the [example worksheet](../examples/commissioning-mppg5b.json).
Its fictional setups and evidence placeholder are illustrative only, not guideline defaults or calibration evidence.

For a complete starting inventory of test designs, open the [MPPG 5.b plan specifications](../examples/commissioning-mppg5b-plan-set.json).
The [plan setup guide](../docs/mppg5b-plan-set.md) describes how to expand the set for the local machine and build the plans in the TPS.

Choose a test on the left and use **Add case…** to create a row in its table.
Use **Duplicate…** to vary one part of a setup, such as SSD or field size, while retaining the rest.
Select **Include** or **Exclude** to control which cases appear in the export.
The count beside each test shows its included cases.

For beam tests, record the machine and model, energy, field shape and dimensions, SSD/SAD, MU, depths, angles, modifiers and aperture details as applicable.
Select the reference plane when entering field dimensions.
Enter central-axis measurement depths from the phantom surface in centimetres, separated by commas.
Image voxel spacing uses three XYZ values in millimetres and is independent of the dose-grid setting.
Monte Carlo uncertainty and its mode are optional planning values.
For arbitrary apertures, record dimensions and a description or reference to the leaf, jaw or cutout geometry.
CT-to-density, modulated plans, external end-to-end work and routine QA have fields for the relevant phantom, plan or evidence.

**Save** keeps the entire editable worksheet in JSON.
**Export JSON…** writes a separate editable JSON containing only included cases, with the MPPG edition, test IDs, stable case IDs and entered values.
Guideline examples stay in the reference pane and local setup values start blank.
An included case represents an intended setup, with blank values permitted during drafting.
Use **Build Monaco patient…** to stage a native patient folder with plans for the assigned cases.

1. Choose a copy of a native Monaco phantom patient directory named `1~<patient ID>` containing the applicable studysets and saved template plans.
2. Enter a new patient ID and a Monaco name in `Family^Given` format.
3. Select each case you want to build and assign a template with matching machine, beam geometry, aperture, SSD and MU.
   Use separate templates for different beam setups.
4. Choose a staging directory.
   Copy the resulting `1~<new patient ID>` folder into the target Monaco Installation/Clinic folder under an unused patient ID.
5. Open the patient in Monaco and check the studyset, beam geometry, MU and calculation settings before calculation.

Each assigned case creates a separate plan with the test ID and part of the case ID in its name.
The builder copies the native studysets, uses the template beam and prescription records, and applies the worksheet dose grid and Monte Carlo settings when supplied and supported.
Use a phantom with compatible clinic machine models and CT-to-density tables.
The source phantom image UIDs and cached image metadata are carried over, so use a phantom without patient information.
The builder omits inherited dose files, calculation logs and known locks.
Native plan status and checksum records remain inherited from the templates.
HyperIO checks the exported native metadata locally, and Monaco load, save and calculation are the next validation steps.
Automatic beam construction from worksheet field size, SSD, MU or aperture values is pending.

The catalogue follows [AAPM MPPG 5.b (2022)](https://doi.org/10.1002/acm2.13641) Tables 4–10 and Section 9.

## RED overrides

1. Choose a directory containing a Monaco patient set (or multiple patient sets), or use **Choose ZIP…** to select a patient-set archive.
2. In each output tab, choose an **Input plan** using its patient ID, studyset, name and member path.
3. Double-click **New RED** or **Resulting mode** to edit individual structures.
   Optionally choose a CSV or TSV preset containing `structure` and `red` headers to populate forced RED overrides for matching names.
   To use CT-derived values, check the preselected calibration or choose a named `DICOM3.<curve name>` file or a ZIP containing it, then select **Calculate CT mean RED**.
   Double-click a value in **CT mean RED** to copy it into **New RED** and set **Resulting mode** as needed.
4. Leave **Output plan name** blank to replace that input plan in the exported copy, or enter a new name to add a cloned plan alongside it.
5. Choose **Add output** for additional edits or variants; each tab has its own input plan, output name, preset and individual edits.
6. Choose a **Save as** mode, then choose **Save patient…**.
   - **Folder** or **ZIP** applies every tab to a complete copy at a new output path.
   - **Add to source folder** requires a directory input and a new plan name in every tab.
     It adds the plan copies beside their input plans and reuses the existing studysets.

Both modes preserve the existing plan and studyset files at the source.
A full copy retains the relative folder layout, including any enclosing patient folders in an archive.
The new folder receives the source folder's contents directly, without an additional wrapper folder.

Each tab starts from its original input plan, so overrides do not accumulate between tabs.
For example, select PlanC in two tabs, leave the first output name blank and name the second PlanCAlt.
The exported patient contains modified PlanC and a separate modified PlanCAlt, while PlanA, PlanB and PlanD remain unchanged.
A new name clones the entire input plan folder, including its companion files, and updates the native `plan` header name.
Without a preset or individual edits, the input plan's RED settings are retained.
Changing only the resulting mode retains the current RED value.
Manual edits take precedence over preset values, and changing the input plan clears those edits.
**Remove output** removes the selected tab when more than one exists.
Choosing a different source resets the tabs.

CT mean RED is available for head-first supine axial studysets with matching cached DICOM CT images and native contours.
The app selects the curve by the name recorded in the linked studyset.
When you choose an input plan, the app looks for a matching `DICOM3.<curve name>` file in the platform's user data directory.

| Platform | Preferred calibration directory |
| --- | --- |
| Windows | `%LOCALAPPDATA%\HyperIO\data\cttoed` (normally under `%USERPROFILE%\AppData\Local`) |
| macOS | `~/Library/Application Support/HyperIO/data/cttoed` |
| Linux | `$XDG_DATA_HOME/hyperio/data/cttoed` (defaults to `~/.local/share/hyperio/data/cttoed`) |

It then checks `~/.config/hyperio/data/cttoed` and `~/.hyperio/data/cttoed`, in that order.
The first matching file is preselected.
**Choose calibration…** opens the first existing directory in this search order and creates the preferred directory when none exists and permissions allow.
Select a calibration ZIP through the picker to use a curve from that archive.
Use the calibration file or archive from the applicable TPS installation, since a name match cannot establish that the calibration points are identical.
The calculation converts CT voxel centres inside the contour to RED using linear interpolation between the supplied HU points and uses the nearest endpoint outside the curve range.
The displayed mean describes CT-derived density before plan and structure overrides.

Output names must use characters supported by the native Windows encoding and valid Windows/macOS folder names.
Two tabs cannot target the same plan path (case-insensitive).
A new name cannot collide with another existing plan in that patient.
The same name in different patient folders remains distinct.
For a full copy, choose a new path outside the source patient folder.
All edits are checked and staged before publishing the output.

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
Matched records receive forced mode 2 and the requested uniform RED, preserving their fill value and layer.
Only the requested density fields and the output plan-name header line are edited; other source bytes are retained.
The application refuses to overwrite the original or an existing output file.
ZIP inputs are read directly without modifying them; folder and ZIP output are both available regardless of the input format.

Companion files, including saved dose, logs and checksums, are copied verbatim.
The application does not change studyset defaults, resolve density-layer precedence, update checksums or recalculate dose.
Saved dose must be recalculated after density edits; copying it does not establish that it matches the new RED settings.
Native edits remain experimental pending Monaco load/save and recalculation review.

## DVH spreadsheet exporter

1. Choose a directory or use **Choose ZIP…**, then select a plan.
2. Keep the default **include** contour-boundary policy, or explicitly select **exclude** for investigation.
3. Choose **Calculate DVH** to load saved `dose.1`, studyset contours and saved DVH settings.
4. Review the table, choose **xlsx** (default) or **csv**, and choose **Export spreadsheet…**.

The **DVH plot** tab displays the calculated cumulative curves.
Use the checkboxes on the right to show or hide each structure, and the radio buttons to select the structure to inspect.
The selected curve is drawn thicker.
Move the cursor over the plot to choose a dose on that curve; the readout shows dose in cGy and volume in both cm³ and percent.
Click to pin a point, click again to choose another point, or choose **Track cursor** to resume movement.
Enter a positive **Prescription (Gy)** to also show dose as a percentage of that prescription (for example, enter `60` for 60 Gy).
The **Dose** and **Volume** selectors switch the axes between absolute and relative units.
The prescription is a user-supplied display normalization and does not change calculated dose, statistics, criteria or exports.
Cursor values use linear interpolation of the same provisional cumulative histogram used for calculated volume-at-dose queries.
Changing the plan, source or contour-boundary setting clears both the table and plot until the next calculation.

### DVH goal libraries

The **Goal library** dropdown lists JSON files in `src/hyperio/data/dvh/`, including `eviq.json` and `TCC.json`.
Libraries with a single protocol, prescription or structure goal select those choices automatically, so TCC opens directly to its PTV goals.
Select a library, filter the protocol radio list (for example, type `prostate`), select a protocol, then select its prescription.
All structure goals for that prescription become available together.
Selecting a plan structure automatically overlays every matching goal group in that prescription.
Selecting a structure-goal radio button always enables its goal points.
When structures match, Show switches to only those structures; an active matching structure is retained, otherwise the first match becomes active.
When no structures match, the active structure and Show selections stay unchanged, and the goal points still display using the active structure for volume conversion.
Show checkboxes remain manually adjustable after selection.
Selecting a different plan structure resumes automatic name matching.
Matching uses case-insensitive shell-style `structure_patterns`, for example `["*PTV*"]`.
Broad patterns can match subtraction structures or PRVs too; edit them for local naming conventions.
**Advanced: load JSON…** below the goal selection lists loads a library from another location, including a local refresh.
**Advanced…** beside **Calculate DVH** contains the contour-boundary setting.
**Export spreadsheet…** offers Excel and CSV in the save dialog; the selected filename extension determines the writer.

TCC contains the seven user-supplied PTV goals, with separate tolerance and action D2% limits.
Relative-dose goals require the prescription entered in Gy and work with either dose-axis unit.
V95% ≥ 98% and D98% ≥ 95% express the same coverage boundary for an ideal continuous monotone DVH; both requested forms remain in the file.
D2% ≤ 107% and V107% ≤ 2% similarly describe a hotspot boundary, although plateaus, interpolation and equality conventions can affect numerical equivalence.

The updater needs Beautiful Soup in addition to the application dependencies:

```sh
python -m pip install -e '.[applications,eviq]'
hyperio-eviq-update
```

From the checkout, `python scripts/update_eviq.py` runs the same command.
The Nix shell includes its dependencies.
By default the updater discovers protocols in eviQ's public radiation-oncology category listing, including its embedded JSON tree, and writes `~/.hyperio/eviq.json`.
Listing entries explicitly labelled discontinued, superseded or archived are excluded from that tree.
Redirect aliases are deduplicated using the protocol ID displayed in the fetched page.
Load that refreshed file with **Advanced: load JSON…**, or refresh the bundled file explicitly as below.
Run the command again whenever you want to refresh the catalogue, then reload it in the app.
Refreshing needs an internet connection; plotting a saved catalogue works offline.
The app does not contact eviQ or send plan data to it.

To refresh the snapshot kept in Git, run this command from the checkout and review the resulting diff:

```sh
python scripts/update_eviq.py --output src/hyperio/data/dvh/eviq.json --verbose
```

Commit `src/hyperio/data/dvh/eviq.json` after reviewing the update.
The snapshot is also included in installed packages.

For a smaller catalogue or a different location, supply one or more protocol URLs:

```sh
python scripts/update_eviq.py --output ./eviq.json --cache ./eviq-sources \
  --url https://www.eviq.org.au/radiation-oncology/urogenital/prostate/235-prostate-adenocarcinoma-definitive-ebrt-high-r
```

Goal selection lists sit above the plot, with wrapping labels and independent scrollbars.
Numbered axis ticks use an explicit dark text colour on the white plot canvas.
Selecting a structure immediately displays its calculated volume and min/mean/max dose beneath the plot; cursor values appear on a second line.
Goal markers point toward the allowed side on the current axes: `V ≤` uses `v`, `V ≥` uses `^`, `D ≤` uses `<`, and `D ≥` uses `>`.
Goal markers and labels are black by default, orange for explicit ideal/tolerance qualifiers, and red for acceptable/action qualifiers (case-insensitive).
Labels retain the source expression and qualifier.
Recommendations without a parsed point remain in the JSON for manual review.
Switching the volume axis converts percent and absolute volume using the selected structure's calculated volume.
Plot limits expand to include recommendation points.
An absolute-volume threshold larger than the selected structure can consequently appear above 100%.

Use **Open source** to check the current eviQ protocol, its prescription/fractionation, contour definitions, conditional guidance and notes.
Ideal/acceptable and optimal/mandatory recommendations remain separately labelled; both can appear in one organ/regimen entry.
Points support visual comparison and do not assign clinical pass/fail or select the appropriate recommendation for a patient.
This does not establish clinical validation of either the extracted recommendation or the reconstructed DVH.

### Catalogue format and refresh behaviour

The output is UTF-8 JSON with `schema_version`, `generated_at`, `source`, `scope` and `protocols`.
Each protocol contains its URL, title, protocol ID, version and dates when available, source SHA-256, complete OAR section text, extraction warnings and organ/regimen groups.
Each group retains its organ, expanded table-column heading, adjacent contouring notes and recommendation records.
Each record contains the original text, qualifier, `point_expression`, extraction status and either a point or `null`.
Points contain `metric` (`V` or `D`), either `dose_cgy` or `dose_percent`, `volume`, `volume_unit` (`%` or `cm3`) and `operator`.
`point_expression` records the complete metric when eviQ splits a Dx heading from its limits on following lines.
The local source snapshots retain the full protocol, including prescription, version history and references, under `<sha256>.html` in the cache directory.
The hash is of the UTF-8 encoded downloaded text.

Supported points are complete numeric `Vx Gy < y%`, `Vx Gy < y cc`, `Dx% < y Gy` and `Dx cc < y Gy` expressions, with cGy, comparison variants and selected explicit Dx-heading layouts also supported.
The generic loader also supports explicit relative-dose expressions such as `D2% <= 105%` and `V95% >= 98%`.
The eviQ extractor continues to leave relative prescription doses, mean doses, Dmax, EQD2/BED limits, ranges, conditional expressions and unfamiliar notation as text for manual review.
They are not replaced with invented coordinates.
Extraction covers the current **Organs at risk** tables, rather than historical changes, evidence tables or target prescription recommendations.
Unrecognised table layouts remain in `section_text` and produce warnings.
Discovery follows public category links, so it does not prove coverage of unlinked, restricted, retired or newly restructured content.
Inspect warnings and the parsed/manual-review counts after each run.

The updater respects `robots.txt`, uses a named user agent and spaces requests by at least one second.
Transient timeouts and server errors are retried up to three attempts with a short backoff.
Every refresh downloads current content rather than treating cached HTML as current evidence.
A download, robots or discovery-limit failure leaves the previous catalogue intact; replacement is atomic after all selected protocols have been processed.
The fresh discovery inventory replaces the old one, so protocols no longer linked are not silently retained as current.
Using `--url` deliberately replaces the output with only those selected protocols.
Keep prior catalogue files when you need a historical comparison.
The generated JSON catalogue is versioned in `src/hyperio/data/dvh/eviq.json`; full HTML source snapshots stay in the local cache and are not committed.
Use of eviQ content is subject to its [terms](https://www.eviq.org.au/terms) and [disclaimer and copyright notice](https://www.eviq.org.au/copyright).
That notice describes noncommercial reuse with attribution, exceptions for third-party material, and separate permission for commercial entities.

For one plan, the suggested filename is the plan name.
Alternatively, choose **Batch export XLSX…** and an output folder to calculate every discovered plan using the selected contour-boundary policy.
Batch failure reports and application errors open in resizable, scrollable dialogs.
Select text and use Ctrl+C (Command+C on macOS), or choose **Copy all** to copy the complete message.
The observed Unity formats in CellIrrad are supported, including older beam/studyset records, WC slices, isodose XML version 3 and `00be301e` full-grid dose.
Plans without saved `dose.1` are reported individually while other plans continue exporting.
Unity reconstruction has reference-dose consistency evidence; compare exported DVH statistics against Monaco before relying on their numerical agreement.
Each successful workbook is named `<patient ID>-<studyset>-<plan>.xlsx`.
Invalid filename characters are replaced, existing files are never overwritten, and colliding names are reported instead of exported.
A results dialog lists plans that could not be exported; other plans continue.
Results use **INFO** for successful exports, **WARN** for exports with warnings or unavailable structures, and **ERROR** for plan-level failures.
Self-intersecting contour rings are repaired for sampling by splitting edges at intersections, polygonising the resulting linework, and unioning all enclosed faces.
This filled-footprint policy fills internal loops rather than subtracting them as holes, keeps all figure-eight lobes, and preserves outer concavities; it does not use a bounding box or convex hull.
Valid rings are unchanged, and the source contour files are not modified.
Each repaired ring produces a WARN identifying the structure, WC file, record line, original geometry problem and repair policy; warnings remain in exported provenance.
This is an explicit reconstruction convention; compare affected slices and DVH statistics against Monaco to validate agreement.
If a contour has no usable area after repair, remains invalid, or fails sampling, its entire structure's DVH is omitted and the remaining structures continue calculating.
The warning identifies the structure and failure reason; invalid-polygon warnings also identify the WC file, record line and geometry problem.
The table and exports retain a `DVH unavailable` row with blank numerical results for each failed structure.
If every requested structure fails, no curves are produced and all requested structures are reported as unavailable.
For reconstruction from saved dose, unreadable CT-to-ED selection metadata, missing studyset `info`, and unsupported `info` versions are warnings because the DVH calculation does not use CT calibration.
Warnings remain visible after calculation and in batch results, spreadsheet provenance, CSV provenance JSON, and diagnostic reports.
Shared failures such as unreadable contour records, invalid slice geometry, missing dose and unclassified input diagnostics still prevent export.

Use **Export full logs…** or **Export anonymised full logs…** after an error to save a local JSON support report.
These buttons appear below the Patient set and Plan controls, and directly in batch-failure and application-error dialogs when a source has been selected.
After updating an installed copy, close and reopen the application to load the new controls.
The report collects metadata inspection diagnostics, relevant file format versions, software versions, session errors and the latest batch results without decoding dose or image arrays.
Full logs include patient/plan/structure identifiers, source paths, raw parsed metadata and error tracebacks; treat them as patient data.
Anonymised logs use generated plan/studyset/folder labels, counts, format versions and fixed diagnostic categories only.
They omit names, patient IDs, paths, raw records, timestamps and tracebacks, and withhold unrecognised error text rather than trying to scrub names from arbitrary text.
This deliberately loses some diagnostic detail; inspect the saved report before sharing it.
Reports are saved locally and are not sent automatically.

The exporter calculates the structures enabled in the saved isodose configuration.
The source can be a patient directory, its parent directory, or a ZIP containing either layout.
ZIP contents are read directly without writing an extracted patient set.
Opening the source reads only bounded plan identity headers to populate the plan selector.
Directory entries are enumerated, but unrelated image and dose files are not opened or queried for their sizes.
Full metadata validation, native dose loading and contour reading wait until **Calculate DVH** or batch export.
**Batch export XLSX…** opens a scrollable plan checklist with all plans selected by default.
Untick any plans to omit, then choose **Continue…** and select the destination folder.
**Select all** and **Clear all** change the whole checklist; at least one plan must be selected to continue.
Cancelling either dialog leaves the export unstarted.
Calculation inspects the selected plan and its linked studyset without parsing every other plan in the source.
Consequently, errors beyond the identity header are reported when that plan is calculated.
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
Unsupported required layouts, missing dose/configuration, ambiguous plan identity and critical reader diagnostics produce an error rather than a fabricated export.
Full member paths distinguish identically named plans in different patient sets.
No Monaco dose calculation is triggered, and saved dose freshness is not established.
Contour-boundary and histogram conventions remain provisional; a small OAR volume/mean residual remains in the supplied reference case.
Monaco's CI formula is unresolved, so its column remains blank.
Reconstructed criterion indicators and spreadsheet colours are not clinical approval.

The source screenshots are recorded by path and hash in `tests/fixtures/vmat-2026-10-29-ground-truth.json`.
Their raw image files remain local to the user's machine and are not application dependencies.
