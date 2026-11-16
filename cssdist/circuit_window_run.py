"""Run and audit a cutoff-specific cover of a detector fault model."""
import json
import math
from pathlib import Path
import time

from .circuit import DetectorModel, METRIC
from .circuit_run import build_circuit, _checked_decision, _native_receipt, _verify_command, _write_manifest
from .circuit_window_search import detector_layer_ids, window_model, window_plan
from .code import json_bytes


def _decide(source, config, plan, build, get_receipt):
    """Combine completed representative exclusions and lift each witness to the source."""
    cutoff = config['cutoff']
    checked = []
    known = [source.check_witness(s) for s in source.document['witnesses']]
    free = plan['detector_free_witness']
    if free is not None:
        witness = source.check_witness([free])
        known.append(witness)
        if cutoff > 0:
            checked.append(witness)

    completed = nodes = roots = 0
    all_node_counts_reported = True
    process_seconds = last_end = 0.0
    runs = []
    for i, rep in enumerate(plan['representatives']):
        available = config['node_cap'] - nodes
        if available <= 0:
            break
        options = dict(config, node_cap=available)
        relative = Path('windows') / str(rep['start'])
        record = get_receipt(relative, rep, options)
        if record is None:
            break
        local, receipt = record
        offset = receipt['window_start_seconds']
        if type(offset) not in (float, int) or not math.isfinite(offset) or not last_end <= offset < config['seconds']:
            raise ValueError('Invalid window start time or shared wall budget')
        options['seconds'] = config['seconds'] - offset
        _verify_command(options, receipt, build, relative / 'model.txt', rep['root_end'])
        status, found, terminal = _checked_decision(local, options, receipt, rep['root_end'])
        timing = receipt['timing']
        last_end = offset + timing['end_to_end_seconds']
        process_seconds += timing['process_seconds']
        runs.append({'representative': i, 'start_layer': rep['start'], 'status': status})
        if terminal is not None and terminal['event'] == 'result':
            nodes += terminal['nodes']
            roots += terminal['roots_completed']
        else:
            all_node_counts_reported = False
        for witness in found:
            lifted = source.check_witness([rep['source_columns'][j] for j in witness['support']])
            if (lifted['weight'] != witness['weight']
                    or lifted['observable_flips'] != witness['observable_flips']):
                raise ValueError('Window witness differs on the original circuit model')
            checked.append(lifted)
        if status != 'EXCLUDED':
            break
        completed += 1

    representatives = plan['representatives']
    lower = None
    if checked:
        status = 'WITNESS_FOUND'
        if any(w['weight'] == 1 for w in checked):
            lower = 1  # The empty pattern has zero observable parity.
    elif completed == len(representatives):
        status, lower = 'EXCLUDED', cutoff + 1
    else:
        status = 'INCOMPLETE'
    upper = min((w['weight'] for w in known + checked), default=None)
    if lower is not None and upper is not None and lower > upper:
        raise ValueError('Window exclusion contradicts a checked source witness')
    result = {'schema': 'qedist.circuit-window-result.v1', 'metric': METRIC, 'status': status,
              'input_fingerprint': source.fingerprint, 'cutoff': cutoff,
              'distance_lower_bound': lower, 'distance_upper_bound': upper,
              'exact_distance': upper if upper == lower else None, 'checked_witnesses': checked,
              'window_layers': plan['window_layers'], 'max_fault_span': plan['max_fault_span'],
              'windows_covered_by_plan': len(plan['windows']), 'representatives_required': len(representatives),
              'representatives_excluded': completed, 'roots_required': sum(r['root_end'] for r in representatives),
              'roots_completed': roots, 'nodes': nodes if all_node_counts_reported else None, 'window_runs': runs}
    return result, process_seconds, last_end


def _finish(result, timing, seconds, process_seconds, last_end):
    for field in ('build_seconds_excluded', 'preparation_seconds', 'process_seconds', 'end_to_end_seconds'):
        value = timing[field]
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError(f'Invalid window timing field: {field}')
    if (timing['process_seconds'] != process_seconds
            or timing['end_to_end_seconds'] + 1e-8 < max(last_end, timing['preparation_seconds'] + process_seconds)):
        raise ValueError('Window timing differs from native receipts')
    result['timing'] = timing
    result['completed_within_budget'] = (result['status'] != 'INCOMPLETE'
                                         and timing['end_to_end_seconds'] <= seconds)
    return result


