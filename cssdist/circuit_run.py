"""Execution and read-only audit of direct detector/observable exclusions."""
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

from .circuit import DetectorModel, METRIC
from .code import digest, json_bytes
from .engine import (compiler_identity, FLAGS, NATIVE_INTEGER_MAX, memory_budget_bytes,
                     validate_memory_bytes, select_capacity)
from .audit import resource_failure

NATIVE = Path(__file__).resolve().parent / 'native_circuit'
_RECURSIVE_SOURCES = {
    'common.hpp': 'e2fe6046b8f6d907cf4e8b0f15f358a231f46520237f7f94704221c811208960',
    'exact.cpp': 'fbc6163168c247332e7bae2f2bf99d2b1fa6d4aa432bd3bd9b4934ec0b788249',
}


def source_hashes(directory=NATIVE):
    return {p.name: digest(p.read_bytes()) for p in sorted(Path(directory).iterdir())
            if p.suffix in ('.cpp', '.hpp', '.inc')}


def build_circuit(destination, compiler='c++', cache=None, *, large_capacity=True):
    if type(large_capacity) is not bool:
        raise ValueError('large_capacity must be a boolean')
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    compiler_path, version = compiler_identity(compiler)
    native = NATIVE if large_capacity else NATIVE / 'fixed'
    sources = source_hashes(native)
    identity = {'source_sha256': sources, 'compiler': compiler_path,
                'compiler_version': version, 'flags': FLAGS, 'profile': 'circuit-v1'}
    cache = Path(cache) if cache else Path(tempfile.gettempdir()) / f'qedist-circuit-{os.getuid()}'
    cache.mkdir(parents=True, exist_ok=True)
    entry = cache / digest(json_bytes(identity))
    valid = False
    try:
        saved = json.loads((entry / 'build.json').read_text())
        valid = saved.get('identity') == identity and saved.get('executable_sha256') == digest((entry / 'exact').read_bytes())
    except (OSError, ValueError, AttributeError):
        pass
    if not valid:
        with tempfile.TemporaryDirectory(prefix='build-', dir=cache) as tmp:
            tmp = Path(tmp)
            for name in sources:
                shutil.copy2(native / name, tmp / name)
            if source_hashes(tmp) != sources:
                raise ValueError('Circuit sources changed during build preparation')
            subprocess.run([compiler_path, *FLAGS, str(tmp / 'exact.cpp'), '-o', str(tmp / 'exact')],
                           capture_output=True, text=True, check=True)
            saved = {'identity': identity, 'executable_sha256': digest((tmp / 'exact').read_bytes())}
            (tmp / 'build.json').write_bytes(json_bytes(saved))
            entry.mkdir(exist_ok=True)
            (tmp / 'exact').replace(entry / 'exact')
            (tmp / 'build.json').replace(entry / 'build.json')
    for name in sources:
        shutil.copy2(native / name, destination / name)
    shutil.copy2(Path(__file__).with_name('LICENSE.txt'), destination / 'LICENSE.txt')
    shutil.copy2(entry / 'exact', destination / 'exact')
    if source_hashes(destination) != sources or digest((destination / 'exact').read_bytes()) != saved['executable_sha256']:
        raise ValueError('Circuit sources or executable changed during copy')
    (destination / 'build.json').write_bytes(json_bytes(saved))
    return saved


def _parameters(cutoff, seconds, node_cap, weighted, neutral):
    if type(cutoff) is not int or not 0 <= cutoff <= NATIVE_INTEGER_MAX:
        raise ValueError(f'Circuit cutoff must be an integer from 0 to {NATIVE_INTEGER_MAX}')
    if type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds <= 0:
        raise ValueError('seconds must be finite and positive')
    if type(node_cap) is not int or not 0 <= node_cap < 2**64:
        raise ValueError('node_cap must be an unsigned 64-bit integer')
    if type(weighted) is not bool or type(neutral) is not bool:
        raise ValueError('Pruning switches must be Boolean')


