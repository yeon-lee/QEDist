# General stabilizer-code distance

`certify-stabilizer` accepts commuting Pauli generators, including mixed X/Y/Z checks, and measures weight on physical qubits. Every nonidentity single-qubit Pauli contributes one to the weight.

## Run the five-qubit code

```sh
qedist inspect-stabilizer examples/five_qubit.json
qedist certify-stabilizer examples/five_qubit.json --cutoff 2 --shards 3 --workers 3 --seconds 30 --out runs/five-qubit
qedist audit-stabilizer runs/five-qubit
qedist export runs/five-qubit --output five-qubit-proof.tar.gz
qedist audit-bundle five-qubit-proof.tar.gz
```

The exclusion through weight two and a checked weight-three logical give `EXACT_DISTANCE` with `exact_distance: 3`. Its verified cyclic symmetry leaves three Pauli roots, one per shard in this example. Each independent search uses a new output directory. Use `--resume` to continue the same search after its budget is exhausted.

### Plain-fold PP example

The included `examples/plain_fold_p13.json` is the 52-qubit, 15-logical-qubit plain-fold code `j3l8_p13_00382`, with mixed-Pauli checks of weight eight. Its checks and weight-seven witness come from the author's design-principles data. The commands below reproduce exact distance seven by excluding through weight six across all 156 Pauli-column roots. [Original construction](https://github.com/ultra-high-rate-qec/design-principles-data/blob/main/codes/plain_fold/j3l8/instances/j3l8_p13_00382.json)

```sh
qedist certify-stabilizer examples/plain_fold_p13.json --cutoff 6 --seconds 30 --out runs/plain-fold-p13
qedist audit-stabilizer runs/plain-fold-p13
```

## Input formats

The supplied example contains the following input.

```json
{
  "schema": "qedist.stabilizer.v1",
  "name": "Five-qubit perfect code",
  "n": 5,
  "cyclic_period": 5,
  "stabilizers": ["XZZXI", "IXZZX", "XIXZZ", "ZXIXZ"],
  "witnesses": ["XXXXX"]
}
```

The leftmost character acts on qubit zero. Strings contain exactly `n` uppercase `I`, `X`, `Y`, or `Z` characters. The interface specifies the commuting binary symplectic span. Consistent generator signs select an eigenspace and leave distance invariant. Commuting redundant generators and identity rows are allowed. A code with stabilizer rank `r` encodes `n-r` qubits. Distance certification requires at least one encoded qubit.

Alternatively, use paired `x` and `z` lists of sparse row supports. Each pair describes one generator. An index appearing in both lists carries a Y Pauli. This input specifies the same five-qubit code.

```json
{
  "schema": "qedist.stabilizer.v1",
  "n": 5,
  "x": [[0, 3], [1, 4], [0, 2], [1, 3]],
  "z": [[1, 2], [2, 3], [3, 4], [0, 4]]
}
```

Use one representation per input. Optional `witnesses` are Pauli strings in either representation. Every witness is checked for commutation and nontriviality modulo the stabilizer span. `name` and `metadata` hold descriptive information. An initial upper bound is also obtained from an automatically constructed logical quotient basis.

```python
from cssdist import StabilizerCode
from cssdist.stabilizer_run import certify_stabilizer

code = StabilizerCode.from_paulis(
    ["XZZXI", "IXZZX", "XIXZZ", "ZXIXZ"],
    witnesses=["XXXXX"],
    cyclic_period=5,
)
result = certify_stabilizer(code, "runs/five-qubit-python", cutoff=2, seconds=30,
                           shards=3, workers=3)
print(result["exact_distance"], result["witness"])
```

`StabilizerCode.from_symplectic(n, x, z)` accepts the sparse symplectic representation directly.

## Verified qubit symmetry

Two optional input fields specify physical qubit permutations.

- `cyclic_period: P` shifts each consecutive block of `P` qubits by one. The period must divide `n`.
- `symmetry_generators` lists permutations of `0,...,n-1`. Each list maps old index `q` to its new index. All supplied generators and the cyclic action contribute to the joint orbits.

QEDist checks that each permutation preserves the full binary symplectic stabilizer space. A generator may map a check to a product of checks. Preserving the listed rows individually is unnecessary. Invalid symmetry declarations are rejected when the input is loaded, including with `--no-symmetry`.

For product groups, pass each independent translation. The helper `product_translation_generators((a, b, c), blocks=...)` returns these permutations for lexicographic coordinates with the last factor varying fastest. It can be passed as `symmetry_generators` to either stabilizer constructor. Noncommuting generators, fixed points and unequal orbit sizes are also supported. `inspect-stabilizer` reports the chosen `symmetry_root_qubits`.

A verified permutation preserves Pauli weight, commutation and nontriviality modulo stabilizers. Any minimum-weight logical can therefore be moved so that an occupied qubit lies at its joint-orbit representative. QEDist searches the X, Y and Z roots at every such representative. With `r` qubit orbits, this requires `3r` roots. The full binary model still contains all `3n` columns. Root columns are placed first so that the moved support starts at a searched root, and `search/coverage.json` records the permutation of columns. The auditor recomputes the orbits and this mapping from the physical input.

