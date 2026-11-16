"""Independent Pauli oracles, complete logical detection, and public commands."""
import itertools
import json
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from cssdist import StabilizerCode, cyclic_lp
from cssdist.campaign import certify
from cssdist.code import digest, json_bytes
from cssdist.portable import export_bundle, audit_bundle
from cssdist.stabilizer_run import certify_stabilizer, audit_stabilizer

FIVE = ['XZZXI', 'IXZZX', 'XIXZZ', 'ZXIXZ']
PRODUCT = {a + b: 'IXZY'['IXZY'.index(a) ^ 'IXZY'.index(b)]
           for a in 'IXYZ' for b in 'IXYZ'}


def multiply(a, b):
    return ''.join(PRODUCT[x + y] for x, y in zip(a, b))


def commutes(a, b):
    return sum(x != 'I' and y != 'I' and x != y for x, y in zip(a, b)) % 2 == 0


def oracle(rows, n):
    stabilizers = {'I' * n}
    for row in rows:
        stabilizers |= {multiply(g, row) for g in stabilizers}
    for weight in range(1, n + 1):
        for sites in itertools.combinations(range(n), weight):
            for labels in itertools.product('XYZ', repeat=weight):
                word = ['I'] * n
                for q, label in zip(sites, labels):
                    word[q] = label
                word = ''.join(word)
                if word not in stabilizers and all(commutes(word, g) for g in rows):
                    return weight
    raise AssertionError('Oracle received a stabilizer state')


def transformed_rows(n, rng):
    rows = [['Z' if q == i else 'I' for q in range(n)] for i in range(n - 1)]
    for _ in range(6 * n):
        gate = rng.choice(('H', 'S', 'CX'))
        a, b = rng.sample(range(n), 2)
        for row in rows:
            if gate == 'H':
                row[a] = {'I': 'I', 'X': 'Z', 'Y': 'Y', 'Z': 'X'}[row[a]]
            elif gate == 'S':
                row[a] = {'I': 'I', 'X': 'Y', 'Y': 'X', 'Z': 'Z'}[row[a]]
            else:
                xa, za = int(row[a] in 'XY'), int(row[a] in 'ZY')
                xb, zb = int(row[b] in 'XY'), int(row[b] in 'ZY')
                row[a] = 'IXZY'[xa + 2 * (za ^ zb)]
                row[b] = 'IXZY'[(xa ^ xb) + 2 * zb]
    return [''.join(row) for row in rows]


def rehash(root):
    values = {str(p.relative_to(root)): digest(p.read_bytes()) for p in root.rglob('*')
              if p.is_file() and p != root / 'SHA256SUMS.json'}
    (root / 'SHA256SUMS.json').write_bytes(json_bytes({'files': values}))


