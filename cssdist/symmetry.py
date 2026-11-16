"""Verified physical permutations and orbits of the group they generate."""
from math import prod

from .algebra import basis, permute, remainder


def validate_generators(generators, n, checks, stabilizers):
    """Check bijectivity and preservation of both binary row spaces."""
    if not isinstance(generators, list):
        raise ValueError('symmetry_generators must be a list of permutations')
    if not generators:
        return
    spaces = (basis(checks), basis(stabilizers))
    for index, generator in enumerate(generators):
        if (not isinstance(generator, list) or len(generator) != n
                or any(type(j) is not int for j in generator)
                or set(generator) != set(range(n))):
            raise ValueError(f'Symmetry generator {index} must be a permutation of 0,...,n-1')
        for space in spaces:
            if any(remainder(permute(row, generator), space) for row in space.values()):
                raise ValueError(f'Symmetry generator {index} does not preserve both check spaces')


def orbit_representatives(n, generators, period=1):
    """Minimum site in each joint orbit, without enumerating group elements.

    Inputs are verified before this function is used for search coverage.
    The optional block-cyclic action is included alongside all generators.
    """
    if not generators:
        return list(range(0, n, period))
    parents = [(j // period) * period for j in range(n)]

    def find(site):
        while site != parents[site]:
            parents[site] = parents[parents[site]]
            site = parents[site]
        return site

    for generator in generators:
        for site, image in enumerate(generator):
            a, b = find(site), find(image)
            parents[max(a, b)] = min(a, b)
    return sorted({find(site) for site in range(n)})


def symmetry_text(n, generators):
    lines = [f'{n} {len(generators)}']
    lines.extend(' '.join(map(str, generator)) for generator in generators)
    return '\n'.join(lines) + '\n'


def product_translation_generators(factors, *, blocks=1):
    """Independent translations of C_a x C_b x ..., in each physical block.

    Coordinates are lexicographic, with the last factor varying fastest.
    The returned permutations map each old qubit index to its new index.
    """
    factors = tuple(factors)
    if not factors or any(type(size) is not int or size < 1 for size in factors):
        raise ValueError('Product factors must be positive integers')
    if type(blocks) is not int or blocks < 1:
        raise ValueError('blocks must be a positive integer')
    volume = prod(factors)
    generators = []
    for axis, size in enumerate(factors):
        stride = prod(factors[axis + 1:])
        generators.append([
            site + stride if (site % volume // stride) % size + 1 < size
            else site - (size - 1) * stride
            for site in range(blocks * volume)
        ])
    return generators
