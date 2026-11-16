# Verification example

The AJ58 lifted-product code has 1,972 physical qubits and 248 logical qubits. A completed exclusion through weight 19 and verified weight-20 logical operators establish distance 20. The example input records the published construction source.

```sh
qedist audit-bundle validation/AJ58-exact.tar.gz
qedist certify examples/aj58.json --profile lp --cutoff 19 --out runs/aj58
qedist audit runs/aj58
```

The archive contains a completed QEDist 0.1 run using the `lp` engine, its physical witnesses, and the corresponding checker sources. The auditor checks the input, native sources, witnesses, and completion records.

Fresh QEDist 0.1 runs visited 4,710,327 nodes with the `css` engine and 1,278,318 with the `lp` engine, using the same physical input and search policy. These counts measure search-tree size on this instance.

## Tests

Run `python -m unittest discover -s tests -v` from the source directory. Tests cover small-code distance oracles, input validation, CSS and LP coverage, fixed pruning settings, kernel parity, product-group actions, resumed and sharded searches, circuit models, portable archives and corrupted records. Symmetry tests include relabeled coordinates, fixed points, induced LP stripe actions and altered generator files or root lists. The CI workflow runs on Linux and macOS.
