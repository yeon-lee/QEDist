"""Read-only validation of inputs, witnesses and exhaustive-run coverage.

Completion receipts are execution evidence, not per-node formal proof objects.
This checker does not invoke the search engine or trust a stored summary.
"""
import json
import math
from pathlib import Path

from .algebra import basis, permute, remainder, support, vector
from .code import CSSCode, digest
from .engine import (DEFAULT_PROFILE, NATIVE_INTEGER_MAX, canonical_profile, check_limits,
                     audited_source_hashes, profile_options, uses_dynamic_storage,
                     validate_memory_bytes)
from .lp_blocks import layout, search_problems


def require(condition, message):
    if not condition:
        raise ValueError(message)


def require_object(value, name):
    """Reject malformed JSON containers before accessing proof fields."""
    require(isinstance(value, dict), f'{name} must be a JSON object')
    return value


def configuration(code, cutoff, shards, split_weight, use_symmetry=True, coset_pruning=True,
                  profile=DEFAULT_PROFILE, proposed_additions=False, large_capacity=None):
    profile = canonical_profile(profile)
    check_limits(code, cutoff, profile, legacy=large_capacity is False)
    require(type(shards) is int and 1 <= shards <= 1000000, 'Invalid shard count')
    require(type(split_weight) is int and 1 <= split_weight <= cutoff, 'Invalid partition depth')
    require(type(use_symmetry) is bool and type(coset_pruning) is bool, 'Invalid boolean option')
    require(type(proposed_additions) is bool, 'proposed_additions must be a boolean')
    require(large_capacity is None or type(large_capacity) is bool,
            'large_capacity must be a boolean or None')
    exchange = use_symmetry and code.exchange is not None
    result = {'cutoff': cutoff, 'shards': shards, 'split_weight': split_weight,
            'use_symmetry': use_symmetry, 'coset_pruning': coset_pruning,
            'period': code.period if use_symmetry else 1,
            'sector_exchange_used': exchange, 'sectors': ['Z'] if exchange else ['X', 'Z']}
    result['native_profile'] = profile
    if large_capacity is not None:
        result['large_capacity'] = large_capacity
    if proposed_additions:
        result['proposed_additions'] = True
    if use_symmetry and code.symmetry_generators:
        result['generator_symmetry'] = True
    if profile == 'lp':
        sa, sc, fiber = layout(code)
        result['lp_anchor_site'] = sa * sc * fiber
    return result


def command(config, sector, shard, seconds, node_cap, memory_bytes=None):
    args = ['engine/exact', f'inputs/{sector}.mat', str(config['period']), str(config['cutoff']),
            str(float(seconds)), '--shard', str(shard), str(config['shards']),
            str(config['split_weight']), str(node_cap)]
    args += profile_options(config.get('native_profile'), config.get('proposed_additions', False))
    if memory_bytes is not None:
        args.append(f'memory-bytes={validate_memory_bytes(memory_bytes)}')
    if config.get('generator_symmetry'):
        args.append(f'symmetry-file=inputs/{sector}.symmetry')
    if 'lp_anchor_site' in config:
        anchor_site = config['lp_anchor_site'] if sector.endswith('-anchor') else 0
        args.append(f'anchor-site={anchor_site}')
    return args if config['coset_pruning'] else args + ['no-coset']


def _read(path, root):
    require(path.resolve().is_relative_to(root.resolve()) and not path.is_symlink(),
            f'Proof path escapes campaign: {path}')
    return path.read_bytes()


def events_from_stdout(data, allow_truncated=False):
    lines = data.decode('utf-8').splitlines()
    events = []
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            if allow_truncated and i == len(lines) - 1:
                break
            raise ValueError('Malformed native transcript') from None
        require(isinstance(event, dict) and event.get('event') in ('witness', 'result', 'resource_limit'),
                'Unexpected native event')
        events.append(event)
    return events


def resource_failure(events, returncode, memory_bytes=None):
    """Recognize an allocation failure without granting exclusion credit."""
    resources = [event for event in events if event['event'] == 'resource_limit']
    if not resources:
        return None
    require(len(events) == 1 and returncode == 75, 'Invalid resource-limit transcript')
    event = resources[0]
    require(event.get('resource') == 'memory' and type(event.get('limit_bytes')) is int
            and event['limit_bytes'] == (memory_bytes or 0), 'Invalid memory-limit event')
    peak = event.get('peak_bytes')
    require(type(peak) is int and peak >= 0 and (memory_bytes is None or peak <= memory_bytes),
            'Invalid peak native allocation')
    return event


