"""Cutoff-specific coverage of connected, minimum-weight circuit faults."""
from collections import Counter

from .circuit import DetectorModel


def detector_layer_ids(model, detectors_per_layer, detector_layers):
    """Assign every detector to a layer, preserving its order within that layer."""
    count = len(model.detectors)
    if detectors_per_layer is not None:
        if detector_layers is not None or type(detectors_per_layer) is not int or detectors_per_layer < 1:
            raise ValueError('Choose either a positive detectors-per-layer count or a detector layer map')
        return [row // detectors_per_layer for row in range(count)]
    if (not isinstance(detector_layers, (list, tuple)) or len(detector_layers) != count
            or any(type(t) is not int or t < 0 for t in detector_layers)):
        raise ValueError('The layer map must give one nonnegative integer for every detector row')
    # Empty time steps have no bearing on detector overlap.
    rank = {t: i for i, t in enumerate(sorted(set(detector_layers)))}
    return [rank[t] for t in detector_layers]


def window_plan(model, cutoff, layers):
    """Cover each possible earliest layer, proving translated containment on full signatures.

    A signature records (offset of first layer, relative detector positions, observables).
    Multiplicities ensure an injective map of unit-cost columns, including duplicates.
    Only whole columns enter a window. The first columns of a representative are its roots.
    """
    if type(cutoff) is not int or not 0 <= cutoff <= 2**31 - 1:
        raise ValueError('Circuit cutoff must be a nonnegative signed 32-bit integer')
    layers = detector_layer_ids(model, None, layers)
    positions = Counter()
    sites = [[] for _ in range(model.n)]
    for row, columns in enumerate(model.document['detector_rows']):
        t = layers[row]
        site = (t, positions[t])
        positions[t] += 1
        for j in columns:
            sites[j].append(site)

    observable_bits = [0] * model.n
    for i, columns in enumerate(model.document['observable_rows']):
        for j in columns:
            observable_bits[j] |= 1 << i

    by_first = [[] for _ in positions]
    last = [0] * model.n
    shapes = [None] * model.n
    max_span = 0
    detector_free_witness = None
    for j, support in enumerate(sites):
        if not support:
            if observable_bits[j] and detector_free_witness is None:
                detector_free_witness = j
            continue
        support.sort()
        first = support[0][0]
        last[j] = support[-1][0]
        max_span = max(max_span, last[j] - first)
        by_first[first].append(j)
        shapes[j] = (tuple((t - first, slot) for t, slot in support), observable_bits[j])

    layer_count = len(by_first)
    length = min(layer_count, cutoff * max_span + 1)
    windows = []
    representatives = []
    signatures = []
    if cutoff > 0 and detector_free_witness is None:
        for start, anchors in enumerate(by_first):
            if not anchors:
                continue
            stop = min(layer_count, start + length)
            columns = []
            counts = Counter()
            for t in range(start, stop):
                for j in by_first[t]:
                    if last[j] < stop:
                        columns.append(j)
                        counts[t - start, shapes[j]] += 1
            # Counts include every observable bit. Comparing detectors alone could
            # discard the only logical fault in an otherwise identical boundary.
            rep = next((i for i, other in enumerate(signatures)
                        if len(columns) <= len(representatives[i]['source_columns'])
                        and counts <= other), None)
            if rep is None:
                rep = len(representatives)
                signatures.append(counts)
                representatives.append({'start': start, 'root_end': len(anchors),
                                        'source_columns': columns})
            windows.append({'start': start, 'stop': stop, 'representative': rep})

    return {'schema': 'qedist.circuit-window-cover.v1', 'cutoff': cutoff,
            'layer_count': layer_count, 'max_fault_span': max_span, 'window_layers': length,
            'detector_free_witness': detector_free_witness,
            'windows': windows, 'representatives': representatives}


def window_model(source, columns):
    """Restrict to whole source faults, removing only identically empty detector rows."""
    local = {j: i for i, j in enumerate(columns)}
    if (not columns or len(local) != len(columns)
            or any(type(j) is not int or not 0 <= j < source.n for j in local)):
        raise ValueError('A window must contain distinct original fault indices')

    def restrict(row):
        return sorted(local[j] for j in row if j in local)

    ds = [selected for row in source.document['detector_rows'] if (selected := restrict(row))]
    obs = [restrict(row) for row in source.document['observable_rows']]
    # A neutral with any omitted fault cannot be used as a truncated relation.
    neutrals = [sorted(local[j] for j in row) for row in source.document['neutral_rows']
                if all(j in local for j in row)]
    return DetectorModel.from_sparse(len(columns), ds, obs, neutral_rows=neutrals)
