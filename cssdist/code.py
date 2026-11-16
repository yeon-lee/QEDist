"""Physical CSS inputs and independently verified symmetry declarations."""
import copy
import hashlib
import json
from pathlib import Path

from .algebra import basis, kernel_basis, permute, remainder, same_span, support, vector
from .symmetry import orbit_representatives, validate_generators

SCHEMA = 'cssdist.code.v1'


def json_bytes(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def native_matrix(n, checks, stabilizers):
    lines = [f'{n} {len(checks)} {len(stabilizers)}']
    for word in checks + stabilizers:
        indices = support(word)
        lines.append(' '.join(map(str, [len(indices), *indices])))
    return '\n'.join(lines) + '\n'


class CSSCode:
    def __init__(self, document):
        if not isinstance(document, dict):
            raise ValueError('A CSS input must be a JSON object')
        data = copy.deepcopy(document)
        if data.get('schema') != SCHEMA:
            raise ValueError(f'Expected input schema {SCHEMA}')
        self.n = data.get('n')
        if type(self.n) is not int or self.n < 1:
            raise ValueError('n must be a positive integer')
        for key in ('hx', 'hz'):
            if not isinstance(data.get(key), list):
                raise ValueError(f'{key} must be a list of sparse row supports')
        self.hx = [vector(row, self.n) for row in data['hx']]
        self.hz = [vector(row, self.n) for row in data['hz']]
        if any((x & z).bit_count() % 2 for x in self.hx for z in self.hz):
            raise ValueError('CSS commutation failed: H_X H_Z^T is not zero')
        self.bx, self.bz = basis(self.hx), basis(self.hz)
        self.k = self.n - len(self.bx) - len(self.bz)
        self.period = data.get('cyclic_period', 1)
        if type(self.period) is not int or self.period < 1 or self.n % self.period:
            raise ValueError('cyclic_period must be a positive divisor of n')
        translation = [(j // self.period) * self.period + (j + 1) % self.period
                       for j in range(self.n)]
        if not same_span(self.hx, [permute(v, translation) for v in self.hx]):
            raise ValueError('Declared cyclic action does not preserve the X check space')
        if not same_span(self.hz, [permute(v, translation) for v in self.hz]):
            raise ValueError('Declared cyclic action does not preserve the Z check space')
        self.symmetry_generators = data.get('symmetry_generators', [])
        validate_generators(self.symmetry_generators, self.n, self.hx, self.hz)
        self.exchange = data.get('sector_exchange')
        if self.exchange is not None:
            if (not isinstance(self.exchange, list) or len(self.exchange) != self.n
                    or any(type(j) is not int for j in self.exchange)
                    or set(self.exchange) != set(range(self.n))):
                raise ValueError('sector_exchange must be a permutation of 0,...,n-1')
            if not (same_span([permute(v, self.exchange) for v in self.hx], self.hz)
                    and same_span([permute(v, self.exchange) for v in self.hz], self.hx)):
                raise ValueError('Declared permutation does not exchange both CSS check spaces')
        known = data.get('witnesses', {})
        if not isinstance(known, dict) or set(known) - {'X', 'Z'}:
            raise ValueError('witnesses must map X/Z to lists of supports')
        self.witnesses = {'X': [], 'Z': []}
        for sector in ('X', 'Z'):
            if not isinstance(known.get(sector, []), list):
                raise ValueError('Each witness sector must be a list')
            for indices in known.get(sector, []):
                word = vector(indices, self.n)
                if not self.is_logical(word, sector):
                    raise ValueError(f'Invalid {sector} logical witness')
                self.witnesses[sector].append(word)
        data['hx'] = [support(row) for row in self.hx]
        data['hz'] = [support(row) for row in self.hz]
        data['cyclic_period'] = self.period
        data['witnesses'] = {s: [support(v) for v in rows] for s, rows in self.witnesses.items()}
        self.document = data

    @classmethod
    def load(cls, path):
        return cls(json.loads(Path(path).read_text()))

    @classmethod
    def from_sparse(cls, n, hx, hz, **metadata):
        return cls(dict(metadata, schema=SCHEMA, n=n, hx=hx, hz=hz))

    @classmethod
    def from_dense(cls, hx, hz, n=None, **metadata):
        hx, hz = [list(row) for row in hx], [list(row) for row in hz]
        rows = hx + hz
        if n is None:
            if not rows:
                raise ValueError('Specify n when both matrices have no rows')
            n = len(rows[0])
        if any(len(row) != n or any(type(v) is not int or v not in (0, 1) for v in row)
               for row in rows):
            raise ValueError('Dense matrices must have n binary entries in every row')
        sparse = lambda matrix: [[j for j, v in enumerate(row) if v] for row in matrix]
        return cls.from_sparse(n, sparse(hx), sparse(hz), **metadata)

    @property
    def fingerprint(self):
        return digest(json_bytes(self.document))

    def save(self, path):
        Path(path).write_bytes(json_bytes(self.document))

    def sector(self, sector):
        if sector == 'Z':
            return self.hx, self.hz, self.bz
        if sector == 'X':
            return self.hz, self.hx, self.bx
        raise ValueError('Sector must be X or Z')

    def is_logical(self, word, sector):
        checks, _, stabilizers = self.sector(sector)
        return (type(word) is int and 0 < word < (1 << self.n)
                and all((word & row).bit_count() % 2 == 0 for row in checks)
                and bool(remainder(word, stabilizers)))

    def kernel_even_weight(self, sector):
        """Whether every word in this sector's physical kernel has even weight.

        This is a row-space fact about the syndrome checks, not a statement
        about all mixed-Pauli operators or just chosen logical representatives.
        """
        self.sector(sector)  # Validate the sector name before selecting a basis.
        checks_basis = self.bx if sector == 'Z' else self.bz
        return remainder((1 << self.n) - 1, checks_basis) == 0

    def upper_witnesses(self):
        result = {}
        if self.k == 0:
            return result
        for sector in ('X', 'Z'):
            checks, _, stabilizers = self.sector(sector)
            candidates = list(self.witnesses[sector])
            candidates += [v for v in kernel_basis(checks, self.n) if remainder(v, stabilizers)]
            if not candidates:
                raise ValueError('Failed to find a logical direction despite k > 0')
            result[sector] = min(candidates, key=lambda v: (v.bit_count(), v))
        if self.exchange is not None:
            original = dict(result)
            for source, dest in [('X', 'Z'), ('Z', 'X')]:
                v = permute(original[source], self.exchange)
                if not self.is_logical(v, dest):
                    raise ValueError('Sector exchange failed the logical-witness check')
                result[dest] = min(result[dest], v, key=lambda v: (v.bit_count(), v))
        return result

    def native_text(self, sector):
        checks, stabilizers, _ = self.sector(sector)
        return native_matrix(self.n, checks, stabilizers)

    def inspect(self):
        def weights(rows):
            return {'max_row': max((v.bit_count() for v in rows), default=0),
                    'max_column': max((sum((v >> j) & 1 for v in rows)
                                       for j in range(self.n)), default=0)}
        return {'name': self.document.get('name'), 'n': self.n, 'k': self.k,
                'ranks': {'X': len(self.bx), 'Z': len(self.bz)},
                'check_weights': {'X': weights(self.hx), 'Z': weights(self.hz)},
                'verified_cyclic_period': self.period,
                'verified_symmetry_generators': len(self.symmetry_generators),
                'symmetry_orbit_representatives': orbit_representatives(
                    self.n, self.symmetry_generators, self.period),
                'verified_sector_exchange': self.exchange is not None,
                'kernel_even_weight': {s: self.kernel_even_weight(s) for s in ('X', 'Z')},
                'code_sha256': self.fingerprint,
                'upper_bounds': {s: v.bit_count() for s, v in self.upper_witnesses().items()}}