class StabilizerInputTests(unittest.TestCase):
    def test_pauli_and_symplectic_formats_match(self):
        paulis = StabilizerCode.from_paulis(['XZY', 'III'])
        binary = StabilizerCode.from_symplectic(3, [[0, 2], []], [[1, 2], []])
        self.assertEqual(paulis.fingerprint, binary.fingerprint)
        self.assertEqual(paulis.k, 2)
        self.assertEqual(paulis.pauli(paulis.parse_pauli('YYI')), 'YYI')
        self.assertEqual(paulis.weight(paulis.parse_pauli('YYI')), 2)
        self.assertEqual(len(paulis.logical_basis()), 4)

    def test_invalid_inputs_and_stabilizer_state(self):
        invalid = [None, {}, {'schema': 'qedist.stabilizer.v1', 'n': True, 'stabilizers': []},
                   {'schema': 'qedist.stabilizer.v1', 'n': 1, 'stabilizers': ['X', 'Z']},
                   {'schema': 'qedist.stabilizer.v1', 'n': 1, 'stabilizers': ['+X']},
                   {'schema': 'qedist.stabilizer.v1', 'n': 2, 'x': [[0]], 'z': []},
                   {'schema': 'qedist.stabilizer.v1', 'n': 2, 'x': [[0, 0]], 'z': [[]]},
                   {'schema': 'qedist.stabilizer.v1', 'n': 1, 'stabilizers': [], 'cyclic_period': 2}]
        for doc in invalid:
            with self.subTest(doc=doc), self.assertRaises(ValueError):
                StabilizerCode(doc)
        with self.assertRaisesRegex(ValueError, 'outside their span'):
            StabilizerCode.from_paulis(['ZZ'], witnesses=['ZZ'])
        state = StabilizerCode.from_paulis(['XX', 'ZZ'])
        self.assertEqual(state.inspect()['k'], 0)
        with self.assertRaisesRegex(ValueError, 'k=0'):
            state.detector_model()

    def test_weight_one_y_and_local_cancellation(self):
        code = StabilizerCode.from_paulis([], n=1, witnesses=['Y'])
        model = code.detector_model()
        self.assertEqual(code.error_columns(code.parse_pauli('Y')), [1])
        self.assertTrue(model.is_logical(1 << 1))
        self.assertEqual(code.column_witness([0, 2]), {'pauli': 'Y', 'support': [0], 'weight': 1})
        self.assertEqual(model.document['neutral_rows'], [[0, 1, 2]])
        with self.assertRaisesRegex(ValueError, 'stabilizer'):
            code.column_witness([0, 1, 2])
        with self.assertRaisesRegex(ValueError, 'Repeated'):
            code.column_witness([1, 1])

    def test_all_logical_classes_are_detected(self):
        code = StabilizerCode.from_paulis(FIVE + [FIVE[0], 'IIIII'])
        model = code.detector_model()
        span = {'I' * code.n}
        for row in FIVE:
            span |= {multiply(g, row) for g in span}
        self.assertEqual(len(code.logical_basis()), 2 * code.k)
        for labels in itertools.product('IXYZ', repeat=code.n):
            pauli = ''.join(labels)
            word = code.parse_pauli(pauli)
            encoded = sum(1 << i for i in code.error_columns(word))
            logical = pauli not in span and all(commutes(pauli, g) for g in FIVE)
            self.assertEqual(model.is_logical(encoded), logical, pauli)
        for neutral in model.neutrals:
            self.assertTrue(all((neutral & row).bit_count() % 2 == 0
                                for row in model.detectors + model.observables))

    def test_redundant_binary_patterns_preserve_logical_action(self):
        rows = ['XYZ', 'ZYX']
        code = StabilizerCode.from_paulis(rows)
        model = code.detector_model()
        span = {'III', rows[0], rows[1], multiply(*rows)}
        for encoded in range(1 << model.n):
            pauli = 'III'
            columns = [i for i in range(model.n) if (encoded >> i) & 1]
            for i in columns:
                single = ['I'] * code.n
                single[i // 3] = 'XYZ'[i % 3]
                pauli = multiply(pauli, ''.join(single))
            logical = pauli not in span and all(commutes(pauli, row) for row in rows)
            self.assertEqual(model.is_logical(encoded), logical)
            if logical:
                checked = code.column_witness(columns)
                self.assertEqual(checked['pauli'], pauli)
                self.assertLessEqual(checked['weight'], len(columns))


class StabilizerSearchTests(unittest.TestCase):
    def test_capacity_modes_preserve_distance(self):
        package = Path(__file__).resolve().parents[1]
        code = StabilizerCode.load(package / 'examples/plain_fold_p13.json')
        nodes = []
        with tempfile.TemporaryDirectory() as tmp:
            for selected in (None, False, True):
                out = Path(tmp) / str(selected)
                result = certify_stabilizer(code, out, cutoff=6, large_capacity=selected)
                self.assertEqual(result['exact_distance'], 7)
                self.assertEqual(audit_stabilizer(out), result)
                config = json.loads((out / 'search/config.json').read_text())
                self.assertIs(config['large_capacity'], selected is True)
                search = json.loads((out / 'search/result.json').read_text())
                nodes.append(search['terminal']['nodes'])
        self.assertEqual(nodes, [nodes[0]] * 3)

    def test_automatic_expansion_and_invalid_capacity_options(self):
        n = 171
        rows = [row + 'I' * (n - 5) for row in FIVE]
        rows += ['I' * q + 'Y' + 'I' * (n - q - 1) for q in range(5, n)]
        code = StabilizerCode.from_paulis(rows)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'automatic'
            result = certify_stabilizer(code, out, cutoff=513)
            self.assertEqual(result['distance_upper_bound'], 3)
            self.assertEqual(audit_stabilizer(out), result)
            config = json.loads((out / 'search/config.json').read_text())
            self.assertIs(config['large_capacity'], True)
            invalid = [{'large_capacity':False}, {'large_capacity':'auto'},
                       {'memory_mib':0}, {'memory_mib':float('nan')},
                       {'large_capacity':False, 'memory_mib':1}]
            for i, options in enumerate(invalid):
                rejected = Path(tmp) / f'invalid-{i}'
                with self.subTest(options=options), self.assertRaises(ValueError):
                    certify_stabilizer(code, rejected, cutoff=513, **options)
                self.assertFalse(rejected.exists())

    def test_memory_budget_and_portable_audit(self):
        code = StabilizerCode.from_paulis(FIVE)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'memory'
            result = certify_stabilizer(code, out, cutoff=2, memory_mib=0.0001)
            self.assertEqual(result['status'], 'INCOMPLETE')
            self.assertEqual(result['distance_lower_bound'], 1)
            self.assertEqual(result['resource_limit']['resource'], 'memory')
            self.assertEqual(audit_stabilizer(out), result)
            archive = Path(tmp) / 'memory.tar.gz'
            export_bundle(out, archive)
            self.assertEqual(audit_bundle(archive)['result'], result)

    def test_capacity_cli_options(self):
        package = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            for flag in ('--large-capacity', '--no-large-capacity'):
                out = Path(tmp) / flag[2:]
                command = [sys.executable, '-m', 'cssdist', 'certify-stabilizer',
                           str(package / 'examples/five_qubit.json'), '--cutoff', '2',
                           '--out', str(out), flag]
                result = subprocess.run(command, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)['exact_distance'], 3)
                config = json.loads((out / 'search/config.json').read_text())
                self.assertIs(config['large_capacity'], flag == '--large-capacity')

    def test_plain_fold_pp_example(self):
        package = Path(__file__).resolve().parents[1]
        code = StabilizerCode.load(package / 'examples/plain_fold_p13.json')
        self.assertEqual((code.n, code.k), (52, 15))
        self.assertEqual(code.inspect()['max_check_weight'], 8)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'plain-fold'
            result = certify_stabilizer(code, out, cutoff=6)
            self.assertEqual(result['exact_distance'], 7)
            self.assertEqual(result['witness']['weight'], 7)
            self.assertEqual(audit_stabilizer(out), result)
            search = json.loads((out / 'search/result.json').read_text())
            self.assertEqual(search['terminal']['roots_completed'], 156)

    def test_five_qubit_exclusion_and_separate_witness_search(self):
        code = StabilizerCode.from_paulis(FIVE, witnesses=['XXXXX'])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for weighted, neutral in itertools.product((False, True), repeat=2):
                out = root / f'{weighted}-{neutral}'
                result = certify_stabilizer(code, out, cutoff=2, weighted=weighted, neutral=neutral)
                self.assertEqual(result['status'], 'EXACT_DISTANCE')
                self.assertEqual(result['exact_distance'], 3)
                self.assertEqual(result['witness']['weight'], 3)
                self.assertEqual(audit_stabilizer(out), result)
            result = certify_stabilizer(code, root / 'witness', cutoff=3)
            self.assertEqual(result['status'], 'WITNESS_FOUND')
            self.assertEqual(result['distance_lower_bound'], 1)
            self.assertEqual(result['distance_upper_bound'], 3)
            self.assertIsNone(result['exact_distance'])

    def test_random_clifford_codes_against_independent_oracle(self):
        rng = random.Random(4671)
        with tempfile.TemporaryDirectory() as tmp:
            for trial in range(20):
                n = rng.randrange(2, 8)
                rows = transformed_rows(n, rng)
                expected = oracle(rows, n)
                code = StabilizerCode.from_paulis(rows)
                for neutral in (False, True):
                    out = Path(tmp) / f'{trial}-{neutral}'
                    result = certify_stabilizer(code, out, cutoff=expected - 1,
                                                neutral=neutral, weighted=bool(trial % 2))
                    self.assertEqual(result['distance_lower_bound'], expected)
                    self.assertGreaterEqual(result['distance_upper_bound'], expected)
                    self.assertEqual(audit_stabilizer(out), result)
                    if expected < result['distance_upper_bound']:
                        found = certify_stabilizer(code, Path(tmp) / f'witness-{trial}-{neutral}',
                                                   cutoff=expected, neutral=neutral)
                        self.assertEqual(found['distance_upper_bound'], expected)

    def test_css_input_agrees_with_the_specialized_engine(self):
        css = cyclic_lp([[1, 1]], [[1, 1, 0], [0, 1, 1]])
        rows = [''.join('X' if (row >> q) & 1 else 'I' for q in range(css.n)) for row in css.hx]
        rows += [''.join('Z' if (row >> q) & 1 else 'I' for q in range(css.n)) for row in css.hz]
        witnesses = [''.join(sector if (word >> q) & 1 else 'I' for q in range(css.n))
                     for sector, word in css.upper_witnesses().items()]
        code = StabilizerCode.from_paulis(rows, witnesses=witnesses)
        with tempfile.TemporaryDirectory() as tmp:
            a = certify(css, Path(tmp) / 'css', cutoff=1)
            b = certify_stabilizer(code, Path(tmp) / 'general', cutoff=1)
            self.assertEqual((b['n'], b['k']), (css.n, css.k))
            self.assertEqual(b['exact_distance'], a['exact_distance'])

    def test_budget_interruptions_grant_no_exclusion(self):
        code = StabilizerCode.from_paulis(FIVE)
        with tempfile.TemporaryDirectory() as tmp:
            for name, options in [('nodes', {'node_cap': 0}), ('time', {'seconds': 0.000001})]:
                out = Path(tmp) / name
                result = certify_stabilizer(code, out, cutoff=2, **options)
                self.assertEqual(result['status'], 'INCOMPLETE')
                self.assertEqual(result['distance_lower_bound'], 1)
                self.assertIsNone(result['exact_distance'])
                self.assertEqual(audit_stabilizer(out), result)

    def test_invalid_budget_preserves_output_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'invalid'
            with self.assertRaises(ValueError):
                certify_stabilizer(StabilizerCode.from_paulis(FIVE), out, cutoff=-1)
            self.assertFalse(out.exists())

    def test_portable_relocation_and_read_only_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / 'run'
            result = certify_stabilizer(StabilizerCode.from_paulis(FIVE), run, cutoff=2)
            relocated = root / 'relocated'
            shutil.move(run, relocated)
            with patch('subprocess.Popen', side_effect=AssertionError('audit executed a process')):
                self.assertEqual(audit_stabilizer(relocated), result)
                exported = export_bundle(relocated, root / 'evidence.tar.gz')
                self.assertEqual(exported['kind'], 'stabilizer')
                self.assertEqual(audit_bundle(root / 'evidence.tar.gz')['result'], result)

    def test_tampered_conversion_and_result_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'source'
            certify_stabilizer(StabilizerCode.from_paulis(FIVE), source, cutoff=2)
            for name in ('observable', 'summary', 'input'):
                run = root / name
                shutil.copytree(source, run)
                if name == 'observable':
                    path = run / 'search/input.json'
                    data = json.loads(path.read_text())
                    data['observable_rows'].pop()
                elif name == 'summary':
                    path = run / 'result.json'
                    data = json.loads(path.read_text())
                    data['exact_distance'] = 4
                else:
                    path = run / 'code.json'
                    data = json.loads(path.read_text())
                    data['stabilizers'][0] = 'IIIII'
                path.write_bytes(json_bytes(data))
                rehash(run)
                with self.subTest(name=name), self.assertRaises(ValueError):
                    audit_stabilizer(run)

    def test_cli(self):
        package = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'cli'
            base = [sys.executable, '-m', 'cssdist']
            command = base + ['certify-stabilizer', str(package / 'examples/five_qubit.json'),
                              '--cutoff', '2', '--out', str(out)]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['exact_distance'], 3)
            checked = subprocess.run(base + ['audit-stabilizer', str(out)], capture_output=True, text=True)
            self.assertEqual(checked.returncode, 0, checked.stderr)
            self.assertEqual(json.loads(result.stdout), json.loads(checked.stdout))


if __name__ == '__main__':
    unittest.main()
