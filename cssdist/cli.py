"""Command-line entry point. All proof-critical validation uses exceptions."""
import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
from tempfile import NamedTemporaryFile

from . import __version__
from .audit import audit_run
from .campaign import certify
from .calibration import calibrate, audit_calibration
from .code import CSSCode, json_bytes
from .constructors import load_lp
from .engine import DEFAULT_PROFILE, PROFILES, profile_limits
from .lp_blocks import layout, search_problems
from .portable import export_bundle, audit_bundle
from .formats import import_css_matrices, matrix_market_text
from .circuit import DetectorModel, import_dem, import_stim
from .circuit_run import certify_circuit, audit_circuit
from .circuit_reduction import (reduce_detector_sector, reduce_stim_sector,
                                verify_sector_reduction)
from .stabilizer import StabilizerCode
from .stabilizer_run import certify_stabilizer, audit_stabilizer


def load_input(path):
    document = json.loads(Path(path).read_text())
    if not isinstance(document, dict):
        raise ValueError('An input must be a JSON object')
    return load_lp(document) if document.get('schema') == 'cssdist.lp.v1' else CSSCode(document)


def write_new_pair(first, second):
    """Publish both outputs with exclusive creation. Undo our first link if the second fails."""
    if first[0].resolve() == second[0].resolve():
        raise ValueError('Choose two distinct, new output paths')
    staged, published = [], []
    with ExitStack() as cleanup:
        for path, data in (first, second):
            if path.exists() or path.is_symlink():
                raise ValueError('Choose two distinct, new output paths')
            path.parent.mkdir(parents=True, exist_ok=True)
            with NamedTemporaryFile(dir=path.parent, delete=False) as stream:
                temporary = Path(stream.name)
                cleanup.callback(temporary.unlink, missing_ok=True)
                stream.write(data)
            staged.append((temporary, path))
        try:
            for temporary, path in staged:
                os.link(temporary, path)
                published.append((temporary, path))
        except OSError:
            for temporary, path in published:
                if path.exists() and path.samefile(temporary):
                    path.unlink()
            raise


