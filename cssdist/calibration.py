"""Bounded root sampling for runtime planning, separate from distance certification.

An incomplete root is censored, not an observation of its completion cost.
No finite completion forecast is returned when any sampled root is censored.
"""
import json
import math
from pathlib import Path
import platform
import random
import shutil
import subprocess
import sys
import time

from .algebra import vector
from .audit import (check_parity_metadata, check_profile_metadata, check_symmetry_metadata,
                    events_from_stdout, require, require_object, resource_failure)
from .campaign import write_json
from .code import CSSCode, digest, json_bytes
from .engine import (DEFAULT_PROFILE, NATIVE_INTEGER_MAX, canonical_profile, build, check_limits,
                     audited_source_hashes, profile_options, memory_budget_bytes,
                     validate_memory_bytes, uses_dynamic_storage, select_code_capacity)
from .symmetry import orbit_representatives, symmetry_text


def root_schedule(code, samples, seed, use_symmetry=True):
    require(type(samples) is int and samples > 0, 'samples must be a positive integer')
    require(type(seed) is int, 'seed must be an integer')
    require(type(use_symmetry) is bool, 'Invalid symmetry option')
    period = code.period if use_symmetry else 1
    sectors = ['Z'] if use_symmetry and code.exchange is not None else ['X', 'Z']
    generators = code.symmetry_generators if use_symmetry else []
    roots = len(orbit_representatives(code.n, generators, period))
    rng = random.Random(seed)
    return period, {s: rng.sample(range(roots), min(samples, roots)) for s in sectors}


def summarize_roots(records, population, seed=0):
    """Design-based mean expansion, plus descriptive empirical bootstrap spread.

    The bootstrap cannot represent unobserved extreme roots; its quantiles
    are explicitly not a rigorous confidence interval or scheduling bound.
    """
    require(type(population) is int and population > 0, 'Invalid root population')
    require(len(records) <= population, 'More sampled roots than population')
    completed = [r for r in records if r['status'] == 'excluded']
    censored = [r for r in records if r['status'] == 'incomplete']
    failures = [r for r in records if r['status'] == 'error']
    witnesses = [r for r in records if r['status'] == 'witness']
    result = {'population_roots': population, 'sampled_roots': len(records),
              'completed_roots': len(completed), 'censored_roots': len(censored),
              'error_roots': len(failures), 'witness_roots': len(witnesses),
              'observed_process_seconds': sum(r['wall_seconds'] for r in records),
              'estimated_total_native_seconds': None, 'empirical_bootstrap_10_90_seconds': None,
              'distance_claim': None, 'forecast_scope': 'Unsharded native root-search work; excludes compilation, input loading, all preprocessing and row-space validation, sharding overhead, and scheduling. This is not parallel makespan or end-to-end runtime.'}
    if failures:
        result['status'] = 'ERROR'
    elif witnesses:
        result['status'] = 'WITNESS_FOUND'
    elif censored:
        result['status'] = 'CENSORED'
        result['reason'] = 'At least one sampled root did not finish; its total work and a finite completion forecast are unknown.'
    elif len(completed) < min(4, population):
        result['status'] = 'INSUFFICIENT_SAMPLE'
    else:
        costs = [r['native_seconds'] for r in completed]
        require(all(type(x) in (int, float) and math.isfinite(x) and x >= 0 for x in costs),
                'Invalid completed-root time')
        total = population * sum(costs) / len(costs)
        result['estimated_total_native_seconds'] = total
        result['sample_native_seconds'] = costs
        result['status'] = 'ALL_ROOTS_MEASURED' if len(costs) == population else 'EMPIRICAL_ESTIMATE'
        if len(costs) == population:
            result['empirical_bootstrap_10_90_seconds'] = [total, total]
        else:
            rng = random.Random(seed)
            totals = sorted(population * sum(rng.choices(costs, k=len(costs))) / len(costs)
                            for _ in range(1000))
            result['empirical_bootstrap_10_90_seconds'] = [totals[100], totals[899]]
            result['uncertainty_note'] = ('Descriptive resampling spread, not a confidence guarantee. '
                                          'Unobserved hard roots can make the actual total arbitrarily larger.')
    return result


def root_command(config, sector, root):
    args = ['engine/exact', f'inputs/{sector}.mat', str(config['period']), str(config['cutoff']),
            str(config['seconds_per_root']), str(root), '0', str(config.get('branch_end', 64)),
            str(config['node_cap'])]
    args += profile_options(config.get('native_profile'), config.get('proposed_additions', False))
    if config.get('memory_bytes') is not None:
        args.append(f'memory-bytes={validate_memory_bytes(config["memory_bytes"])}')
    if config.get('generator_symmetry'):
        args.append(f'symmetry-file=inputs/{sector}.symmetry')
    return args if config['coset_pruning'] else args + ['no-coset']


