# Search engines

QEDist includes three native engines.

| Engine | Source directory | Use |
|---|---|---|
| `css` | `cssdist/native_css` | Default search on physical CSS check matrices. |
| `lp` | `cssdist/native_lp` | CSS search with a verified lifted-product tensor-block reduction. |
| Circuit | `cssdist/native_circuit` | Detector/observable fault models through `certify-circuit`, and general Pauli distance through `certify-stabilizer`. |

Choose `--profile css` or `--profile lp` with `inspect` and `certify`. The default is `css`. `calibrate` uses the CSS engine to measure search times from sampled starting qubits.

## Capacity and memory

Each engine has a fast variant with bounded capacity and an expanded-storage variant. New searches automatically use the fast variant when the input and cutoff fit its limits. The variants use the same pruning rules. The fast native sources are byte-identical to the original engines and are included in each source directory's `fixed/` subdirectory.

| Selection | Behavior |
|---|---|
| Neither capacity flag | Use the fast variant when possible, otherwise expanded storage. On resume, retain the saved engine. |
| `--large-capacity` | Use expanded storage. |
| `--no-large-capacity` | Require the fast variant. Reject inputs or options that exceed its capabilities. |

This choice is available for `certify`, `calibrate`, `certify-circuit`, and `certify-stabilizer`. In Python, pass `large_capacity=None`, `True`, or `False`, respectively.

The CSS and LP fixed-storage variants accept up to 8,192 qubits, 2,048 check rows per sector, check-row weight 64, and cutoff 64. The fast circuit variant already sizes its matrix storage dynamically. It accepts an effective recursive search depth through 512 and applies an 8 GiB guard to its estimated base storage. Effective depth is the smaller of the cutoff and the number of fault mechanisms. Inputs exceeding these limits select expanded storage automatically. Specifying `--memory-mib` also selects expanded storage, which implements the allocation budget. Combining it with `--no-large-capacity` is rejected.

Expanded storage sizes matrices, syndromes and branch storage to the input. Check neighborhoods use one machine word for up to 64 entries and multiple words for larger rows. An explicit heap-backed stack supports deep searches. Dimensions and requested cutoffs must fit a signed 32-bit integer, up to 2,147,483,647. The effective search depth also respects the number of physical coordinates. Expanded storage can add overhead on inputs that fit the fast variant, which is why selection defaults to the latter.

`--memory-mib` optionally bounds live native vector capacity for each worker. It covers the matrix storage, bit masks, pruning scratch and search frames. The allocator checks the budget before each allocation, including the temporary overlap of old and new storage during vector growth. With the option omitted, allocations proceed as available memory permits. Python input validation, compiler memory and other process overhead contribute additional resident memory beyond this budget.

An allocation failure records `resource_limit` with `resource: memory`, the configured budget and peak tracked allocation. The attempt is incomplete and has no search-node count. Its transcript gives no exclusion credit. CSS, LP and general stabilizer campaigns can resume with a larger budget or with the option omitted. Each worker has its own budget, so total native usage can scale with `--workers`. Runtime can still grow exponentially with the cutoff.

The CSS engine uses minimum-availability check selection, stabilizer-overlap pruning, packing bounds, signed weighted-check bounds and kernel-parity reduction. The weighted bound includes up to four satisfied-check repairs. Ties between equally small check neighborhoods use overlap information through support weight eight.

The LP engine applies the same search policy to two problems covering each required logical sector. It searches supports that touch the second tensor block and supports confined to the first block. The [LP guide](lp-block-search.md) specifies the input layout and the coverage argument.

## Kernel parity

Both engines test whether the all-ones vector is a sum of the syndrome-check rows. When this holds, every kernel vector has even weight, so excluding through an odd cutoff `W` is equivalent to excluding through `W-1`. The native transcript records both cutoffs and the check rows giving the all-ones vector. The Python auditor independently verifies that sum and the row-space condition. At cutoff one, this can establish exclusion with zero search nodes.

## Fixed search policy and existing records

Both CSS engines use `fractional=2 repair-depth=8 even-repairs=4`. These settings are recorded and checked in every completed run. Source checksums cover `exact.cpp`, `common.hpp`, `symmetry.hpp`, and `even_methods.inc`. A resumed run must retain its input, engine, cutoff, partition and symmetry settings.

New `certify` searches, CSS calibration and the example benchmark runner enable the proposed-addition test by passing `proposed-additions=on` to the engine. It rejects a candidate qubit when the parent's weighted inequality already exceeds the remaining budget after adding that qubit. Use `--no-proposed-additions` to disable the test. With neither flag supplied, resume inherits the saved setting. Older records without this field mean disabled. The audit checks the setting, and an explicit change on resume is rejected.

The native executable's omitted-option behavior remains disabled so that saved commands retain their original meaning. The public commands select the appropriate setting before invoking it.

The auditor and resume path recognize the former `weighted8192` and `lpblocks8192` labels. New runs record `css` or `lp` and the selected `large_capacity` setting. Earlier records are identified from their native source hashes. Auditing uses each recognized engine's capacity and root-coverage rules, and resuming executes its saved engine. An explicit conflicting capacity flag on resume is rejected. The optional allocation budget requires the expanded-storage engine. Original source and transcript checks apply throughout. Other retired implementations require the corresponding archived package.