def _checked_decision(model, config, receipt, root_end, root_begin=0):
    """Validate one native decision for a root interval. Coverage is checked separately."""
    cutoff = config['cutoff']
    if (type(root_begin) is not int or type(root_end) is not int
            or not 0 <= root_begin <= root_end <= model.n):
        raise ValueError('Invalid expected circuit root interval')
    root_count = root_end - root_begin
    if not isinstance(receipt.get('timing'), dict):
        raise ValueError('Missing circuit timing record')
    for key in ('build_seconds_excluded', 'preparation_seconds', 'process_seconds', 'end_to_end_seconds'):
        value = receipt['timing'].get(key)
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError('Invalid circuit timing field: ' + key)
    timing = receipt['timing']
    if timing['preparation_seconds'] + timing['process_seconds'] > timing['end_to_end_seconds'] + 1e-8:
        raise ValueError('Circuit timing components exceed total elapsed time')
    if type(receipt.get('external_timeout')) is not bool or type(receipt.get('returncode')) is not int:
        raise ValueError('Invalid circuit process status')
    events = []
    lines = receipt['stdout'].splitlines()
    for index, line in enumerate(lines):
        if line.strip():
            try:
                event = json.loads(line)
            except ValueError:
                if receipt['external_timeout'] and index == len(lines) - 1:
                    break  # A killed writer may leave a partial last record; no completion credit.
                raise
            if not isinstance(event, dict) or event.get('event') not in ('witness', 'result', 'resource_limit'):
                raise ValueError('Malformed native event')
            events.append(event)
    resource = resource_failure(events, receipt['returncode'], config.get('memory_bytes'))
    if resource is not None:
        if receipt['external_timeout'] or receipt['source_sha256'] == _RECURSIVE_SOURCES:
            raise ValueError('Invalid circuit allocation-failure receipt')
        return 'INCOMPLETE', [], resource
    terminals = [e for e in events if e.get('event') == 'result']
    if len(terminals) > 1 or (terminals and events[-1] is not terminals[0]):
        raise ValueError('Unexpected circuit terminal record ordering')
    terminal = terminals[0] if terminals else None
    checked = [model.check_witness(e['support']) for e in events if e.get('event') == 'witness']
    for event, witness in zip((e for e in events if e.get('event') == 'witness'), checked):
        if type(event.get('weight')) is not int or event['weight'] != witness['weight']:
            raise ValueError('Printed native witness weight differs from its support')
    if any(w['weight'] > cutoff for w in checked):
        raise ValueError('Native witness exceeds the requested cutoff')
    status = 'INCOMPLETE'
    if terminal:
        if (type(terminal.get('roots_completed')) is not int
                or not 0 <= terminal['roots_completed'] <= root_count
                or type(terminal.get('nodes')) is not int or terminal['nodes'] < 0):
            raise ValueError('Invalid native completion counters')
        expected = {'W': cutoff, 'effective_W': min(cutoff, model.n),
                    'mechanisms': model.n, 'detectors': len(model.detectors),
                    'observables': len(model.observables), 'neutral_rows': len(model.neutrals),
                    'weighted': config['weighted'], 'neutral_pruning': config['neutral'],
                    'root_begin': root_begin, 'root_end': root_end, 'roots_total': model.n}
        for key, value in expected.items():
            if type(terminal.get(key)) is not type(value) or terminal[key] != value:
                raise ValueError(f'Circuit terminal metadata mismatch: {key}')
        native_status = terminal.get('status')
        if native_status == 'excluded':
            normal_exit = receipt['returncode'] == 0
            killed_at_deadline = receipt['external_timeout'] and receipt['returncode'] in (-9, -15)
            if (not (normal_exit or killed_at_deadline)
                    or terminal.get('complete') is not (root_begin == 0 and root_end == model.n)
                    or type(terminal.get('roots_completed')) is not int
                    or terminal['roots_completed'] != root_count or checked
                    or terminal['nodes'] > config['node_cap']
                    or terminal.get('timedout') is not False):
                coverage = 'root-range'
                if root_begin == 0:
                    coverage = 'all-root' if root_end == model.n else 'window-root'
                raise ValueError(f'Exclusion lacks a complete {coverage} execution')
            # A child may flush its last line while the wall watchdog expires.
            # Preserve that transcript and give this attempt no lower-bound credit.
            status = 'INCOMPLETE' if receipt['external_timeout'] else 'EXCLUDED'
        elif native_status == 'witness':
            if (receipt['returncode'] != 10 or len(checked) != 1
                    or terminal.get('complete') is not False or terminal.get('timedout') is not False
                    or not 1 <= terminal['nodes'] <= config['node_cap']
                    or any(not root_begin <= w['support'][0] < root_end for w in checked)):
                raise ValueError('Native witness status has no valid witness/exit code')
            status = 'WITNESS_FOUND'
        elif native_status in ('timeout', 'node_limit', 'interrupted'):
            if terminal.get('complete') is not False or receipt['returncode'] != 75 or checked:
                raise ValueError('Inconsistent incomplete-search record')
        else:
            raise ValueError('Unknown circuit terminal status')
    elif not receipt.get('external_timeout'):
        raise ValueError('Native process did not emit a terminal record')
    return status, checked, terminal


