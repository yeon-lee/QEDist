"""Certified unit-cost detector-coordinate projection.

The retained columns are actual source columns. Every source column projects to
one retained column or zero, preserving ALL observable bits. Thus projection
cannot increase fault count, and lifting a reduced solution preserves its count.
These two maps prove equality of the additive model's minimum fault distance.
Detector basis labels are only a way to propose a subset, never a proof premise.
"""
import copy
import json
from pathlib import Path

from .algebra import support, vector
from .circuit import DetectorModel, METRIC, _stim
from .code import digest, json_bytes

SCHEMA = 'qedist.circuit_sector_reduction.v1'


def _indices(values, bound, name):
    if not isinstance(values, list) or any(type(x) is not int or not 0 <= x < bound for x in values):
        raise ValueError(f'{name} must be a list of in-range integer indices')
    if len(set(values)) != len(values):
        raise ValueError(f'{name} contains duplicate indices')
    return values


def _project_signature(signature, kept, num_detectors):
    result = (signature >> num_detectors) << len(kept)
    for new, old in enumerate(kept):
        result |= ((signature >> old) & 1) << new
    return result


def _rows(columns, count):
    result = [[] for _ in range(count)]
    for column, signature in enumerate(columns):
        while signature:
            bit = signature & -signature
            result[bit.bit_length() - 1].append(column)
            signature ^= bit
    return result


def project_fault_support(indices, source_to_reduced):
    """Map a binary support, cancelling repeated projected columns modulo two."""
    _indices(indices, len(source_to_reduced), 'source support')
    result = set()
    for old in indices:
        new = source_to_reduced[old]
        if new is not None:
            if type(new) is not int or new < 0:
                raise ValueError('Invalid source-to-reduced map')
            result.symmetric_difference_update([new])
    return sorted(result)


def lift_reduced_witness(indices, certificate, source=None, reduced=None):
    """Lift via actual retained columns; optionally validate the logical witness.

    Call verify_sector_reduction first when consuming an untrusted certificate.
    """
    representatives = certificate['reduced_to_source']
    _indices(indices, len(representatives), 'reduced support')
    result = sorted(representatives[j] for j in indices)
    if len(set(result)) != len(result):
        raise ValueError('Lift is not injective')
    if source is not None:
        source.check_witness(result)
    if reduced is not None:
        reduced.check_witness(indices)
    return result


