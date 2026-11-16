"""Cyclic lifted products from two independent, arbitrary-rank constituents."""
from .algebra import support
from .code import CSSCode

RHO = {0: ((0, 0), (0, 0)), 1: ((1, 0), (0, 1)),
       2: ((0, 1), (1, 1)), 3: ((1, 1), (1, 0))}


def polynomial_matrix(matrix, field, period):
    if not isinstance(matrix, list) or not matrix or not isinstance(matrix[0], list) or not matrix[0]:
        raise ValueError('A constituent must be a nonempty rectangular matrix')
    width = len(matrix[0])
    out = []
    for row in matrix:
        if not isinstance(row, list) or len(row) != width:
            raise ValueError('Ragged constituent matrix')
        converted = []
        for entry in row:
            terms = [[0, entry]] if type(entry) is int else entry
            if not isinstance(terms, list):
                raise ValueError('Use a constant coefficient or a list of [exponent, coefficient] terms')
            p = {}
            for term in terms:
                if (not isinstance(term, list) or len(term) != 2
                        or any(type(v) is not int for v in term)):
                    raise ValueError('Invalid polynomial term')
                exponent, coefficient = term
                if not 0 <= coefficient < field:
                    raise ValueError('Coefficient outside the specified field')
                e = exponent % period
                p[e] = p.get(e, 0) ^ coefficient
            converted.append({e: c for e, c in sorted(p.items()) if c})
        out.append(converted)
    return out


def cyclic_lp(A, C=None, *, period=1, field=2, check_basis='raw', name=None,
              witnesses=None, provenance=None, symmetry_generators=None):
    """Construct H_X=[A⊗I | I⊗C†], H_Z=[I⊗C | A†⊗I].

    A and C may have different dimensions and need not have invertible pivots.
    Entries are constants or lists of [exponent, coefficient] pairs. F4 uses
    coefficients 0,1,2,3 = 0,1,omega,omega^2 and binary physical coordinates.
    """
    if type(period) is not int or period < 1 or type(field) is not int or field not in (2, 4):
        raise ValueError('Use a positive period and field 2 or 4')
    if check_basis not in ('raw', 'balanced', 'redundant'):
        raise ValueError('check_basis must be raw, balanced, or redundant')
    if field == 2 and check_basis != 'raw':
        raise ValueError('Trace-basis balancing applies only to field 4')
    a = polynomial_matrix(A, field, period)
    c = polynomial_matrix(A if C is None else C, field, period)
    ra, sa, rc, sc = len(a), len(a[0]), len(c), len(c[0])
    components = 1 if field == 2 else 2
    blocks = sa * sc + ra * rc
    n = components * period * blocks

    def bar(poly):
        return {(-e) % period: coefficient for e, coefficient in poly.items()}

    def expand(entries):
        rows = []
        for alpha in range(components):
            for t in range(period):
                word = 0
                for block, poly in entries:
                    for exponent, coefficient in poly.items():
                        for beta in range(components):
                            value = coefficient if field == 2 else RHO[coefficient][alpha][beta]
                            if value:
                                word ^= 1 << ((components * block + beta) * period + (t - exponent) % period)
                rows.append(word)
        if field == 4 and check_basis == 'redundant':
            return rows + [rows[t] ^ rows[period + t] for t in range(period)]
        if field == 4 and check_basis == 'balanced':
            chosen = []
            for t in range(period):
                u, v = rows[t], rows[period + t]
                chosen.extend(sorted((u, v, u ^ v), key=int.bit_count)[:2])
            return chosen
        return rows

    hx, hz = [], []
    for i in range(ra):
        for b in range(sc):
            hx += expand([(x * sc + b, a[i][x]) for x in range(sa)] +
                         [(sa * sc + i * rc + j, bar(c[j][b])) for j in range(rc)])
    for x in range(sa):
        for j in range(rc):
            hz += expand([(x * sc + b, c[j][b]) for b in range(sc)] +
                         [(sa * sc + i * rc + j, bar(a[i][x])) for i in range(ra)])
    metadata = {'cyclic_period': period,
                'construction': {'family': 'cyclic_lp', 'field': field, 'period': period,
                                 'A': A, 'C': A if C is None else C, 'check_basis': check_basis}}
    if name is not None:
        metadata['name'] = name
    if witnesses is not None:
        metadata['witnesses'] = witnesses
    if provenance is not None:
        metadata['provenance'] = provenance
    if symmetry_generators is not None:
        metadata['symmetry_generators'] = symmetry_generators
    if a == c:
        # Propose tensor transposition; CSSCode independently verifies it.
        permutation = []
        for q in range(n):
            physical_block, t = divmod(q, period)
            block, beta = divmod(physical_block, components)
            if block < sa * sc:
                x, b = divmod(block, sc)
                target = b * sa + x
            else:
                i, j = divmod(block - sa * sc, rc)
                target = sa * sc + j * ra + i
            permutation.append((components * target + beta) * period + t)
        metadata['sector_exchange'] = permutation
    return CSSCode.from_sparse(n, [support(v) for v in hx], [support(v) for v in hz], **metadata)


def load_lp(document):
    if not isinstance(document, dict) or document.get('schema') != 'cssdist.lp.v1':
        raise ValueError('Expected input schema cssdist.lp.v1')
    return cyclic_lp(document['A'], document.get('C'), period=document.get('period', 1),
                     field=document.get('field', 2), check_basis=document.get('check_basis', 'raw'),
                     name=document.get('name'), witnesses=document.get('witnesses'),
                     provenance=document.get('provenance'),
                     symmetry_generators=document.get('symmetry_generators'))