def classify(raw, code, config, sector, root):
    """Validate one complete native root transcript, without assigning distance credit."""
    events = events_from_stdout(raw['stdout'], raw['hard_timeout'])
    resource = resource_failure(events, raw['returncode'], config.get('memory_bytes'))
    if resource is not None:
        require(not raw['hard_timeout'], 'Allocation failure marked as timeout')
        return {'sector': sector, 'root': root, 'status': 'incomplete',
                'wall_seconds': raw['wall_seconds'], 'native_seconds': None, 'nodes': None,
                'terminal': resource, 'witnesses': []}
    finals = [e for e in events if e['event'] == 'result']
    witnesses = [e for e in events if e['event'] == 'witness']
    require(len(finals) <= 1 and (not finals or events[-1] == finals[0]), 'Invalid terminal ordering')
    terminal = finals[0] if finals else None
    for w in witnesses:
        word = vector(w.get('support'), code.n)
        require(code.is_logical(word, sector) and word.bit_count() == w.get('weight')
                and word.bit_count() <= config['cutoff'], 'Invalid calibration logical witness')
    if terminal:
        if config.get('generator_symmetry'):
            check_symmetry_metadata(terminal, code.symmetry_generators,
                                    orbit_representatives(code.n, code.symmetry_generators, config['period']))
        check_profile_metadata(terminal, config)
        parity_trivial = check_parity_metadata(terminal, code, config, sector)
        expected = {'W': config['cutoff'], 'root': root, 'branch_begin': 0,
                    'branch_end': config.get('branch_end', 64),
                    'partition': 'root_branch_v1', 'shard': 0, 'shards': 1, 'split_weight': 1,
                    'coset_pruning': config['coset_pruning']}
        require(all(terminal.get(k) == v and type(terminal.get(k)) is type(v) for k, v in expected.items()),
                'Wrong native root, cutoff or search mode')
        require(type(terminal.get('nodes')) is int
                and (terminal['nodes'] >= 1 or (terminal['nodes'] == 0 and parity_trivial)),
                'Invalid node count')
        require(type(terminal.get('seconds')) in (int, float) and math.isfinite(terminal['seconds'])
                and terminal['seconds'] >= 0, 'Invalid native time')
        require(type(terminal.get('roots_completed')) is int and terminal['roots_completed'] in (0, 1),
                'Invalid root completion count')
    if raw['hard_timeout']:
        status = 'incomplete'
    elif raw['returncode'] == 0:
        require(terminal is not None and terminal.get('status') == 'excluded'
                and terminal['roots_completed'] == 1 and not witnesses and len(events) == 1
                and terminal['nodes'] <= config['node_cap'], 'Root exclusion lacks complete execution')
        status = 'excluded'
    elif raw['returncode'] == 10:
        require(terminal is not None and terminal.get('status') == 'witness' and witnesses,
                'Witness exit without validated witness')
        status = 'witness'
    elif raw['returncode'] == 75:
        require(terminal is not None and terminal.get('status') == 'incomplete' and not witnesses,
                'Incomplete exit lacks a valid terminal')
        status = 'incomplete'
    else:
        status = 'error'
    return {'sector': sector, 'root': root, 'status': status, 'wall_seconds': raw['wall_seconds'],
            'native_seconds': terminal.get('seconds') if terminal else None,
            'nodes': terminal.get('nodes') if terminal else None,
            'terminal': terminal, 'witnesses': witnesses}