def _conclusion(model, config, receipt):
    status, checked, terminal = _checked_decision(model, config, receipt, model.n)
    known = [model.check_witness(s) for s in model.document['witnesses']]
    upper = min((w['weight'] for w in checked + known), default=None)
    cutoff = config['cutoff']
    lower = cutoff + 1 if status == 'EXCLUDED' else None
    if lower is not None and upper is not None and lower > upper:
        raise ValueError('Completed exclusion contradicts a checked witness')
    return {'schema': 'qedist.circuit-result.v1', 'status': status, 'metric': METRIC,
            'input_fingerprint': model.fingerprint, 'cutoff': cutoff,
            'distance_lower_bound': lower, 'distance_upper_bound': upper,
            'exact_distance': upper if upper == lower and upper is not None else None,
            'checked_witnesses': checked, 'terminal': terminal,
            'timing': receipt['timing'],
            'completed_within_budget': (status in ('EXCLUDED', 'WITNESS_FOUND')
                                       and receipt['timing']['end_to_end_seconds'] <= config['seconds']
                                       and not receipt.get('external_timeout')),
            'interpretation': 'Completed exhaustive execution record; not a formal proof of every branch. Physical-location equivalence is a separate model obligation.'}


def _native_options(config, seconds_argument, root_end, root_begin=0):
    options = [str(config['cutoff']), seconds_argument, str(config['node_cap']),
               'weighted=' + ('on' if config['weighted'] else 'off'),
               'neutral=' + ('on' if config['neutral'] else 'off'), 'even-repairs=4', 'repair-depth=8']
    if config.get('memory_bytes') is not None:
        options.append(f'memory-bytes={validate_memory_bytes(config["memory_bytes"])}')
    if root_end is not None:
        options.append(f'root-end={root_end}')
    if root_begin:
        options.append(f'root-begin={root_begin}')
    return options


def _native_receipt(output, model_path, config, build, build_seconds, begun, root_end=None,
                    root_begin=0):
    preparation = time.monotonic() - begun
    remaining = max(0.0, config['seconds'] - preparation)
    command = [str(output / 'engine/exact'), str(model_path),
               *_native_options(config, format(remaining, '.17g'), root_end, root_begin)]
    process_start = time.monotonic()
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as process:
        external_timeout = False
        try:
            stdout, stderr = process.communicate(timeout=max(0.001, remaining))
        except subprocess.TimeoutExpired:
            external_timeout = True
            process.terminate()
            try:
                stdout, stderr = process.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
        process_seconds = time.monotonic() - process_start
    return {'command': command, 'returncode': process.returncode,
            'stdout': stdout, 'stderr': stderr, 'external_timeout': external_timeout,
            'timing': {'build_seconds_excluded': build_seconds,
                       'preparation_seconds': preparation, 'process_seconds': process_seconds,
                       'end_to_end_seconds': time.monotonic() - begun},
            'source_sha256': build['identity']['source_sha256'],
            'executable_sha256': build['executable_sha256']}


def select_circuit_capacity(model, cutoff, large_capacity=None, memory_bytes=None):
    """Choose storage before creating a circuit or stabilizer run directory."""
    if not isinstance(model, DetectorModel):
        raise ValueError('Expected a validated DetectorModel')
    base_storage = (192 * model.n + 64 * len(model.detectors)
                    + 40 * len(model.observables) + 48 * len(model.neutrals))
    return select_capacity(min(cutoff, model.n) > 512 or base_storage > 8 * 1024**3,
                           large_capacity, memory_bytes)


