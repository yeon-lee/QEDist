# Paper catalogue and reproduction

This catalogue follows Appendix C of the QEDist manuscript, `main_v7`, as recorded on 2026-11-16. It includes every row in the distance catalogue.

The principal survey contains 95 codes, with 88 exact distances and seven unresolved intervals. The tables also include seven supplemental LP inputs, six PP codes, and two X-sector-only TT results. Two earlier-cutoff rows show the progress toward the final NM-P83 and RA-4-23N results.

## Repeat an exclusion

Run these commands from the source distribution or repository after installation. They list the available rows, check all physical inputs, and repeat a short exclusion.

```sh
python -m pip install .
python -m tools.catalogue list
python -m tools.catalogue verify
python -m tools.catalogue run LP04-175 --output runs/catalogue/LP04-175 --seconds-per-shard 60
qedist audit runs/catalogue/LP04-175
```

Replace `LP04-175` with a row ID below. The runner uses the recorded cutoff, symmetry, engine profile, partition and proposed-addition setting. It checks the input hash before searching and audits the resulting campaign. Weighted-check, stabilizer and disjoint-neighborhood pruning are enabled. NM-P83 uses the LP tensor-block reduction. Other rows use the CSS engine.

`--workers` controls simultaneous workers. `--seconds-per-shard` is the limit for each partition, so the total allowance grows with the number of partitions and searched sectors. `--shards` overrides the recorded partition count for a new experiment. `--proposed-additions` enables the test for rows whose published runs predate its use. `--resume` continues unfinished partitions with their saved settings.

For the two X-sector-only TT rows, the public certification command checks both sectors. The comparison in `catalogue-replay.json` uses the X-sector bound and its search time. The campaign also reports the separate Z-sector result.

Each fresh run records its actual engine sources, compiler, configuration and measurements. The published times below remain the measurements from the preserved executions. The separate manuscript reproduction archive contains the frozen engines and execution records. [Reproduction archive](reproduction.md)

## Reading the tables

`W` is the requested exclusion cutoff. A completed exclusion through `W` gives a lower bound of `W + 1`. A matching nontrivial logical witness establishes an exact distance. The input files contain the available physical witnesses. For unresolved rows, the cited upper bound and the weight of the lightest supplied witness are recorded separately in the JSON manifest.

Times are sums of worker search times, expressed on the Apple M3 Pro reference scale. They exclude input preparation and compilation. Cluster measurements use the recorded processor conversion factor. The 82 refreshed exclusions use the median of three repetitions. The other rows retain their individual timing conventions in the manifest.

Every row uses the weighted bound. Proposed-addition pruning was enabled for 101 of the 112 recorded row configurations. Three PP and eight TT rows retain earlier measurements with that test disabled. New searches through the main QEDist CLI enable it by default.

All 63 matched exclusions in the catalogue timing comparison improved, with a median speedup of 4.94×. That comparison adds weighted-check and proposed-addition pruning together with updated check selection. The paper reports the isolated effect of the weighted bound in its separate controlled comparison.

Source status is U for an upper bound or estimate, E for an exact distance, ? for unclear certification, N for no reported distance, I for a rigorous interval, X for a source discrepancy, and D for a diagnostic input. Results in X rows apply to the printed matrices.

`P` is the cyclic period, `w` the maximum binary check weight, and `w_c` the maximum column weight. Product and non-Abelian construction groups are written explicitly. An em dash marks a quantity omitted from that paper table.

## Catalogue

### Monomial LP benchmarks (principal)

