# Calibrating a search budget

`qedist calibrate` measures search times from selected starting qubits (roots) at the requested cutoff before a longer certification attempt. It uses the same selected engine, physical matrices, and validated symmetries as `certify`. These measurements help estimate runtime. Use `certify` to establish distance bounds.

```sh
python -m cssdist calibrate examples/catalogue/lp-f2-1122-148-20-partial.json \
  --cutoff 19 --samples 8 --seconds-per-root 2 --seed 17 \
  --out runs/calibration-1122
python -m cssdist audit-calibration runs/calibration-1122
```

Calibration samples whole-code roots using the `css` engine. It selects fixed or expanded storage by the same rules as certification. Use `--large-capacity` or `--no-large-capacity` to choose explicitly. The optional `--memory-mib` selects expanded storage and budgets native vector allocations for each sampled root. See [search engines](native-profiles.md) for capacity and search-policy details.

## What is sampled

The command samples roots uniformly without replacement in each required CSS sector. Verified permutations give one root per joint qubit orbit. With symmetry disabled, roots are physical coordinates. A verified sector-exchange permutation permits sampling only Z. The seed, complete sampling plan, original input, generator files, compiler/source/binary identities, and every bounded attempt are preserved.

Root calls run sequentially, with compilation performed first. Native search time and full root-process time are recorded separately. The native forecast excludes compilation, input loading, preprocessing and row-space validation; it estimates unsharded search work, not end-to-end runtime or parallel completion time. It also excludes scheduler delays, parallel imbalance, repeated shard-prefix work, and changes of machine. Reusing unfinished shards is still distinct from resuming an individual search tree.

## Reading the diagnostic

The top-level `CALIBRATION_COMPLETE` status and exit code 0 mean that the requested sampling operation and its audit finished successfully. Individual sectors may still be `CENSORED` or `INSUFFICIENT_SAMPLE`; inspect each sector's status and forecast field before using an estimate. This status does not establish a distance bound.

| Sector status | Interpretation |
|---|---|
| `ALL_ROOTS_MEASURED` | Every root finished; the reported total is the sum of their measured native search times. |
| `EMPIRICAL_ESTIMATE` | At least four roots finished and none was censored; population size times sampled mean gives a planning estimate. |
| `CENSORED` | At least one sampled root reached a time/node limit. No finite total-runtime estimate is issued. |
| `INSUFFICIENT_SAMPLE` | Too few completed roots for the empirical estimate. |
| `WITNESS_FOUND` | A physical nontrivial logical at or below the target cutoff was found; an exclusion at that cutoff is impossible. |
| `ERROR` | A process or validation error prevents interpretation. |

For a partial uncensored sample, the reported 10th–90th percentile bootstrap spread describes resampling variation within that sample. It is not a guaranteed confidence interval or a scheduling bound. An unseen hard root can dominate the total, even when all sampled roots finished quickly. Reporting an estimate only when no sampled root was censored can also select unusually easy samples. Repeated calibration with a larger uniform sample can reveal these failures; the package never converts a timeout into a completed-root timing observation.

The output always keeps `distance_claim` null. Even a complete calibration census is not presented as a certification campaign: use `certify` and its sector/shard audit to establish a lower bound. Any returned witness is independently checked against the physical syndrome and full stabilizer row space and remains available in the calibration receipts.

When comparing pruning policies, node throughput alone is insufficient: a
cheaper rule can visit many more nodes in the completed tree. Compare identical completed root subproblems
where feasible, retain timeouts, and treat extrapolation to higher cutoffs as
unvalidated. Policies that change branch ordering must not be compared using
the same narrow branch index as though it selected the same support family.

## Independent checks

`audit-calibration` ignores a saved result summary and recomputes it from the inputs, sampling plan and native transcripts. It verifies source and executable hashes, root identities, cutoff, process status, full completion of any root reported as excluded, and logical nontriviality of witnesses. It does not rerun the search or verify a formal proof of every branch.

The estimation rule is an experimental planning aid. Its usefulness must be assessed against complete root-cost measurements on representative problems, including cases with censored and uneven roots. A small sample alone cannot justify a reliable finite upper runtime bound.