def calibrate(code, output, *, cutoff, samples=8, seconds_per_root=1.0, seed=0,
              node_cap=2**64-1, use_symmetry=True, coset_pruning=True,
              profile=DEFAULT_PROFILE, compiler='c++', cache=None, proposed_additions=True,
              memory_mib=None, large_capacity=None):
    profile = canonical_profile(profile)
    require(profile != 'lp', 'Calibration samples whole-code roots; the LP block profile has two different root sets')
    check_limits(code, cutoff, profile)
    require(type(seconds_per_root) in (float, int) and math.isfinite(seconds_per_root)
            and seconds_per_root > 0, 'seconds_per_root must be positive and finite')
    require(type(node_cap) is int and 1 <= node_cap < 2**64, 'Invalid node cap')
    require(type(coset_pruning) is bool, 'Invalid pruning option')
    require(type(proposed_additions) is bool, 'proposed_additions must be a boolean')
    memory_bytes = memory_budget_bytes(memory_mib)
    selected_capacity = select_code_capacity(code, cutoff, large_capacity, memory_bytes)
    period, schedule = root_schedule(code, samples, seed, use_symmetry)
    root = Path(output).resolve()
    require(not root.exists(), 'Calibration output already exists; choose a new directory')
    root.mkdir(parents=True)
    code.save(root/'code.json')
    (root/'inputs').mkdir()
    for sector in schedule:
        (root/f'inputs/{sector}.mat').write_text(code.native_text(sector))
        if use_symmetry and code.symmetry_generators:
            (root/f'inputs/{sector}.symmetry').write_text(symmetry_text(code.n, code.symmetry_generators))
    built = build(root/'engine', compiler=compiler, cache=cache, profile=profile,
                  large_capacity=selected_capacity)
    config = {'cutoff': cutoff, 'samples': samples, 'seconds_per_root': float(seconds_per_root),
              'seed': seed, 'node_cap': node_cap, 'period': period, 'use_symmetry': use_symmetry,
              'coset_pruning': coset_pruning, 'native_profile': profile, 'schedule': schedule,
              'branch_end': NATIVE_INTEGER_MAX if selected_capacity else 64,
              'large_capacity': selected_capacity}
    if memory_bytes is not None:
        config['memory_bytes'] = memory_bytes
    if proposed_additions:
        config['proposed_additions'] = True
    if use_symmetry and code.symmetry_generators:
        config['generator_symmetry'] = True
    meta = {'schema': 'cssdist.calibration.v1', 'config': config, 'code_sha256': code.fingerprint,
            'input_sha256': {s:digest((root/f'inputs/{s}.mat').read_bytes()) for s in schedule},
            'engine': built, 'build_sha256': digest((root/'engine/build.json').read_bytes()),
            'sampling': 'Uniform root sampling without replacement separately in each required sector.',
            'python': sys.version, 'platform': platform.platform(),
            'distance_claim': None, 'purpose': 'Runtime planning; no lower-bound or exact-distance result.'}
    if config.get('generator_symmetry'):
        meta['symmetry_sha256'] = {s: digest((root/f'inputs/{s}.symmetry').read_bytes()) for s in schedule}
    write_json(root/'calibration.json', meta)
    for sector, roots in schedule.items():
        for r in roots:
            folder = root/f'roots/{sector}/{r:06d}'
            folder.mkdir(parents=True)
            command = root_command(config, sector, r)
            started = time.monotonic()
            try:
                proc = subprocess.run([str(root/command[0]), *command[1:]], cwd=root,
                                      capture_output=True, timeout=float(seconds_per_root)+5)
                stdout, stderr, rc, timeout = proc.stdout, proc.stderr, proc.returncode, False
            except subprocess.TimeoutExpired as exc:
                stdout, stderr, rc, timeout = exc.stdout or b'', exc.stderr or b'', -9, True
            wall = time.monotonic()-started
            (folder/'stdout.jsonl').write_bytes(stdout); (folder/'stderr.txt').write_bytes(stderr)
            raw = {'stdout': stdout, 'returncode': rc, 'hard_timeout': timeout, 'wall_seconds': wall}
            try:
                record = classify(raw, code, config, sector, r)
            except ValueError as exc:
                record = {'sector':sector, 'root':r, 'status':'error', 'wall_seconds':wall,
                          'native_seconds':None, 'nodes':None, 'validation_error':str(exc)}
            record.update(command=command, returncode=rc, hard_timeout=timeout,
                          stdout_sha256=digest(stdout), stderr_sha256=digest(stderr))
            write_json(folder/'receipt.json', record)
    result = audit_calibration(root)
    write_json(root/'result.json', result)
    return result


