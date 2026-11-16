# BB144 circuit fault distance

One noisy extraction cycle followed by two noiseless cycles has fault distance **10** in both sectors of IBM's gross code. The static code distance is 12. All twelve logical qubits are monitored. A faulty CNOT costs one even when it acts on both operands. In this CSS circuit any undetectable mixed-Pauli logical has a nontrivial projection in at least one sector at equal or smaller cost. [IBM's experiment](https://github.com/sbravyi/BivariateBicycleCodes/blob/fa77e3333d3ec44c79d8f914dd24c040d1da471b/circuit_distance.py)

| Single-core search | X faults | Z faults |
| --- | ---: | ---: |
| Exclude up to nine faults | 8.35 s | 6.79 s |
| Find a ten-fault logical | 49.01 s | 6.80 s |

The times are native search times on an AMD EPYC 7713 on the Illinois Campus Cluster. They exclude preprocessing, compilation and queue time. The two exclusion runs visited 7,619,164 and 6,986,955 nodes.

## Reproduce

From an installed QEDist 0.1 or its source root, run:

```sh
python -m cssdist.benchmarks.bb144
python -m cssdist.benchmarks.bb144 --search
```

The first command regenerates the symmetry and fault-replacement data, verifies the recorded engine identity and root coverage, and checks both ten-fault witnesses against the detector and logical matrices. The second also compiles the packaged C++17 engine and repeats the exhaustive nine-fault search in each sector. Its two decisions run sequentially. The archived timings and source hashes identify the fast recursive engine used by default for fresh searches. Add `--large-capacity` to repeat the search with expanded storage. Checking a recorded completion alone does not replay the search tree.

For gate-level replay, obtain the pinned source below. With NumPy, SciPy, ldpc and bposd installed, the following regenerates the inputs and replays the ten distinct physical faults in each sector through all three cycles. The driver checks the upstream SHA-256 digest before running the supplied file.

```sh
curl -fLO https://raw.githubusercontent.com/sbravyi/BivariateBicycleCodes/fa77e3333d3ec44c79d8f914dd24c040d1da471b/decoder_setup.py
python -m cssdist.benchmarks.bb144 --ibm-source decoder_setup.py
```

IBM's generator enumerates 3,024 candidate single-fault outcomes per sector. After merging identical detector and logical signatures and dropping the zero signature, 936 X and 864 Z columns remain. The two lattice translations preserve detector parity and the joint detector/logical kernel. Every nonempty support can therefore be translated to include a representative of one of 13 X or 12 Z orbits. Representatives are ordered first, so searching those root indices covers the full sector. The native record's `complete` flag refers to searching every column as a root. The checker verifies the reduced coverage separately. Neutral triples and quadruples preserve all detector and logical flips, so replacing a strict majority by its complement shortens a fault set.
