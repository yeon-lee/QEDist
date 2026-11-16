"""Compare cyclic, diagonal and full generator actions on identical CSS inputs."""
import argparse
import copy
import json
import math
from pathlib import Path
import statistics
import time

from cssdist import CSSCode, __version__
from cssdist.audit import audit_run
from cssdist.campaign import certify, write_json
from cssdist.cli import load_input
from cssdist.engine import build
from cssdist.symmetry import orbit_representatives


CASES = {
    'bb144': ('examples/symmetry/bb144.json', 11),
    'pp512': ('examples/symmetry/pp512.json', 16),
    'toric3d7': ('examples/symmetry/toric3d7.json', 6),
}


def actions(code):
    generators = copy.deepcopy(code.symmetry_generators)
    if code.period > 1:
        cyclic = [(q // code.period) * code.period + (q + 1) % code.period for q in range(code.n)]
        if cyclic not in generators:
            generators.append(cyclic)
    if not generators:
        raise ValueError('This comparison requires declared symmetry generators')
    diagonal = list(range(code.n))
    for generator in generators:
        diagonal = [generator[q] for q in diagonal]
    return {'cyclic': [generators[0]], 'diagonal': [diagonal], 'product': generators}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--cases', nargs='+', choices=list(CASES), default=list(CASES))
    parser.add_argument('--repeats', type=int, default=5)
    parser.add_argument('--seconds', type=float, default=120)
    parser.add_argument('--cutoff', type=int, help='Override the per-example cutoffs for a short pilot')
    args = parser.parse_args()
    if args.repeats < 1 or not math.isfinite(args.seconds) or args.seconds <= 0:
        parser.error('Use positive repeat and time budgets')
    args.out.mkdir(parents=True, exist_ok=False)
    # Exclude compilation from the measured campaigns by warming the shared cache.
    build_record = build(args.out/'engine-warmup')
    report = {'package_version': __version__, 'build': build_record, 'cases': [],
              'settings': {'shards': 1, 'workers': 1, 'split_weight': 1,
                           'seconds_per_shard': args.seconds, 'repeats': args.repeats},
              'timing': 'Native search excludes input validation. Process time includes native validation. '
                        'Campaign time includes Python validation, preparation and auditing, with a warm compiler cache.'}
    for name in args.cases:
        filename, cutoff = CASES[name]
        if args.cutoff is not None:
            cutoff = args.cutoff
        code = load_input(filename)
        modes = actions(code)
        entry = {'name': name, 'input': filename, 'n': code.n, 'k': code.k, 'cutoff': cutoff,
                 'runs': {mode: [] for mode in modes}}
        report['cases'].append(entry)
        for repeat in range(args.repeats):
            # Rotate the order across repetitions to reduce order effects.
            names = list(modes)
            order = names[repeat % len(names):] + names[:repeat % len(names)]
            for mode in order:
                data = copy.deepcopy(code.document)
                data['cyclic_period'] = 1
                data['symmetry_generators'] = modes[mode]
                folder = args.out/name/mode/f'{repeat:02d}'
                start = time.monotonic()
                candidate = CSSCode(data)
                result = certify(candidate, folder, cutoff=cutoff, split_weight=1,
                                 seconds_per_shard=args.seconds)
                checked = audit_run(folder)
                wall = time.monotonic() - start
                if checked['sector_bounds'] != result['sector_bounds']:
                    raise ValueError('Fresh audit disagrees with the campaign')
                receipts = [json.loads(path.read_text()) for path in folder.glob('jobs/*/*/attempt-*/receipt.json')]
                native_times = [r['terminal']['seconds'] for r in receipts if r['terminal'] is not None]
                manifest = json.loads((folder/'campaign.json').read_text())
                entry['environment'] = manifest['environment']
                measurement = {'repetition': repeat, 'campaign_seconds': wall,
                    'process_seconds': sum(r['wall_seconds'] for r in receipts),
                    'native_seconds': sum(native_times) if len(native_times) == len(receipts) else None,
                    'nodes': checked['nodes_in_recorded_attempts'],
                    'roots_per_sector': len(orbit_representatives(candidate.n, candidate.symmetry_generators)),
                    'input_sha256': manifest['input_sha256'], 'status': checked['status'],
                    'all_excluded': checked['all_required_shards_excluded'],
                    'bounds': [checked['distance_lower_bound'], checked['distance_upper_bound']]}
                entry['runs'][mode].append(measurement)
                write_json(args.out/'summary.json', report)
                print(name, mode, repeat, json.dumps(measurement), flush=True)
        hashes = [r['input_sha256'] for runs in entry['runs'].values() for r in runs]
        if any(h != hashes[0] for h in hashes):
            raise ValueError('The comparison changed the physical matrices')
        entry['medians'] = {mode: {key: statistics.median(r[key] for r in runs)
                                   if all(r[key] is not None for r in runs) else None
                          for key in ('native_seconds', 'process_seconds', 'campaign_seconds', 'nodes')}
                            for mode, runs in entry['runs'].items()}
        write_json(args.out/'summary.json', report)


if __name__ == '__main__':
    main()
