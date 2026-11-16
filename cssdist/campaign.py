"""Bounded parallel searches with immutable attempts and shard-level resume."""
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from contextlib import contextmanager
import json
import math
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile
import time
import uuid

from .audit import audit_run, check_receipt, command, configuration, events_from_stdout, require
from .code import digest, json_bytes
from .engine import (DEFAULT_PROFILE, canonical_profile, build, memory_budget_bytes,
                     uses_dynamic_storage, select_code_capacity)
from .lp_blocks import search_problems


def write_json(path, value):
    path = Path(path)
    temp = path.with_name(path.name + '.tmp-' + uuid.uuid4().hex)
    temp.write_bytes(json_bytes(value))
    temp.replace(path)


@contextmanager
def campaign_lock(root):
    lock = root / '.running.lock'
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ValueError('Campaign is locked. If its process has stopped, remove .running.lock before resuming.') from None
    try:
        with os.fdopen(descriptor, 'w') as handle:
            handle.write(str(os.getpid()) + '\n')
        yield
    finally:
        lock.unlink(missing_ok=True)


def initialize(code, root, config, compiler, cache):
    root.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.cssdist-init-', dir=root.parent) as tmp:
        stage = Path(tmp) / 'campaign'
        stage.mkdir()
        problems = search_problems(code, config)
        code.save(stage / 'code.json')
        build_record = build(stage / 'engine', compiler=compiler, cache=cache,
                             profile=config['native_profile'],
                             large_capacity=config.get('large_capacity', True))
        (stage / 'inputs').mkdir()
        input_hashes = {}
        symmetry_hashes = {}
        for name, problem in problems.items():
            data = problem.text().encode()
            (stage / f'inputs/{name}.mat').write_bytes(data)
            input_hashes[name] = digest(data)
            if config.get('generator_symmetry'):
                data = problem.symmetry_text().encode()
                (stage / f'inputs/{name}.symmetry').write_bytes(data)
                symmetry_hashes[name] = digest(data)
        cpu = platform.processor()
        if platform.system() == 'Darwin' and shutil.which('sysctl'):
            probe = subprocess.run(['sysctl', '-n', 'machdep.cpu.brand_string'], capture_output=True, text=True)
            if probe.returncode == 0:
                cpu = probe.stdout.strip()
        campaign = {'schema': 'cssdist.campaign.v1', 'code_sha256': code.fingerprint,
                    'config': config, 'input_sha256': input_hashes,
                    'engine': {'source_sha256': build_record['identity']['source_sha256'],
                               'executable_sha256': build_record['executable_sha256'],
                               'build_sha256': digest((stage / 'engine/build.json').read_bytes())},
                    'environment': {'python': platform.python_version(), 'system': platform.system(),
                                    'machine': platform.machine(), 'processor': cpu or 'unavailable'},
                    'evidence_kind': 'Completed exhaustive execution records; not a formal proof trace.'}
        if config.get('generator_symmetry'):
            campaign['symmetry_sha256'] = symmetry_hashes
        write_json(stage / 'campaign.json', campaign)
        require(not root.exists(), 'Output directory appeared during initialization')
        stage.rename(root)


def run_attempt(root, campaign, sector, shard, seconds, node_cap, memory_bytes=None):
    job = root / f'jobs/{sector}/{shard:06d}'
    job.mkdir(parents=True, exist_ok=True)
    old = [int(p.name.split('-')[-1]) for p in job.glob('attempt-*') if p.is_dir()]
    attempt = job / f'attempt-{max(old, default=0) + 1:06d}'
    attempt.mkdir()
    cmd = command(campaign['config'], sector, shard, seconds, node_cap, memory_bytes)
    executable_cmd = [str(root / cmd[0]), *cmd[1:]]
    started = time.monotonic()
    timeout = False
    try:
        result = subprocess.run(executable_cmd, cwd=root, capture_output=True,
                                timeout=seconds + max(5.0, 0.1 * seconds))
        stdout, stderr, returncode = result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired as exc:
        stdout, stderr, returncode = exc.stdout or b'', exc.stderr or b'', -9
        timeout = True
    (attempt / 'stdout.jsonl').write_bytes(stdout)
    (attempt / 'stderr.txt').write_bytes(stderr)
    events = events_from_stdout(stdout, timeout)
    finals = [e for e in events if e['event'] in ('result', 'resource_limit')]
    receipt = {'schema': 'cssdist.receipt.v1', 'code_sha256': campaign['code_sha256'],
               'input_sha256': campaign['input_sha256'][sector],
               'source_sha256': campaign['engine']['source_sha256'],
               'executable_sha256': campaign['engine']['executable_sha256'],
               'sector': sector, 'shard': shard, 'command': cmd,
               'limits': {'seconds': float(seconds), 'nodes': node_cap},
               'returncode': returncode, 'hard_timeout': timeout,
               'wall_seconds': time.monotonic() - started,
               'stdout_sha256': digest(stdout), 'stderr_sha256': digest(stderr),
               'terminal': finals[-1] if finals else None}
    if memory_bytes is not None:
        receipt['limits']['memory_bytes'] = memory_bytes
    if campaign['config'].get('generator_symmetry'):
        receipt['symmetry_sha256'] = campaign['symmetry_sha256'][sector]
    write_json(attempt / 'receipt.json', receipt)
    return receipt


