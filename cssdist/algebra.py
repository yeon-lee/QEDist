"""Small independent GF(2) routines, using Python integer bit vectors."""
import itertools


def support(word):
    out = []
    while word:
        bit = word & -word
        out.append(bit.bit_length() - 1)
        word ^= bit
    return out


def vector(indices, n):
    if not isinstance(indices, (list, tuple)):
        raise ValueError('A support must be a list of coordinate indices')
    if any(type(j) is not int or not 0 <= j < n for j in indices):
        raise ValueError('Support coordinate outside 0,...,n-1')
    if len(set(indices)) != len(indices):
        raise ValueError('Repeated support coordinate')
    return sum(1 << j for j in indices)


def basis(rows):
    pivots = {}
    for row in rows:
        while row:
            pivot = row.bit_length() - 1
            if pivot not in pivots:
                pivots[pivot] = row
                break
            row ^= pivots[pivot]
    return pivots


def remainder(word, pivots):
    while word:
        pivot = word.bit_length() - 1
        if pivot not in pivots:
            break
        word ^= pivots[pivot]
    return word


def same_span(a, b):
    aa, bb = basis(a), basis(b)
    return len(aa) == len(bb) and all(not remainder(v, bb) for v in aa.values())


def kernel_basis(rows, n):
    pivots = basis(rows)
    out = []
    for free in range(n):
        if free in pivots:
            continue
        word = 1 << free
        for pivot in sorted(pivots):
            if (word & pivots[pivot]).bit_count() % 2:
                word ^= 1 << pivot
        out.append(word)
    return out


def permute(word, permutation):
    return sum(1 << permutation[j] for j in support(word))


def brute_distance(checks, stabilizers, n, cutoff=None):
    """Independent combinatorial oracle for small regression cases only."""
    stab = basis(stabilizers)
    for weight in range(1, min(n, cutoff if cutoff is not None else n) + 1):
        for indices in itertools.combinations(range(n), weight):
            word = sum(1 << j for j in indices)
            if all((word & h).bit_count() % 2 == 0 for h in checks) and remainder(word, stab):
                return weight, list(indices)
    return None
