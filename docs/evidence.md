# Checking search evidence

Each certification run contains the physical input, search configuration, native source and build identity, execution transcripts and logical witnesses. A lower bound requires completed exclusions covering every required sector and search partition (shard). A checked witness supplies an upper bound. Equality gives an exact distance.

```sh
qedist audit runs/my-code
qedist export runs/my-code --output bundles/my-code.tar.gz
qedist audit-bundle bundles/my-code.tar.gz
```

`audit` reconstructs the physical problem and checks the recorded source, inputs, commands, completion coverage and witnesses. `audit-bundle` first checks archive membership and file checksums, then performs the same audit. Details are in the [portable-evidence guide](portable-evidence.md).

The AJ58 example includes a completed exclusion through weight 19 and checked weight-20 logical operators, certifying distance 20. Its records come from a QEDist 0.1 run using the `lp` engine. [Verification and replay](../validation/README.md)

Checksums detect changed and mismatched files. Completed execution records rely on the correctness and completeness of the recorded search implementation. Independent per-branch proof traces would be a stronger form of evidence.

Historical catalogue and comparator archives are maintained separately. They retain the exact software versions used for those measurements and their own checkers.
