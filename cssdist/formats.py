"""Plain-text sparse .mtx matrices interpreted over the binary field."""
from pathlib import Path

from .algebra import support
from .code import CSSCode, digest


def read_matrix_market(path):
    """Read integer or pattern coordinate/general data, summing repeats in F2.

    Integer entries must explicitly be zero or one. The parser rejects
    symmetric, dense-array, real and complex formats.
    Returns (column_count, sparse_row_supports).
    """
    return _parse_matrix_market(Path(path).read_bytes())


def _parse_matrix_market(data):
    lines = data.decode('utf-8').splitlines()
    if not lines:
        raise ValueError('Empty .mtx input')
    header = lines[0].strip().lower().split()
    if (len(header) != 5 or header[:3] != ['%%matrixmarket','matrix','coordinate']
            or header[3] not in ('integer','pattern') or header[4] != 'general'):
        raise ValueError('Require .mtx coordinate integer/pattern general format')
    records = [(i+2, line.split()) for i, line in enumerate(lines[1:])
               if line.strip() and not line.lstrip().startswith('%')]
    if not records or len(records[0][1]) != 3:
        raise ValueError('Missing .mtx matrix dimensions')
    try:
        m, n, count = map(int, records[0][1])
    except ValueError:
        raise ValueError('.mtx matrix dimensions must be integers') from None
    if m < 0 or n < 1 or count < 0:
        raise ValueError('Require nonnegative row/entry counts and positive column count')
    if len(records)-1 != count:
        raise ValueError('.mtx entry count differs from the declared count')
    rows = [set() for _ in range(m)]
    for line_number, fields in records[1:]:
        expected = 3 if header[3] == 'integer' else 2
        if len(fields) != expected:
            raise ValueError(f'Wrong number of fields on .mtx line {line_number}')
        try:
            values = list(map(int, fields))
        except ValueError:
            raise ValueError(f'Noninteger .mtx entry on line {line_number}') from None
        i, j = values[:2]
        value = values[2] if expected == 3 else 1
        if not (1 <= i <= m and 1 <= j <= n) or value not in (0,1):
            raise ValueError(f'Invalid binary coordinate on .mtx line {line_number}')
        if value:
            rows[i-1].symmetric_difference_update((j-1,))
    return n, [sorted(row) for row in rows]


def matrix_market_text(rows, n):
    """Export binary integer masks as canonical one-based sparse coordinates."""
    if type(n) is not int or n < 1:
        raise ValueError('Positive column count required')
    words = list(rows)
    if any(type(v) is not int or not 0 <= v < 1 << n for v in words):
        raise ValueError('Invalid binary matrix row')
    lines = ['%%MatrixMarket matrix coordinate integer general',
             '% Binary coefficients; duplicate coordinates sum modulo two.',
             f'{len(words)} {n} {sum(v.bit_count() for v in words)}']
    lines += [f'{i+1} {j+1} 1' for i, row in enumerate(words) for j in support(row)]
    return '\n'.join(lines)+'\n'


def import_css_matrices(hx_path, hz_path, *, period=1, name=None):
    x_data, z_data = Path(hx_path).read_bytes(), Path(hz_path).read_bytes()
    nx, hx = _parse_matrix_market(x_data)
    nz, hz = _parse_matrix_market(z_data)
    if nx != nz:
        raise ValueError('The two .mtx inputs have different column counts')
    metadata = {'cyclic_period':period,
                'provenance':{'format':'Matrix Market over F2',
                    'hx_file_sha256':digest(x_data),
                    'hz_file_sha256':digest(z_data),
                    'duplicate_coordinates':'summed modulo two'}}
    if name is not None:
        metadata['name'] = name
    # This independently checks commutation, ranks and any declared cyclic action.
    return CSSCode.from_sparse(nx, hx, hz, **metadata)