def certify_circuit(model, output, *, cutoff, seconds=30.0, node_cap=2**64-1,
                    weighted=True, neutral=True, compiler='c++', cache=None,
                    detectors_per_layer=None, detector_layers=None, memory_mib=None,
                    large_capacity=None):
    """Decide a circuit cutoff, optionally covering it with verified detector-layer windows."""
    _parameters(cutoff, seconds, node_cap, weighted, neutral)
    memory_bytes = memory_budget_bytes(memory_mib)
    selected_capacity = select_circuit_capacity(model, cutoff, large_capacity, memory_bytes)
    if detectors_per_layer is not None or detector_layers is not None:
        from .circuit_window_run import certify_windows
        return certify_windows(model, output, cutoff=cutoff, seconds=seconds, node_cap=node_cap,
                               weighted=weighted, neutral=neutral, compiler=compiler, cache=cache,
                               detectors_per_layer=detectors_per_layer, detector_layers=detector_layers,
                               memory_bytes=memory_bytes, large_capacity=selected_capacity)
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    build_start = time.monotonic()
    build = build_circuit(output / 'engine', compiler=compiler, cache=cache,
                          large_capacity=selected_capacity)
    build_seconds = time.monotonic() - build_start
    begun = time.monotonic()
    # Revalidate the serialized input, then freeze it before running.
    model = DetectorModel(model.document)
    (output / 'input.json').write_bytes(json_bytes(model.document))
    (output / 'model.txt').write_text(model.native_text())
    config = {'schema': 'qedist.circuit-run.v1', 'input_fingerprint': model.fingerprint,
              'original_run_directory': str(output),
              'cutoff': cutoff, 'seconds': float(seconds), 'node_cap': node_cap,
              'weighted': weighted, 'neutral': neutral, 'root_coverage': 'all',
              'large_capacity': selected_capacity,
              'repair_depth': 8, 'even_repair_cap': 4,
              'timing_scope': 'wall budget after build; input revalidation, serialization, native initialization and search included'}
    if memory_bytes is not None:
        config['memory_bytes'] = memory_bytes
    (output / 'config.json').write_bytes(json_bytes(config))
    receipt = _native_receipt(output, output / 'model.txt', config, build, build_seconds, begun)
    # Persist the raw execution before any parser/validation can raise.
    (output / 'receipt.json').write_bytes(json_bytes(receipt))
    result = _conclusion(model, config, receipt)
    receipt['timing']['end_to_end_seconds'] = time.monotonic() - begun
    receipt['timing']['scope'] = 'input revalidation, native preparation/execution and independent conclusion check; excludes build and final evidence serialization/hashing'
    result['completed_within_budget'] = (result['status'] in ('EXCLUDED', 'WITNESS_FOUND')
                                        and receipt['timing']['end_to_end_seconds'] <= seconds
                                        and not receipt['external_timeout'])
    (output / 'receipt.json').write_bytes(json_bytes(receipt))
    (output / 'result.json').write_bytes(json_bytes(result))
    _write_manifest(output)
    return result


def _write_manifest(output):
    hashes = {str(p.relative_to(output)): digest(p.read_bytes()) for p in sorted(output.rglob('*'))
              if p.is_file()}
    (output / 'SHA256SUMS.json').write_bytes(json_bytes({'files': hashes}))


def _verified_files(output):
    manifest = output / 'SHA256SUMS.json'
    if manifest.is_symlink():
        raise ValueError('Circuit integrity manifest must be a local regular file')
    hashes = json.loads(manifest.read_text())['files']
    required = {'input.json', 'config.json', 'receipt.json', 'result.json',
                'engine/build.json', 'engine/exact'}
    required.update('engine/' + name for name in source_hashes())
    if not isinstance(hashes, dict) or not required.issubset(hashes):
        raise ValueError('Circuit integrity manifest omits required files')
    for name, expected in hashes.items():
        path = output / name
        if (Path(name).is_absolute() or Path(name).as_posix() != name or '..' in Path(name).parts
                or path.resolve() != path or not path.is_file() or digest(path.read_bytes()) != expected):
            raise ValueError(f'Circuit integrity check failed: {name}')
    return hashes