| ID and input | (n, k) | P or group | w | w_c | Source distance | Result | W | Search time (s) |
|---|---|---|---:|---:|---|---|---:|---:|
| [LP04-175](../examples/catalogue/paper/LP04-175.json) | (175, 19) | 7 | 7 | — | ≤ 10 (U) [source 1](https://arxiv.org/abs/2111.07029) | d = 10 | 9 | <0.01 |
| [LP04-225](../examples/catalogue/paper/LP04-225.json) | (225, 21) | 9 | 7 | — | ≤ 12 (U) [source 1](https://arxiv.org/abs/2111.07029) | d = 12 | 11 | <0.01 |
| [LP04-425](../examples/catalogue/paper/LP04-425.json) | (425, 29) | 17 | 7 | — | ≤ 18 (U) [source 1](https://arxiv.org/abs/2111.07029) | d = 18 | 17 | 0.487 |
| [LP04-475](../examples/catalogue/paper/LP04-475.json) | (475, 31) | 19 | 7 | — | ≤ 20 (U) [source 1](https://arxiv.org/abs/2111.07029) | d = 20 | 19 | 2.25 |
| [LP118-544](../examples/catalogue/paper/LP118-544.json) | (544, 80) | 16 | 8 | — | 12 (E) [source 1](https://arxiv.org/abs/2111.07029) [source 2](https://arxiv.org/abs/2603.22532) | d = 12 | 11 | <0.01 |
| [LP118-714](../examples/catalogue/paper/LP118-714.json) | (714, 100) | 21 | 8 | — | ≤ 16 (U) [source 1](https://arxiv.org/abs/2111.07029) [source 2](https://arxiv.org/abs/2603.22532) | d = 16 | 15 | 0.1 |
| [LP118-1020](../examples/catalogue/paper/LP118-1020.json) | (1020, 136) | 30 | 8 | — | ≤ 16 (U) [source 1](https://arxiv.org/abs/2111.07029) [source 2](https://arxiv.org/abs/2603.22532) | d = 16 | 15 | 0.0658 |
| [Tanner-1054](../examples/catalogue/paper/Tanner-1054.json) | (1054, 140) | 31 | 8 | — | ≤ 20 (U) [source 1](https://arxiv.org/abs/2012.04068) [source 2](https://arxiv.org/abs/2411.13509) [source 3](https://arxiv.org/abs/2603.22532) | d = 20 | 19 | 2.07 |
| [Xu-1428](../examples/catalogue/paper/Xu-1428.json) | (1428, 184) | 42 | 8 | — | ≤ 24 (U) [source 1](https://arxiv.org/abs/2308.08648) [source 2](https://arxiv.org/abs/2603.22532) | d = 24 | 23 | 48.3 |
| [WG-AJ52](../examples/catalogue/paper/WG-AJ52.json) | (1768, 224) | 52 | 8 | — | ≤ 22 (U) [source 1](https://arxiv.org/abs/2603.22532) [source 2](https://arxiv.org/html/2606.12445#A1) | d = 22 | 21 | 6.64 |
| [WG-AJ58](../examples/catalogue/paper/WG-AJ58.json) | (1972, 248) | 58 | 8 | — | ≤ 20 (U) [source 1](https://arxiv.org/abs/2603.22532) | d = 20 | 19 | 1.06 |
| [WG-AJ60](../examples/catalogue/paper/WG-AJ60.json) | (2040, 256) | 60 | 8 | — | ≤ 20 (U) [source 1](https://arxiv.org/abs/2603.22532) | d = 20 | 19 | 1.34 |
| [WG-AJ61](../examples/catalogue/paper/WG-AJ61.json) | (2074, 260) | 61 | 8 | — | ≤ 24 (U) [source 1](https://arxiv.org/abs/2603.22532) | d = 24 | 23 | 28.2 |
| [WG-AJ67](../examples/catalogue/paper/WG-AJ67.json) | (2278, 284) | 67 | 8 | — | ≤ 22 (U) [source 1](https://arxiv.org/abs/2603.22532) | d = 22 | 21 | 5.33 |
| [WG-AJ73](../examples/catalogue/paper/WG-AJ73.json) | (2482, 308) | 73 | 8 | — | ≤ 24 (U) [source 1](https://arxiv.org/abs/2603.22532) | d = 24 | 23 | 21.5 |
| [WG-AJ80](../examples/catalogue/paper/WG-AJ80.json) | (2720, 336) | 80 | 8 | — | ≤ 22 (U) [source 1](https://arxiv.org/abs/2603.22532) | d = 22 | 21 | 4.53 |
| [WG-AJ85](../examples/catalogue/paper/WG-AJ85.json) | (2890, 356) | 85 | 8 | — | ≤ 24 (U) [source 1](https://arxiv.org/abs/2603.22532) | d = 24 | 23 | 20.5 |
| [WG-AJ95](../examples/catalogue/paper/WG-AJ95.json) | (3230, 396) | 95 | 8 | — | ≤ 24 (U) [source 1](https://arxiv.org/abs/2603.22532) | d = 24 | 23 | 18.2 |

### Logical spectroscopy (principal)

| ID and input | (n, k) | P or group | w | w_c | Source distance | Result | W | Search time (s) |
|---|---|---|---:|---:|---|---|---:|---:|
| [LS-P15-2X4](../examples/catalogue/paper/LS-P15-2X4.json) | (300, 60) | 15 | 11 | — | 9 (E) [source 1](https://arxiv.org/html/2607.05386v2#A3.E182) | d = 9 | 8 | <0.01 |
| [LS-E14-3X4](../examples/catalogue/paper/LS-E14-3X4.json) | (350, 26) | 14 | 7 | — | ≤ 14 (U) [source 1](https://arxiv.org/html/2607.05386v2#A3.E176) | d = 14 | 13 | 0.0242 |
| [LS-R21-4X5](../examples/catalogue/paper/LS-R21-4X5.json) | (861, 45) | 21 | 9 | — | ≤ 26 (U) [source 1](https://arxiv.org/html/2607.05386v2#A3.E175) | 23 ≤ d ≤ 26 | 22 | 25.3 |
| [LS-P35-3X4](../examples/catalogue/paper/LS-P35-3X4.json) | (875, 35) | 35 | 13 | — | ≤ 35 (U) [source 1](https://arxiv.org/html/2607.05386v2#A3.E183) | 21 ≤ d ≤ 35 | 20 | 151 |
| [LS-P31-2X5](../examples/catalogue/paper/LS-P31-2X5.json) | (899, 279) | 31 | 13 | — | ≤ 8 (U) [source 1](https://arxiv.org/html/2607.05386v2#A3.E184) | d = 8 | 7 | <0.01 |
| [LS-H33-3X9](../examples/catalogue/paper/LS-H33-3X9.json) | (2970, 1188) | 33 | 23 | — | ≤ 18 (U) [source 1](https://arxiv.org/html/2607.05386v2#A3.E181) | 13 ≤ d ≤ 18 | 12 | 161 |
| [LS-H41-3X8](../examples/catalogue/paper/LS-H41-3X8.json) | (2993, 1025) | 41 | 21 | — | ≤ 26 (U) [source 1](https://arxiv.org/html/2607.05386v2#A3.E180) | 14 ≤ d ≤ 26 | 13 | 53.3 |
| [LS-P75-3X7](../examples/catalogue/paper/LS-P75-3X7.json) | (4350, 1200) | 75 | 19 | — | ≤ 25 (U) [source 1](https://arxiv.org/html/2607.05386v2#A3.E178) | 19 ≤ d ≤ 25 | 18 | 420 |
| [LS-R75-3X7](../examples/catalogue/paper/LS-R75-3X7.json) | (4350, 1224) | 75 | 10 | — | ≤ 16 (U) [source 1](https://arxiv.org/html/2607.05386v2#A3.E173) | d = 16 | 15 | 0.433 |
| [LS-R81-3X7](../examples/catalogue/paper/LS-R81-3X7.json) | (4698, 1320) | 81 | 10 | — | ≤ 16 (U) [source 1](https://arxiv.org/html/2607.05386v2#A3.E173) | d = 16 | 15 | 0.642 |
| [LS-M45-5X9](../examples/catalogue/paper/LS-M45-5X9.json) | (4770, 784) | 45 | 14 | — | ≤ 50 (U) [source 1](https://arxiv.org/html/2607.05386v2#A3.E174) | 22 ≤ d ≤ 50 | 21 | 40.9 |
| [LS-M45-4X10](../examples/catalogue/paper/LS-M45-4X10.json) | (5220, 1674) | 45 | 14 | — | ≤ 16 (U) [source 1](https://arxiv.org/html/2607.05386v2#A3.E172) | d = 16 | 15 | 2.55 |
| [LS-P91-3X7](../examples/catalogue/paper/LS-P91-3X7.json) | (5278, 1456) | 91 | 19 | — | ≤ 70 (U) [source 1](https://arxiv.org/html/2607.05386v2#A3.E179) | 19 ≤ d ≤ 70 | 18 | 117 |

### High-rate monomial LP codes (principal)

| ID and input | (n, k) | P or group | w | w_c | Source distance | Result | W | Search time (s) |
|---|---|---|---:|---:|---|---|---:|---:|
| [Cain-2610](../examples/catalogue/paper/Cain-2610.json) | (2610, 744) | 45 | 10 | — | ≤ 16 (U) [source 1](https://arxiv.org/abs/2603.28627) [source 2](https://arxiv.org/html/2607.05386v2#A3.E171) | d = 16 | 15 | 0.763 |
| [Cain-4350](../examples/catalogue/paper/Cain-4350.json) | (4350, 1224) | 75 | 10 | — | ≤ 20 (U) [source 1](https://arxiv.org/abs/2603.28627) [source 2](https://arxiv.org/html/2607.05386v2#A3.E171) | d = 20 | 19 | 25.4 |
| [Cain-5278](../examples/catalogue/paper/Cain-5278.json) | (5278, 1480) | 91 | 10 | — | ≤ 22 (U) [source 1](https://arxiv.org/abs/2603.28627) [source 2](https://arxiv.org/html/2607.05386v2#A3.E172) | d = 22 | 21 | 164 |

### Radial codes (principal)

| ID and input | (n, k) | P or group | w | w_c | Source distance | Result | W | Search time (s) |
|---|---|---|---:|---:|---|---|---:|---:|
| [Radial-90](../examples/catalogue/paper/Radial-90.json) | (90, 8) | 5 | 6 | — | ≤ 10 (U) [source 1](https://arxiv.org/abs/2406.14445) | d = 10 | 9 | <0.01 |
| [RA-3-7D](../examples/catalogue/paper/RA-3-7D.json) | (126, 14) | 7 | 6 | — | ≤ 8 (U) [source 1](https://arxiv.org/abs/2406.14445) | d = 8 | 7 | <0.01 |
| [RA-4-7N](../examples/catalogue/paper/RA-4-7N.json) | (224, 18) | 7 | 8 | — | ≤ 14 (U) [source 1](https://arxiv.org/abs/2406.14445) | d = 14 | 13 | 0.0411 |
| [RA-3-13D](../examples/catalogue/paper/RA-3-13D.json) | (234, 8) | 13 | 6 | — | ≤ 12 (U) [source 1](https://arxiv.org/abs/2406.14445) | d = 12 | 11 | <0.01 |
| [RA-3-13N](../examples/catalogue/paper/RA-3-13N.json) | (234, 8) | 13 | 6 | — | ≤ 14 (U) [source 1](https://arxiv.org/abs/2406.14445) | d = 14 | 13 | <0.01 |
| [RA-3-17D](../examples/catalogue/paper/RA-3-17D.json) | (306, 8) | 17 | 6 | — | ≤ 14 (U) [source 1](https://arxiv.org/abs/2406.14445) | d = 14 | 13 | <0.01 |
| [Radial-352](../examples/catalogue/paper/Radial-352.json) | (352, 18) | 11 | 8 | — | ≤ 20 (U) [source 1](https://arxiv.org/abs/2406.14445) | d = 20 | 19 | 3.26 |
| [RA-4-13N](../examples/catalogue/paper/RA-4-13N.json) | (416, 18) | 13 | 8 | — | ≤ 18 (U) [source 1](https://arxiv.org/abs/2406.14445) | d = 18 | 17 | 0.308 |
| [RA-4-17N](../examples/catalogue/paper/RA-4-17N.json) | (544, 18) | 17 | 8 | — | ≤ 22 (U) [source 1](https://arxiv.org/abs/2406.14445) | d = 22 | 21 | 4.15 |
| [RA-4-23N-initial](../examples/catalogue/paper/RA-4-23N.json) | (736, 18) | 23 | 8 | — | ≤ 26 (U) [source 1](https://arxiv.org/abs/2406.14445) | 24 ≤ d ≤ 26 | 23 | 9.34 |
| [RA-4-23N](../examples/catalogue/paper/RA-4-23N.json) | (736, 18) | 23 | 8 | — | ≤ 26 (U) [source 1](https://arxiv.org/abs/2406.14445) | d = 26 | 25 | 64.9 |

### Weight-reduction inputs (principal)

| ID and input | (n, k) | P or group | w | w_c | Source distance | Result | W | Search time (s) |
|---|---|---|---:|---:|---|---|---:|---:|
| [Sabo-260](../examples/catalogue/paper/Sabo-260.json) | (260, 58) | 13 | 6 | — | ≤ 6 (U) [source 1](https://doi.org/10.1103/PRXQuantum.5.040302) | d = 6 | 5 | <0.01 |
| [Sabo-775](../examples/catalogue/paper/Sabo-775.json) | (775, 43) | 31 | 7 | — | ≤ 24 (U) [source 1](https://doi.org/10.1103/PRXQuantum.5.040302) | d = 24 | 23 | 37.6 |
| [Sabo-1150](../examples/catalogue/paper/Sabo-1150.json) | (1150, 50) | 46 | 7 | — | ≤ 21 (U) [source 1](https://doi.org/10.1103/PRXQuantum.5.040302) | d = 21 | 20 | 2.8 |

### Bias-tailoring CSS input (principal)

| ID and input | (n, k) | P or group | w | w_c | Source distance | Result | W | Search time (s) |
|---|---|---|---:|---:|---|---|---:|---:|
| [Roffe-416](../examples/catalogue/paper/Roffe-416.json) | (416, 18) | 13 | 8 | — | ≤ 20 (U) [source 1](https://arxiv.org/abs/2202.01702) | d = 20 | 19 | 1.02 |

### Polynomial-domain LP codes (principal)

| ID and input | (n, k) | P or group | w | w_c | Source distance | Result | W | Search time (s) |
|---|---|---|---:|---:|---|---|---:|---:|
| [NM-P10](../examples/catalogue/paper/NM-P10.json) | (250, 18) | 10 | 10 | — | 8 (?) [source 1](https://arxiv.org/abs/2609.01305) | d = 8 | 7 | <0.01 |
| [NM-P11](../examples/catalogue/paper/NM-P11.json) | (275, 15) | 11 | 8 | — | 12 (?) [source 1](https://arxiv.org/abs/2609.01305) | d = 12 | 11 | <0.01 |
| [NM-P12](../examples/catalogue/paper/NM-P12.json) | (300, 20) | 12 | 10 | — | 12 (?) [source 1](https://arxiv.org/abs/2609.01305) | d = 12 | 11 | 0.0101 |
| [NM-P13](../examples/catalogue/paper/NM-P13.json) | (325, 17) | 13 | 10 | — | 14 (?) [source 1](https://arxiv.org/abs/2609.01305) | d = 14 | 13 | 0.0576 |
| [NM-P14](../examples/catalogue/paper/NM-P14.json) | (350, 22) | 14 | 8 | — | 12 (?) [source 1](https://arxiv.org/abs/2609.01305) | d = 12 | 11 | <0.01 |
| [NM-P15](../examples/catalogue/paper/NM-P15.json) | (375, 19) | 15 | 10 | — | 16 (?) [source 1](https://arxiv.org/abs/2609.01305) | d = 16 | 15 | 0.337 |
| [NM-P16](../examples/catalogue/paper/NM-P16.json) | (400, 24) | 16 | 10 | — | 13 (?) [source 1](https://arxiv.org/abs/2609.01305) | d = 13 | 12 | 0.0192 |
| [NM-P17](../examples/catalogue/paper/NM-P17.json) | (425, 21) | 17 | 10 | — | 18 (?) [source 1](https://arxiv.org/abs/2609.01305) | d = 18 | 17 | 1.08 |
| [NM-P24](../examples/catalogue/paper/NM-P24.json) | (600, 32) | 24 | 10 | — | ≤ 20 (U) [source 1](https://arxiv.org/abs/2609.01305) | d = 20 | 19 | 3.71 |
| [NM-P41](../examples/catalogue/paper/NM-P41.json) | (1025, 45) | 41 | 10 | — | ≤ 26 (U) [source 1](https://arxiv.org/abs/2609.01305) | d = 26 | 25 | 152 |
| [NM-P83-initial](../examples/catalogue/paper/NM-P83.json) | (2075, 87) | 83 | 10 | — | ≤ 34 (U) [source 1](https://arxiv.org/abs/2609.01305) | 28 ≤ d ≤ 34 | 27 | 195 |
| [NM-P83](../examples/catalogue/paper/NM-P83.json) | (2075, 87) | 83 | 10 | — | ≤ 34 (U) [source 1](https://arxiv.org/abs/2609.01305) | d = 34 | 33 | 20500 |

### Clustered-cyclic LP codes (principal)

| ID and input | (n, k) | P or group | w | w_c | Source distance | Result | W | Search time (s) |
|---|---|---|---:|---:|---|---|---:|---:|
| [QGPU-8-7](../examples/catalogue/paper/QGPU-8-7.json) | (56, 8) | 7 | 8 | — | ≤ 7 (U) [source 1](https://arxiv.org/abs/2603.05398) | d = 7 | 6 | <0.01 |
| [QGPU-8-11](../examples/catalogue/paper/QGPU-8-11.json) | (88, 8) | 11 | 8 | — | ≤ 10 (U) [source 1](https://arxiv.org/abs/2603.05398) | d = 10 | 9 | 0.0114 |
| [QGPU-8-13](../examples/catalogue/paper/QGPU-8-13.json) | (104, 8) | 13 | 8 | — | ≤ 11 (U) [source 1](https://arxiv.org/abs/2603.05398) | d = 11 | 10 | 0.0197 |
| [QGPU-18-7](../examples/catalogue/paper/QGPU-18-7.json) | (126, 18) | 7 | 8 | — | ≤ 7 (U) [source 1](https://arxiv.org/abs/2603.05398) | d = 7 | 6 | <0.01 |
| [QGPU-8-17](../examples/catalogue/paper/QGPU-8-17.json) | (136, 8) | 17 | 8 | — | ≤ 14 (U) [source 1](https://arxiv.org/abs/2603.05398) | d = 14 | 13 | 0.4 |
| [QGPU-18-11](../examples/catalogue/paper/QGPU-18-11.json) | (198, 18) | 11 | 8 | — | ≤ 10 (U) [source 1](https://arxiv.org/abs/2603.05398) | d = 10 | 9 | <0.01 |

### Erasure-decoding LP inputs (principal)

| ID and input | (n, k) | P or group | w | w_c | Source distance | Result | W | Search time (s) |
|---|---|---|---:|---:|---|---|---:|---:|
| [KO-925](../examples/catalogue/paper/KO-925.json) | (925, 49) | 37 | 7 | — | — (N) [source 1](https://arxiv.org/abs/2411.13509) | d = 20 | 19 | 1.38 |
| [KO-2075](../examples/catalogue/paper/KO-2075.json) | (2075, 95) | 83 | 7 | — | — (N) [source 1](https://arxiv.org/abs/2411.13509) | d = 24 | 23 | 16.9 |
| [KO-2210](../examples/catalogue/paper/KO-2210.json) | (2210, 276) | 65 | 8 | — | — (N) [source 1](https://arxiv.org/abs/2411.13509) | d = 24 | 23 | 39.1 |
| [KO-4075](../examples/catalogue/paper/KO-4075.json) | (4075, 175) | 163 | 7 | — | — (N) [source 1](https://arxiv.org/abs/2411.13509) | d = 24 | 23 | 11.1 |
| [KO-4114](../examples/catalogue/paper/KO-4114.json) | (4114, 500) | 121 | 8 | — | — (N) [source 1](https://arxiv.org/abs/2411.13509) | d = 24 | 23 | 15.7 |

### Finite-length distance examples (principal)

| ID and input | (n, k) | P or group | w | w_c | Source distance | Result | W | Search time (s) |
|---|---|---|---:|---:|---|---|---:|---:|
| [RDV600-1](../examples/catalogue/paper/RDV600-1.json) | (600, 36) | 24 | 7 | — | 7 (?) [source 1](https://arxiv.org/abs/2503.07567) | d = 7 | 6 | <0.01 |
| [RDV600-2](../examples/catalogue/paper/RDV600-2.json) | (600, 36) | 24 | 7 | — | 20 (?) [source 1](https://arxiv.org/abs/2503.07567) | d = 20 | 19 | 1.39 |

### Other Abelian matrix LP examples (principal)

| ID and input | (n, k) | P or group | w | w_c | Source distance | Result | W | Search time (s) |
|---|---|---|---:|---:|---|---|---:|---:|
| [LCS-369](../examples/catalogue/paper/LCS-369.json) | (369, 9) | 9 | 6 | — | 9 (?) [source 1](https://arxiv.org/abs/2401.02911) | d = 9 | 8 | <0.01 |
| [Cyclic-560](../examples/catalogue/paper/Cyclic-560.json) | (560, 112) | 28 | 9 | — | ≤ 14 (U) [source 1](https://arxiv.org/abs/2607.28795) | d = 14 | 13 | 0.366 |

### Cyclic spatially coupled example (principal)

| ID and input | (n, k) | P or group | w | w_c | Source distance | Result | W | Search time (s) |
|---|---|---|---:|---:|---|---|---:|---:|
| [SCE-R1E01](../examples/catalogue/paper/SCE-R1E01.json) | (1428, 186) | 42 | 8 | — | ≤ 18 (U) [source 1](https://arxiv.org/abs/2606.24808) | d = 18 | 17 | 0.42 |

### Non-Abelian LP (principal)

| ID and input | (n, k) | P or group | w | w_c | Source distance | Result | W | Search time (s) |
|---|---|---|---:|---:|---|---|---:|---:|
| [Mitten-150](../examples/catalogue/paper/Mitten-150.json) | (150, 30) | $C_5\times S_3$ (P=5) | 9 | — | 10 (?) [source 1](https://arxiv.org/abs/2607.28795) | d = 10 | 9 | 0.0395 |
| [Mitten-200](../examples/catalogue/paper/Mitten-200.json) | (200, 40) | $C_4\times D_{10}$ (P=4) | 9 | — | 12 (?) [source 1](https://arxiv.org/abs/2607.28795) | d = 12 | 11 | 0.36 |
| [Mitten-300](../examples/catalogue/paper/Mitten-300.json) | (300, 60) | $C_{10}\times S_3$ (P=10) | 9 | — | 14 (?) [source 1](https://arxiv.org/abs/2607.28795) | d = 14 | 13 | 0.894 |
| [Hong-390](../examples/catalogue/paper/Hong-390.json) | (390, 78) | $C_{26}\rtimes C_3$ (P=1) | 9 | — | ≤16 (U) [source 1](https://arxiv.org/abs/2607.27644) | d = 16 | 15 | 25.4 |
| [Mitten-500](../examples/catalogue/paper/Mitten-500.json) | (500, 100) | $C_5\times(C_5\rtimes C_4)$ (P=5) | 9 | — | 16 (?) [source 1](https://arxiv.org/abs/2607.28795) | d = 16 | 15 | 4.91 |
| [Mitten-540](../examples/catalogue/paper/Mitten-540.json) | (540, 108) | $(C_9\rtimes C_3)\rtimes C_4$ (P=2) | 9 | — | 18 (?) [source 1](https://arxiv.org/abs/2607.28795) | d = 18 | 17 | 84.7 |
| [Hong-550](../examples/catalogue/paper/Hong-550.json) | (550, 110) | $C_{22}\rtimes C_5$ (P=1) | 9 | — | ≤18 (U) [source 1](https://arxiv.org/abs/2607.27644) | d = 18 | 17 | 101.6 |
| [Hong-625](../examples/catalogue/paper/Hong-625.json) | (625, 125) | $C_{25}\rtimes C_5$ (P=1) | 9 | — | ≤20 (U) [source 1](https://arxiv.org/abs/2607.27644) | d = 20 | 19 | 430.4 |
| [Mitten-630](../examples/catalogue/paper/Mitten-630.json) | (630, 126) | $C_7\rtimes C_{18}$ (P=3) | 9 | — | ≤20 (U) [source 1](https://arxiv.org/abs/2607.28795) | d = 20 | 19 | 391 |
| [Mitten-780](../examples/catalogue/paper/Mitten-780.json) | (780, 156) | $C_{13}\times A_4$ (P=13) | 9 | — | ≤22 (U) [source 1](https://arxiv.org/abs/2607.28795) | d = 22 | 21 | 714 |
| [Mitten-975](../examples/catalogue/paper/Mitten-975.json) | (975, 195) | $C_5\times(C_{13}\rtimes C_3)$ (P=5) | 9 | — | ≤24 (U) [source 1](https://arxiv.org/abs/2607.28795) | d = 24 | 23 | 8056 |

### Scalar-by-matrix LP codes (supplemental)

| ID and input | (n, k) | P or group | w | w_c | Source distance | Result | W | Search time (s) |
|---|---|---|---:|---:|---|---|---:|---:|
| [PK-B1-882](../examples/catalogue/paper/PK-B1-882.json) | (882, 24) | 63 | 6 | — | [18,24] (I) [source 1](https://arxiv.org/abs/1904.02703) | d = 24 | 23 | 23.1 |
| [KO-GHP882](../examples/catalogue/paper/KO-GHP882.json) | (882, 48) | 63 | 8 | — | 16 (?) [source 1](https://arxiv.org/abs/2411.13509) [source 2](https://arxiv.org/html/2411.13509) | d = 16 | 15 | 0.0741 |
| [PK-B3-1270](../examples/catalogue/paper/PK-B3-1270.json) | (1270, 28) | 127 | 6 | — | [16,46] (I) [source 1](https://arxiv.org/abs/1904.02703) | 24 ≤ d ≤ 46 | 23 | 13.1 |

### Printed matrices (supplemental)

| ID and input | (n, k) | P or group | w | w_c | Source distance | Result | W | Search time (s) |
|---|---|---|---:|---:|---|---|---:|---:|
| [Pradhan-printed-775](../examples/catalogue/paper/Pradhan-printed-775.json) | (775, 43) | 31 | 7 | — | ≤ 20 (X) [source 1](https://arxiv.org/abs/2608.31040) | d = 24 | 23 | 41.9 |
| [Pradhan-printed-1054](../examples/catalogue/paper/Pradhan-printed-1054.json) | (1054, 140) | 31 | 8 | — | ≤ 20 (X) [source 1](https://arxiv.org/abs/2608.31040) | d = 16 | 15 | 0.0552 |

### Spectroscopy diagnostic constituents (supplemental)

| ID and input | (n, k) | P or group | w | w_c | Source distance | Result | W | Search time (s) |
|---|---|---|---:|---:|---|---|---:|---:|
| [LS-RES7-3X4](../examples/catalogue/paper/LS-RES7-3X4.json) | (175, 19) | 7 | 7 | — | — (D) [source 1](https://arxiv.org/html/2607.05386v2#A3.E177) | d = 10 | 9 | <0.01 |
| [LS-CMP15-2X4](../examples/catalogue/paper/LS-CMP15-2X4.json) | (300, 66) | 15 | 6 | — | 6 (D) [source 1](https://arxiv.org/html/2607.05386v2#A2.SS2) | d = 6 | 5 | <0.01 |

### PP (PP)

| ID and input | (n, k) | P or group | w | w_c | Source distance | Result | W | Search time (s) |
|---|---|---|---:|---:|---|---|---:|---:|
| [PP-170](../examples/catalogue/paper/PP-170.json) | (170, 8) | 85 | 10 | 5 | 20 (E) [source 1](https://arxiv.org/abs/2609.30069) | d = 20 | 19 | 2110 |
| [PP-248](../examples/catalogue/paper/PP-248.json) | (248, 66) | 31 | 8 | 3 | 12 (E) [source 1](https://arxiv.org/abs/2609.30069) | d = 12 | 11 | 0.00708 |
| [PP-372](../examples/catalogue/paper/PP-372.json) | (372, 130) | 31 | 12 | 4 | 18 (E) [source 1](https://arxiv.org/abs/2609.30069) | d = 18 | 17 | 158 |
| [PP-584](../examples/catalogue/paper/PP-584.json) | (584, 150) | 73 | 8 | 3 | 18 (E) [source 1](https://arxiv.org/abs/2609.30069) | d = 18 | 17 | 2.31 |
| [PP-1112](../examples/catalogue/paper/PP-1112.json) | (1112, 282) | 139 | 8 | 3 | 20 (E) [source 1](https://arxiv.org/abs/2609.30069) | d = 20 | 19 | 10.7 |
| [PP-1784](../examples/catalogue/paper/PP-1784.json) | (1784, 450) | 223 | 8 | 3 | 24 (E) [source 1](https://arxiv.org/abs/2609.30069) | d = 24 | 23 | 419 |

### BB (principal)

| ID and input | (n, k) | P or group | w | w_c | Source distance | Result | W | Search time (s) |
|---|---|---|---:|---:|---|---|---:|---:|
| [BB288](../examples/catalogue/paper/BB288.json) | (288, 12) | $C_{12}^2$ | 6 | 3 | 18 (E) [source 1](https://arxiv.org/abs/2308.07915) | d = 18 | 17 | 0.0675 |
| [BB360](../examples/catalogue/paper/BB360.json) | (360, 12) | $C_{30}\times C_6$ | 6 | 3 | ≤24 (U) [source 1](https://arxiv.org/abs/2308.07915) | d = 24 | 23 | 36.6 |
| [BB756](../examples/catalogue/paper/BB756.json) | (756, 16) | $C_{21}\times C_{18}$ | 6 | 3 | ≤34 (U) [source 1](https://arxiv.org/abs/2308.07915) | d = 34 | 33 | 123000 |

### TT (principal)

| ID and input | (n, k) | P or group | w | w_c | Source distance | Result | W | Search time (s) |
|---|---|---|---:|---:|---|---|---:|---:|
| [TT588-k9](../examples/catalogue/paper/TT588-k9.json) | (588, 9) | $C_7^2\times C_4$ | 9 | 6 | ≤14 (U) [source 1](https://arxiv.org/abs/2508.08191) | d = 14 | 13 | 0.0362 |
| [TT648-k6](../examples/catalogue/paper/TT648-k6.json) | (648, 6) | $C_6^3$ | 9 | 6 | ≤16 (U) [source 1](https://arxiv.org/abs/2508.08191) | d = 16 | 15 | 0.510 |
| [TT648-k12](../examples/catalogue/paper/TT648-k12.json) | (648, 12) | $C_6^3$ | 9 | 6 | ≤14 (U) [source 1](https://arxiv.org/abs/2508.08191) | d = 14 | 13 | 0.0290 |
| [TT735-k18](../examples/catalogue/paper/TT735-k18.json) | (735, 18) | $C_7^2\times C_5$ | 9 | 6 | ≤14 (U) [source 1](https://arxiv.org/abs/2508.08191) | d = 14 | 13 | 0.0261 |
| [TT840-k9](../examples/catalogue/paper/TT840-k9.json) | (840, 9) | $C_8\times C_7\times C_5$ | 9 | 6 | ≤16 (U) [source 1](https://arxiv.org/abs/2508.08191) | d = 16 | 15 | 0.245 |
| [TT1029-k18](../examples/catalogue/paper/TT1029-k18.json) | (1029, 18) | $C_7^3$ | 9 | 6 | ≤16 (U) [source 1](https://arxiv.org/abs/2508.08191) | d = 16 | 15 | 0.156 |

### TT (sector only)

| ID and input | (n, k) | P or group | w | w_c | Source distance | Result | W | Search time (s) |
|---|---|---|---:|---:|---|---|---:|---:|
| [TT180-k12](../examples/catalogue/paper/TT180-k12.json) | (180, 12) | $C_5\times C_4\times C_3$ | 9 | 6 | ≤20 (U) [source 1](https://arxiv.org/abs/2508.08191) | d_X = 20 | 19 | 0.0132 |
| [TT432-k12](../examples/catalogue/paper/TT432-k12.json) | (432, 12) | $C_6^2\times C_4$ | 9 | 6 | ≤36 (U) [source 1](https://arxiv.org/abs/2508.08191) | d_X = 36 | 35 | 25.9 |

## Machine-readable records

The manifest records physical input hashes, supplied witness weights, paper results, search configurations, timing provenance and manuscript source hashes. [Catalogue manifest](../examples/catalogue/paper.json)

Regenerate this page after updating the manifest.

```sh
python -m tools.catalogue markdown --output docs/catalogue.md
```
