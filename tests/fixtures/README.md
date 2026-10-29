# Review-data test fixtures

`vmat-2026-10-29-ground-truth.json` transcribes the three user-designated Monaco screenshots supplied on 29 October 2026.
The matching returned plan is `D291026AG`, linked to studyset `CT1`.
Screenshot filenames, local source paths and SHA-256 hashes retain the transcription's provenance.
The raw screenshots and native patient archive are local assets and are not required for the synthetic reader tests.

The fixture retains all visible DVH statistics, criterion definitions and displayed results, reference-dose rows, DRPs and IMRT objectives.
JSON null represents a blank UI cell, or the dash in the CBCT beam-dose cell as documented by the tests.
Repeated rows and screenshot ordering are preserved.
Native objective values are compared at the displayed decimal precision, without rounding library results in place.

The executable examples in [test_vmat_evidence.py](../test_vmat_evidence.py) show how to inspect an archive, select a plan, check diagnostics and read each collection through the public API.
Set `HYPERIO_VMAT_ARCHIVE` to a local ZIP or extracted patient directory before running them:

```sh
export HYPERIO_VMAT_ARCHIVE='/absolute/path/to/returned-plan.zip'
python3 -m pytest tests/test_vmat_evidence.py -v
```

These tests check 10 saved criterion definitions, 13 saved objective rows, two DRP records and the saved DVH sampling settings.
They do not yet independently calculate the fixture's DVH statistics, histogram reference-dose values, HI/CI values or displayed pass/fail outcomes.
Those expected values remain available for future dose-analysis tests.

For examples that need no private archive, run [test_plan_review.py](../test_plan_review.py):

```sh
python3 -m pytest tests/test_plan_review.py -v
```

Its small synthetic documents demonstrate byte-reader usage, native versus displayed units, per-target margins, provenance, unknown values and error handling.