def reduce_detector_sector(model, kept_detectors, *, selection_metadata=None):
    """Return (reduced DetectorModel, independently replayable certificate).

    Reject a projection unless EVERY source effect maps to zero or an existing
    full effect supported on kept detectors. Zero projected columns are removed;
    duplicate retained signatures use their first original representative.
    """
    if not isinstance(kept_detectors, (list, tuple)):
        raise ValueError('kept_detectors must be a list or tuple of integer indices')
    kept = sorted(_indices(list(kept_detectors), len(model.detectors), 'kept_detectors'))
    columns = model.columns()
    dmask = (1 << len(model.detectors)) - 1
    kept_mask = sum(1 << d for d in kept)
    removed_mask = dmask ^ kept_mask
    signature_to_new, representatives, reduced_columns = {}, [], []
    for old, signature in enumerate(columns):
        if not signature or signature & removed_mask:
            continue
        projected = _project_signature(signature, kept, len(model.detectors))
        if projected not in signature_to_new:
            signature_to_new[projected] = len(representatives)
            representatives.append(old)
            reduced_columns.append(projected)
    mapping, failures = [], []
    for old, signature in enumerate(columns):
        projected = _project_signature(signature, kept, len(model.detectors))
        if not projected:
            mapping.append(None)
        elif projected in signature_to_new:
            mapping.append(signature_to_new[projected])
        else:
            failures.append(old)
    if failures:
        raise ValueError(f'Projection is not closed: {len(failures)} source columns lack a retained representative; first indices {failures[:8]}')
    if not representatives:
        raise ValueError('Projection leaves no nonzero fault effects; empty models are not supported')
    rows = _rows(reduced_columns, len(kept) + len(model.observables))
    mapped_neutrals = [project_fault_support(support(row), mapping) for row in model.neutrals]
    neutral_rows = sorted({tuple(row) for row in mapped_neutrals if row}, key=lambda row: (len(row), row))
    witnesses = [project_fault_support(support(row), mapping) for row in model.witnesses]
    metadata = copy.deepcopy(model.document.get('metadata', {}))
    # Event descriptions refer to source coordinates; preserve them only there.
    metadata.pop('events', None)
    metadata['sector_reduction'] = {
        'source_fingerprint': model.fingerprint, 'kept_detectors': kept,
        'selection': selection_metadata or {'method': 'explicit_detector_indices'},
        'proof': 'Every original signature projects to zero or one actual retained source signature; all observable bits are retained.',
        'distance_preserved': True,
        'scope': 'Minimum unit-count distance for the supplied annotated observables, not probabilities or decoder failure rates.'}
    reduced = DetectorModel.from_sparse(len(representatives), rows[:len(kept)], rows[len(kept):],
                neutral_rows=[list(r) for r in neutral_rows], witnesses=witnesses, metadata=metadata)
    neutral_indices = {row: i for i, row in enumerate(neutral_rows)}
    certificate = {
        'schema': SCHEMA, 'metric': METRIC,
        'source_fingerprint': model.fingerprint, 'reduced_fingerprint': reduced.fingerprint,
        'kept_detectors': kept, 'source_to_reduced': mapping, 'reduced_to_source': representatives,
        'source_neutral_to_reduced': [neutral_indices[tuple(row)] if row else None for row in mapped_neutrals],
        'projected_witnesses': witnesses,
        'selection': selection_metadata or {'method': 'explicit_detector_indices'},
        'proof_obligations': ['all observable coordinates unchanged', 'projection sends every source column to zero or one retained column',
                              'each retained column lifts to an identical original column with zero removed detectors',
                              'neutral supports and witness supports mapped modulo two']}
    verify_sector_reduction(model, reduced, certificate)
    return reduced, certificate


