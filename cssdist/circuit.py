"""Detector/observable inputs for unit-cost, binary circuit-fault distance.

A certificate concerns the supplied additive fault model, not an arbitrary
physical noise process or decoder. Whole DEM errors remain single columns.
Stim is optional and is imported only by the import helpers.
"""
import copy
import json
from pathlib import Path

from .algebra import support, vector
from .code import digest, json_bytes

SCHEMA = 'qedist.detector.v1'
METRIC = 'independent_unit_fault_mechanisms'


class DetectorModel:
    def __init__(self, document):
        if not isinstance(document, dict) or document.get('schema') != SCHEMA:
            raise ValueError(f'Expected a JSON object with schema {SCHEMA}')
        data = copy.deepcopy(document)
        self.n = data.get('n_faults')
        if type(self.n) is not int or not 1 <= self.n <= 2**31-1:
            raise ValueError('n_faults must be a positive signed-32-bit integer')
        if data.get('metric', METRIC) != METRIC:
            raise ValueError('Only independent unit-cost binary fault mechanisms are supported')
        if not isinstance(data.get('metadata', {}), dict):
            raise ValueError('metadata must be an object')
        self.rows = {}
        for key in ('detector_rows', 'observable_rows', 'neutral_rows'):
            rows = data.get(key, [] if key == 'neutral_rows' else None)
            if not isinstance(rows, list):
                raise ValueError(f'{key} must be a list of sparse supports')
            self.rows[key] = [vector(row, self.n) for row in rows]
            data[key] = [support(row) for row in self.rows[key]]
        self.detectors = self.rows['detector_rows']
        self.observables = self.rows['observable_rows']
        self.neutrals = self.rows['neutral_rows']
        if not self.observables:
            raise ValueError('At least one annotated logical observable is required')
        columns = self.columns() if self.neutrals else []
        for neutral in self.neutrals:
            signature = 0
            for j in support(neutral):
                signature ^= columns[j]
            if not neutral or signature:
                raise ValueError('Every neutral row must be nonempty and satisfy Dg=Og=0')
        witnesses = data.get('witnesses', [])
        if not isinstance(witnesses, list):
            raise ValueError('witnesses must be a list of supports')
        self.witnesses = [vector(row, self.n) for row in witnesses]
        if any(not self.is_logical(word) for word in self.witnesses):
            raise ValueError('Invalid undetected logical fault witness')
        data['witnesses'] = [support(row) for row in self.witnesses]
        data['metric'] = METRIC
        self.document = data

    @classmethod
    def load(cls, path):
        return cls(json.loads(Path(path).read_text()))

    @classmethod
    def from_sparse(cls, n_faults, detector_rows, observable_rows, **kwargs):
        return cls(dict(kwargs, schema=SCHEMA, n_faults=n_faults,
                        detector_rows=detector_rows, observable_rows=observable_rows))

    @property
    def fingerprint(self):
        return digest(json_bytes(self.document))

    def save(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as target:
            target.write(json_bytes(self.document))

    def is_logical(self, word):
        return (type(word) is int and 0 < word < (1 << self.n)
                and not any((word & row).bit_count() & 1 for row in self.detectors)
                and any((word & row).bit_count() & 1 for row in self.observables))

    def check_witness(self, indices):
        word = vector(indices, self.n)
        if not self.is_logical(word):
            raise ValueError('Witness must satisfy De=0 and Oe!=0')
        return {'weight': word.bit_count(), 'support': support(word),
                'observable_flips': [i for i, row in enumerate(self.observables)
                                     if (word & row).bit_count() & 1]}

    def native_text(self):
        header = f'QEDIST_CIRCUIT_V1 {self.n} {len(self.detectors)} {len(self.observables)} {len(self.neutrals)}'
        lines = [header]
        for rows in (self.detectors, self.observables, self.neutrals):
            for row in rows:
                indices = support(row)
                lines.append(' '.join(map(str, [len(indices), *indices])))
        return '\n'.join(lines) + '\n'

    def columns(self):
        result = [0] * self.n
        for i, row in enumerate(self.detectors + self.observables):
            for j in support(row):
                result[j] |= 1 << i
        return result

    def inspect(self):
        degrees = [0] * self.n
        for row in self.detectors:
            for j in support(row):
                degrees[j] += 1
        return {'schema': SCHEMA, 'fingerprint': self.fingerprint, 'metric': METRIC,
                'n_faults': self.n, 'detectors': len(self.detectors),
                'observables': len(self.observables), 'neutral_relations': len(self.neutrals),
                'max_faults_per_detector': max((r.bit_count() for r in self.detectors), default=0),
                'max_detectors_per_fault': max(degrees, default=0),
                'hyperedge_faults': sum(d > 2 for d in degrees),
                'known_upper_bound': min((r.bit_count() for r in self.witnesses), default=None),
                'symmetry': 'all fault coordinates are roots in the default search',
                'physical_fault_correspondence': self.document.get('metadata', {}).get(
                    'physical_fault_correspondence', 'not established by this input validator')}

    def with_sparse_neutrals(self, pair_budget=200_000, max_relations=10_000):
        """Find a bounded optional subset of weight <=3 neutral relations.

        Pair attempts are between columns sharing a detector. Incompleteness of
        this helper affects only pruning strength: all returned rows are checked.
        It is not an enumeration certificate or a distance bound.
        """
        if (type(pair_budget) is not int or pair_budget < 0 or
                type(max_relations) is not int or max_relations < 0):
            raise ValueError('Neutral-generation budgets must be nonnegative integers')
        columns = self.columns()
        first = {}
        relations = set(self.neutrals)
        cap = len(relations) + max_relations
        for i, col in enumerate(columns):
            if len(relations) >= cap:
                break
            if col == 0:
                relations.add(1 << i)
            elif col in first:
                relations.add((1 << i) | (1 << first[col]))
            else:
                first[col] = i
        # Include all signatures even if an early relation cap was reached.
        for i, col in enumerate(columns):
            first.setdefault(col, i)
        seen = set()
        stop = len(relations) >= cap or pair_budget == 0
        for row in self.detectors:
            if stop:
                break
            indices = support(row)
            for offset, i in enumerate(indices):
                for j in indices[offset + 1:]:
                    pair = (i, j)
                    if pair in seen:
                        continue
                    seen.add(pair)
                    k = first.get(columns[i] ^ columns[j])
                    if k is not None and k != i and k != j:
                        relations.add((1 << i) | (1 << j) | (1 << k))
                    if len(seen) >= pair_budget or len(relations) >= cap:
                        stop = True
                        break
                if stop:
                    break
        data = copy.deepcopy(self.document)
        data['neutral_rows'] = [support(v) for v in sorted(relations,
                               key=lambda v: (v.bit_count(), tuple(support(v))))]
        data.setdefault('metadata', {})['neutral_generation'] = {
            'method': 'bounded_shared_detector_pairs_v1', 'pair_budget': pair_budget,
            'pairs_examined': len(seen), 'max_new_relations': max_relations,
            'new_relations': len(relations) - len(set(self.neutrals)),
            'complete': False, 'distance_claim': None}
        return DetectorModel(data)


def _stim():
    try:
        import stim
    except ImportError as exc:
        raise ValueError('Stim import requires the optional dependency: pip install "qedist[circuit]"') from exc
    return stim


def from_dem_text(text, *, metadata=None):
    stim = _stim()
    dem = stim.DetectorErrorModel(text).flattened()
    detector_rows = [[] for _ in range(dem.num_detectors)]
    observable_rows = [[] for _ in range(dem.num_observables)]
    events = []
    for index, instruction in enumerate(dem):
        if instruction.type != 'error':
            continue
        probability, = instruction.args_copy()
        if probability <= 0:
            continue
        det, obs, separators = set(), set(), 0
        for target in instruction.targets_copy():
            if target.is_separator():
                separators += 1
                continue  # Components of ONE event: XOR their complete targets.
            if target.is_relative_detector_id():
                dest = det
            elif target.is_logical_observable_id():
                dest = obs
            else:
                raise ValueError('Unsupported DEM error target')
            if target.val in dest:
                dest.remove(target.val)
            else:
                dest.add(target.val)
        j = len(events)
        for i in det:
            detector_rows[i].append(j)
        for i in obs:
            observable_rows[i].append(j)
        events.append({'flattened_instruction': index, 'probability': probability,
                       'detectors': sorted(det), 'observables': sorted(obs),
                       'correlated_component_separators': separators})
    meta = copy.deepcopy(metadata or {})
    meta.update({'dem_sha256': digest(text.encode()), 'stim_version': stim.__version__,
                 'event_interpretation': 'one positive-probability DEM error instruction per unit-cost column; separators are not separate faults',
                 'events': events})
    return DetectorModel.from_sparse(len(events), detector_rows, observable_rows, metadata=meta)


def import_dem(path):
    path = Path(path)
    raw = path.read_bytes()
    return from_dem_text(raw.decode(), metadata={'source_name': path.name,
                         'source_sha256': digest(raw), 'source_type': 'stim_dem'})


def import_stim(path):
    """Import without disjoint-error approximation or graphlike decomposition.

    These flags alone do not establish physical-location fault-count equivalence
    for arbitrary channels. That is explicitly left as a separate obligation.
    """
    path = Path(path)
    stim = _stim()
    raw = path.read_bytes()
    circuit = stim.Circuit(raw.decode())
    dem = circuit.detector_error_model(decompose_errors=False,
              approximate_disjoint_errors=False, flatten_loops=True)
    return from_dem_text(str(dem), metadata={
        'source_name': path.name, 'source_sha256': digest(raw),
        'source_type': 'stim_circuit', 'num_qubits': circuit.num_qubits,
        'num_ticks': circuit.num_ticks,
        'conversion': {'decompose_errors': False, 'approximate_disjoint_errors': False,
                       'flatten_loops': True},
        'physical_fault_correspondence': 'DEM event count; equivalence to faulty circuit locations requires a noise-model-specific argument'})