def audit_calibration(directory):
    root = Path(directory).resolve()
    def read(name):
        p = root/name
        require(p.resolve().is_relative_to(root) and not p.is_symlink(), 'Calibration path escapes its directory')
        return p.read_bytes()
    meta = require_object(json.loads(read('calibration.json')), 'Calibration')
    require(meta.get('schema') == 'cssdist.calibration.v1', 'Unknown calibration schema')
    code = CSSCode(json.loads(read('code.json')))
    require(code.fingerprint == meta['code_sha256'], 'Calibration code changed')
    config = require_object(meta['config'], 'Calibration configuration')
    engine = require_object(meta['engine'], 'Calibration engine')
    require_object(engine['identity'], 'Calibration build identity')
    require_object(meta['input_sha256'], 'Calibration input hashes')
    require(canonical_profile(config.get('native_profile')) != 'lp', 'LP block roots are outside the calibration model')
    check_limits(code, config['cutoff'], config['native_profile'])
    period, schedule = root_schedule(code, config['samples'], config['seed'], config['use_symmetry'])
    require(period == config['period'] and schedule == config['schedule'], 'Root sample changed')
    require(config.get('generator_symmetry', False) is bool(config['use_symmetry'] and code.symmetry_generators),
            'Calibration declares an unsupported symmetry configuration')
    require(type(config['seconds_per_root']) in (int,float) and math.isfinite(config['seconds_per_root'])
            and config['seconds_per_root'] > 0, 'Invalid root time limit')
    require(type(config['node_cap']) is int and 1 <= config['node_cap'] < 2**64, 'Invalid root node cap')
    require(type(config['coset_pruning']) is bool, 'Invalid pruning option')
    archived_sources = audited_source_hashes(root/'engine', config['native_profile'],
                                              allow_cyclic_01=not config.get('generator_symmetry'),
                                              proposed_additions=config.get('proposed_additions', False))
    dynamic = uses_dynamic_storage(archived_sources)
    if 'large_capacity' in config:
        require(type(config['large_capacity']) is bool and config['large_capacity'] == dynamic,
                'Capacity setting differs from the calibration engine')
    check_limits(code, config['cutoff'], config['native_profile'], legacy=not dynamic)
    require(type(config.get('branch_end', 64)) is int
            and config.get('branch_end', 64) == (NATIVE_INTEGER_MAX if dynamic else 64),
            'Calibration does not cover all root branches')
    validate_memory_bytes(config.get('memory_bytes'))
    require(dynamic or config.get('memory_bytes') is None, 'Saved engine has no memory-budget support')
    require(archived_sources == meta['engine']['identity']['source_sha256'],
            'Calibration native source changed')
    require(digest(read('engine/build.json')) == meta['build_sha256']
            and json.loads(read('engine/build.json')) == meta['engine'], 'Build receipt changed')
    require(digest(read('engine/exact')) == meta['engine']['executable_sha256'], 'Native executable changed')
    records, reports = [], {}
    if config.get('generator_symmetry'):
        require(isinstance(meta.get('symmetry_sha256'), dict)
                and set(meta['symmetry_sha256']) == set(schedule), 'Invalid calibration symmetry hashes')
    for sector, roots in schedule.items():
        matrix = read(f'inputs/{sector}.mat')
        require(matrix == code.native_text(sector).encode() and digest(matrix) == meta['input_sha256'][sector],
                'Calibration physical matrix changed')
        if config.get('generator_symmetry'):
            symmetry = read(f'inputs/{sector}.symmetry')
            require(symmetry == symmetry_text(code.n, code.symmetry_generators).encode()
                    and digest(symmetry) == meta['symmetry_sha256'][sector],
                    'Calibration symmetry input changed')
        local = []
        for r in roots:
            base = f'roots/{sector}/{r:06d}'
            saved = require_object(json.loads(read(base+'/receipt.json')), 'Calibration receipt')
            stdout, stderr = read(base+'/stdout.jsonl'), read(base+'/stderr.txt')
            require(digest(stdout) == saved['stdout_sha256'] and digest(stderr) == saved['stderr_sha256'],
                    'Calibration transcript changed')
            require(saved['command'] == root_command(config, sector, r), 'Calibration command changed')
            require(type(saved['returncode']) is int and type(saved['hard_timeout']) is bool
                    and type(saved['wall_seconds']) in (int,float) and math.isfinite(saved['wall_seconds'])
                    and saved['wall_seconds'] >= 0, 'Invalid process receipt')
            try:
                actual = classify(dict(saved, stdout=stdout), code, config, sector, r)
            except ValueError as exc:
                require(saved.get('status') == 'error' and saved.get('validation_error') == str(exc),
                        'Calibration failure classification differs')
                actual = {k:saved[k] for k in ('sector','root','status','wall_seconds','native_seconds','nodes','validation_error')}
            require(all(saved.get(k) == v for k,v in actual.items()), 'Stored root interpretation differs')
            local.append(actual); records.append(actual)
        generators = code.symmetry_generators if config['use_symmetry'] else []
        population = len(orbit_representatives(code.n, generators, period))
        reports[sector] = summarize_roots(local, population, config['seed'])
    return {'schema':'cssdist.calibration.summary.v1',
            'status':'ERROR' if any(r['status']=='error' for r in records) else 'CALIBRATION_COMPLETE',
            'code_sha256':code.fingerprint, 'cutoff':config['cutoff'], 'native_profile':config['native_profile'],
            'sectors':reports, 'records':records, 'distance_claim':None,
            'interpretation':'Empirical runtime planning. Sampled exclusions do not establish a code distance lower bound.'}
