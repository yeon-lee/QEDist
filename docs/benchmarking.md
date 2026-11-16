# Benchmarking the current engines

The [paper catalogue](catalogue.md) contains every Appendix C row, its physical input, exclusion cutoff and recorded timing. Use its runner to repeat a selected paper result.

```sh
python -m tools.catalogue run WG-AJ58 --output runs/catalogue/WG-AJ58 \
  --workers 1 --seconds-per-shard 60
```

The catalogue includes the weighted-check timing refresh and the later exact-distance results. Its 63 matched timing comparisons combine weighted-check pruning, proposed-addition pruning and changes to check selection. The separate four-configuration experiment in the manuscript measures the weighted bound's individual contribution. The numerical reproduction archive preserves both experiments.

## Small example benchmark

The example runner records physical inputs, engine sources, compiler settings, search limits, elapsed times, node counts and audited outcomes.

```sh
python -m tools.benchmark --cases steane independent_qc binary_320 \
  --profile css --shards 1 --workers 1 --seconds-per-shard 30 \
  --out runs/css-benchmark --summary runs/css-benchmark.json
```

For lifted-product inputs, repeat with `--profile lp` and a separate output directory and summary. Use the same input, cutoff, symmetry, partition and budget when comparing engines. The Steane example uses general CSS checks, so select LP examples when using the LP engine.

The proposed-addition test is enabled by default. To measure its effect, repeat the same command with `--no-proposed-additions` and new output paths. Keep every other setting fixed. The summary records the effective setting for each case, and each native transcript reports its skipped branches. On resume, omitted flags preserve each existing campaign's setting. The summary's top-level `proposed_additions` is `null` if its cases use different settings.

Compile the engines before timing and run conditions serially on the same machine. Repeat measurements and retain unfinished searches and errors. Native loop time, process time, end-to-end time, worker effort and parallel elapsed time measure different costs and should be identified explicitly.

The runner is a functionality and performance tool for the current package. Published comparisons use their recorded source versions and configurations. Those historical benchmark bundles are maintained separately from this source package.
