# Search completeness and the evidence boundary

This document describes the inherited binary-support search. The [native profile guide](native-profiles.md) also describes the default weighted-check refinement and its fixed policy. It specializes to neither a pivot family nor a particular logical frame. The method is described in Appendix A of [Lee, arXiv:2610.06820](https://arxiv.org/abs/2610.06820); native source provenance is recorded alongside the engine.

## The actual decision problem

For the Z sector the search asks whether there is a binary vector z with

\[
1\le |z|\le W,\qquad H_Xz=0,\qquad z\notin\operatorname{row}(H_Z).
\]

The X sector exchanges the checks. Binary elimination tests membership in the **entire stabilizer row space**. Thus logical directions missed by a partial frame are still detected. Two completed sector exclusions prove `d ≥ W+1`. For a CSS code, a nontrivial mixed Pauli has at least one nontrivial pure-sector component, with component support contained in its Pauli support, so the two pure-sector exclusions also bound unrestricted Pauli distance.

## Why searching selected supports is enough

Assume a nontrivial logical exists within the cutoff. Choose a minimum-weight nontrivial logical v in that sector. Its support contains no proper nonempty zero-syndrome subset u:

- If u is nontrivial, it is a lighter logical, a contradiction.
- If u is a stabilizer, v+u is a lighter representative of v, again a contradiction.

Starting from a coordinate in v, any proper nonempty selected subset therefore has an unsatisfied check. At least one unselected coordinate of v touches that check. The engine branches on its available coordinates. After considering an option, that option is forbidden in later sibling branches; the first option belonging to v still defines a branch containing v. This partitions possibilities without losing the minimum logical. A zero-syndrome stabilizer terminates a branch; the argument above explains why no minimum nontrivial logical is lost there.

This proves an existence test, **not enumeration of every low-weight representative**.

## Safe pruning

1. **Remaining degree.** If the current syndrome has s unsatisfied checks and each remaining qubit touches at most Δ checks, fewer than `ceil(s/Δ)` additional qubits cannot cancel it.
2. **Disjoint available neighborhoods.** If p unsatisfied checks have pairwise disjoint available qubit neighborhoods, at least p further qubits are required. The engine finds such packings greedily and with a bounded auxiliary search. An interrupted auxiliary search merely forgoes this pruning; it never prunes on an unproved packing.
3. **Stabilizer overlap.** A minimum nontrivial binary logical v obeys `2|supp(v) ∩ supp(g)| ≤ |g|` for every stabilizer g, otherwise v+g is lighter. Selected support only grows down a branch. Once a partial support violates the inequality for a supplied stabilizer generator, no extension can be the chosen minimum representative. Dependent stabilizer rows are harmless.

The overlap rule is specifically for binary single-sector supports. It is not a valid unlabeled-support rule for a general non-CSS Pauli search. Disabling it still leaves the irreducible-support branching, so `--no-coset-pruning` is not a complete-pool enumeration mode.

## Testing proposed additions

The proposed-addition test uses the weighted bound already computed at a node to test its children. It is enabled by default for new searches and calibration, with `--no-proposed-additions` available to disable it. Suppose every completion obeys `A <= sum_q c_q x_q`, every coefficient is at most `D`, and at most `b` more qubits may be added. Fixing `x_v = 1` leaves the necessary inequality `A - c_v <= D * (b - 1)`. A violation excludes that child.

The engine computes each child's decision before descending into any child, because recursion reuses the coefficient workspace. A skipped child still excludes its coordinate from later siblings. The test therefore preserves the usual root and shard coverage. It applies to CSS searches and both parts of the LP reduction. A run records the option and the numbers of rejected candidates and skipped branches, and the auditor checks the setting against the command and transcript. Resume requires the same setting.

## Optional parity preprocessing

The `css` profile additionally tests whether the all-ones vector belongs to the row space of the sector's syndrome matrix H. If a row combination a satisfies `aH = 1`, then every kernel vector z obeys `|z| mod 2 = 1·z = aHz = 0`. Consequently an odd cutoff W can be replaced by W−1 without changing the decision. This is an elementary binary row-space criterion, not an LP-specific theorem.

The native output records both cutoffs and the original check rows in this XOR combination. The Python checker reconstructs their XOR and independently tests row-space membership before accepting the reduction. For W=1, the certificate alone excludes all possible weight-one words, so a valid execution can report zero search nodes. For larger cutoffs, every required reduced-cutoff subtree must still complete. The original requested cutoff remains the one used to report the resulting lower bound.

Having even chosen representatives modulo stabilizers would not justify this step: an odd stabilizer could change their parity. The test applies to the entire binary sector kernel. It also does not imply even support weight for a mixed Pauli assembled from two even pure-sector components.

## Root coverage and verified symmetry

A root is the first qubit selected by a search. Without symmetry, every physical coordinate is used as a root, with earlier coordinates forbidden. A target support is covered at its least coordinate.

For the verified block-cyclic permutation of period P, take the first occupied block of a target and translate a chosen occupied coordinate of that block to zero. Earlier blocks remain empty. Therefore one root at coordinate zero of **every physical block** covers an orbit representative. Verification of both stabilizer spaces ensures translation preserves logical nontriviality and weight. With P=1 this reduces to all physical coordinates.

For several generators, order their joint qubit orbits by their minimum indices. Given any nonempty logical support, choose its first occupied orbit and send an occupied site to that orbit's minimum r using a group element. Every earlier orbit remains empty. Every physical index below r lies in an earlier orbit, so the transformed support is covered by the search rooted at r with all smaller indices forbidden. Weight and logical nontriviality are preserved. This proves coverage for arbitrary orbit sizes and arbitrary physical index orderings.

The implementation computes joint orbits by joining each site to its image under each generator. This avoids enumerating the group. It reduces the starting roots of the search. The branching and pruning rules within each root remain the same. Both Python and C++ verify every generator against the two row spaces. The auditor also reconstructs the generator files and checks the native root list against independently computed orbit minima.

A sector-exchange permutation may remove one sector only after a separate row-space verification. The adapter's algebraic expectations do not substitute for this physical check. The framework does not assume a complete regular action on the logical quotient.

## Shards and completion

The search is divided into independent partitions called shards. Every shard traverses the same deterministic prefix tree. At a selected support size `split_weight`, a deterministic path hash assigns each subtree to exactly one shard by its residue modulo the shard count. Paths with the same hash are assigned to the same shard. Short branches terminating before the frontier are checked in every shard.

For exclusion credit, the checker requires:

- The exact code, native matrix, source and executable identities recorded for that campaign.
- The correct cutoff, period, pruning mode and partition in each command and terminal record.
- Normal successful exclusion, complete root coverage and no contradictory witness.
- A completed exclusion for every shard in every required sector.
- Identical prefix counts/digests and total owned frontier count equal to the common frontier count.

A timeout, nonzero error exit, missing shard or malformed record cannot establish the target lower bound. Independently checked witnesses survive incomplete work. Native time checks are periodic; the wrapper supplies a hard timeout with grace. Resuming preserves the records and starts a new attempt for each unfinished shard.

## What the independent checker does—and cannot do

The Python checker reconstructs ranks and row spaces, verifies symmetries and physical witnesses, checks input/source hashes, and validates consistency and coverage of completion records. It ignores any previously written `result.json` summary. Its implementation is independent of the C++ engine and has no assertion-dependent validation that disappears under `python -O`.

An execution receipt says the specified program reported completion on the specified input. It is **not a per-node proof trace**, a signed attestation of execution, or an independent proof that the executable was compiled from the named source. A fabricated internally consistent transcript is outside this evidence model. Trust in a lower bound still includes the search implementation and successful execution; a fresh replay provides additional reproducibility evidence. Small-code direct enumeration tests exercise correctness but do not constitute a general correctness proof.

The campaign includes the source and binary used so that identities can be checked later. The checker accepts the current engine and the exact source identities of the initial cyclic-only 0.1 engine, using the corresponding coverage rules. Other engine versions require their matching checker. A future formal proof format would need additional independently checkable branch-exclusion evidence.
