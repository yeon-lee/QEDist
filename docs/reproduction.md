# Reproducing the main_v7 manuscript

The [paper catalogue](catalogue.md) reproduces all Appendix C rows with the current paper results and timings. The source package includes their physical inputs and a runner for fresh QEDist searches. Its machine-readable manifest records the cutoff, symmetry and pruning settings for each row.

The manuscript's numerical reproduction archive, `qedist-main-v7-reproduction.tar.gz`, is prepared separately for distribution with the manuscript. It contains normalized catalogue inputs, checked witnesses, completed-execution records, frozen measurement engines and numerical plotting programs.

After extracting it, follow its `README.md` and `CLAIM_MAP.md`. Python 3.10 or later can check file identities, inputs, witnesses and the recorded four-configuration statistics.

```sh
python3.12 -B reproduce.py verify
```

The archive includes the completed 82-case catalogue timing refresh, the 63 matched earlier measurements, and the subsequent NM-P83, RA-4-23N and Hong exclusions. It also provides commands to repeat the four configurations of the weighted bound, matched cutoff sweeps, and LP tensor-block comparisons. The drivers compile the engines used for those measurements. Baseline methods require the dependencies described in the archive. Historical implementation labels identify those preserved measurements. The public software version is 0.1.

The public package enables the proposed-addition test by default for new CSS and LP searches and for calibration. `--no-proposed-additions` disables it. Resume inherits the saved setting when neither flag is supplied. Its tests include exhaustive small-code comparisons, product-group symmetry, sharding, resume checks and evidence auditing.

Completed-execution audits verify the saved inputs, outputs, witnesses and partition coverage. Distance exclusions also rely on the search algorithm's completeness. The archive retains the implementation and commands needed for a fresh exhaustive run.
