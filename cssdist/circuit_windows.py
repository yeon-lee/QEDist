"""Bounded, optional circuit-window neutral relations for unit fault count.

This module does not assert circuit coverage or a distance bound. Each returned
relation is independently checked against the complete detector/observable
signature, so omitting windows can weaken pruning but cannot invalidate it.
"""
from itertools import product


def window_relations(columns, location_columns, windows, baseline=(), *, max_configurations_per_window=4096):
    """Enumerate one outcome per location in selected small circuit windows.

    ``location_columns[l]`` lists the distinct retained effect indices available
    at physical location l; the identity outcome is always included. A repeated
    column in a configuration cancels modulo two. Cost comparisons use this
    resulting binary support, exactly matching DetectorModel's objective.

    For every complete signature, choose its least-weight support, with a
    deterministic lexicographic tie break. Pair it with heavier supports to
    obtain full-signature null vectors. Equal-cost pairs are intentionally not
    included. ``baseline`` is a collection of already supplied neutral supports.
    Windows exceeding the explicit configuration budget are skipped; this only
    weakens optional pruning and is recorded in the returned statistics.
    """
    if any(type(x) is not int or x < 0 for x in columns):
        raise ValueError('Column signatures must be nonnegative integers')
    if type(max_configurations_per_window) is not int or max_configurations_per_window < 0:
        raise ValueError('The configuration budget must be a nonnegative integer')
    locations = []
    for group in location_columns:
        if any(type(j) is not int or not 0 <= j < len(columns) for j in group):
            raise ValueError('Invalid location column index')
        locations.append(tuple(sorted(set(group))))
    known = set()
    for row in baseline:
        row = tuple(sorted(row))
        if len(set(row)) != len(row) or not row:
            raise ValueError('Invalid baseline support')
        sig = 0
        for j in row:
            if type(j) is not int or not 0 <= j < len(columns):
                raise ValueError('Invalid baseline column')
            sig ^= columns[j]
        if sig:
            raise ValueError('Baseline must preserve detectors and observables')
        known.add(row)
    relations = {}
    counts = dict(windows=0, windows_skipped_budget=0, configurations=0, distinct_window_supports=0,
                  strict_replacements=0, baseline_relations_rediscovered=0)
    for window in windows:
        window = tuple(window)
        if (len(set(window)) != len(window) or not 1 <= len(window) <= 3 or
                any(type(l) is not int or not 0 <= l < len(locations) for l in window)):
            raise ValueError('Windows must contain one to three distinct locations')
        counts['windows'] += 1
        size = 1
        for l in window:
            size *= 1 + len(locations[l])
        if size > max_configurations_per_window:
            counts['windows_skipped_budget'] += 1
            continue
        effects = {}
        for choices in product(*( (None,) + locations[l] for l in window)):
            counts['configurations'] += 1
            word = 0
            sig = 0
            for j in choices:
                if j is not None:
                    word ^= 1 << j
                    sig ^= columns[j]
            effects.setdefault(sig, set()).add(word)
        for sig, words in effects.items():
            counts['distinct_window_supports'] += len(words)
            best = min(words, key=lambda w: (w.bit_count(), tuple(_support(w))))
            for word in sorted(words):
                if word.bit_count() <= best.bit_count():
                    continue
                counts['strict_replacements'] += 1
                row = tuple(_support(word ^ best))
                if row in known:
                    counts['baseline_relations_rediscovered'] += 1
                    continue
                check = 0
                for j in row:
                    check ^= columns[j]
                if not row or check:
                    raise AssertionError('Invalid generated neutral relation')
                relations.setdefault(row, dict(window=list(window),
                    heavier=_support(word), cheaper=_support(best)))
    rows = sorted(relations, key=lambda row: (len(row), row))
    counts['new_distinct_relations'] = len(rows)
    return rows, [dict(support=list(row), **relations[row]) for row in rows], counts


def _support(word):
    result = []
    while word:
        bit = word & -word
        result.append(bit.bit_length() - 1)
        word ^= bit
    return result
