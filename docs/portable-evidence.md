# Portable execution evidence

Export a stopped campaign after its records have been independently audited:

```sh
python -m cssdist export runs/lp20 --output bundles/lp20.tar.gz
python -m cssdist audit-bundle bundles/lp20.tar.gz
```

The archive contains the full campaign input, native source and executable, build identity, original attempts and transcripts, physical witnesses, a fresh audit summary, and a snapshot of the Python checker source. A deterministic manifest identifies every archived file. Exporting identical evidence with the same checker sources gives the same archive hash.

The checker carries QEDist's MIT notice in `checker/cssdist/LICENSE.txt`. New run directories also include the notice alongside their native source and executable in `engine/LICENSE.txt`.

`audit-bundle` validates member names, membership and hashes, then recomputes the campaign result with the installed package. It does **not** execute the archived executable or Python code. The installed package must recognize the campaign's recorded native profile. `VERIFY.txt` also describes how a reader can inspect and use the archived checker source explicitly.

The same commands export and audit LP block searches, ordinary CSS runs, circuit fault runs (direct or windowed), and runtime calibrations. For circuits the auditor checks the detector model, native command and timing, and either all roots or the reconstructed window cover. For calibration, `distance_claim` remains null. An incomplete search keeps its incomplete status in the bundle.

General stabilizer runs also use these export commands. Their auditor reconstructs the complete Pauli-column model and joint symmetry orbits from the original mixed-Pauli checks, then validates every required shard range, execution record and physical logical witness. [General stabilizer distance](stabilizer-distance.md)

The exporter refuses locked campaigns, symlinks, output paths inside the original campaign, and an existing destination file. Archives with duplicate or unsafe paths, links, unexpected members, corrupt hashes or inconsistent summaries are rejected. The original evidence is not modified. Current archive limits are 100,000 files and 2 GiB of uncompressed content; large campaigns can remain as ordinary directories.

These archives are portable **execution records**, not formal proofs of every branch. Hashes expose changes and mismatched files; they do not prove that a program ran or that its source is correct. A lower bound still relies on the recorded exhaustive program and its completed execution. Small physical witnesses can be checked independently of that search.