def certify_windows(model, output, *, cutoff, seconds, node_cap, weighted, neutral,
                    compiler, cache, detectors_per_layer, detector_layers, memory_bytes=None,
                    large_capacity=True):
    validation_start = time.monotonic()
    source = DetectorModel(model.document)
    layers = detector_layer_ids(source, detectors_per_layer, detector_layers)
    validation_seconds = time.monotonic() - validation_start
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    build_start = time.monotonic()
    build = build_circuit(output / 'engine', compiler=compiler, cache=cache,
                          large_capacity=large_capacity)
    build_seconds = time.monotonic() - build_start
    start = time.monotonic() - validation_seconds
    plan = window_plan(source, cutoff, layers)
    config = {'schema': 'qedist.circuit-window-run.v1', 'root_coverage': 'detector_windows',
              'input_fingerprint': source.fingerprint, 'original_run_directory': str(output),
              'cutoff': cutoff, 'seconds': float(seconds), 'node_cap': node_cap,
              'weighted': weighted, 'neutral': neutral, 'repair_depth': 8, 'even_repair_cap': 4,
              'large_capacity': large_capacity,
              'detector_layers': layers}
    if memory_bytes is not None:
        config['memory_bytes'] = memory_bytes
    (output / 'input.json').write_bytes(json_bytes(source.document))
    (output / 'config.json').write_bytes(json_bytes(config))
    (output / 'coverage.json').write_bytes(json_bytes(plan))
    preparation = time.monotonic() - start

    def execute(relative, rep, options):
        task_start = time.monotonic()
        offset = task_start - start
        if offset >= seconds:
            return None
        local = window_model(source, rep['source_columns'])
        directory = output / relative
        directory.mkdir(parents=True)
        path = directory / 'model.txt'
        path.write_text(local.native_text())
        task_config = dict(options, seconds=seconds - offset)
        receipt = _native_receipt(output, path, task_config, build, 0.0, task_start, rep['root_end'])
        receipt['window_start_seconds'] = offset
        (directory / 'receipt.json').write_bytes(json_bytes(receipt))
        return local, receipt

    result, process_seconds, last_end = _decide(source, config, plan, build, execute)
    timing = {'build_seconds_excluded': build_seconds, 'preparation_seconds': preparation,
              'process_seconds': process_seconds, 'end_to_end_seconds': time.monotonic() - start}
    _finish(result, timing, seconds, process_seconds, last_end)
    (output / 'receipt.json').write_bytes(json_bytes({'timing': timing}))
    (output / 'result.json').write_bytes(json_bytes(result))
    _write_manifest(output)
    return result


def audit_windows(output, source, config, build, hashes):
    if config['root_coverage'] != 'detector_windows' or 'coverage.json' not in hashes:
        raise ValueError('Missing window coverage information')
    layers = detector_layer_ids(source, None, config['detector_layers'])
    plan = window_plan(source, config['cutoff'], layers)
    if (output / 'coverage.json').read_bytes() != json_bytes(plan):
        raise ValueError('Window coverage does not match the original fault signatures')
    consumed = set()

    def read_receipt(relative, rep, options):
        model_file = str(relative / 'model.txt')
        receipt_file = str(relative / 'receipt.json')
        if model_file not in hashes and receipt_file not in hashes:
            return None
        if not {model_file, receipt_file}.issubset(hashes):
            raise ValueError('Incomplete window evidence files')
        local = window_model(source, rep['source_columns'])
        if (output / model_file).read_text() != local.native_text():
            raise ValueError('Window native model differs from its full source columns')
        consumed.update((model_file, receipt_file))
        return local, json.loads((output / receipt_file).read_text())

    result, process_seconds, last_end = _decide(source, config, plan, build, read_receipt)
    if consumed != {name for name in hashes if name.startswith('windows/')}:
        raise ValueError('Unexpected or out-of-order window evidence')
    timing = json.loads((output / 'receipt.json').read_text())['timing']
    _finish(result, timing, config['seconds'], process_seconds, last_end)
    if (output / 'result.json').read_bytes() != json_bytes(result):
        raise ValueError('Window conclusion differs from the verified coverage and receipts')
    return result
