"""Inspect the paper catalogue and repeat a selected exclusion with QEDist."""
import argparse
import hashlib
import json
from pathlib import Path

from cssdist import __version__
from cssdist.audit import audit_run
from cssdist.campaign import certify, write_json
from cssdist.cli import load_input

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'examples/catalogue/paper.json'


def catalogue():
    return json.loads(MANIFEST.read_text())


def checked_input(row):
    path = ROOT / row['input']
    if hashlib.sha256(path.read_bytes()).hexdigest() != row['input_sha256']:
        raise ValueError(f'Changed catalogue input for {row["id"]}')
    code = load_input(path)
    if (code.n, code.k) != (row['n'], row['k']):
        raise ValueError(f'Parameter mismatch for {row["id"]}')
    weights = {s: min((w.bit_count() for w in code.witnesses[s]), default=None)
               for s in ('X', 'Z')}
    if weights != row['witness_weights']:
        raise ValueError(f'Witness mismatch for {row["id"]}')
    if max(word.bit_count() for word in code.hx + code.hz) != row['w']:
        raise ValueError(f'Check-weight mismatch for {row["id"]}')
    relevant = [weight for sector, weight in weights.items()
                if weight is not None and (row['scope'] == 'd' or sector == 'X')]
    if row['result']['exact'] and min(relevant, default=None) != row['result']['upper']:
        raise ValueError(f'Missing matching witness for {row["id"]}')
    return code


def distance_text(row):
    result = row['result']
    if result['exact']:
        return f'{row["scope"]} = {result["lower"]}'
    return f'{result["lower"]} ≤ {row["scope"]} ≤ {result["upper"]}'


def verify(document):
    seen = {}
    for row in document['rows']:
        identity = (row['input'], row['input_sha256'])
        if row['code_id'] not in seen:
            checked_input(row)
            seen[row['code_id']] = identity
        elif seen[row['code_id']] != identity:
            raise ValueError(f'Inconsistent repeated input for {row["id"]}')
    return {'input_checks': 'PASS', 'physical_inputs': len(seen), 'table_rows': len(document['rows']),
            'scope': 'Input identities, CSS commutation, dimensions, declared symmetry and supplied witnesses.'}


