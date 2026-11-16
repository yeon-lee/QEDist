"""General Pauli-distance searches with independently audited model conversion."""
import json
from pathlib import Path

from .audit import _read, require, require_object
from .circuit import DetectorModel
from .circuit_run import audit_circuit
from .code import digest, json_bytes
from .stabilizer import StabilizerCode


def _conclusion(code, model, search):
    logicals = [code.column_witness(s) for s in model.document['witnesses']]
    logicals.extend(code.column_witness(w['support']) for w in search['checked_witnesses'])
    best = min(logicals, key=lambda w: (w['weight'], w['pauli']))
    lower = search['distance_lower_bound'] or 1
    upper = best['weight']
    require(lower <= upper, 'Pauli witness contradicts the completed binary exclusion')
    exact = lower == upper
    status = search['status']
    if exact:
        status = 'EXACT_DISTANCE'
    elif status == 'EXCLUDED':
        status = 'CERTIFIED_INTERVAL'
    result = {'schema': 'qedist.stabilizer-result.v1', 'status': status,
            'metric': 'pauli_weight', 'n': code.n, 'k': code.k,
            'code_sha256': code.fingerprint, 'model_sha256': model.fingerprint,
            'cutoff': search['cutoff'], 'distance_lower_bound': lower,
            'distance_upper_bound': upper, 'exact_distance': lower if exact else None,
            'witness': best, 'search_status': search['status'],
            'search_timing': search['timing'],
            'completed_within_search_budget': search['completed_within_budget']}
    terminal = search.get('terminal') or {}
    if terminal.get('event') == 'resource_limit':
        result['resource_limit'] = terminal
    return result


def certify_stabilizer(code, output, *, cutoff, seconds=30.0, node_cap=2**64 - 1,
                      weighted=None, neutral=None, compiler='c++', cache=None,
                      memory_mib=None, large_capacity=None, use_symmetry=None,
                      shards=None, workers=1, resume=False):
    """Run verified Pauli-orbit shards, preserving their settings on resume."""
    from .stabilizer_campaign import certify_campaign
    return certify_campaign(code, output, cutoff=cutoff, seconds=seconds, node_cap=node_cap,
                            weighted=weighted, neutral=neutral, compiler=compiler, cache=cache,
                            memory_mib=memory_mib, large_capacity=large_capacity,
                            use_symmetry=use_symmetry, shards=shards, workers=workers, resume=resume)


def audit_stabilizer(output):
    """Rebuild the Pauli expansion and audit the source-bound binary search."""
    root = Path(output).resolve()
    try:
        metadata = require_object(json.loads(_read(root / 'stabilizer_run.json', root)), 'Stabilizer run')
        if metadata.get('schema') == 'qedist.stabilizer-run.v2':
            from .stabilizer_campaign import audit_campaign
            return audit_campaign(root)
        manifest = require_object(json.loads(_read(root / 'SHA256SUMS.json', root)), 'Manifest')
        hashes = require_object(manifest.get('files'), 'Manifest files')
        required = {'code.json', 'stabilizer_run.json', 'result.json', 'search/SHA256SUMS.json'}
        require(required <= set(hashes), 'Stabilizer manifest omits required files')
        for name, expected in hashes.items():
            require(type(name) is str and not Path(name).is_absolute()
                    and Path(name).as_posix() == name and '..' not in Path(name).parts,
                    'Unsafe stabilizer manifest path')
            require(digest(_read(root / name, root)) == expected, 'Stabilizer checksum mismatch: ' + name)
        code = StabilizerCode(json.loads(_read(root / 'code.json', root)))
        model = code.detector_model()
        metadata = json.loads(_read(root / 'stabilizer_run.json', root))
        require(metadata == {'schema': 'qedist.stabilizer-run.v1',
                             'conversion': 'stabilizer_pauli_columns_v1',
                             'code_sha256': code.fingerprint, 'model_sha256': model.fingerprint},
                'Stabilizer conversion metadata mismatch')
        recorded = DetectorModel(json.loads(_read(root / 'search/input.json', root)))
        require(recorded.document == model.document, 'Binary model differs from the Pauli expansion')
        result = _conclusion(code, model, audit_circuit(root / 'search'))
        require(result == json.loads(_read(root / 'result.json', root)),
                'Stabilizer conclusion differs from the checked evidence')
        return result
    except (KeyError, TypeError, IndexError, AttributeError) as exc:
        raise ValueError('Malformed stabilizer execution metadata: ' + str(exc)) from exc
