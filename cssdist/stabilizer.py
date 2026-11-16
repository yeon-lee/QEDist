"""General stabilizer codes and a Pauli-weight-preserving binary expansion."""
import copy
import json
from pathlib import Path

from .algebra import basis, kernel_basis, permute, remainder, support, vector
from .circuit import DetectorModel
from .code import digest, json_bytes
from .symmetry import orbit_representatives, validate_generators

SCHEMA = 'qedist.stabilizer.v1'
PAULIS = 'IXZY'  # Index x + 2*z for a phase-free single-qubit Pauli.


class StabilizerCode:
    """Commuting phase-free Paulis, with qubit 0 at the left of each string.

    Internal vectors store x in the low n bits and z in the next n bits.
    Consistent generator signs choose an eigenspace and leave distance invariant.
    """

    def __init__(self, document):
        if not isinstance(document, dict) or document.get('schema') != SCHEMA:
            raise ValueError(f'Expected a JSON object with schema {SCHEMA}')
        data = copy.deepcopy(document)
        if any(type(key) is not str for key in data):
            raise ValueError('Stabilizer input field names must be strings')
        allowed = {'schema', 'n', 'stabilizers', 'x', 'z', 'witnesses', 'name', 'metadata',
                   'cyclic_period', 'symmetry_generators'}
        if set(data) - allowed:
            raise ValueError('Unknown stabilizer input fields: ' + ', '.join(sorted(set(data) - allowed)))
        self.n = data.get('n')
        if type(self.n) is not int or not 1 <= self.n <= (2**31 - 1) // 3:
            raise ValueError('n must be positive and its 3n Pauli columns must fit signed 32-bit indices')
        if not isinstance(data.get('metadata', {}), dict):
            raise ValueError('metadata must be an object')
        if 'stabilizers' in data:
            if 'x' in data or 'z' in data or not isinstance(data['stabilizers'], list):
                raise ValueError('Supply either a list of stabilizer strings or paired x/z row lists')
            self.generators = [self.parse_pauli(row) for row in data['stabilizers']]
        else:
            x, z = data.get('x'), data.get('z')
            if not isinstance(x, list) or not isinstance(z, list) or len(x) != len(z):
                raise ValueError('x and z must be equally sized lists of sparse row supports')
            self.generators = [vector(a, self.n) | (vector(b, self.n) << self.n)
                               for a, b in zip(x, z)]
        self.stabilizer_basis = basis(self.generators)
        independent = list(self.stabilizer_basis.values())
        if any(self.pair(a, b) for i, a in enumerate(independent) for b in independent[:i]):
            raise ValueError('Stabilizer generators must commute pairwise')
        self.period = data.get('cyclic_period', 1)
        if type(self.period) is not int or self.period < 1 or self.n % self.period:
            raise ValueError('cyclic_period must be a positive divisor of n')
        self.symmetry_generators = data.get('symmetry_generators', [])
        validate_generators(self.symmetry_generators, self.n, [], [])
        permutations = list(self.symmetry_generators)
        if self.period > 1:
            permutations.append([(q // self.period) * self.period + (q + 1) % self.period
                                 for q in range(self.n)])
        for permutation in permutations:
            symplectic = permutation + [self.n + q for q in permutation]
            if any(remainder(permute(row, symplectic), self.stabilizer_basis)
                   for row in independent):
                raise ValueError('Qubit symmetry must preserve the full stabilizer space')
        self.k = self.n - len(independent)
        witnesses = data.get('witnesses', [])
        if not isinstance(witnesses, list):
            raise ValueError('witnesses must be a list of Pauli strings')
        self.witnesses = [self.parse_pauli(row) for row in witnesses]
        if any(not self.is_logical(row) for row in self.witnesses):
            raise ValueError('Each witness must commute with the stabilizers and lie outside their span')
        data.pop('x', None)
        data.pop('z', None)
        data['stabilizers'] = [self.pauli(row) for row in self.generators]
        data['witnesses'] = [self.pauli(row) for row in self.witnesses]
        self.document = data

    @classmethod
    def from_paulis(cls, stabilizers, *, n=None, **metadata):
        rows = list(stabilizers)
        if n is None:
            if not rows or not isinstance(rows[0], str):
                raise ValueError('Specify n when no stabilizer string supplies its length')
            n = len(rows[0])
        return cls(dict(metadata, schema=SCHEMA, n=n, stabilizers=rows))

    @classmethod
    def from_symplectic(cls, n, x, z, **metadata):
        return cls(dict(metadata, schema=SCHEMA, n=n, x=x, z=z))

    @classmethod
    def load(cls, path):
        return cls(json.loads(Path(path).read_text()))

    def save(self, path):
        Path(path).write_bytes(json_bytes(self.document))

    @property
    def fingerprint(self):
        return digest(json_bytes(self.document))

    def parse_pauli(self, text):
        if not isinstance(text, str) or len(text) != self.n or any(p not in PAULIS for p in text):
            raise ValueError(f'Each phase-free Pauli string must contain exactly {self.n} I/X/Y/Z characters')
        word = 0
        for qubit, pauli in enumerate(text):
            value = PAULIS.index(pauli)
            word |= (value & 1) << qubit
            word |= (value >> 1) << (self.n + qubit)
        return word

    def pauli(self, word):
        if type(word) is not int or not 0 <= word < 1 << (2 * self.n):
            raise ValueError('Invalid binary symplectic vector')
        return ''.join(PAULIS[((word >> q) & 1) + 2 * ((word >> (self.n + q)) & 1)]
                       for q in range(self.n))

    def pair(self, a, b):
        return (((a & (b >> self.n)) ^ (b & (a >> self.n))).bit_count() & 1)

    def weight(self, word):
        return ((word | (word >> self.n)) & ((1 << self.n) - 1)).bit_count()

    def is_logical(self, word):
        return (type(word) is int and 0 < word < 1 << (2 * self.n)
                and all(not self.pair(word, row) for row in self.generators)
                and bool(remainder(word, self.stabilizer_basis)))

    def check_witness(self, pauli):
        word = self.parse_pauli(pauli)
        if not self.is_logical(word):
            raise ValueError('Pauli witness is outside the normalizer or is a stabilizer')
        physical_support = (word | (word >> self.n)) & ((1 << self.n) - 1)
        return {'pauli': self.pauli(word), 'support': support(physical_support),
                'weight': physical_support.bit_count()}

    def logical_basis(self):
        """A complete quotient basis suffices to detect every logical class."""
        if self.k == 0:
            raise ValueError('This code has k=0; nontrivial logical distance is undefined')
        mask = (1 << self.n) - 1
        equations = [(row >> self.n) | ((row & mask) << self.n)
                     for row in self.stabilizer_basis.values()]
        span = dict(self.stabilizer_basis)
        logicals = []
        for word in kernel_basis(equations, 2 * self.n):
            reduced = remainder(word, span)
            if reduced:
                span[reduced.bit_length() - 1] = reduced
                logicals.append(word)
        if len(logicals) != 2 * self.k:
            raise ValueError('Failed to construct the complete logical quotient')
        return logicals

    def error_columns(self, word):
        """One column per occupied qubit, in the order X_q,Y_q,Z_q."""
        columns = []
        for q, pauli in enumerate(self.pauli(word)):
            if pauli != 'I':
                columns.append(3 * q + 'XYZ'.index(pauli))
        return columns

    def column_witness(self, columns):
        encoded = vector(columns, 3 * self.n)
        word = 0
        for column in support(encoded):
            qubit, pauli = divmod(column, 3)
            if pauli in (0, 1):
                word ^= 1 << qubit
            if pauli in (1, 2):
                word ^= 1 << (self.n + qubit)
        return self.check_witness(self.pauli(word))

    def detector_model(self):
        """The binary minimum equals Pauli distance, including weight-one Y."""
        logicals = self.logical_basis()

        def commutation_row(word):
            row = []
            for q, pauli in enumerate(self.pauli(word)):
                if pauli != 'I':
                    row.extend(3 * q + i for i, error in enumerate('XYZ') if error != pauli)
            return row

        # Each local triple multiplies to identity up to phase. The remaining
        # neutral rows are the supplied stabilizers, expanded into Pauli columns.
        neutrals = [[3 * q, 3 * q + 1, 3 * q + 2] for q in range(self.n)]
        neutrals.extend(self.error_columns(row) for row in self.generators if row)
        best = min(logicals + self.witnesses, key=lambda word: (self.weight(word), word))
        return DetectorModel.from_sparse(
            3 * self.n, [commutation_row(row) for row in self.generators],
            [commutation_row(row) for row in logicals], neutral_rows=neutrals,
            witnesses=[self.error_columns(best)], metadata={
                'construction': 'stabilizer_pauli_columns_v1',
                'code_sha256': self.fingerprint,
                'column_order': 'X_0,Y_0,Z_0,X_1,Y_1,Z_1,...',
                'logical_observable_paulis': [self.pauli(row) for row in logicals],
                'physical_fault_correspondence': 'Minimum column count equals minimum nontrivial Pauli weight.',
            })

    def inspect(self):
        result = {'name': self.document.get('name'), 'n': self.n, 'k': self.k,
                  'stabilizer_rank': len(self.stabilizer_basis),
                  'max_check_weight': max(map(self.weight, self.generators), default=0),
                  'metric': 'pauli_weight', 'binary_search_columns': 3 * self.n,
                  'code_sha256': self.fingerprint,
                  'symmetry_root_qubits': orbit_representatives(
                      self.n, self.symmetry_generators, self.period),
                  'cyclic_period': self.period}
        if self.k:
            model = self.detector_model()
            result['upper_bound'] = min(self.column_witness(s)['weight']
                                        for s in model.document['witnesses'])
        return result
