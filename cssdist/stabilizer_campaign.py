"""Symmetry-reduced Pauli searches with immutable, independently checked shards."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import tempfile
import time

from .audit import _read, require, require_object
from .campaign import campaign_lock, write_json
from .circuit import DetectorModel
from .circuit_run import (build_circuit, select_circuit_capacity, _checked_decision,
                          _native_receipt, _parameters, _verified_build, _verify_command,
                          source_hashes, _RECURSIVE_SOURCES)
from .code import digest, json_bytes
from .engine import memory_budget_bytes, validate_memory_bytes
from .stabilizer import StabilizerCode
from .symmetry import orbit_representatives

SCHEMA = 'qedist.stabilizer-run.v2'


def search_plan(code, use_symmetry):
    """Put one X/Y/Z root per verified qubit orbit first, preserving every column."""
    require(type(use_symmetry) is bool, 'use_symmetry must be a boolean')
    qubits = (orbit_representatives(code.n, code.symmetry_generators, code.period)
              if use_symmetry else list(range(code.n)))
    roots = [3 * q + p for q in qubits for p in range(3)]
    root_set = set(roots)
    order = roots + [i for i in range(3 * code.n) if i not in root_set]
    inverse = [0] * len(order)
    for index, original in enumerate(order):
        inverse[original] = index
    model = code.detector_model()
    if order != list(range(model.n)):
        document = dict(model.document)
        for field in ('detector_rows', 'observable_rows', 'neutral_rows', 'witnesses'):
            document[field] = [[inverse[i] for i in row] for row in document[field]]
        document['metadata'] = dict(document['metadata'],
                                    column_order='Orbit roots first, mapped by coverage.json')
        model = DetectorModel(document)
    coverage = {'schema': 'qedist.stabilizer-coverage.v1', 'use_symmetry': use_symmetry,
                'root_qubits': qubits, 'column_order': order, 'roots_required': len(roots)}
    return model, coverage


def root_ranges(count, shards):
    require(type(shards) is int and shards >= 1, 'shards must be a positive integer')
    active = min(count, shards)
    return [[count * i // active, count * (i + 1) // active] for i in range(active)]


def _snapshot(root):
    files = {p.relative_to(root).as_posix(): digest(p.read_bytes())
             for p in sorted(root.rglob('*')) if p.is_file()
             and p.name not in ('SHA256SUMS.json', '.running.lock')
             and '.tmp-' not in p.name}
    write_json(root / 'SHA256SUMS.json', {'files': files})


def _initialize(code, root, model, coverage, config, compiler, cache):
    root.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.qedist-stabilizer-', dir=root.parent) as folder:
        stage = Path(folder) / 'run'
        search = stage / 'search'
        search.mkdir(parents=True)
        code.save(stage / 'code.json')
        model.save(search / 'input.json')
        (search / 'model.txt').write_text(model.native_text())
        write_json(search / 'coverage.json', coverage)
        write_json(search / 'config.json', config)
        started = time.monotonic()
        build_circuit(search / 'engine', compiler=compiler, cache=cache,
                      large_capacity=config['large_capacity'])
        elapsed = time.monotonic() - started
        files = {p.relative_to(stage).as_posix(): digest(p.read_bytes())
                 for p in stage.rglob('*') if p.is_file()}
        write_json(stage / 'stabilizer_run.json', {
            'schema': SCHEMA, 'conversion': 'stabilizer_orbit_columns_v1',
            'code_sha256': code.fingerprint, 'model_sha256': model.fingerprint,
            'build_seconds': elapsed, 'files': files})
        _snapshot(stage)
        require(not root.exists(), 'Output directory appeared during initialization')
        stage.rename(root)


def _load(root):
    metadata = require_object(json.loads(_read(root / 'stabilizer_run.json', root)), 'Stabilizer run')
    require(metadata.get('schema') == SCHEMA, 'Unsupported stabilizer campaign schema')
    files = require_object(metadata.get('files'), 'Immutable files')
    expected_files = {'code.json', 'search/input.json', 'search/model.txt', 'search/coverage.json',
                      'search/config.json', 'search/engine/build.json', 'search/engine/exact',
                      'search/engine/LICENSE.txt'}
    expected_files.update('search/engine/' + name for name in source_hashes())
    require(set(files) == expected_files, 'Immutable stabilizer file inventory mismatch')
    for name, expected in files.items():
        require(digest(_read(root / name, root)) == expected, 'Stabilizer file changed: ' + name)
    code = StabilizerCode(json.loads(_read(root / 'code.json', root)))
    config = require_object(json.loads(_read(root / 'search/config.json', root)), 'Search configuration')
    model, coverage = search_plan(code, config['use_symmetry'])
    expected_config = {
        'schema': 'qedist.stabilizer-search.v2', 'cutoff': config['cutoff'],
        'shards': config['shards'], 'weighted': config['weighted'], 'neutral': config['neutral'],
        'use_symmetry': config['use_symmetry'], 'large_capacity': config['large_capacity'],
        'repair_depth': 8, 'even_repair_cap': 4,
        'root_ranges': root_ranges(coverage['roots_required'], config['shards'])}
    require(config == expected_config, 'Stabilizer search configuration mismatch')
    _parameters(config['cutoff'], 1.0, 0, config['weighted'], config['neutral'])
    require(type(config['large_capacity']) is bool, 'Invalid capacity setting')
    require(coverage == json.loads(_read(root / 'search/coverage.json', root)),
            'Stabilizer orbit coverage mismatch')
    require(model.document == json.loads(_read(root / 'search/input.json', root)),
            'Binary model differs from the Pauli expansion')
    require(model.native_text().encode() == _read(root / 'search/model.txt', root),
            'Native input differs from the Pauli expansion')
    require(metadata['conversion'] == 'stabilizer_orbit_columns_v1'
            and metadata['code_sha256'] == code.fingerprint
            and metadata['model_sha256'] == model.fingerprint, 'Stabilizer conversion mismatch')
    build = _verified_build(root / 'search')
    require(config['large_capacity'] == (build['identity']['source_sha256'] != _RECURSIVE_SOURCES),
            'Capacity setting differs from the saved engine')
    select_circuit_capacity(model, config['cutoff'], config['large_capacity'])
    require(type(metadata['build_seconds']) in (int, float)
            and 0 <= metadata['build_seconds'] < float('inf'), 'Invalid build time')
    return code, model, coverage, config, metadata, build


def _attempt(root, config, model, build, shard, seconds, node_cap, memory_bytes):
    folder = root / 'search/jobs' / f'{shard:06d}'
    folder.mkdir(parents=True, exist_ok=True)
    previous = [int(p.stem.split('-')[-1]) for p in folder.glob('attempt-*.json')]
    destination = folder / f'attempt-{max(previous, default=0) + 1:06d}.json'
    limits = {'seconds': float(seconds), 'node_cap': node_cap, 'memory_bytes': memory_bytes}
    native_config = dict(config, **limits, original_run_directory=str(root / 'search'))
    begin, end = config['root_ranges'][shard]
    receipt = _native_receipt(root / 'search', root / 'search/model.txt', native_config,
                              build, 0.0, time.monotonic(), root_end=end, root_begin=begin)
    record = {'schema': 'qedist.stabilizer-attempt.v1', 'shard': shard, 'limits': limits,
              'run_directory': str(root / 'search'), 'model_sha256': model.fingerprint,
              'config_sha256': digest(json_bytes(config)), 'receipt': receipt,
              'receipt_sha256': digest(json_bytes(receipt))}
    write_json(destination, record)
    return destination


def _read_attempt(root, path, shard, model, config, build):
    record = require_object(json.loads(_read(path, root)), 'Shard attempt')
    require(record.get('schema') == 'qedist.stabilizer-attempt.v1'
            and type(record['shard']) is int and record['shard'] == shard
            and record['model_sha256'] == model.fingerprint
            and record['config_sha256'] == digest(json_bytes(config)), 'Shard attempt identity mismatch')
    limits = require_object(record['limits'], 'Attempt limits')
    require(set(limits) == {'seconds', 'node_cap', 'memory_bytes'}, 'Unsupported attempt limits')
    _parameters(config['cutoff'], limits['seconds'], limits['node_cap'], config['weighted'], config['neutral'])
    validate_memory_bytes(limits['memory_bytes'])
    require(config['large_capacity'] or limits['memory_bytes'] is None,
            'The saved engine does not support memory budgets')
    receipt = require_object(record['receipt'], 'Native receipt')
    require(digest(json_bytes(receipt)) == record['receipt_sha256'], 'Native receipt checksum mismatch')
    native_config = dict(config, **limits, original_run_directory=record['run_directory'])
    begin, end = config['root_ranges'][shard]
    _verify_command(native_config, receipt, build, root_end=end, root_begin=begin)
    status, witnesses, terminal = _checked_decision(model, native_config, receipt, end, begin)
    within = (status in ('EXCLUDED', 'WITNESS_FOUND')
              and receipt['timing']['end_to_end_seconds'] <= limits['seconds'])
    return status, witnesses, terminal, receipt['timing'], within


def _result(root, loaded):
    code, model, coverage, config, metadata, build = loaded
    order = coverage['column_order']
    candidates = [code.column_witness([order[q] for q in row])
                  for row in model.document['witnesses']]
    jobs, checked, terminals = [], [], []
    totals = {key: 0.0 for key in ('preparation_seconds', 'process_seconds', 'end_to_end_seconds')}
    all_nodes_known = True
    nodes = 0
    for shard, (begin, end) in enumerate(config['root_ranges']):
        paths = sorted((root / 'search/jobs' / f'{shard:06d}').glob('attempt-*.json'))
        status, within = 'PENDING', False
        for path in paths:
            found, witnesses, terminal, timing, on_budget = _read_attempt(
                root, path, shard, model, config, build)
            terminals.append(terminal)
            checked.extend(witnesses)
            for witness in witnesses:
                candidates.append(code.column_witness([order[q] for q in witness['support']]))
            for key in totals:
                totals[key] += timing[key]
            if terminal and 'nodes' in terminal:
                nodes += terminal['nodes']
            else:
                all_nodes_known = False
            if found in ('EXCLUDED', 'WITNESS_FOUND'):
                require(status not in ('EXCLUDED', 'WITNESS_FOUND') or status == found,
                        'Contradictory decisions for a shard')
                status, within = found, on_budget
            elif status == 'PENDING':
                status = 'INCOMPLETE'
        jobs.append({'shard': shard, 'root_begin': begin, 'root_end': end, 'status': status,
                     'attempts': len(paths), 'completed_within_budget': within})
    excluded = all(job['status'] == 'EXCLUDED' for job in jobs)
    witnessed = any(job['status'] == 'WITNESS_FOUND' for job in jobs)
    lower = config['cutoff'] + 1 if excluded else 1
    best = min(candidates, key=lambda word: (word['weight'], word['pauli']))
    upper = best['weight']
    require(lower <= upper, 'Pauli witness contradicts completed shard exclusions')
    search_status = 'INCOMPLETE'
    if witnessed:
        search_status = 'WITNESS_FOUND'
    if excluded:
        search_status = 'EXCLUDED'
    status = search_status
    if excluded:
        status = 'CERTIFIED_INTERVAL'
    if lower == upper:
        status = 'EXACT_DISTANCE'
    within = all(job['completed_within_budget'] for job in jobs)
    timing = dict(totals, build_seconds_excluded=metadata['build_seconds'],
                  scope='Sum of recorded attempt times across workers; excludes conversion and build')
    result = {'schema': 'qedist.stabilizer-result.v1', 'status': status, 'metric': 'pauli_weight',
              'n': code.n, 'k': code.k, 'code_sha256': code.fingerprint,
              'model_sha256': model.fingerprint, 'cutoff': config['cutoff'],
              'distance_lower_bound': lower, 'distance_upper_bound': upper,
              'exact_distance': lower if lower == upper else None, 'witness': best,
              'search_status': search_status, 'search_timing': timing,
              'completed_within_search_budget': within,
              'roots_required': coverage['roots_required'], 'full_pauli_roots': model.n,
              'roots_excluded': sum(job['root_end'] - job['root_begin'] for job in jobs
                                    if job['status'] == 'EXCLUDED'),
              'jobs': jobs, 'nodes_in_recorded_attempts': nodes if all_nodes_known else None}
    terminal = terminals[-1] if len(jobs) == 1 and terminals else None
    if terminal and terminal.get('event') == 'resource_limit':
        result['resource_limit'] = terminal
    search = {'schema': 'qedist.stabilizer-shards.v1', 'status': search_status,
              'terminal': terminal, 'checked_witnesses': checked, 'jobs': jobs,
              'roots_required': coverage['roots_required'], 'timing': timing}
    return result, search


def audit_campaign(root, *, check_summary=True):
    root = Path(root).resolve()
    loaded = _load(root)
    manifest = require_object(json.loads(_read(root / 'SHA256SUMS.json', root)), 'Manifest')
    hashes = require_object(manifest.get('files'), 'Manifest files')
    for name, expected in hashes.items():
        require(type(name) is str and not Path(name).is_absolute()
                and Path(name).as_posix() == name and '..' not in Path(name).parts,
                'Unsafe stabilizer manifest path')
        if not check_summary and name in ('result.json', 'search/result.json'):
            continue
        require(digest(_read(root / name, root)) == expected, 'Stabilizer checksum mismatch: ' + name)
    result, search = _result(root, loaded)
    if check_summary:
        require(result == json.loads(_read(root / 'result.json', root)),
                'Stabilizer conclusion differs from the checked evidence')
        require(search == json.loads(_read(root / 'search/result.json', root)),
                'Stabilizer shard summary differs from the checked evidence')
    return result


def certify_campaign(code, output, *, cutoff, seconds=30.0, node_cap=2**64 - 1,
                     weighted=None, neutral=None, compiler='c++', cache=None,
                     memory_mib=None, large_capacity=None, use_symmetry=None,
                     shards=None, workers=1, resume=False):
    require(isinstance(code, StabilizerCode), 'Expected a validated StabilizerCode')
    require(type(workers) is int and workers >= 1, 'workers must be a positive integer')
    require(type(resume) is bool, 'resume must be a boolean')
    for name, value in [('weighted', weighted), ('neutral', neutral), ('use_symmetry', use_symmetry),
                        ('large_capacity', large_capacity)]:
        require(value is None or type(value) is bool, name + ' must be a boolean or None')
    code = StabilizerCode(code.document)
    root = Path(output).resolve()
    memory_bytes = memory_budget_bytes(memory_mib)
    if resume:
        require((root / 'stabilizer_run.json').is_file(), 'Cannot resume a missing stabilizer campaign')
        saved = require_object(json.loads(_read(root / 'stabilizer_run.json', root)), 'Stabilizer run')
        require(saved.get('schema') == SCHEMA,
                'This single-run record predates shard resume; start a new campaign with the same input')
        existing = require_object(json.loads(_read(root / 'search/config.json', root)), 'Search configuration')
    else:
        require(not root.exists(), 'Output directory already exists; use --resume or choose a new directory')
        existing = {'weighted': True, 'neutral': True, 'use_symmetry': True, 'shards': 1}
    weighted = existing['weighted'] if weighted is None else weighted
    neutral = existing['neutral'] if neutral is None else neutral
    use_symmetry = existing['use_symmetry'] if use_symmetry is None else use_symmetry
    shards = existing['shards'] if shards is None else shards
    if resume and large_capacity is None:
        large_capacity = existing['large_capacity']
    _parameters(cutoff, seconds, node_cap, weighted, neutral)
    model, coverage = search_plan(code, use_symmetry)
    capacity = select_circuit_capacity(model, cutoff, large_capacity, memory_bytes)
    config = {'schema': 'qedist.stabilizer-search.v2', 'cutoff': cutoff, 'weighted': weighted,
              'neutral': neutral, 'use_symmetry': use_symmetry, 'shards': shards,
              'large_capacity': capacity, 'repair_depth': 8, 'even_repair_cap': 4,
              'root_ranges': root_ranges(coverage['roots_required'], shards)}
    if not resume:
        _initialize(code, root, model, coverage, config, compiler, cache)
    with campaign_lock(root):
        loaded = _load(root)
        require(loaded[0].fingerprint == code.fingerprint and loaded[3] == config,
                'Resume requires the saved input, cutoff, shards, symmetry, pruning and engine')
        prior = audit_campaign(root, check_summary=False)
        todo = [job['shard'] for job in prior['jobs'] if job['status'] not in ('EXCLUDED', 'WITNESS_FOUND')]
        build = loaded[-1]
        with ThreadPoolExecutor(max_workers=workers) as pool:
            pending = [pool.submit(_attempt, root, config, model, build, shard, seconds, node_cap, memory_bytes)
                       for shard in todo]
            for future in as_completed(pending):
                path = future.result()
                shard = int(path.parent.name)
                _read_attempt(root, path, shard, model, config, build)
        result, search = _result(root, loaded)
        write_json(root / 'search/result.json', search)
        write_json(root / 'result.json', result)
        _snapshot(root)
        return audit_campaign(root)