def markdown(document):
    lines = [
        '# Paper catalogue and reproduction', '',
        'This catalogue follows Appendix C of the QEDist manuscript, `main_v7`, '
        f'as recorded on {document["snapshot_date"]}. It includes every row in the distance catalogue.', '',
        'The principal survey contains 95 codes, with 88 exact distances and seven unresolved intervals. '
        'The tables also include seven supplemental LP inputs, six PP codes, and two X-sector-only TT results. '
        'Two earlier-cutoff rows show the progress toward the final NM-P83 and RA-4-23N results.', '',
        '## Repeat an exclusion', '',
        'Run these commands from the source distribution or repository after installation. '
        'They list the available rows, check all physical inputs, and repeat a short exclusion.', '',
        '```sh', 'python -m pip install .', 'python -m tools.catalogue list',
        'python -m tools.catalogue verify',
        'python -m tools.catalogue run LP04-175 --output runs/catalogue/LP04-175 --seconds-per-shard 60',
        'qedist audit runs/catalogue/LP04-175', '```', '',
        'Replace `LP04-175` with a row ID below. The runner uses the recorded cutoff, symmetry, '
        'engine profile, partition and proposed-addition setting. It checks the input hash before searching '
        'and audits the resulting campaign. Weighted-check, stabilizer and disjoint-neighborhood pruning '
        'are enabled. NM-P83 uses the LP tensor-block reduction. Other rows use the CSS engine.', '',
        '`--workers` controls simultaneous workers. `--seconds-per-shard` is the limit for each partition, '
        'so the total allowance grows with the number of partitions and searched sectors. '
        '`--shards` overrides the recorded partition count for a new experiment. '
        '`--proposed-additions` enables the test for rows whose published runs predate its use. '
        '`--resume` continues unfinished partitions with their saved settings.', '',
        'For the two X-sector-only TT rows, the public certification command checks both sectors. '
        'The comparison in `catalogue-replay.json` uses the X-sector bound and its search time. '
        'The campaign also reports the separate Z-sector result.', '',
        'Each fresh run records its actual engine sources, compiler, configuration and measurements. '
        'The published times below remain the measurements from the preserved executions. '
        'The separate manuscript reproduction archive contains the frozen engines and execution records. '
        '[Reproduction archive](reproduction.md)', '',
        '## Reading the tables', '',
        '`W` is the requested exclusion cutoff. A completed exclusion through `W` gives a lower bound '
        'of `W + 1`. A matching nontrivial logical witness establishes an exact distance. '
        'The input files contain the available physical witnesses. For unresolved rows, the cited '
        'upper bound and the weight of the lightest supplied witness are recorded separately '
        'in the JSON manifest.', '',
        'Times are sums of worker search times, expressed on the Apple M3 Pro reference scale. '
        'They exclude input preparation and compilation. Cluster measurements use the recorded '
        'processor conversion factor. The 82 refreshed exclusions use the median of three repetitions. '
        'The other rows retain their individual timing conventions in the manifest.', '',
        'Every row uses the weighted bound. Proposed-addition pruning was enabled for 101 of the '
        '112 recorded row configurations. Three PP and eight TT rows retain earlier measurements '
        'with that test disabled. New searches through the main QEDist CLI enable it by default.', '',
        'All 63 matched exclusions in the catalogue timing comparison improved, with a median speedup '
        'of 4.94×. That comparison adds weighted-check and proposed-addition pruning together with '
        'updated check selection. The paper reports the isolated effect of the weighted bound in '
        'its separate controlled comparison.', '',
        'Source status is U for an upper bound or estimate, E for an exact distance, ? for unclear '
        'certification, N for no reported distance, I for a rigorous interval, X for a source discrepancy, '
        'and D for a diagnostic input. Results in X rows apply to the printed matrices.', '',
        '`P` is the cyclic period, `w` the maximum binary check weight, and `w_c` the maximum '
        'column weight. Product and non-Abelian construction groups are written explicitly. '
        'An em dash marks a quantity omitted from that paper table.', '',
        '## Catalogue', '',
    ]
    previous = None
    for row in document['rows']:
        collection = 'principal' if row['collection'] == 'earlier cutoff' else row['collection']
        group = (collection, row['family'])
        if group != previous:
            if previous is not None:
                lines.append('')
            lines += [f'### {row["family"]} ({collection})', '',
                      '| ID and input | (n, k) | P or group | w | w_c | Source distance | Result | W | Search time (s) |',
                      '|---|---|---|---:|---:|---|---|---:|---:|']
            previous = group
        source = f'{row["source_distance"]} ({row["source_status"]})'
        links = ' '.join(f'[source {i + 1}]({url})' for i, url in enumerate(row['source_urls']))
        source += ' ' + links if links else ''
        group_display = row.get('group_display', str(row['period']))
        if row['family'] == 'Non-Abelian LP':
            group_display += f' (P={row["period"]})'
        lines.append(f'| [{row["id"]}](../{row["input"]}) | ({row["n"]}, {row["k"]}) | '
                     f'{group_display} | {row["w"]} | {row.get("w_c", "—")} | '
                     f'{source} | {distance_text(row)} | '
                     f'{row["recommended_cutoff"]} | {row["paper_timing"]["display_seconds"]} |')
    lines += ['', '## Machine-readable records', '',
              'The manifest records physical input hashes, supplied witness weights, paper results, '
              'search configurations, timing provenance and manuscript source hashes. '
              '[Catalogue manifest](../examples/catalogue/paper.json)', '',
              'Regenerate this page after updating the manifest.', '',
              '```sh', 'python -m tools.catalogue markdown --output docs/catalogue.md', '```', '']
    return '\n'.join(lines)