def check_parity_metadata(final, code, config, sector, problem=None):
    """Independently verify the algebraic cutoff reduction.

    The native positive certificate is an XOR of original physical check rows.
    Gaussian row-space membership independently determines when it must exist.
    Return True only for the zero-search exclusion of cutoff one.
    """
    canonical_profile(config.get('native_profile'))
    if problem is not None and problem.stripes:
        n, checks = problem.n, problem.checks
        even = remainder((1 << n) - 1, basis(checks)) == 0
    else:
        n = code.n
        physical_sector = problem.sector if problem else sector
        checks, _, _ = code.sector(physical_sector)
        even = code.kernel_even_weight(physical_sector)
    effective = config['cutoff'] - (config['cutoff'] % 2 if even else 0)
    require(final.get('kernel_even') is even and final.get('parity_cutoff_enabled') is True,
            'Native kernel parity differs from the physical row-space test')
    require(type(final.get('effective_W')) is int and final['effective_W'] == effective,
            'Invalid parity-reduced cutoff')
    trivial = effective == 0
    require(final.get('parity_trivial_exclusion') is trivial, 'Invalid algebraic exclusion flag')
    rows = final.get('parity_certificate_rows')
    require(type(rows) is list and all(type(i) is int and 0 <= i < len(checks) for i in rows)
            and rows == sorted(set(rows)), 'Invalid parity certificate row indices')
    combined = 0
    for i in rows:
        combined ^= checks[i]
    require(combined == ((1 << n) - 1 if even else 0)
            and (even or not rows), 'Parity certificate does not sum to the all-ones functional')
    if trivial:
        require(final.get('nodes') == 0 and final.get('status') == 'excluded'
                and all(final.get(k, 0) == 0 for k in ('frontier_seen','frontier_owned','common_nodes')),
                'Invalid zero-search parity exclusion')
    return trivial


def check_profile_metadata(final, config):
    """Do not accept a weighted receipt produced with a different runtime policy."""
    canonical_profile(config.get('native_profile'))
    expected = {'fractional_mode': 2, 'repair_depth': 8, 'even_repair_cap': 4,
                'fractional_placement': 'before_mis'}
    require(all(type(final.get(k)) is type(v) and final[k] == v for k, v in expected.items()),
            'Native weighted profile settings differ from the frozen policy')
    enabled = config.get('proposed_additions', False)
    require(type(enabled) is bool and final.get('proposed_additions', False) is enabled,
            'Native proposed-addition setting differs from the campaign')
    if enabled:
        counts = [final.get(key) for key in
                  ('proposed_candidates', 'proposed_prunes', 'proposed_prefix_prunes')]
        require(all(type(count) is int and count >= 0 for count in counts)
                and counts[0] >= counts[1] >= counts[2],
                'Invalid proposed-addition counters')


def check_symmetry_metadata(final, generators, representatives):
    require(type(final.get('symmetry_generators')) is int
            and final['symmetry_generators'] == len(generators), 'Wrong symmetry generator count')
    roots = final.get('root_representatives')
    require(type(roots) is list and all(type(site) is int for site in roots)
            and roots == representatives, 'Native roots differ from verified joint orbits')


