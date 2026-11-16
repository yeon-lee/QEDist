# Example benchmark runner

The full [paper catalogue](../docs/catalogue.md) has a dedicated runner. `python -m tools.catalogue list` lists the paper IDs. `python -m tools.catalogue run LP04-175 --output runs/catalogue/LP04-175` repeats the recorded exclusion with the installed QEDist engine. `python -m tools.catalogue verify` checks all supplied physical inputs and witnesses.

Run `python -m tools.benchmark --help` from the source directory. The runner searches the selected examples, audits each result, and writes a JSON report containing the configuration and measurements.

Use `--profile css` for general CSS inputs or `--profile lp` for lifted-product inputs with the required tensor layout. Set the worker count and time limits explicitly for timing comparisons. See [benchmarking](../docs/benchmarking.md).

Certification records and portable bundles are checked with `qedist audit` and `qedist audit-bundle`.

`python -m tools.benchmark_symmetry --out runs/product-comparison --repeats 5` compares one cyclic generator, the diagonal product, and all independent generators. It uses identical physical matrices, cutoffs, pruning settings and per-shard budgets, with one worker. The report records search time, total native process time and full campaign time separately. Run `--help` to select examples or shorten the cutoff for a pilot. [Inputs and measurements](../docs/product-symmetry-benchmark.md)
