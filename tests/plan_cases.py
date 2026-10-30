"""Data-only reference-plan registry used by the generic integration examples.

Archives stay local. A case names a source environment variable and optionally
an ignored fallback path; its GT and calculation options are ordinary JSON.
Adding a case therefore does not require a new test function or numeric waiver.
"""
from dataclasses import dataclass
import json
import os
from pathlib import Path

from hyperio import ComparisonPolicy


@dataclass(frozen=True)
class PlanCase:
    id: str
    plan_name: str
    source_environment: str | None
    source_fallback: Path | None
    reference_path: Path
    reference: dict
    calculation_options: dict

    def resolve_source(self, environment=None):
        """An explicit but missing source is an error; absent private data can skip."""
        environment = os.environ if environment is None else environment
        selected = environment.get(self.source_environment) if self.source_environment else None
        if selected:
            path = Path(selected).expanduser().resolve()
            if not path.exists():
                raise FileNotFoundError(f'{self.id}: configured source does not exist: {path}')
            return path
        return self.source_fallback if self.source_fallback and self.source_fallback.exists() else None


@dataclass(frozen=True)
class PlanLibrary:
    policies: dict
    cases: tuple[PlanCase, ...]


def load_plan_library(path):
    """Load registry-relative paths and reject ambiguous case identities."""
    path = Path(path).resolve()
    document = json.loads(path.read_text())
    if document.get('schema_version') != 1:
        raise ValueError('unsupported plan-library schema')
    policies = {unit: ComparisonPolicy(unit=unit, **settings)
                for unit, settings in document['comparison_policies'].items()}
    cases, seen = [], set()
    for record in document['cases']:
        if set(record) - {'id', 'description', 'plan_name', 'source', 'ground_truth', 'calculation_options'}:
            raise ValueError('unsupported case fields; numerical policies belong to the shared registry')
        identity = record['id']
        if not isinstance(identity, str) or not identity.strip() or identity in seen:
            raise ValueError(f'duplicate or invalid plan-library case id: {identity!r}')
        seen.add(identity)
        source = record['source']
        source_environment, fallback = source.get('environment'), source.get('path')
        if not source_environment and not fallback:
            raise ValueError(f'{identity}: specify a source environment or path')
        reference_path = (path.parent / record['ground_truth']).resolve()
        reference = json.loads(reference_path.read_text())
        plan_name = record['plan_name']
        if reference.get('plan', {}).get('name', plan_name) != plan_name:
            raise ValueError(f'{identity}: plan name disagrees with ground truth')
        options = record.get('calculation_options', {})
        if not isinstance(options, dict) or set(options) - {'structures', 'boundary', 'include_conformity', 'max_samples'}:
            raise ValueError(f'{identity}: unsupported calculation options')
        cases.append(PlanCase(identity, plan_name, source_environment,
                              (path.parent / fallback).resolve() if fallback else None,
                              reference_path, reference, options))
    if not cases:
        raise ValueError('plan library must contain at least one case')
    return PlanLibrary(policies, tuple(cases))
