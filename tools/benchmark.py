#!/usr/bin/env python3
"""Run a small example benchmark with the current QEDist engines."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time

from cssdist import __version__
from cssdist.audit import audit_run
from cssdist.campaign import certify, write_json
from cssdist.cli import load_input
from cssdist.code import digest
from cssdist.engine import DEFAULT_PROFILE, PROFILES

CASES = [
    ('steane', 'examples/steane.json', 2, 'known small code'),
    ('independent_hgp', 'examples/independent_hgp.json', 1, 'synthetic HGP, unequal constituents and sector distances'),
    ('rank_deficient', 'examples/rank_deficient_lp.json', 1, 'synthetic LP without a full-rank constituent'),
    ('independent_qc', 'examples/independent_qc.json', 3, 'synthetic cyclic LP, unequal polynomial constituents'),
    ('polynomial_20', 'examples/catalogue/lp-f2-20-4-3.json', 2, 'own paper, polynomial constituent'),
    ('binary_320', 'examples/catalogue/lp-f2-320-64-10.json', 9, 'own paper, binary polynomial constituent'),
    ('quaternary_476', 'examples/catalogue/lp-f4-476-56-14.json', 13, 'own paper, odd-period quaternary input'),
    ('published_1122', 'examples/catalogue/lp-f2-1122-148-20-partial.json', 19, 'Zhou et al. published instance III; no complete regular frame'),
    ('quaternary_1088', 'examples/catalogue/lp-f4-1088-128-22-w10-f22.json', 21, 'own paper, principal quaternary LP'),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=Path('runs/pilot'))
    parser.add_argument('--summary', type=Path, default=Path('benchmarks/pilot.json'))
    parser.add_argument('--seconds-per-shard', type=float, default=30)
    parser.add_argument('--shards', type=int, default=4)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--profile', choices=list(PROFILES), default=DEFAULT_PROFILE)
    parser.add_argument('--proposed-additions', action=argparse.BooleanOptionalAction, default=None,
                        help='Enabled for new searches, inherits each saved setting on resume')
    parser.add_argument('--large-capacity', action=argparse.BooleanOptionalAction, default=None,
                        help='Force expanded storage; default selects by input and preserves saved engines')
    parser.add_argument('--cases', nargs='+', choices=[c[0] for c in CASES])
    args = parser.parse_args()
    if args.summary.exists() and not args.resume:
        parser.error('Summary exists; use --resume or choose a new summary file')
    report = {'schema': 'cssdist.benchmark.v1', 'package_version': __version__,
              'started_utc': datetime.now(timezone.utc).isoformat(),
              'budget_per_shard_seconds': args.seconds_per_shard,
              'shards': args.shards, 'workers': args.workers, 'cases': [],
              'native_profile': args.profile,
              'proposed_additions': args.proposed_additions,
              'large_capacity': args.large_capacity,
              'scope': 'Nine-example benchmark. The complete paper catalogue is provided by tools.catalogue.'}
    started = time.monotonic()
    for case, path, cutoff, role in CASES:
        if args.cases and case not in args.cases:
            continue
        root = args.out / case
        input_path = Path(__file__).resolve().parents[1] / path
        code = load_input(input_path)
        print(f'{case}: n={code.n}, k={code.k}, exclusion through {cutoff}', flush=True)
        result = certify(code, root, cutoff=cutoff, shards=args.shards, workers=args.workers,
                         seconds_per_shard=args.seconds_per_shard,
                         resume=args.resume and root.exists(), profile=args.profile,
                         proposed_additions=args.proposed_additions,
                         large_capacity=args.large_capacity)
        checked = audit_run(root)
        if checked['status'] != result['status'] or checked['sector_bounds'] != result['sector_bounds']:
            raise ValueError('Independent audit disagrees with the search summary')
        campaign = json.loads((root / 'campaign.json').read_text())
        build = json.loads((root / 'engine/build.json').read_text())
        record = {'case': case, 'input': path, 'input_file_sha256': digest(input_path.read_bytes()),
                  'role': role, 'campaign': str(root), 'environment': campaign['environment'],
                  'proposed_additions': campaign['config'].get('proposed_additions', False),
                  'large_capacity': campaign['config'].get('large_capacity'),
                  'build': build, 'result': result}
        report['cases'].append(record)
        policies = {case['proposed_additions'] for case in report['cases']}
        report['proposed_additions'] = policies.pop() if len(policies) == 1 else None
        report['wall_seconds_this_invocation'] = time.monotonic() - started
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        write_json(args.summary, report)
        print(f"  {result['status']}: {result['distance_lower_bound']} <= d <= "
              f"{result['distance_upper_bound']}; {result['nodes_in_recorded_attempts']} nodes; "
              f"{result['last_invocation']['wall_seconds']:.2f} s", flush=True)
    report['finished_utc'] = datetime.now(timezone.utc).isoformat()
    write_json(args.summary, report)


if __name__ == '__main__':
    main()
