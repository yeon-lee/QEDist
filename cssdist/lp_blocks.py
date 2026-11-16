"""Physical subproblems used by CSS campaigns and the optional LP block split."""
from dataclasses import dataclass, field

from .algebra import basis, same_span
from .code import native_matrix
from .symmetry import orbit_representatives, symmetry_text, validate_generators


def layout(code):
    """Read physical block dimensions independently of the symmetry action."""
    construction = code.document.get('construction')

    def dimensions(matrix):
        if not isinstance(matrix, list) or not matrix or not isinstance(matrix[0], list) or not matrix[0]:
            raise ValueError('Missing rectangular LP constituent')
        width = len(matrix[0])
        if any(not isinstance(row, list) or len(row) != width for row in matrix):
            raise ValueError('Invalid rectangular LP constituent')
        return len(matrix), width

    sizes = None
    if isinstance(construction, dict) and construction.get('family') == 'cyclic_lp':
        ra, sa = dimensions(construction.get('A'))
        rc, sc = dimensions(construction.get('C', construction['A']))
        field, period = construction.get('field'), construction.get('period')
        if type(field) is not int or field not in (2, 4) or type(period) is not int or period != code.period:
            raise ValueError('LP field or period disagrees with the physical layout')
        sizes = ra, sa, rc, sc, period * (1 if field == 2 else 2)

    if 'lp_layout' in code.document:
        declared = code.document['lp_layout']
        if not isinstance(declared, dict) or set(declared) != {'A_shape', 'C_shape', 'block_size'}:
            raise ValueError('lp_layout requires A_shape, C_shape and block_size')
        for name in ('A_shape', 'C_shape'):
            shape = declared[name]
            if (not isinstance(shape, list) or len(shape) != 2
                    or any(type(v) is not int or v < 1 for v in shape)):
                raise ValueError(f'lp_layout {name} must contain positive integer row and column counts')
        fiber = declared['block_size']
        if type(fiber) is not int or fiber < 1:
            raise ValueError('lp_layout block_size must be a positive integer')
        physical = (*declared['A_shape'], *declared['C_shape'], fiber)
        if sizes is not None and sizes != physical:
            raise ValueError('lp_layout disagrees with the cyclic LP construction')
        sizes = physical

    if sizes is None:
        raise ValueError('lp requires a cyclic LP input or physical checks with lp_layout')
    ra, sa, rc, sc, fiber = sizes
    if (ra * rc + sa * sc) * fiber != code.n:
        raise ValueError('LP dimensions disagree with the physical coordinates')
    return sa, sc, fiber


def _restrict(word, blocks, fiber):
    mask = (1 << fiber) - 1
    return sum(((word >> (j * fiber)) & mask) << (i * fiber) for i, j in enumerate(blocks))


def _embed(word, blocks, fiber):
    mask = (1 << fiber) - 1
    return sum(((word >> (i * fiber)) & mask) << (j * fiber) for i, j in enumerate(blocks))


def _zero_images(pairs):
    """Representatives of linear combinations whose first component is zero."""
    pivots, kernel = {}, []
    for image, representative in pairs:
        while image:
            pivot = image.bit_length() - 1
            if pivot not in pivots:
                pivots[pivot] = image, representative
                break
            old_image, old_representative = pivots[pivot]
            image ^= old_image
            representative ^= old_representative
        if not image and representative:
            kernel.append(representative)
    return list(basis(kernel).values())


def _common_stabilizers(stabilizers, stripes, fiber):
    # A local word is trivial for this one search only if it is a stabilizer
    # in *every* physical placement. These intersections also cover degenerate LPs.
    common = None
    independent = basis(stabilizers).values()
    for blocks in stripes:
        mask = sum(((1 << fiber) - 1) << (j * fiber) for j in blocks)
        supported = _zero_images((row & ~mask, row) for row in independent)
        local = [_restrict(row, blocks, fiber) for row in supported]
        if common is None:
            common = local
        elif local:
            common = _zero_images([(word, 0) for word in local] + [(word, word) for word in common])
        else:
            return []
        if not common:
            return []
    return common


