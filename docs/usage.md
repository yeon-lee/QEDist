# Using QEDist

Commands below assume QEDist is installed and the source or companion folder is the current directory. `python -m cssdist` can replace `qedist`.
Use a fresh output directory for each independent campaign.

## Physical check matrices

```python
from cssdist import CSSCode
from cssdist.campaign import certify

code = CSSCode.from_sparse(n=4, hx=[[0, 1, 2, 3]], hz=[[0, 1, 2, 3]])
result = certify(code, 'runs/my-code', cutoff=1, seconds_per_shard=30)
print(result['exact_distance'])  # 2
```

`CSSCode.from_dense(hx, hz)` accepts rows of binary integers. Physical sparse
supports use zero-based qubit indices. Polynomial and F₄ conventions are given
in [input-format.md](input-format.md). `k=0` inputs have no nontrivial logical
distance and are rejected.

Import or export check matrices as plain-text sparse `.mtx` files.

```sh
qedist import-matrices hx.mtx hz.mtx --output runs/imported.json
qedist export-matrices runs/imported.json \
  --hx runs/hx-export.mtx --hz runs/hz-export.mtx
```

Supported files are `coordinate integer general` or `coordinate pattern general`,
with one-based indices and binary coefficients. Repeated entries sum modulo two.
Only add `--period P` when the matrices use consecutive length-P cyclic blocks;
the corresponding physical translation must preserve both stabilizer spaces.
Matrix import does not infer sector exchange.

## Run limits and resume

General stabilizer inputs use `certify-stabilizer` and `audit-stabilizer`. That interface supports verified qubit symmetries, `--shards`, `--workers` and `--resume`. Its `--seconds` and `--seconds-per-shard` flags are aliases for the per-shard wall budget. Omitted symmetry and pruning flags inherit the saved configuration on resume. [General stabilizer example, coverage proof and conventions](stabilizer-distance.md)

A shard is an independent partition of the search. For CSS inputs, `--shards` sets the number of partitions per sector or LP subproblem, and `--workers` limits how many run concurrently.

```sh
qedist certify examples/independent_qc.json --cutoff 3 \
  --shards 4 --workers 2 --seconds-per-shard 30 --out runs/resumable
qedist certify examples/independent_qc.json --cutoff 3 \
  --shards 4 --workers 2 --seconds-per-shard 60 --out runs/resumable --resume
```

Code, cutoff, shard partition, native profile and symmetry/pruning settings must
stay fixed. Time or node limits may increase. Completed shards are reused;
unfinished shards restart their assigned search, retaining records of prior
attempts. Changing the number of concurrent workers does not change the
partition. More shards can repeat work near the top of the search tree.

New CSS searches and calibration enable the proposed-addition test by default.
Use `--no-proposed-additions` to disable it for either command. On resume,
omitting this option and `--proposed-additions` inherits the campaign's saved
setting. Older campaigns without this field retain the disabled setting.
An explicit conflicting flag is rejected. In Python, `certify` uses
`proposed_additions=None` for this automatic choice. Pass `True` or `False`
to choose explicitly. `calibrate` defaults to `proposed_additions=True`.

New searches automatically select the fast engine when the input
and cutoff fit, and expanded storage otherwise. Use `--large-capacity` to force
expanded storage or `--no-large-capacity` to require the fast variant. The latter
rejects inputs and options exceeding its capabilities. A resumed campaign keeps
its recorded engine, and a conflicting flag is rejected. The Python argument
`large_capacity=None` makes the automatic choice, with `True` and `False` forcing
the corresponding variant. This option is available for `certify`, `calibrate`,
`certify-circuit` and `certify-stabilizer`. See [engine capacities](native-profiles.md#capacity-and-memory).

`--node-cap` bounds native nodes. Limits apply per shard; native checks are
periodic and the wrapper allows a small cleanup grace period. For `certify`, `--stop-on-witness`
stops launching additional shards after a physically verified witness is found;
already-running shards finish under their limits. No pending shard receives
lower-bound credit.

`--memory-mib 1024` optionally budgets one GiB of live native vector allocations
per worker. It is available for `certify`, `calibrate`, `certify-circuit` and `certify-stabilizer`,
or as `memory_mib=1024` in their Python calls. A memory budget automatically
selects expanded storage and cannot be combined with `--no-large-capacity`.
Omitting the budget allows allocations as memory permits. Input validation in
Python and other process overhead use
additional memory. Reaching the allocation budget records an incomplete
attempt, whose node count is unavailable. CSS, LP and general stabilizer campaigns can resume with a
larger budget or with the option omitted. Campaigns saved with fixed storage
retain that engine and accept time and node budgets.

For CSS inputs, `--no-symmetry` uses every physical qubit as a starting point (root) in both sectors. `--no-coset-pruning`
disables stabilizer-overlap pruning but does not produce a complete pool of
low-weight logical representatives. Distance certification and pool enumeration
have different completeness requirements.

## Results and exit status

| Exit code | Outcome |
|---|---|
| 0 | Exact distance or completed certified interval. |
| 10 | Witness found without a matching completed lower bound. |
| 75 | Incomplete required search. |
| 2 | Invalid input, incompatible records or execution failure. |

A weight-one witness is already exact for a code with `k>0`. A verified parity
certificate can also tighten the effective cutoff. The requested cutoff and
physical certificate remain in the records; the audit checks the reduction.

Each run preserves physical inputs, immutable configuration, native sources,
build identity, executable, transcripts, attempts and witnesses. Recompute the
bounds with `qedist audit RUN_DIRECTORY` for CSS or LP runs, with
`qedist audit-stabilizer RUN_DIRECTORY` for general stabilizer runs, and with
`qedist audit-circuit RUN_DIRECTORY` for circuit runs. Inspect
`distance_lower_bound`, `distance_upper_bound` and `exact_distance` in the output.
A circuit result can have `status: EXCLUDED` and a non-null `exact_distance`
when the exclusion and a checked witness give matching bounds. A
`WITNESS_FOUND` result returns exit code 10, including when reproduced by an
audit. Copy the complete directory when transferring a campaign.

A `.running.lock` prevents simultaneous writers. Remove a stale lock only after
confirming the original writer has stopped. Keep failed and timed-out attempts:
they are part of the execution history, not evidence of a completed exclusion.

## Cache and profiles

The compiler is selected through the configured C++ toolchain. Use
`qedist certify --help` for the current options, including `--cache` when you
want build files in a specified directory. Original campaigns must be resumed
with their recorded profile; they are never migrated to the current default.
See [native-profiles.md](native-profiles.md).

## Tests

From the release root, with the wheel installed or the source available:

```sh
python -m unittest discover -s tests -v
```

The suite compares small instances against direct support enumeration and
exercises symmetry checks, parity, degeneracy, sharding, resume, source
identity and tampered evidence. Passing tests does not certify a new input;
that requires a completed campaign and audit.

For a small functionality replay:

```sh
python -m tools.benchmark --cases polynomial_20 independent_qc \
  --out runs/functionality --summary runs/functionality-summary.json
```

This includes local startup and build effects. The [benchmark guide](benchmarking.md)
explains how to control the inputs, budgets and timing scope in a comparison.

For LP tensor blocks, including non-Abelian inputs, see [split search and per-shard budgets](lp-block-search.md). For detector/observable models, see [circuit search](CIRCUIT_DISTANCE.txt).
