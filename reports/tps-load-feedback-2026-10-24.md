# User-reported TPS loading feedback, 2026-10-24

The user reported: "I tried V01 and V02 but both same thing, failed to load anything."
They suggested five slices might be needed, then requested an empty CT using the supplied example as a template, with new identifiers, 5 mm voxels, 500x500x500 mm extent and all-zero data.
The current rebuilt Batch 001 has no V01 case, so the exact installed package/case association is unresolved.
Do not silently assign this report to the current V00 or infer a minimum slice requirement.
The native load failure's cause is unknown; slice count alone has not been established as the cause.

The next candidate is a standard DICOM CT import, not another patched native studyset.
Its 100 slices remove dependence on the three-versus-five-slice hypothesis.
Both stored values and HU values are zero (slope 1 / intercept 0).
Import acceptance, save/reopen and returned native records remain pending.

## Indexed DICOM candidate outcome

The user reports that ct-002's directory can be selected but Monaco ignores its contents and does not register the CT for import.
No new importer log was supplied with this report.
The single RTDIR.dir specimen does not identify its UID fields or show the working parent/subfolder hierarchy and image filenames.
The current generated folder is flat, with CT_001.dcm through CT_100.dcm and identical .rtDir/RTDIR.dir text indices.
This layout and index semantics were hypotheses and have not been validated by Monaco.
An official Elekta conformance statement documents network reception into temporary staging, followed by application import, but does not document the depot index or folder layout.
Source: https://www.elekta.com/products/oncology-informatics/dicom-conformance-statements/documents/Focal-Monaco-Release-Focal-480-Monaco-330-Document-LEDDCMFCLMON000170.pdf (2012, Focal 4.80/Monaco 3.30; applicability to installed build unverified).
Next evidence: a directory listing around the supplied working RTDIR.dir and one associated DICOM CT file to compare the specimen UIDs and geometry against labelled DICOM tags.
Do not infer rejection of zero-valued pixels or minimum slice count from this empty-list observation.