def verify_sector_reduction(source, reduced, certificate):
    """Check the full matrix/map certificate without trusting detector labels."""
    if not isinstance(certificate, dict) or certificate.get('schema') != SCHEMA:
        raise ValueError('Unknown sector-reduction certificate schema')
    if certificate.get('metric') != METRIC or source.document['metric'] != METRIC or reduced.document['metric'] != METRIC:
        raise ValueError('Sector reduction only certifies unit-cost fault count')
    if certificate.get('source_fingerprint') != source.fingerprint or certificate.get('reduced_fingerprint') != reduced.fingerprint:
        raise ValueError('Source or reduced model fingerprint mismatch')
    kept = _indices(certificate.get('kept_detectors'), len(source.detectors), 'kept_detectors')
    if kept != sorted(kept) or len(reduced.detectors) != len(kept) or len(reduced.observables) != len(source.observables):
        raise ValueError('Detector or observable dimensions changed incorrectly')
    mapping, representatives = certificate.get('source_to_reduced'), certificate.get('reduced_to_source')
    if not isinstance(mapping, list) or len(mapping) != source.n or any(x is not None and (type(x) is not int or not 0 <= x < reduced.n) for x in mapping):
        raise ValueError('Invalid source-to-reduced column map')
    _indices(representatives, source.n, 'reduced_to_source')
    if len(representatives) != reduced.n:
        raise ValueError('Incorrect number of retained representatives')
    original, compact = source.columns(), reduced.columns()
    if 0 in compact or len(set(compact)) != reduced.n:
        raise ValueError('Reduced signatures must be nonzero and distinct')
    removed_mask = ((1 << len(source.detectors)) - 1) ^ sum(1 << d for d in kept)
    for new, old in enumerate(representatives):
        if original[old] & removed_mask or _project_signature(original[old], kept, len(source.detectors)) != compact[new] or mapping[old] != new:
            raise ValueError(f'Retained column {new} does not lift to its original effect')
    for old, new in enumerate(mapping):
        projected = _project_signature(original[old], kept, len(source.detectors))
        if projected != (0 if new is None else compact[new]):
            raise ValueError(f'Projection map invalid at source column {old}')
    neutral_map = certificate.get('source_neutral_to_reduced')
    if not isinstance(neutral_map, list) or len(neutral_map) != len(source.neutrals):
        raise ValueError('Invalid neutral-relation map length')
    expected_neutrals = set()
    for old, new in enumerate(neutral_map):
        mapped = project_fault_support(support(source.neutrals[old]), mapping)
        if not mapped:
            if new is not None:
                raise ValueError('Zero projected neutral must map to null')
        else:
            if type(new) is not int or not 0 <= new < len(reduced.neutrals) or mapped != support(reduced.neutrals[new]):
                raise ValueError('Neutral-relation map does not match projected support')
            expected_neutrals.add(tuple(mapped))
    if expected_neutrals != {tuple(support(row)) for row in reduced.neutrals} or len(expected_neutrals) != len(reduced.neutrals):
        raise ValueError('Reduced neutral relations are not exactly the deduplicated images')
    expected_witnesses = [project_fault_support(support(row), mapping) for row in source.witnesses]
    if certificate.get('projected_witnesses') != expected_witnesses or reduced.document['witnesses'] != expected_witnesses:
        raise ValueError('Witness projection mismatch')
    for before, after in zip(source.witnesses, expected_witnesses):
        reduced.check_witness(after)
        if len(after) > before.bit_count():
            raise ValueError('Projection increased witness fault count')
    return {'status': 'VERIFIED', 'distance_preserved': True, 'metric': METRIC,
            'source_faults': source.n, 'reduced_faults': reduced.n,
            'source_detectors': len(source.detectors), 'reduced_detectors': len(reduced.detectors),
            'observables_preserved': len(source.observables),
            'zero_projected_columns': sum(x is None for x in mapping),
            'source_neutrals': len(source.neutrals), 'reduced_neutrals': len(reduced.neutrals),
            'source_witnesses': len(source.witnesses)}


def reduce_stim_sector(model, circuit_path, *, basis='auto'):
    """Propose Chromobius detector basis 0 (X) or 1 (Z), then prove closure.

    The fourth detector coordinate must be an integer in 0..5; coordinate//3
    labels the detector basis, not the fault Pauli (Z detectors respond to X
    faults in a CSS memory circuit). No observable is discarded.
    In auto mode choose the smallest certified model, breaking ties X then Z.
    """
    if basis not in ('auto', 'X', 'Z'):
        raise ValueError('basis must be auto, X, or Z')
    path = Path(circuit_path)
    raw = path.read_bytes()
    circuit = _stim().Circuit(raw.decode())
    if circuit.num_detectors != len(model.detectors):
        raise ValueError('Stim circuit and model have different detector counts')
    coordinates = circuit.get_detector_coordinates()
    groups = {0: [], 1: []}
    for d in range(circuit.num_detectors):
        c = coordinates.get(d, [])
        if len(c) < 4 or not c[3].is_integer() or not 0 <= c[3] <= 5:
            raise ValueError(f'Detector {d} lacks a valid Chromobius fourth coordinate (0..5)')
        groups[int(c[3]) // 3].append(d)
    candidates, failures = [], {}
    for name in ('X', 'Z') if basis == 'auto' else (basis,):
        try:
            candidates.append(reduce_detector_sector(model, groups[int(name == 'Z')], selection_metadata={
                'method': 'chromobius_fourth_coordinate_proposal', 'basis': name,
                'coordinate_rule': f'int(detector_coordinate[3]) // 3 == {int(name == "Z")}',
                'circuit_sha256': digest(raw), 'labels_are_not_proof_premises': True}))
        except ValueError as exc:
            failures[name] = str(exc)
    if not candidates:
        raise ValueError('No certified detector sector: ' + json.dumps(failures, sort_keys=True))
    return min(candidates, key=lambda result: result[0].n)