def certify(code, output, *, cutoff, shards=1, split_weight=None, workers=1,
            seconds_per_shard=30.0, node_cap=2**64 - 1, resume=False,
            use_symmetry=True, coset_pruning=True, compiler='c++', cache=None,
            progress=None, profile=DEFAULT_PROFILE, stop_on_witness=False,
            proposed_additions=None, memory_mib=None, large_capacity=None):
    """Run or resume a campaign with recorded pruning and capacity settings.

    New campaigns enable proposed-addition pruning and choose the fixed-storage
    engine when the input fits. Resume inherits both settings when unspecified.
    """
    require(type(workers) is int and workers > 0, 'workers must be a positive integer')
    require(type(seconds_per_shard) in (int, float) and math.isfinite(seconds_per_shard)
            and seconds_per_shard > 0, 'seconds_per_shard must be positive and finite')
    require(type(node_cap) is int and 1 <= node_cap < 2**64, 'Invalid node limit')
    require(type(stop_on_witness) is bool, 'stop_on_witness must be a boolean')
    require(proposed_additions is None or type(proposed_additions) is bool,
            'proposed_additions must be a boolean or None')
    memory_bytes = memory_budget_bytes(memory_mib)
    selected_capacity = select_code_capacity(code, cutoff, large_capacity, memory_bytes)
    selected_proposed = True if proposed_additions is None else proposed_additions
    if split_weight is None:
        split_weight = min(4, cutoff)
    cfg = configuration(code, cutoff, shards, split_weight, use_symmetry, coset_pruning,
                        profile, selected_proposed, selected_capacity)
    root = Path(output).resolve()
    if root.exists():
        require(resume, 'Output directory already exists; use --resume or choose a new directory')
        require((root / 'campaign.json').is_file(), 'Existing directory is not a cssdist campaign')
    else:
        require(not resume, 'Cannot resume a missing campaign')
        initialize(code, root, cfg, compiler, cache)
    with campaign_lock(root):
        campaign = json.loads((root / 'campaign.json').read_text())
        recorded_config = dict(campaign['config'])
        recorded_config['native_profile'] = canonical_profile(recorded_config.get('native_profile'))
        if resume:
            recorded_capacity = uses_dynamic_storage(campaign['engine']['source_sha256'])
            require(large_capacity is None or large_capacity == recorded_capacity,
                    'Resume requires the saved capacity setting and engine')
            if proposed_additions is None:
                selected_proposed = recorded_config.get('proposed_additions', False)
            cfg = configuration(code, cutoff, shards, split_weight, use_symmetry, coset_pruning,
                                profile, selected_proposed,
                                recorded_config.get('large_capacity'))
        require(campaign['code_sha256'] == code.fingerprint and recorded_config == cfg,
                'Resume requires the same code, cutoff, partition, symmetry and pruning options')
        prior = audit_run(root)
        require(memory_bytes is None or uses_dynamic_storage(campaign['engine']['source_sha256']),
                'The saved engine does not support memory budgets; resume it without memory_mib')
        todo = [(job['sector'], job['shard']) for job in prior['jobs']
                if job['status'] not in ('excluded', 'witness')]
        started = time.monotonic()
        stopped_for_witness = stop_on_witness and any(j['status'] == 'witness' for j in prior['jobs'])
        next_job = 0
        jobs_run = 0
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {}
            while futures or (next_job < len(todo) and not stopped_for_witness):
                while not stopped_for_witness and len(futures) < workers and next_job < len(todo):
                    sector, shard = todo[next_job]
                    future = pool.submit(run_attempt, root, campaign, sector, shard,
                                         seconds_per_shard, node_cap, memory_bytes)
                    futures[future] = (sector, shard)
                    next_job += 1
                    jobs_run += 1
                if not futures:
                    break
                done, _ = wait(futures, return_when=FIRST_COMPLETED)
                for future in done:
                    sector, shard = futures.pop(future)
                    record = future.result()
                    if stop_on_witness and (record.get('terminal') or {}).get('status') == 'witness':
                        attempts = sorted((root / f'jobs/{sector}/{shard:06d}').glob('attempt-*/receipt.json'))
                        checked = check_receipt(attempts[-1], root, campaign, code, sector, shard)
                        stopped_for_witness = stopped_for_witness or checked['status'] == 'witness'
                    if progress:
                        progress(record)
                # Already running attempts finish under their existing limits.
                # Unstarted shards remain pending, so the auditor cannot infer
                # a lower bound from the intentionally incomplete union.
        result = audit_run(root)
        result['last_invocation'] = {'wall_seconds': time.monotonic() - started, 'workers': workers,
                                     'jobs_run': jobs_run, 'jobs_reused': len(prior['jobs']) - len(todo),
                                     'seconds_per_shard': float(seconds_per_shard), 'node_cap': node_cap,
                                     'stop_on_witness': stop_on_witness,
                                     'stopped_for_witness': stopped_for_witness,
                                     'jobs_not_started': len(todo) - jobs_run}
        if memory_bytes is not None:
            result['last_invocation']['memory_bytes'] = memory_bytes
        write_json(root / 'result.json', result)
        return result