def check_receipt(path, root, campaign, code, sector, shard, problem=None):
    receipt = require_object(json.loads(_read(path, root)), 'Receipt')
    config = require_object(campaign['config'], 'Campaign configuration')
    if problem is None:
        problem = search_problems(code, config)[sector]
    representatives = problem.roots(config['period'])
    roots = len(representatives)
    require(receipt.get('schema') == 'cssdist.receipt.v1', 'Unknown receipt schema')
    require(receipt.get('code_sha256') == code.fingerprint, 'Receipt code mismatch')
    require(receipt.get('input_sha256') == campaign['input_sha256'][sector], 'Receipt matrix mismatch')
    if config.get('generator_symmetry'):
        require(receipt.get('symmetry_sha256') == campaign['symmetry_sha256'][sector],
                'Receipt symmetry mismatch')
    require(receipt.get('source_sha256') == campaign['engine']['source_sha256'], 'Receipt source mismatch')
    require(receipt.get('executable_sha256') == campaign['engine']['executable_sha256'], 'Receipt executable mismatch')
    require(receipt.get('sector') == sector and type(receipt.get('shard')) is int
            and receipt['shard'] == shard, 'Receipt job identity mismatch')
    limits = require_object(receipt['limits'], 'Receipt limits')
    seconds, cap = limits['seconds'], limits['nodes']
    memory_bytes = validate_memory_bytes(limits.get('memory_bytes'))
    require(memory_bytes is None or uses_dynamic_storage(campaign['engine']['source_sha256']),
            'Saved engine has no memory-budget support')
    require(type(seconds) in (int, float) and math.isfinite(seconds) and seconds > 0, 'Invalid time budget')
    require(type(cap) is int and 1 <= cap < 2**64, 'Invalid node budget')
    require(receipt.get('command') == command(config, sector, shard, seconds, cap, memory_bytes),
            'Receipt command mismatch')
    stdout, stderr = _read(path.parent / 'stdout.jsonl', root), _read(path.parent / 'stderr.txt', root)
    require(digest(stdout) == receipt.get('stdout_sha256') and digest(stderr) == receipt.get('stderr_sha256'),
            'Transcript checksum mismatch')
    timed_out = receipt.get('hard_timeout')
    require(type(timed_out) is bool and type(receipt.get('returncode')) is int, 'Invalid process status')
    events = events_from_stdout(stdout, timed_out)
    resource = resource_failure(events, receipt['returncode'], memory_bytes)
    if resource is not None:
        require(uses_dynamic_storage(campaign['engine']['source_sha256']) and not timed_out
                and receipt.get('terminal') == resource, 'Invalid allocation-failure receipt')
        return {'status': 'incomplete', 'nodes': None, 'witnesses': [], 'terminal': resource,
                'resource_limit': 'memory', 'receipt': str(path.relative_to(root)),
                'receipt_sha256': digest(_read(path, root))}
    witnesses, finals = [], []
    for event in events:
        if event['event'] == 'witness':
            word = vector(event.get('support'), problem.n)
            physical = problem.physical_witness(code, word)
            require(type(event.get('weight')) is int and event['weight'] == word.bit_count()
                    and word.bit_count() <= config['cutoff'], 'Witness weight mismatch')
            witnesses.append(physical)
        else:
            finals.append(event)
    require(len(finals) <= 1 and (not finals or events[-1] == finals[0]), 'Invalid terminal-result ordering')
    final = finals[0] if finals else None
    require(receipt.get('terminal') == final, 'Stored terminal result differs from transcript')
    nodes = 0
    parity_trivial = False
    if final is not None:
        if config.get('generator_symmetry'):
            check_symmetry_metadata(final, problem.generators, representatives)
        branch_end = NATIVE_INTEGER_MAX if uses_dynamic_storage(campaign['engine']['source_sha256']) else 64
        expected = {'W': config['cutoff'], 'root': 0, 'branch_begin': 0, 'branch_end': branch_end,
                    'shard': shard, 'shards': config['shards'], 'split_weight': config['split_weight']}
        if 'lp_anchor_site' in config:
            expected['anchor_site'] = problem.anchor_site
        require(all(type(final.get(k)) is int and final[k] == v for k, v in expected.items()),
                'Terminal cutoff or partition mismatch')
        require(final.get('partition') == 'hash_prefix_v1'
                and final.get('coset_pruning') is config['coset_pruning'], 'Terminal search mode mismatch')
        for key in ('nodes', 'roots_completed', 'frontier_seen', 'frontier_owned', 'common_nodes'):
            require(type(final.get(key)) is int and final[key] >= 0, 'Invalid terminal count')
        require(0 <= final['roots_completed'] <= roots, 'Invalid completed-root count')
        require(0 <= final['frontier_owned'] <= final['frontier_seen'] <= final['common_nodes'] <= final['nodes'],
                'Invalid frontier counts')
        require(isinstance(final.get('frontier_digest'), str) and final['frontier_digest'].isdigit()
                and 0 <= int(final['frontier_digest']) < 2**64, 'Invalid frontier digest')
        require(type(final.get('seconds')) in (int, float) and math.isfinite(final['seconds'])
                and final['seconds'] >= 0, 'Invalid elapsed time')
        nodes = final['nodes']
        check_profile_metadata(final, config)
        parity_trivial = check_parity_metadata(final, code, config, sector, problem)
    status = 'incomplete'
    if timed_out:
        require(receipt['returncode'] != 0, 'Hard timeout cannot report normal completion')
    elif receipt['returncode'] == 0:
        require(final is not None and final.get('status') == 'excluded'
                and len(events) == 1 and not witnesses, 'Successful process lacks a clean exclusion result')
        require(final['roots_completed'] == roots, 'Incomplete root coverage')
        require((0 < nodes <= cap) or (nodes == 0 and parity_trivial),
                'Exclusion exceeded its node budget or lacks a valid algebraic certificate')
        status = 'excluded'
    elif receipt['returncode'] == 10:
        require(final is not None and final.get('status') == 'witness' and witnesses,
                'Witness exit status without a valid witness')
        status = 'witness'
    elif receipt['returncode'] == 75:
        require(final is not None and final.get('status') == 'incomplete' and not witnesses,
                'Invalid incomplete result')
    else:
        raise ValueError(f'Engine process failed with exit status {receipt["returncode"]}: {path}')
    return {'status': status, 'nodes': nodes, 'witnesses': witnesses, 'terminal': final,
            'receipt': str(path.relative_to(root)), 'receipt_sha256': digest(_read(path, root))}