def _verified_build(output):
    build = json.loads((output / 'engine/build.json').read_text())
    expected = source_hashes(output / 'engine')
    source_names = {p.name for p in (output / 'engine').iterdir() if p.suffix in ('.cpp', '.hpp', '.inc')}
    if source_names != set(source_hashes()):
        raise ValueError('Circuit source inventory mismatch')
    if (build['identity'].get('profile') != 'circuit-v1'
            or build['identity'].get('flags') != FLAGS
            or expected not in (source_hashes(), _RECURSIVE_SOURCES)
            or expected != build['identity']['source_sha256']
            or digest((output / 'engine/exact').read_bytes()) != build['executable_sha256']):
        raise ValueError('Circuit build identity mismatch')
    return build


def _verify_command(config, receipt, build, model_relative='model.txt', root_end=None, root_begin=0):
    if (receipt['source_sha256'] != build['identity']['source_sha256']
            or receipt['executable_sha256'] != build['executable_sha256']):
        raise ValueError('Circuit receipt/build identity mismatch')
    command = receipt['command']
    original = Path(config['original_run_directory'])
    if (not isinstance(command, list) or len(command) < 4 or not original.is_absolute()
            or Path(command[0]) != original / 'engine/exact'
            or Path(command[1]) != original / model_relative
            or command[2:] != _native_options(config, command[3], root_end, root_begin)
            or not math.isfinite(float(command[3])) or not 0 <= float(command[3]) <= config['seconds']):
        raise ValueError('Circuit command/configuration mismatch')
    expected_seconds = max(0.0, config['seconds'] - receipt['timing']['preparation_seconds'])
    if command[3] != format(expected_seconds, '.17g'):
        raise ValueError('Circuit command differs from its remaining wall budget')


def _audit_circuit(output):
    """Recheck identity, witness validity and completion accounting, without running code."""
    output = Path(output).resolve()
    hashes = _verified_files(output)
    model = DetectorModel.load(output / 'input.json')
    config = json.loads((output / 'config.json').read_text())
    _parameters(config['cutoff'], config['seconds'], config['node_cap'], config['weighted'], config['neutral'])
    if (config.get('repair_depth') != 8 or config.get('even_repair_cap') != 4
            or config['input_fingerprint'] != model.fingerprint):
        raise ValueError('Circuit configuration/input mismatch')
    build = _verified_build(output)
    if 'large_capacity' in config:
        dynamic = build['identity']['source_sha256'] != _RECURSIVE_SOURCES
        if type(config['large_capacity']) is not bool or config['large_capacity'] != dynamic:
            raise ValueError('Capacity setting differs from the circuit engine')
    validate_memory_bytes(config.get('memory_bytes'))
    if (build['identity']['source_sha256'] == _RECURSIVE_SOURCES
            and (min(config['cutoff'], model.n) > 512 or config.get('memory_bytes') is not None)):
        raise ValueError('Circuit configuration exceeds the saved engine capabilities')
    if config.get('schema') == 'qedist.circuit-window-run.v1':
        from .circuit_window_run import audit_windows
        return audit_windows(output, model, config, build, hashes)
    if config.get('schema') != 'qedist.circuit-run.v1' or config['root_coverage'] != 'all':
        raise ValueError('Circuit configuration schema or coverage mismatch')
    if 'model.txt' not in hashes or (output / 'model.txt').read_text() != model.native_text():
        raise ValueError('Native detector input differs from the validated model')
    receipt = json.loads((output / 'receipt.json').read_text())
    _verify_command(config, receipt, build)
    result = _conclusion(model, config, receipt)
    if result != json.loads((output / 'result.json').read_text()):
        raise ValueError('Circuit conclusion differs from recorded evidence')
    return result


def audit_circuit(output):
    """Reject malformed metadata as a structured validation failure."""
    try:
        return _audit_circuit(output)
    except (KeyError, TypeError, IndexError, AttributeError) as exc:
        raise ValueError('Malformed circuit execution metadata: ' + str(exc)) from exc
