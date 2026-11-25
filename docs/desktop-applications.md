# HyperIO desktop reference

Start with the [desktop quick start](../applications/README.md) for installation, screenshots and the main workflows.

## Run from the checkout

On macOS or Linux with Nix, run these commands from the repository root.

```sh
nix develop
python applications/dvh.py
python applications/override_reds.py
python applications/commissioning.py
```

The Nix shell provides Python, Tk and the optional analysis and export dependencies.
The launcher scripts can also run from a regular Python environment with the `applications` extra installed.
On Windows use `py` in place of `python` if needed.
Run `python -m tkinter` in that environment to check Tk support.

## DVH exports and diagnostics

The exporter uses the selected plan's saved `dose.1`, contours from its linked studyset, and saved DVH and isodose settings.
It calculates structures enabled in those settings and retains the saved order and repeated reference requests.
Under **Advanced…**, choose whether to include or exclude contour boundary voxels (include is the default).
The prescription entered in the plot controls display normalization and relative-dose goal overlays.
Reconstruction requires a supported native dose grid and axial contour layout. [Validation record](validation.md) · [Unity dose evidence](../reports/unity-dvh-2026-11-05.md)

- **XLSX** has **DVH Statistics** and **Provenance** sheets.
  The latter records the source path, selected plan, dose grid, sampling policy and limitations.
- **CSV** has the same data columns and writes provenance to a companion `.csv.provenance.json` file.
- **Batch XLSX** creates one workbook per selected plan as `<patient ID>-<studyset>-<plan>.xlsx`.
  It reports plan failures individually and skips collisions with existing output files.

Dose is in cGy, absolute volume is in cm³ and relative volume is in percent.
The HI is dimensionless and the CI column is left blank while the Monaco CI calculation remains unresolved.
Criterion fills display reconstructed results for the saved goal definitions.
Review the saved dose history in Monaco when dose freshness matters.

Self-intersecting contour rings may be repaired for sampling by polygonising their split edges and filling the union of the enclosed faces.
This convention fills internal loops and can change the sampled volume.
A warning identifies the structure, contour file, record line and repair.
A structure with no usable area or a sampling failure appears as `DVH unavailable` while the other structures continue.
Errors that affect the whole plan, such as missing dose or unreadable contour records, prevent that plan's export.
CT-to-ED selection issues appear as warnings because reconstructing a DVH from saved dose requires no calibration curve.

Use **Export full logs…** or **Export anonymised full logs…** to save local JSON diagnostics.
Full logs can contain patient, plan and structure identifiers, source paths, raw metadata and tracebacks.
Anonymised logs use generated labels, counts, format versions and fixed error categories.
Review the file before sharing it.

### DVH goal libraries

Select a library, protocol, prescription, and structure goal group.
Matching uses case-insensitive wildcard patterns such as `*PTV*`, which can also match derived structures.
Use **Advanced: load JSON…** to load a local catalogue.
Review the protocol source, fractionation, contour definitions and applicability before using the markers.
Recommendations without a parsed point remain as text for manual review.

Install the optional updater and refresh the local eviQ catalogue from the repository root.

```sh
python -m pip install -e '.[applications,eviq]'
hyperio-eviq-update
```

The updater writes `~/.hyperio/eviq.json` by default.
Load the result using **Advanced: load JSON…**.
The refresh fetches public protocol pages and changes the catalogue only after all selected pages have been processed.
Inspect the extraction warnings and retain older catalogues if you need to compare versions.
Plotting from a saved catalogue works offline.

Use `python scripts/update_eviq.py --help` for output, cache and protocol URL options.
To refresh the bundled snapshot, run the following from the checkout and review the diff.

```sh
python scripts/update_eviq.py --output src/hyperio/data/dvh/eviq.json --verbose
```

The [bundled catalogue](../src/hyperio/data/dvh/eviq.json) retains source URLs, protocol metadata, original recommendations, parsed points and extraction warnings.
eviQ documents its reuse terms and copyright conditions. [Terms](https://www.eviq.org.au/terms) · [Copyright](https://www.eviq.org.au/copyright)

## RED calibration and export

CT mean RED requires a head-first supine axial studyset with matching cached DICOM CT images and native contours.
The app looks for a calibration named `DICOM3.<curve name>` using the name recorded in the selected plan's studyset.
Use the file or calibration ZIP from the applicable installation.
The calculation interpolates the calibration at CT voxel centres inside the contour and uses the nearest endpoint outside the curve's HU range.

| Platform | Preferred calibration directory |
| --- | --- |
| Windows | `%LOCALAPPDATA%\HyperIO\data\cttoed` |
| macOS | `~/Library/Application Support/HyperIO/data/cttoed` |
| Linux | `$XDG_DATA_HOME/hyperio/data/cttoed` or `~/.local/share/hyperio/data/cttoed` |

Fallback directories are `~/.config/hyperio/data/cttoed` and `~/.hyperio/data/cttoed`, in that order.
**Choose calibration…** can select a file or a ZIP containing the curve.

RED presets contain exact, case-sensitive names and set matching structures to forced mode.
Manual values take precedence over the preset.
Each output tab starts from its selected input plan.
For a full copy, choose a new destination outside the source folder.
Adding named copies alongside the originals reuses the existing studysets.
The app copies companion files, including saved dose, logs and checksums.
Verify how the resulting overrides apply in Monaco and calculate fresh dose before evaluating each variant.

## Commissioning plan staging

The worksheet catalogue follows MPPG 5.b Tables 4–10 and Section 9.
Use the [plan specifications](../examples/commissioning-mppg5b-plan-set.json) to expand the case set for your machine. [Plan setup guide](mppg5b-plan-set.md)

1. Start with a copy of a native phantom patient directory named `1~<patient ID>`.
   Use phantom data without patient information, since the builder carries over image UIDs and cached image metadata.
2. Assign a template that already has the intended machine model, beam setup, aperture, SSD, MU and prescription.
   Use templates and CT-to-density tables compatible with the destination Monaco installation.
3. Enter an unused patient ID and a name in `Family^Given` format.
   Stage the new folder and copy it to the intended Monaco Installation/Clinic directory.
4. Open the staged patient in Monaco and verify the studyset, geometry, MU, prescription and calculation settings before calculating.

The builder makes a separate plan for each assigned case, using the test ID and part of the case ID in its name.
It copies the studysets, inherits beam and prescription records, and applies supplied dose grid and Monte Carlo settings when supported.
It omits inherited dose files, calculation logs and known locks.
Native status and checksum records come from the templates.
