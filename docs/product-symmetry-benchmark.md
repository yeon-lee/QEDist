# Product-group symmetry benchmarks

These measurements compare three symmetry declarations on identical physical check matrices and row orderings. The cyclic control uses the first listed generator. The diagonal control uses the composition of all listed generators. The product case uses their joint action. All three use the same compiled CSS engine, pruning policy, witnesses, cutoffs and sector-exchange declarations.

Runs used an Apple M3 Pro, Python 3.12.4 and Apple clang 21.0.0 with `-O3 -std=c++17`. There was one worker, one shard, `split_weight=1`, and a 60-second budget per searched sector. Each configuration was repeated five times, rotating execution order. Compilation was cached before timing. Every reported exclusion completed and passed the independent audit.

## Search work

Root counts are per searched CSS sector. Node counts and native search times sum all required sectors. BB144 and PP512 have verified sector exchanges. The toric example searches both sectors. Times are medians in seconds.

| Input | Excluded through weight | Cyclic → product roots | Cyclic → product nodes | Cyclic → product search seconds |
|---|---:|---:|---:|---:|
| BB144 | 11 | 12 → 2 | 11,700 → 2,636 | 0.00272567 → 0.000709083 |
| PP512 | 16 | 32 → 16 | 24,664,499 → 14,458,059 | 16.8219 → 9.83681 |
| 3D toric, L=7 | 6 | 147 → 3 | 28,190 → 731 | 0.00201645 → 0.000121875 |

For PP512, the full action reduces search time by about 1.71× against the C16 subgroup and 1.99× against the diagonal subgroup. The diagonal control visits 28,801,415 nodes. BB144 visits 4.44× fewer nodes, and the three-factor toric example visits 38.56× fewer nodes. These reductions arise from fewer starting roots. The search within each root uses the same rules.

A separate PP512 run using the original `cyclic_period=16` interface reproduced the cyclic control's 24,664,499 nodes and completed the same exclusion through weight 16.

## Validation and process overhead

The validated-workflow timing includes input validation, campaign preparation, native execution and a fresh independent audit. Native search timing above excludes preprocessing and permutation validation. For the shortest searches, these other costs dominate.

| Input | Cyclic workflow seconds | Diagonal workflow seconds | Product workflow seconds |
|---|---:|---:|---:|
| BB144 | 0.1227 | 0.1157 | 0.1171 |
| PP512 | 17 | 19.78 | 10.07 |
| 3D toric, L=7 | 0.4053 | 0.4075 | 0.4318 |

The complete measurement file also records total native-process time, including loading and validation, and the source identities and matrix checksums. [Measurements](../validation/product-symmetry-benchmark.json)

## Inputs and certification scope

- BB144 uses C12 × C6 and the polynomials `A=x^3+y+y^2`, `B=y^3+x+x^2`. Exclusion through 11 and verified weight-12 representatives establish distance 12. [Input](../examples/symmetry/bb144.json) · [Authors' construction](https://github.com/sbravyi/BivariateBicycleCodes/blob/main/decoder_setup.py)
- PP512 is the binary-expanded quaternary C16 × C2 example with 512 physical and 128 logical qubits. The supplied weight-19 witness is independently checked. These timed runs establish the interval 17 ≤ d ≤ 19. An initial 60-second-per-configuration pilot at cutoff 18 remained incomplete in all three configurations. [Input](../examples/symmetry/pp512.json) · [Construction paper](https://arxiv.org/abs/2610.06820)
- The three-dimensional toric example has 1,029 edge qubits on a periodic 7 × 7 × 7 cubic lattice. Vertex X checks and plaquette Z checks admit C7 × C7 × C7 translations. Both-sector exclusions through 6 and a checked weight-7 loop establish distance 7. [Input](../examples/symmetry/toric3d7.json)

## Reproduction

Run from the source directory. Each invocation needs a new output directory.

```sh
python -m tools.benchmark_symmetry --out runs/product-comparison --repeats 5 --seconds 60
qedist audit runs/product-comparison/pp512/product/00
```

The runner saves all physical inputs, generator files, build records, transcripts and audited results. The first generator acts along C12 for BB144, C16 for PP512, and the first C7 coordinate for the toric example. All inputs have `cyclic_period=1` so the declared generators specify the entire comparison.
