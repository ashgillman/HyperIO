# Depot layout established from Monthly QC.zip

The complete working archive contains 130 CT datasets and two text indices in one patient directory.
Every CT_<SOPInstanceUID> filename agrees with its DICOM SOPInstanceUID.
CT_<SeriesInstanceUID>.dir contains the ordered SOPInstanceUID list and references every image exactly once.
RTDIR.dir line 4 matches SeriesInstanceUID, line 5 matches StudyInstanceUID, line 6 matches StudyID, line 7 matches PatientName and line 8 matches FrameOfReferenceUID across all 130 headers.
Lines 9-11 and 12-17 match ImagePositionPatient and ImageOrientationPatient of the first indexed CT.
The CT datasets are implicit-VR little-endian without Part 10 preamble or file meta.

The ct-002 writer had reversed lines 4/5, substituted SeriesDescription for StudyID, omitted the per-series SOP list and used arbitrary CT filenames with .dcm suffix.
It also used Part 10 explicit-VR images rather than the encoding observed in this depot.
The complete specimen supports correcting those relationships; generated Monaco import acceptance is still pending.

ct-003 reproduces the observed relationships and encoding for all 100 generated images.
Its CT dataset values, pixel bytes, geometry and entity identifiers are unchanged from ct-001.
Its final ZIP was independently checked by the same fixture relationship inspector and contains exactly one 100-image depot series.
Source/archive hashes and scope are in monthly-qc-depot-layout.json; output hashes are in the candidate manifest.