def audit_run(directory):
    root = Path(directory).resolve()
    campaign = require_object(json.loads(_read(root / 'campaign.json', root)), 'Campaign')
    require(campaign.get('schema') == 'cssdist.campaign.v1', 'Unknown campaign schema')
    code = CSSCode(json.loads(_read(root / 'code.json', root)))
    require(campaign.get('code_sha256') == code.fingerprint, 'Campaign code mismatch')
    cfg = require_object(campaign['config'], 'Campaign configuration')
    require_object(campaign['engine'], 'Campaign engine')
    require_object(campaign['input_sha256'], 'Campaign input hashes')
    profile = canonical_profile(cfg.get('native_profile'))
    archived_sources = audited_source_hashes(root / 'engine', profile,
                                              allow_cyclic_01=not cfg.get('generator_symmetry'),
                                              proposed_additions=cfg.get('proposed_additions', False))
    check_limits(code, cfg['cutoff'], profile, legacy=not uses_dynamic_storage(archived_sources))
    if 'large_capacity' in cfg:
        require(type(cfg['large_capacity']) is bool
                and cfg['large_capacity'] == uses_dynamic_storage(archived_sources),
                'Capacity setting differs from the saved engine')
    expected = configuration(code, cfg['cutoff'], cfg['shards'], cfg['split_weight'],
                             cfg['use_symmetry'], cfg['coset_pruning'], profile,
                             cfg.get('proposed_additions', False), cfg.get('large_capacity'))
    expected['native_profile'] = cfg['native_profile']
    require(cfg == expected, 'Campaign declares unverified symmetry or unsupported configuration')
    require(archived_sources == campaign['engine']['source_sha256'],
            'Search source differs from this package version')
    build_bytes = _read(root / 'engine/build.json', root)
    require(digest(build_bytes) == campaign['engine']['build_sha256'], 'Build-record checksum mismatch')
    build = require_object(json.loads(build_bytes), 'Build record')
    require_object(build['identity'], 'Build identity')
    binary = digest(_read(root / 'engine/exact', root))
    require(build.get('executable_sha256') == binary == campaign['engine']['executable_sha256'],
            'Executable checksum mismatch')
    require(build['identity']['source_sha256'] == archived_sources, 'Build source identity mismatch')
    problems = search_problems(code, cfg)
    require(set(campaign['input_sha256']) == set(problems), 'Campaign search matrices are missing or unexpected')
    for name, problem in problems.items():
        physical = _read(root / f'inputs/{name}.mat', root)
        require(physical == problem.text().encode(), 'Native matrix differs from physical CSS input')
        require(digest(physical) == campaign['input_sha256'][name], 'Native matrix checksum mismatch')
    if cfg.get('generator_symmetry'):
        symmetry_hashes = require_object(campaign.get('symmetry_sha256'), 'Symmetry input hashes')
        require(set(symmetry_hashes) == set(problems), 'Missing or unexpected symmetry inputs')
        for name, problem in problems.items():
            physical = _read(root / f'inputs/{name}.symmetry', root)
            require(physical == problem.symmetry_text().encode(),
                    'Native generators differ from verified physical symmetries')
            require(digest(physical) == symmetry_hashes[name], 'Symmetry input checksum mismatch')

    best = code.upper_witnesses()
    lower = {'X': 1, 'Z': 1}
    jobs, total_nodes = [], 0
    all_node_counts_reported = True
    excluded_problems = set()
    for name, problem in problems.items():
        sector = problem.sector
        completed = []
        for shard in range(cfg['shards']):
            attempts = sorted((root / f'jobs/{name}/{shard:06d}').glob('attempt-*/receipt.json'))
            checked = [check_receipt(p, root, campaign, code, name, shard, problem) for p in attempts]
            total_nodes += sum(r['nodes'] or 0 for r in checked)
            all_node_counts_reported = all_node_counts_reported and all(r['nodes'] is not None for r in checked)
            for record in checked:
                for v in record['witnesses']:
                    best[sector] = min(best[sector], v, key=lambda v: (v.bit_count(), v))
            exclusions = [r for r in checked if r['status'] == 'excluded']
            witnesses = [r for r in checked if r['witnesses']]
            require(not (exclusions and witnesses), 'Exclusion contradicts an independently checked witness')
            chosen = exclusions[-1] if exclusions else witnesses[-1] if witnesses else checked[-1] if checked else None
            if exclusions:
                completed.append(chosen['terminal'])
            job = {'sector': name, 'shard': shard, 'attempts': len(checked),
                   'status': chosen['status'] if chosen else 'pending'}
            if name != sector:
                job['physical_sector'] = sector
            if chosen:
                job.update({k: chosen[k] for k in ('receipt', 'receipt_sha256', 'nodes')})
                if chosen.get('resource_limit'):
                    job['resource_limit'] = chosen['resource_limit']
            jobs.append(job)
        if len(completed) == cfg['shards']:
            first = completed[0]
            require(all(all(r[key] == first[key] for key in ('frontier_seen', 'frontier_digest', 'common_nodes'))
                        for r in completed), 'Shards traversed different common frontiers')
            require(sum(r['frontier_owned'] for r in completed) == first['frontier_seen'],
                    'Shard union does not cover the complete frontier')
            excluded_problems.add(name)
    for sector in cfg['sectors']:
        if all(name in excluded_problems for name, problem in problems.items() if problem.sector == sector):
            lower[sector] = cfg['cutoff'] + 1
    all_excluded = len(excluded_problems) == len(problems)
    if cfg['sector_exchange_used']:
        lower['X'] = lower['Z']
        v = permute(best['Z'], code.exchange)
        require(code.is_logical(v, 'X'), 'Sector-exchange witness failed')
        best['X'] = min(best['X'], v, key=lambda v: (v.bit_count(), v))
    upper = {s: v.bit_count() for s, v in best.items()}
    require(all(lower[s] <= upper[s] for s in ('X', 'Z')), 'Lower bound contradicts an explicit witness')
    lo, hi = min(lower.values()), min(upper.values())
    has_witness = any(job['status'] == 'witness' for job in jobs)
    status = ('EXACT_DISTANCE' if lo == hi else 'CERTIFIED_INTERVAL' if all_excluded
              else 'WITNESS_FOUND' if has_witness else 'INCOMPLETE')
    return {'schema': 'cssdist.result.v1', 'status': status, 'n': code.n, 'k': code.k,
            'code_sha256': code.fingerprint, 'campaign_sha256': digest(_read(root / 'campaign.json', root)),
            'distance_lower_bound': lo, 'distance_upper_bound': hi,
            'exact_distance': lo if lo == hi else None,
            'sector_bounds': {s: {'lower': lower[s], 'upper': upper[s], 'witness': support(best[s])}
                              for s in ('X', 'Z')},
            'cutoff': cfg['cutoff'], 'all_required_shards_excluded': all_excluded,
            'sector_exchange_used': cfg['sector_exchange_used'], 'effective_period': cfg['period'],
            'nodes_in_recorded_attempts': total_nodes if all_node_counts_reported else None,
            'jobs': jobs,
            'evidence_kind': 'Completed exhaustive execution records, not per-node formal proof objects.'}
