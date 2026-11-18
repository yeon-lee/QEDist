# QEDist

QEDist certifies the minimum weight of a logical operator from stabilizer checks, including general mixed-Pauli generators and binary CSS matrices. It also certifies fault distance in detector/observable models. A completed exhaustive search gives a lower bound, a checked logical witness gives an upper bound, and matching bounds give the exact distance.

## How to cite

If you use QEDist in your research, please cite:

Jong Yeon Lee, *QEDist: Practical Exact Distance Certification for Stabilizer Codes*, [arXiv:2611.21709](https://arxiv.org/abs/2611.21709) (2026).

```bibtex
@misc{lee2026qedist,
  title={{QEDist}: Practical Exact Distance Certification for Stabilizer Codes},
  author={Jong Yeon Lee},
  year={2026},
  eprint={2611.21709},
  archivePrefix={arXiv},
  primaryClass={quant-ph},
  url={https://arxiv.org/abs/2611.21709},
}
```

Please also report the QEDist version used for your computations.

## Development history

The prototype underlying QEDist was developed in late July 2026. It was subsequently used in the following two papers.

- *Design Principles for Ultra-High-Rate Quantum Codes* (September 2026). [arXiv:2609.30069](https://arxiv.org/abs/2609.30069)
- *Designing Group-Valued Codes with Full Regular Low-Weight Bases* (October 2026). [arXiv:2610.06820](https://arxiv.org/abs/2610.06820)

## Install and try it

QEDist **0.1** requires Python 3.10+ and a C++17 compiler on macOS or Linux. The native engine is compiled on first use. The core package uses the Python standard library.

Clone the repository and enter its directory.

```sh
git clone https://github.com/yeon-lee/QEDist.git
cd QEDist
```

For a source or companion archive, open the extracted folder. Check the available Python and compiler versions.

```sh
python3 --version
c++ --version
```

Use Python 3.10 or later to create the environment below. If `python3` reports an older version, use your newer interpreter's command, such as `python3.12 -m venv .venv`. A C++17-capable compiler must be available as `c++`, or selected with the search command's `--compiler` option. After activation, `python` and `qedist` use this environment.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
qedist certify examples/catalogue/lp-f2-20-4-3.json --cutoff 2 --out runs/lp20
qedist audit runs/lp20
```

This example certifies distance 3 for a 20-qubit code. Use a new output directory for each independent run. `qedist`, `cssdist`, and `python -m cssdist` invoke the same interface. A wheel can also be installed with `python -m pip install /path/to/qedist-0.1-py3-none-any.whl`. The source and companion downloads include the example files used here.

## Choose an input format

| What you have | What to supply | Command |
|---|---|---|
| Physical CSS checks | JSON with `n`, `hx`, and `hz` | `qedist certify code.json ...` |
| General stabilizer checks | JSON with `n` and Pauli strings in `stabilizers` | `qedist certify-stabilizer code.json ...` |
| Cyclic lifted-product constituents | JSON with `A`, optional `C`, `field`, and `period` | `qedist certify lp.json ...` |
| Non-Abelian or other expanded LP codes | Physical CSS JSON with `lp_layout` | `qedist certify code.json --profile lp ...` |
| Plain-text sparse check matrices (`.mtx`) | `hx.mtx` and `hz.mtx` | `qedist import-matrices hx.mtx hz.mtx --output code.json` |
| A detector/observable fault model | JSON with fault indices in detector and observable rows | `qedist certify-circuit model.json ...` |
| A Stim circuit or detector error model | A `.stim` or `.dem` file | `qedist import-circuit memory.stim --output model.json` |

The default `css` engine accepts physical CSS inputs and cyclic LP descriptions. `--profile lp` additionally uses the LP tensor-block reduction and requires a verified LP layout. Circuit inputs use the separate `certify-circuit` command. Each engine has a fast variant with bounded capacity and an expanded-storage variant, selected automatically from the input and cutoff. [Search engines](docs/native-profiles.md)

### Physical CSS checks

Save the following as `code.json`.

```json
{
  "schema": "cssdist.code.v1",
  "name": "Four-qubit example",
  "n": 4,
  "hx": [[0, 1, 2, 3]],
  "hz": [[0, 1, 2, 3]]
}
```

Each matrix row lists the **zero-based qubit indices** on which a stabilizer acts. Here the checks are `XXXX` and `ZZZZ`. QEDist verifies CSS commutation and computes the ranks and number of logical qubits. Optional `witnesses` can supply known logical operators. Otherwise, the program constructs valid logical representatives to obtain initial upper bounds.

```sh
qedist inspect code.json
qedist certify code.json --cutoff 1 --seconds-per-shard 30 --out runs/four-qubit
qedist audit runs/four-qubit
```

This example gives `exact_distance: 2`. The same checks can be passed from Python through `CSSCode.from_sparse(n, hx, hz)` or `CSSCode.from_dense(hx, hz)`. The `.mtx` importer accepts plain-text sparse coordinate files with 0/1 entries and one-based indices. [Complete input conventions](docs/input-format.md) · [Python and matrix-file examples](docs/usage.md)

### General stabilizer checks

For non-CSS codes, supply commuting Pauli strings or sparse binary symplectic rows. Qubit zero is the leftmost character, and X, Y and Z each have weight one. The included five-qubit code certifies distance three with the following commands.

```sh
qedist inspect-stabilizer examples/five_qubit.json
qedist certify-stabilizer examples/five_qubit.json --cutoff 2 \
  --shards 3 --workers 3 --seconds-per-shard 30 --out runs/five-qubit
qedist audit-stabilizer runs/five-qubit
```

The search automatically constructs a complete set of logical tests and verifies the physical Pauli witness. It uses the detector/observable engine on three columns per qubit, with weighted-check and neutral-relation pruning. Optional `cyclic_period` and `symmetry_generators` are checked against the full stabilizer space. The five-qubit example declares its cyclic symmetry, reducing the starting roots from 15 to 3. `--no-symmetry` searches all roots.

Use `--shards` to partition the roots and `--workers` to run partitions concurrently. To continue an incomplete run, repeat the command with `--resume` and a larger `--seconds-per-shard` budget. Completed shards are reused, and unfinished shards restart their assigned roots. Omitted symmetry and pruning flags retain their saved settings on resume. Storage selection is automatic, with `--large-capacity`, `--no-large-capacity`, and `--memory-mib` available for explicit control. [Input formats, symmetry, resume and coverage proof](docs/stabilizer-distance.md)

### Cyclic lifted-product constituents

Save the following as `lp.json`.

```json
{
  "schema": "cssdist.lp.v1",
  "field": 2,
  "period": 4,
  "A": [[1, [[0, 1], [1, 1], [3, 1]]]]
}
```

A matrix entry is a constant or a list of `[exponent, coefficient]` terms. The second entry above is `1 + t + t^3`, with exponents taken modulo 4. The optional second constituent `C` defaults to `A`. QEDist constructs the physical checks from these constituents.

```sh
qedist inspect lp.json --profile lp
qedist certify lp.json --profile lp --cutoff 2 --out runs/custom-lp20
qedist audit runs/custom-lp20
```

This also gives a 20-qubit code with distance 3. For quaternary constituents, set `field` to 4 and represent coefficients `0, 1, ω, ω²` by `0, 1, 2, 3`. QEDist converts the construction into binary check matrices and measures logical-operator weight on the physical qubits. The two constituent matrices may differ and may be rank deficient. [LP input conventions](docs/input-format.md#cyclic-lp-inputs) · [LP search coverage](docs/lp-block-search.md)

### Non-Abelian and other expanded LP inputs

The LP block reduction also accepts physical checks from non-Abelian lifted products. Add `lp_layout` to the physical CSS JSON, specifying the constituent shapes and the number of binary coordinates in each lifted block.

```json
"lp_layout": {
  "A_shape": [1, 2],
  "C_shape": [1, 2],
  "block_size": 6
}
```

For binary group-algebra codes, `block_size` is the group order. For binary-expanded F₄ codes, it is twice that order. The first tensor block contains `s_A*s_C` lifted blocks, followed by `r_A*r_C` lifted blocks. QEDist verifies the required stripe equations directly on the physical checks. Symmetry is supplied separately through verified permutations.

```sh
qedist inspect examples/nonabelian_lp.json --profile lp
qedist certify examples/nonabelian_lp.json --profile lp \
  --cutoff 1 --shards 2 --workers 2 --out runs/nonabelian
qedist audit runs/nonabelian
```

This S₃ example has 30 qubits and exact distance 2. Its input includes physical checks and logical witnesses. Use `cyclic_period=1` when supplying only explicit symmetry generators or using no symmetry reduction. [Physical LP layout and coordinate conventions](docs/input-format.md#physical-lp-layouts)

## Optional symmetry

Symmetry reduces how many starting qubits, or *roots*, must be searched. **QEDist verifies each supplied symmetry against the physical stabilizer spaces before using it.**

Physical CSS JSON inputs accept the following optional fields. General stabilizer inputs accept `cyclic_period` and `symmetry_generators` with the same qubit-index conventions, checked against their full symplectic stabilizer space. They search X, Y and Z starting operators at each joint-orbit representative.

| Field | Meaning | When omitted |
|---|---|---|
| `cyclic_period` | Simultaneously shifts each consecutive block of `P` qubits by one position. `P` must divide `n`. | Uses `P = 1`, giving no cyclic reduction. |
| `symmetry_generators` | Lists of qubit permutations, each preserving both stabilizer spaces. Searches one initial qubit per joint orbit of all generators and the declared cyclic action. | Uses the declared cyclic action alone. |
| `sector_exchange` | A list giving the image of every qubit under a permutation that exchanges the X and Z stabilizer spaces. | Searches both CSS sectors. |

For example, adding the following fields to the four-qubit input declares the cycle `0 → 1 → 2 → 3 → 0` and the identity permutation as a sector exchange. These are valid because both check matrices consist of the same all-ones row.

```json
{
  "cyclic_period": 4,
  "sector_exchange": [0, 1, 2, 3]
}
```

The cyclic reduction uses one initial-qubit representative per orbit. A verified sector exchange allows the Z-sector result to transfer to X. For larger inputs, `cyclic_period: 4` also cycles qubits `4, 5, 6, 7`, then `8, 9, 10, 11`, and so on. The qubit ordering must match this convention. The `.mtx` importer accepts the same declaration through `--period P`.

For a product group such as `C_a × C_b × C_c`, supply each independent translation. The helper below uses lexicographic coordinates, with the last factor varying fastest. `blocks` repeats that action in each consecutive group-sized block.

```python
from cssdist import CSSCode, product_translation_generators

code = CSSCode.from_sparse(
    n=8,
    hx=[list(range(8))],
    hz=[[0, 1], [2, 3], [4, 5], [6, 7]],
    symmetry_generators=product_translation_generators((2, 2, 2)),
)
code.save("product.json")
print(code.inspect()["symmetry_orbit_representatives"])  # [0]
```

Each permutation lists the new index of every old qubit. Independent translations generate the full product action. For `C_2 × C_2 × C_2`, they give one eight-site orbit, while their diagonal product has four two-site orbits. QEDist computes these orbits directly, including fixed points and unequal orbit sizes.

```sh
qedist inspect product.json
qedist certify product.json --cutoff 1 --out runs/product
qedist audit runs/product

# A bivariate-bicycle example with verified C12 × C6 symmetry.
qedist certify examples/symmetry/bb144.json --cutoff 11 --out runs/bb144
qedist audit runs/bb144
```

For cyclic LP inputs, `period` supplies the cyclic action automatically. Extra `symmetry_generators` use the expanded physical qubit numbering. When the two constituent matrices coincide after normalization, QEDist tests for a sector-exchange symmetry. The `lp` profile also checks that each supplied symmetry respects the block structure required by its search reduction. General physical permutations are supported by the `css` profile. `--no-symmetry` disables all these search reductions. [LP block requirements](docs/lp-block-search.md) · [Symmetry conventions and audits](docs/input-format.md#optional-symmetry) · [Product-group benchmarks](docs/product-symmetry-benchmark.md)

## Circuit fault distance

A circuit-model JSON supplies `n_faults`, `detector_rows`, and `observable_rows`. Each row lists zero-based **fault indices**. QEDist searches for the smallest number of fault mechanisms that trigger no detectors and flip at least one specified logical observable. Each mechanism is either present or absent and contributes one to the fault count when present. Optional inputs include witnesses and *neutral relations*, verified combinations of faults that affect neither detectors nor logical observables. [Example JSON](examples/circuit_three_fault_chain.json)

```sh
qedist certify-circuit examples/circuit_three_fault_chain.json \
  --cutoff 2 --seconds 30 --out runs/circuit
qedist audit-circuit runs/circuit
```

This example certifies fault distance 3 using its supplied weight-3 witness.

### Exact distance from a Stim circuit

Install the optional importer and import the circuit. The imported model initially has no supplied witness, so first search through weight 3 to find one.

```sh
python -m pip install '.[circuit]'
qedist import-circuit examples/circuit_three_fault_chain.stim --output model.json
qedist certify-circuit model.json --cutoff 3 --seconds 30 \
  --out runs/stim-witness || test "$?" -eq 10
```

The search reports `WITNESS_FOUND` and `distance_upper_bound: 3`. Exit code `10` means a witness was found. The shell expression accepts that exit code and propagates other errors.

Audit the search and save its checked witness in a new model file. The input validator checks the witness against that model again.

```sh
python - <<'PY'
from cssdist import DetectorModel
from cssdist.circuit_run import audit_circuit

model = DetectorModel.load("model.json")
audited = audit_circuit("runs/stim-witness")
witnesses = [item["support"] for item in audited["checked_witnesses"]]
document = {**model.document, "witnesses": witnesses}
DetectorModel(document).save("model-with-witness.json")
PY
qedist certify-circuit model-with-witness.json --cutoff 2 --seconds 30 \
  --out runs/stim-exact
qedist audit-circuit runs/stim-exact
```

The completed exclusion through weight 2 and the checked weight-3 witness establish exact fault distance 3. The final search and audit report these fields among their output.

```json
{
  "status": "EXCLUDED",
  "distance_lower_bound": 3,
  "distance_upper_bound": 3,
  "exact_distance": 3
}
```

Here `EXCLUDED` describes the search through the requested cutoff. Read `exact_distance` to see whether the lower and upper bounds match. A cutoff-2 search on the original imported model gives only `distance_lower_bound: 3`, with `distance_upper_bound` and `exact_distance` set to `null`.

The importer retains correlated events. The physical interpretation of fault count depends on the supplied noise model and its relation to binary fault mechanisms. Circuit searches have their own verified sector-reduction and time-window options. [Circuit inputs and commands](docs/CIRCUIT_DISTANCE.txt) · [Sector reductions](docs/CIRCUIT_REDUCTIONS.txt)

## Read results and control the budget

The proposed-addition test checks each candidate qubit against the current weighted bound before exploring its branch. It is enabled by default for new `certify` searches with either `--profile css` or `--profile lp`, and for CSS calibration. Use `--no-proposed-additions` to disable it, or `--proposed-additions` to enable it explicitly. On resume, omitting both flags preserves the saved setting, including disabled in older runs. Its benefit depends on the input. [Pruning rule and proof](docs/algorithm.md#testing-proposed-additions)

A cutoff `W` is inclusive. Completing all required exclusions through `W` establishes `d ≥ W + 1`. A checked weight-`D` logical establishes `d ≤ D`. The result is exact when these bounds meet. An unfinished search retains only the bounds justified by its completed work and checked witnesses.

CSS and general stabilizer searches support independent search partitions called *shards*. For CSS inputs, `--shards` sets their number per sector or LP subproblem. For general stabilizer inputs, it partitions the required Pauli roots. `--workers` sets how many run concurrently, and `--seconds-per-shard` limits each shard separately. `--resume` reuses completed shards with the same input and search configuration. Circuit searches use `--seconds`. [Budgets, resume, and exit codes](docs/usage.md)

Capacity selection keeps the fast engine for inputs and cutoffs that fit it. Larger searches automatically use expanded storage. Use `--large-capacity` to force expanded storage, or `--no-large-capacity` to require the faster variant. Both use the same pruning rules. A resumed campaign retains its saved engine. [Capacity limits and selection](docs/native-profiles.md#capacity-and-memory)

The optional `--memory-mib` sets a budget for live native vector allocations per worker and automatically selects expanded storage. Reaching it records an incomplete attempt. With this option omitted, allocations proceed as memory permits. Python and compiler memory contribute additional usage. Expanded-storage dimensions and cutoffs use signed 32-bit integers. [Memory accounting](docs/native-profiles.md#capacity-and-memory)

Use the audit command for the type of result being checked. Each command reconstructs the result from the inputs and execution records.

| Result | Audit command |
|---|---|
| CSS or LP code-distance run | `qedist audit RUN` |
| General stabilizer code-distance run | `qedist audit-stabilizer RUN` |
| Circuit fault-distance run | `qedist audit-circuit RUN` |
| Exported bundle | `qedist audit-bundle bundle.tar.gz` |

Export a run with `qedist export RUN --output bundle.tar.gz`. Lower-bound claims rely on the recorded exhaustive program and its completed execution. [Portable evidence](docs/portable-evidence.md)

## Examples and further documentation

For IBM’s $[[144,12,12]]$ gross code, QEDist verifies circuit fault distance 10 in each sector for one noisy syndrome cycle. Run `python -m cssdist.benchmarks.bb144 --search` to repeat the exclusions and check the witnesses. [BB144 circuit benchmark](cssdist/benchmarks/bb144/README.md)

The paper catalogue lists every Appendix C result with its physical input, exclusion cutoff, timing and reproduction command. It includes the updated weighted-check measurements, Abelian and non-Abelian LP codes, and PP examples. [Paper catalogue and reproduction guide](docs/catalogue.md)

```sh
python -m tools.catalogue list
python -m tools.catalogue run LP04-175 --output runs/catalogue/LP04-175
```

The earlier regular-frame examples remain in [examples/catalogue](examples/catalogue), with their input-conversion checks in `IMPORT_REPORT.json`. General CSS, independent-constituent, and circuit examples are also available under [examples](examples).

The AJ58 example supplies a completed exclusion through weight 19 and checked weight-20 logical operators, certifying distance 20 for a 1,972-qubit LP code. The companion download includes these records and a command to repeat the search. [AJ58 verification example](validation/README.md) · [Benchmarking](docs/benchmarking.md) · [Recorded evidence](docs/evidence.md) · [Citation](docs/citation.md)

The separate `main_v7` reproduction archive contains the manuscript's catalogue inputs, completed-execution records, measurement engines and numerical plotting data. Its guide provides commands for checking the evidence and repeating the comparisons. [Manuscript reproduction](docs/reproduction.md)

## License

QEDist is distributed under the MIT License, copyright (c) 2026 Jong Yeon Lee. [License](LICENSE) · [Notices](NOTICE.md)