def main(argv=None):
    parser = argparse.ArgumentParser(description='QEDist: exact distance certification for stabilizer codes and circuit detector/observable fault models')
    parser.add_argument('--version', action='version', version=f'QEDist {__version__}')
    commands = parser.add_subparsers(dest='action', required=True)
    stabilizer_inspect = commands.add_parser('inspect-stabilizer', help='Validate general stabilizer checks and logical witnesses')
    stabilizer_inspect.add_argument('code', type=Path)
    stabilizer_run = commands.add_parser('certify-stabilizer', help='Certify Pauli distance for general stabilizer codes')
    stabilizer_run.add_argument('code', type=Path)
    stabilizer_run.add_argument('--out', type=Path, required=True)
    stabilizer_run.add_argument('--cutoff', type=int, required=True)
    stabilizer_run.add_argument('--seconds', '--seconds-per-shard', type=float, default=30.0,
                                help='Wall-time budget for each shard attempt, after shared preparation')
    stabilizer_run.add_argument('--shards', type=int,
                                help='Number of root partitions; inherits the saved value on resume')
    stabilizer_run.add_argument('--workers', type=int, default=1,
                                help='Maximum number of shard processes running concurrently')
    stabilizer_run.add_argument('--resume', action='store_true')
    stabilizer_run.add_argument('--symmetry', action=argparse.BooleanOptionalAction, default=None,
                                help='Use verified qubit symmetries; enabled by default, inherited on resume')
    stabilizer_run.add_argument('--node-cap', type=int, default=2**64-1)
    stabilizer_run.add_argument('--memory-mib', type=float,
                                help='Optional budget for live native vector allocations, in MiB')
    stabilizer_run.add_argument('--large-capacity', action=argparse.BooleanOptionalAction, default=None,
                                help='Force expanded storage, or --no-large-capacity for the fast engine '
                                     '(default: choose from the input and cutoff)')
    stabilizer_run.add_argument('--weighted-pruning', action=argparse.BooleanOptionalAction, default=None)
    stabilizer_run.add_argument('--neutral-pruning', action=argparse.BooleanOptionalAction, default=None)
    stabilizer_run.add_argument('--compiler', default='c++')
    stabilizer_run.add_argument('--cache', type=Path)
    stabilizer_audit = commands.add_parser('audit-stabilizer', help='Recheck the Pauli expansion and its exhaustive search')
    stabilizer_audit.add_argument('directory', type=Path)
    circuit_import = commands.add_parser('import-circuit', help='Import whole Stim circuit/DEM faults as detector and observable columns')
    circuit_import.add_argument('input', type=Path)
    circuit_import.add_argument('--format', choices=['auto', 'stim', 'dem'], default='auto')
    circuit_import.add_argument('--output', type=Path, required=True)
    circuit_import.add_argument('--neutral-pairs', type=int, default=0,
                                help='Optional bounded shared-detector pair attempts for weight<=3 neutral relations')
    circuit_import.add_argument('--max-neutrals', type=int, default=10000)
    circuit_inspect = commands.add_parser('inspect-circuit', help='Validate a detector/observable fault model')
    circuit_inspect.add_argument('model', type=Path)
    circuit_reduce = commands.add_parser('reduce-circuit', help='Certify a detector-sector projection that preserves unit-fault distance')
    circuit_reduce.add_argument('model', type=Path)
    sector = circuit_reduce.add_mutually_exclusive_group(required=True)
    sector.add_argument('--keep-detectors', type=Path,
                        help='JSON list of zero-based detector indices to retain; all observables are retained')
    sector.add_argument('--stim', type=Path,
                        help='Propose a sector from Chromobius detector coordinates; exact column closure is still required')
    circuit_reduce.add_argument('--basis', choices=['auto', 'X', 'Z'], default='auto')
    circuit_reduce.add_argument('--output', type=Path, required=True)
    circuit_reduce.add_argument('--certificate', type=Path, required=True)
    reduction_audit = commands.add_parser('audit-circuit-reduction', help='Check a sector-reduction certificate without searching')
    reduction_audit.add_argument('source', type=Path)
    reduction_audit.add_argument('reduced', type=Path)
    reduction_audit.add_argument('certificate', type=Path)
    circuit_run = commands.add_parser('certify-circuit', help='Exclude undetected logical faults through a cutoff')
    circuit_run.add_argument('model', type=Path)
    circuit_run.add_argument('--out', type=Path, required=True)
    circuit_run.add_argument('--cutoff', type=int, required=True)
    circuit_run.add_argument('--seconds', type=float, default=30.0)
    circuit_run.add_argument('--node-cap', type=int, default=2**64-1)
    circuit_run.add_argument('--memory-mib', type=float,
                             help='Optional budget for live native vector allocations, in MiB')
    circuit_run.add_argument('--large-capacity', action=argparse.BooleanOptionalAction, default=None,
                             help='Force expanded storage, or --no-large-capacity for the faster engine '
                                  '(default: choose from the input and cutoff)')
    circuit_run.add_argument('--no-weighted-pruning', action='store_true')
    circuit_run.add_argument('--no-neutral-pruning', action='store_true')
    detector_layout = circuit_run.add_mutually_exclusive_group()
    detector_layout.add_argument('--window-search', type=int, metavar='DETECTORS_PER_LAYER',
                        help='Search verified time windows using consecutive detector blocks of this size')
    detector_layout.add_argument('--detector-layers', type=Path, metavar='JSON',
                        help='Search verified windows with one layer index per detector row in a JSON list')
    circuit_run.add_argument('--compiler', default='c++')
    circuit_run.add_argument('--cache', type=Path)
    circuit_audit = commands.add_parser('audit-circuit', help='Recheck circuit run identities, witnesses and root coverage')
    circuit_audit.add_argument('directory', type=Path)
    inspect = commands.add_parser('inspect', help='Validate a physical code or cyclic LP input')
    inspect.add_argument('code', type=Path)
    inspect.add_argument('--profile', choices=list(PROFILES), default=DEFAULT_PROFILE)
    export = commands.add_parser('expand-lp', help='Expand two cyclic constituents to physical binary CSS matrices')
    export.add_argument('input', type=Path)
    export.add_argument('--output', type=Path, required=True)
    imported = commands.add_parser('import-matrices', help='Import H_X and H_Z from plain-text sparse .mtx files')
    imported.add_argument('hx', type=Path)
    imported.add_argument('hz', type=Path)
    imported.add_argument('--period', type=int, default=1, help='Declared block-cyclic period; verified on both check spaces')
    imported.add_argument('--name')
    imported.add_argument('--output', type=Path, required=True)
    matrices = commands.add_parser('export-matrices', help='Export physical CSS checks as plain-text sparse .mtx files with one-based indices')
    matrices.add_argument('code', type=Path)
    matrices.add_argument('--hx', type=Path, required=True)
    matrices.add_argument('--hz', type=Path, required=True)
    run = commands.add_parser('certify', help='Run all required sectors and shards under explicit resource limits')
    run.add_argument('code', type=Path)
    run.add_argument('--out', type=Path, required=True)
    run.add_argument('--cutoff', type=int, required=True, help='Exclude nontrivial logicals through this weight')
    run.add_argument('--shards', type=int, default=1,
                     help='Number of independent search partitions per sector or LP subproblem')
    run.add_argument('--split-weight', type=int)
    run.add_argument('--workers', type=int, default=1,
                     help='Maximum number of search partitions run concurrently')
    run.add_argument('--seconds-per-shard', type=float, default=30.0,
                     help='Time limit for each search partition, in seconds')
    run.add_argument('--node-cap', type=int, default=2**64 - 1)
    run.add_argument('--memory-mib', type=float,
                     help='Optional native vector-allocation budget per worker, in MiB')
    run.add_argument('--large-capacity', action=argparse.BooleanOptionalAction, default=None,
                     help='Force expanded storage, or --no-large-capacity for the faster engine '
                          '(default: choose automatically, inherit on resume)')
    run.add_argument('--resume', action='store_true')
    run.add_argument('--stop-on-witness', action='store_true',
                     help='Stop launching new shards after a physically checked logical is found; running shards finish')
    run.add_argument('--no-symmetry', action='store_true')
    run.add_argument('--no-coset-pruning', action='store_true')
    run.add_argument('--proposed-additions', action=argparse.BooleanOptionalAction, default=None,
                     help='Test candidate qubits against the parent weighted bound '
                          '(enabled for new searches, inherits the saved setting on resume)')
    run.add_argument('--compiler', default='c++')
    run.add_argument('--cache', type=Path)
    run.add_argument('--profile', choices=list(PROFILES), default=DEFAULT_PROFILE)
    audit = commands.add_parser('audit', help='Independently check a campaign without executing the search')
    audit.add_argument('directory', type=Path)
    calibration = commands.add_parser('calibrate', help='Estimate search runtime by sampling starting qubits')
    calibration.add_argument('code', type=Path)
    calibration.add_argument('--out', type=Path, required=True)
    calibration.add_argument('--cutoff', type=int, required=True)
    calibration.add_argument('--samples', type=int, default=8,
                             help='Number of starting qubits sampled per required CSS sector')
    calibration.add_argument('--seconds-per-root', type=float, default=1.0,
                             help='Time limit for the search from each sampled starting qubit, in seconds')
    calibration.add_argument('--seed', type=int, default=0)
    calibration.add_argument('--node-cap', type=int, default=2**64-1)
    calibration.add_argument('--memory-mib', type=float,
                             help='Optional native vector-allocation budget per sampled root, in MiB')
    calibration.add_argument('--large-capacity', action=argparse.BooleanOptionalAction, default=None,
                             help='Force expanded storage, or --no-large-capacity for the faster engine '
                                  '(default: choose from the input and cutoff)')
    calibration.add_argument('--no-symmetry', action='store_true')
    calibration.add_argument('--no-coset-pruning', action='store_true')
    calibration.add_argument('--proposed-additions', action=argparse.BooleanOptionalAction, default=True,
                             help='Test candidate qubits against the parent weighted bound (enabled by default)')
    calibration.add_argument('--profile', choices=[p for p in PROFILES if p != 'lp'], default=DEFAULT_PROFILE)
    calibration.add_argument('--compiler', default='c++')
    calibration.add_argument('--cache', type=Path)
    cal_audit = commands.add_parser('audit-calibration', help='Recheck calibration inputs, transcripts and empirical summaries')
    cal_audit.add_argument('directory', type=Path)
    bundle = commands.add_parser('export', help='Audit and package an inactive campaign with its evidence and checker source')
    bundle.add_argument('directory', type=Path)
    bundle.add_argument('--output', type=Path, required=True)
    bundle_audit = commands.add_parser('audit-bundle', help='Check a portable archive without executing its stored code')
    bundle_audit.add_argument('archive', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.action == 'inspect-stabilizer':
            result = StabilizerCode.load(args.code).inspect()
        elif args.action == 'certify-stabilizer':
            result = certify_stabilizer(StabilizerCode.load(args.code), args.out,
                        cutoff=args.cutoff, seconds=args.seconds, node_cap=args.node_cap,
                        weighted=args.weighted_pruning, neutral=args.neutral_pruning,
                        compiler=args.compiler, cache=args.cache,
                        memory_mib=args.memory_mib, large_capacity=args.large_capacity,
                        use_symmetry=args.symmetry, shards=args.shards,
                        workers=args.workers, resume=args.resume)
        elif args.action == 'audit-stabilizer':
            result = audit_stabilizer(args.directory)
        elif args.action == 'import-circuit':
            if args.output.exists():
                raise ValueError('Output file exists; choose a new path')
            fmt = args.format if args.format != 'auto' else ('dem' if args.input.suffix == '.dem' else 'stim')
            model = (import_dem if fmt == 'dem' else import_stim)(args.input)
            if args.neutral_pairs or args.max_neutrals < 0:
                model = model.with_sparse_neutrals(args.neutral_pairs, args.max_neutrals)
            model.save(args.output)
            result = {'output': str(args.output), **model.inspect()}
        elif args.action == 'inspect-circuit':
            result = DetectorModel.load(args.model).inspect()
        elif args.action == 'reduce-circuit':
            if (args.output.resolve() == args.certificate.resolve()
                    or args.output.exists() or args.certificate.exists()):
                raise ValueError('Choose two distinct, new output paths')
            source = DetectorModel.load(args.model)
            if args.keep_detectors is not None:
                if args.basis != 'auto':
                    raise ValueError('--basis applies only with --stim')
                reduced, certificate = reduce_detector_sector(
                    source, json.loads(args.keep_detectors.read_text()))
            else:
                reduced, certificate = reduce_stim_sector(source, args.stim, basis=args.basis)
            result = verify_sector_reduction(source, reduced, certificate)
            write_new_pair((args.output, json_bytes(reduced.document)), (args.certificate, json_bytes(certificate)))
            result.update({'output': str(args.output), 'certificate': str(args.certificate)})
        elif args.action == 'audit-circuit-reduction':
            result = verify_sector_reduction(
                DetectorModel.load(args.source), DetectorModel.load(args.reduced),
                json.loads(args.certificate.read_text()))
        elif args.action == 'certify-circuit':
            layers = None
            if args.detector_layers is not None:
                layers = json.loads(args.detector_layers.read_text())
                if not isinstance(layers, list):
                    raise ValueError('The detector layer map must be a JSON list')
            result = certify_circuit(DetectorModel.load(args.model), args.out,
                        cutoff=args.cutoff, seconds=args.seconds, node_cap=args.node_cap,
                        weighted=not args.no_weighted_pruning, neutral=not args.no_neutral_pruning,
                        compiler=args.compiler, cache=args.cache,
                        detectors_per_layer=args.window_search, detector_layers=layers,
                        memory_mib=args.memory_mib, large_capacity=args.large_capacity)
        elif args.action == 'audit-circuit':
            result = audit_circuit(args.directory)
        elif args.action == 'inspect':
            code = load_input(args.code)
            result = code.inspect()
            result['native_backend_limits'] = profile_limits(args.profile)
            result['native_profile'] = args.profile
            if args.profile == 'lp':
                sa, sc, fiber = layout(code)
                parts = search_problems(code, {'sectors': ['Z'] if code.exchange is not None else ['X', 'Z'],
                                               'lp_anchor_site': sa * sc * fiber,
                                               'generator_symmetry': bool(code.symmetry_generators)})
                result['lp_search_tasks'] = {name: {'coordinates': part.n,
                    'roots': len(part.roots(code.period))} for name, part in parts.items()}
        elif args.action == 'expand-lp':
            code = load_lp(json.loads(args.input.read_text()))
            if args.output.exists():
                raise ValueError('Output file exists; choose a new path')
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open('xb') as target:
                target.write(json_bytes(code.document))
            result = {'output': str(args.output), **code.inspect()}
        elif args.action == 'import-matrices':
            if args.output.exists():
                raise ValueError('Output file exists; choose a new path')
            code = import_css_matrices(args.hx, args.hz, period=args.period, name=args.name)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open('xb') as target:
                target.write(json_bytes(code.document))
            result = {'output':str(args.output), **code.inspect()}
        elif args.action == 'export-matrices':
            if args.hx.resolve() == args.hz.resolve() or args.hx.exists() or args.hz.exists():
                raise ValueError('Choose two distinct, new output paths')
            code = load_input(args.code)
            write_new_pair((args.hx, matrix_market_text(code.hx, code.n).encode()),
                           (args.hz, matrix_market_text(code.hz, code.n).encode()))
            result = {'hx':str(args.hx), 'hz':str(args.hz), **code.inspect()}
        elif args.action == 'audit':
            result = audit_run(args.directory)
        elif args.action == 'audit-calibration':
            result = audit_calibration(args.directory)
        elif args.action == 'export':
            result = export_bundle(args.directory, args.output)
        elif args.action == 'audit-bundle':
            result = audit_bundle(args.archive)
        elif args.action == 'calibrate':
            result = calibrate(load_input(args.code), args.out, cutoff=args.cutoff, samples=args.samples,
                               seconds_per_root=args.seconds_per_root, seed=args.seed, node_cap=args.node_cap,
                               use_symmetry=not args.no_symmetry, coset_pruning=not args.no_coset_pruning,
                               profile=args.profile, compiler=args.compiler, cache=args.cache,
                               proposed_additions=args.proposed_additions, memory_mib=args.memory_mib,
                               large_capacity=args.large_capacity)
        else:
            code = load_input(args.code)
            def progress(record):
                terminal = record['terminal'] or {}
                print(f"{record['sector']} shard {record['shard']}: "
                      f"{terminal.get('status', 'incomplete')} ({terminal.get('nodes', '?')} nodes)",
                      file=sys.stderr, flush=True)
            result = certify(code, args.out, cutoff=args.cutoff, shards=args.shards,
                             split_weight=args.split_weight, workers=args.workers,
                             seconds_per_shard=args.seconds_per_shard, node_cap=args.node_cap,
                             resume=args.resume, use_symmetry=not args.no_symmetry,
                             coset_pruning=not args.no_coset_pruning, compiler=args.compiler,
                             cache=args.cache, progress=progress, profile=args.profile,
                             stop_on_witness=args.stop_on_witness,
                             proposed_additions=args.proposed_additions, memory_mib=args.memory_mib,
                             large_capacity=args.large_capacity)
        print(json.dumps(result, indent=2))
        return {'INCOMPLETE': 75, 'WITNESS_FOUND': 10, 'ERROR': 2}.get(result.get('status'), 0)
    except (ValueError, KeyError, OSError, tarfile.TarError, subprocess.SubprocessError) as exc:
        print(json.dumps({'status': 'ERROR_NO_NEW_LOWER_BOUND', 'error': str(exc)}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