def run(row, args):
    code = checked_input(row)
    cfg = row['configuration']
    output = args.output.resolve()
    shards = cfg['shards'] if args.shards is None else args.shards
    proposed = args.proposed_additions
    if proposed is None and not args.resume:
        proposed = cfg.get('proposed_additions', False)
    result = certify(code, output, cutoff=cfg['cutoff'], profile=row['profile'],
                     shards=shards, split_weight=cfg['split_weight'], workers=args.workers,
                     seconds_per_shard=args.seconds_per_shard, resume=args.resume,
                     use_symmetry=cfg['use_symmetry'], coset_pruning=cfg['coset_pruning'],
                     proposed_additions=proposed, large_capacity=args.large_capacity)
    checked = audit_run(output)
    if checked['sector_bounds'] != result['sector_bounds'] or checked['status'] != result['status']:
        raise ValueError('Campaign audit disagrees with the search summary')
    target_sectors = ['X'] if row['scope'] == 'd_X' else ['X', 'Z']
    lower = min(checked['sector_bounds'][s]['lower'] for s in target_sectors)
    upper = min((checked['sector_bounds'][s]['upper'] for s in target_sectors
                 if checked['sector_bounds'][s]['upper'] is not None), default=None)
    search_seconds = 0.0
    scope_seconds = 0.0
    for path in output.glob('jobs/*/*/attempt-*/receipt.json'):
        receipt = json.loads(path.read_text())
        terminal = receipt.get('terminal') or {}
        seconds = terminal.get('seconds', 0.0)
        search_seconds += seconds
        if row['scope'] == 'd' or receipt['sector'] == 'X':
            scope_seconds += seconds
    replay = {'schema': 'qedist.catalogue-replay.v1', 'id': row['id'],
              'package_version': __version__, 'paper_result': row['result'],
              'paper_timing': row['paper_timing'], 'scope': row['scope'],
              'fresh_lower': lower, 'fresh_upper': upper,
              'paper_lower_bound_reached': lower >= row['result']['lower'],
              'fresh_exact': lower == upper,
              'native_search_seconds_all_recorded_attempts': search_seconds,
              'scope_search_seconds_all_recorded_attempts': scope_seconds,
              'last_invocation': result['last_invocation']}
    write_json(output / 'catalogue-replay.json', replay)
    print(json.dumps(replay, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('list')
    commands.add_parser('verify')
    render = commands.add_parser('markdown')
    render.add_argument('--output', required=True, type=Path)
    replay = commands.add_parser('run')
    replay.add_argument('case')
    replay.add_argument('--output', type=Path, required=True)
    replay.add_argument('--seconds-per-shard', type=float, default=60)
    replay.add_argument('--workers', type=int, default=1)
    replay.add_argument('--shards', type=int)
    replay.add_argument('--resume', action='store_true')
    replay.add_argument('--proposed-additions', action=argparse.BooleanOptionalAction, default=None,
                        help='Use the paper setting for a new run, or the saved setting on resume')
    replay.add_argument('--large-capacity', action=argparse.BooleanOptionalAction, default=None,
                        help='Force expanded storage; default selects by input and preserves saved engines')
    args = parser.parse_args()
    document = catalogue()
    if args.command == 'list':
        for row in document['rows']:
            print(f'{row["id"]:24s} ({row["n"]},{row["k"]})  {distance_text(row)}  '
                  f'W={row["recommended_cutoff"]}  profile={row["profile"]}')
    elif args.command == 'verify':
        print(json.dumps(verify(document), indent=2))
    elif args.command == 'markdown':
        args.output.write_text(markdown(document))
    else:
        rows = {row['id']: row for row in document['rows']}
        if args.case not in rows:
            parser.error('Unknown case. Use python -m tools.catalogue list.')
        run(rows[args.case], args)


if __name__ == '__main__':
    main()