Symmetry reduction is enabled by default. `--no-symmetry` uses all `3n` roots. These declarations describe qubit permutations. Symmetries involving additional local Clifford rotations require a different representation.

## Why the binary search preserves Pauli distance

Each physical qubit contributes three binary columns in the order `X_q, Y_q, Z_q`. A column records its commutation parity with every stabilizer and every member of a complete logical quotient basis. The first set of rows forms `D` and the second forms `O`. A selected set of columns is accepted precisely when `De=0` and `Oe!=0`.

Let $S$ denote the binary symplectic stabilizer span and $N=S^\perp$ its normalizer. The logical rows form a basis of $N/S$, of dimension $2k$. Within $N$, a vector commuting with these rows belongs to $N^\perp=S$. Thus the observable test detects exactly the nontrivial logical operators. Any complete logical quotient basis supplies this test.

A Pauli of weight `w` gives a binary word of weight `w` by selecting its single X, Y, or Z column at each occupied qubit. Conversely, multiply all selected columns on each qubit. This produces a Pauli with the same syndrome and logical action and weight at most the number of selected columns. These two directions prove equality of the binary minimum and the physical Pauli distance. In particular, a Y has a single unit-cost column.

The search uses the existing detector/observable engine, including its weighted-check bounds. Its verified neutral rows include every local triple `{X_q,Y_q,Z_q}` and the supplied stabilizers. A local triple multiplies to identity up to phase. Replacing two columns from that triple by its remaining column shortens the binary representation. Stabilizer rows also preserve both syndrome and logical action. The neutral-overlap rule therefore remains valid with mixed Pauli checks.

## Budgets and proof data

`--shards` partitions the required roots into disjoint contiguous ranges. `--workers` limits concurrent native processes. The number of nonempty shards is at most the number of roots. Each root can have a different search cost, so parallel speedup depends on the distribution of work.

`--seconds` (also spelled `--seconds-per-shard`) and `--node-cap` apply to each shard attempt. The wall budget starts after shared compilation and stabilizer-to-binary conversion. `search_timing` sums the recorded attempt times across workers. Use `--no-weighted-pruning` or `--no-neutral-pruning` to disable the corresponding rule.

```sh
# Start with a bounded parallel search.
qedist certify-stabilizer examples/plain_fold_p13.json --cutoff 6 \
  --shards 12 --workers 4 --seconds-per-shard 30 --out runs/plain-fold-parallel

# Reuse completed shards and retry any unfinished shards with more time.
qedist certify-stabilizer examples/plain_fold_p13.json --cutoff 6 \
  --workers 4 --seconds-per-shard 120 --out runs/plain-fold-parallel --resume
qedist audit-stabilizer runs/plain-fold-parallel
```

Resume retains the input, cutoff, root partition, symmetry, pruning and engine settings. Omitted switches inherit the saved configuration. Worker count and per-attempt time, node and memory budgets may change. Every attempt is preserved. Completed shards are reused, while unfinished shards restart their assigned root ranges. A lower bound of `cutoff + 1` requires completed exclusions for every required range. Partial coverage is reported in `roots_excluded` and the per-shard `jobs` list.

An active campaign has a `.running.lock` file to prevent concurrent writers. If the process is forcibly killed, confirm that its workers have stopped before removing a stale lock and resuming. Saved attempts are checked again on resume, including attempts written before a summary update. Earlier single-run records remain auditable. Continuing those records requires a new campaign directory because their format predates shard resume.

Storage selection is automatic. The fast engine handles inputs within its capacity, and larger requests use the expanded-storage engine. `--large-capacity` forces expanded storage, and `--no-large-capacity` requires the fast engine. `--memory-mib` sets a budget for native vector allocations and selects expanded storage. In Python, pass `large_capacity=None`, `True`, or `False`, and optionally `memory_mib`. The selected capacity is recorded in `search/config.json`. [Capacity and memory details](native-profiles.md)

```sh
qedist certify-stabilizer examples/plain_fold_p13.json --cutoff 6 --large-capacity --memory-mib 256 --out runs/plain-fold-expanded
```

Dimensions and cutoffs follow the selected engine's limits. The dedicated CSS interface additionally supports the LP tensor-block reduction.

The run directory preserves the original stabilizer input, the conversion identifier, orbit coverage, binary model, native sources, immutable per-shard attempts, physical Pauli witness and checksums. `audit-stabilizer` rebuilds the binary model and symmetry coverage, checks each shard's input and root range, and verifies the physical witness. A timeout or interrupted search retains only the established lower bound and checked upper bound. Exact distance requires a matching completed lower bound and checked witness.

A native allocation failure records `resource_limit` and an incomplete search. The auditor also accepts the saved engine identities of earlier non-CSS runs.

The exported bundle includes these records and the Python checker. Its lower bound relies on the completed exhaustive execution. The witness can be checked directly against the original Pauli generators.