@dataclass
class SectorProblem:
    sector: str
    n: int
    checks: list
    stabilizers: list
    anchor_site: int = 0
    stripes: tuple = ()
    fiber: int = 0
    generators: list = field(default_factory=list)

    def text(self):
        return native_matrix(self.n, self.checks, self.stabilizers)

    def symmetry_text(self):
        return symmetry_text(self.n, self.generators)

    def roots(self, period):
        return [site for site in orbit_representatives(self.n, self.generators, period)
                if site >= self.anchor_site]

    def physical_witness(self, code, word):
        if self.stripes:
            for blocks in self.stripes:
                physical = _embed(word, blocks, self.fiber)
                if code.is_logical(physical, self.sector):
                    return physical
            raise ValueError('Constituent witness has no nontrivial physical placement')
        if not (word >> self.anchor_site) or not code.is_logical(word, self.sector):
            raise ValueError('Engine witness is not a nontrivial physical logical in this root set')
        return word


def _stripe_generators(generators, stripes, fiber):
    """Induce a common local action, allowing permutations of entire stripes."""
    if not generators:
        return []
    sites = [[block * fiber + offset for block in blocks for offset in range(fiber)]
             for blocks in stripes]
    coordinates = {site: (stripe, local) for stripe, row in enumerate(sites)
                   for local, site in enumerate(row)}
    induced = []
    for generator in generators:
        common = None
        for row in sites:
            images = [coordinates.get(generator[site]) for site in row]
            if any(image is None for image in images) or len({image[0] for image in images}) != 1:
                raise ValueError('LP symmetry must map each stripe to a whole stripe; use the css profile for this action')
            local = [image[1] for image in images]
            if common is not None and local != common:
                raise ValueError('LP symmetry must induce the same action in every stripe; use the css profile for this action')
            common = local
        induced.append(common)
    return induced


def search_problems(code, config):
    problems = {}
    for sector in config['sectors']:
        checks, stabilizers, _ = code.sector(sector)
        generators = code.symmetry_generators if config.get('generator_symmetry') else []
        whole = SectorProblem(sector, code.n, checks, stabilizers, generators=generators)
        if 'lp_anchor_site' not in config:
            problems[sector] = whole
            continue
        sa, sc, fiber = layout(code)
        if fiber % config.get('period', code.period):
            raise ValueError('LP block_size must be divisible by the active cyclic period. '
                             'Use --no-symmetry or the css profile for this action')
        first_sites = sa * sc * fiber
        if type(config['lp_anchor_site']) is not int or config['lp_anchor_site'] != first_sites:
            raise ValueError('LP anchor does not match the declared tensor dimensions')
        whole.anchor_site = first_sites
        if any((site < first_sites) != (image < first_sites)
               for generator in generators for site, image in enumerate(generator)):
            raise ValueError('LP symmetry must preserve both tensor blocks; use the css profile for this action')
        problems[sector + '-anchor'] = whole
        if sector == 'Z':
            stripes = tuple(tuple(a * sc + b for a in range(sa)) for b in range(sc))
        else:
            stripes = tuple(tuple(a * sc + b for b in range(sc)) for a in range(sa))
        # Project the original binary checks. Row operations (including balanced
        # quaternary presentations) may change the written rows of individual stripes.
        first_mask = (1 << first_sites) - 1
        restricted = [row & first_mask for row in checks]
        stripe_rows = [[v for row in restricted if (v := _restrict(row, blocks, fiber))] for blocks in stripes]
        first = stripe_rows[0]
        if any(rows != first and not same_span(rows, first) for rows in stripe_rows[1:]):
            raise ValueError('The physical LP stripes have different check kernels')
        if sum(map(len, stripe_rows)) != sum(bool(row) for row in restricted):
            if len(basis(restricted)) != len(stripes) * len(basis(first)):
                raise ValueError('The physical checks couple LP stripes')
        trivial = _common_stabilizers(stabilizers, stripes, fiber)
        local_generators = _stripe_generators(generators, stripes, fiber)
        local_n = len(stripes[0]) * fiber
        validate_generators(local_generators, local_n, first, trivial)
        problems[sector + '-stripe'] = SectorProblem(sector, local_n, first, trivial,
                                                     stripes=stripes, fiber=fiber,
                                                     generators=local_generators)
    return problems
