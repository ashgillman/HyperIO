# Successful zero CT import and returned native studyset

The user confirmed import and supplied 1~zzzInputOutputAG2.zip after appending 2 to the patient ID to avoid overwriting other data.
The source archive is retained unchanged at reference/native-zero-ct/1~zzzInputOutputAG2.zip.
Its SHA-256 is 08d4efd97e506d0192fb3432fc08f1dc3efc6f61165c0d658169c6f6136b9ef4.

The returned native patient is zzzInputOutputAG2, name zzPHYS^Ash, with studyset CT1.
It contains 100 native CT slices, 100 WC files and 100 cached DICOM images.
Every cached DICOM dataset value agrees with the generated source dataset, including pixel bytes, geometry and all image/study/series/frame identifiers.
The cached DICOM PatientID remains zzzInputOutputAG, while the native patient directory, later demographic ID line and studyset reference use zzzInputOutputAG2.
The demographic contains both IDs; no returned identity records were rewritten.

The image matrix is 100x100x100, with 5 mm isotropic spacing and 500 mm extent between outer voxel edges.
All cached DICOM pixels and interpreted HU values are zero.
Native CT headers agree with the corresponding cached DICOM matrices, in-plane spacing, positions and SOP Instance UIDs.
The native slice index lists 100 matching CT files separated by 5 mm, from -352 to -847 mm in descending order.
The native compressed pixel payloads were retained but not interpreted independently.

Monaco selected CT1 as the studyset name and saved the CT-to-ED selection ExtendedSep21.
The selected conversion table contents are not included; no material/dose behavior is inferred.
The WC headers have zero geometry counts and the archive has no plan.
This confirms the generated CT depot's import path for this case, not native plan generation or dose calculation.
Explicit close/reopen, UI cursor readings and Monaco build remain unreported.

See zero-ct-import-roundtrip.json for structured results and the case REVIEW.md for the updated human review record.

## What this explains about the earlier native-plan failure

The retained direct-native batch contains exactly three CT slices per case, with info count 3,0,0.
The supplied help topic eww1554753273916.htm states that studysets with fewer than five cross-sections will not open.
That gives a documented reason for the three-slice control to fail before any plan-setting edit could be assessed.
It is a strong explanation, not an established sole cause: the failed native load has no diagnostic log tied unambiguously to its exact case, and the cropped fixture retained unverified plan/grid/status records.
The returned 100-slice CT1 has no plan, so it does not establish native plan-writer acceptance.
The RTDIR/series-list/naming errors explain later DICOM discovery failures and should not be substituted as the cause of a native patient-folder load failure.
The successful return also demonstrates that original cached DICOM PatientID and the locally selected native PatientID can differ in this workflow.
