DIRECT CIRCUIT-DISTANCE NATIVE BACKEND
====================================

Scope
-----
For binary detector matrix D and logical-observable matrix O, this backend
decides whether some binary vector e satisfies

    weight(e) <= W, D e = 0, O e != 0.

Each coordinate is ONE independent fault mechanism of unit cost. Neither
probabilities nor negative log-likelihoods enter the objective. "Weighted"
below means integer-weighted parity inequalities used for pruning; it does not
mean weighted fault costs. The Python circuit adapter is responsible for the
physical interpretation of mechanisms and for retaining correlated events as
single coordinates. This native program cannot establish that an arbitrary
detector model is equivalent to a requested circuit-noise model.

Interface
---------
Compile:
    c++ -std=c++17 -O3 exact.cpp -o exact

Run:
    exact MODEL W SECONDS NODECAP [weighted=on|off] [neutral=on|off]
          [even-repairs=4] [repair-depth=8]

MODEL is a whitespace-separated sparse text format:

    QEDIST_CIRCUIT_V1 n m o g
    <m rows of D>
    <o rows of O>
    <g optional neutral rows>

Each row is "weight q0 q1 ...", with zero-based coordinates strictly
increasing, unique, and below n. Empty D/O rows and dependent rows are allowed.
The header requires n >= 1, m >= 0, o >= 1, g >= 0. The neutral rows must be
nonempty; duplicates are harmless. Every neutral row a is checked to satisfy
D a = O a = 0, even when neutral pruning is disabled. Neutral rows need not
span this joint kernel. A dense basis for that kernel is never constructed.

Defaults: weighted=on, neutral=on, even-repairs=4, repair-depth=8. Weighted
off disables BOTH fractional odd-check packing and even-check repair, retaining
the same ordinary packing, branch ordering, root coverage, and neutral rule.
For odd-check-only ablation use weighted=on even-repairs=0. Neutral off removes
only neutral-overlap pruning. The minimum-available-degree tie breaker is unchanged
between these ablations unless repair-depth is explicitly changed.

Additional internal options root-begin and root-end select a half-open range
of root indices. They are intended for future range partitioning, not a claim
that one such run covers the full model. No translation or circuit symmetry is
assumed. A full exclusion has complete=true only when all n roots are covered.

Outputs are JSON Lines: a physical support for a found witness, followed by a
terminal result. Exit codes are 0 (excluded within root range), 10 (witness),
75 (timeout, node_limit, interrupted, or allocation failure), and 2 (invalid input/internal error).
The result reports roots_total/roots_completed, nodes, each pruning counter,
search_seconds and cpu_seconds. The reported time starts AFTER parsing and
neutral-row validation; callers should additionally record end-to-end time.
An exclusion with complete=true is a lower bound, not an upper-bound witness.
A timeout or a partial root-range exclusion is not a full-model lower bound.

Dimensions and resources
------------------------
The fixed/ subdirectory supplies the bounded recursive variant selected by public
commands when the input and cutoff fit. Use --large-capacity to select the
expanded-storage implementation in this directory explicitly.
Rows use dynamically sized bit masks indexed within each sparse detector row.
Indices and cutoffs must fit signed 32-bit integers. The search uses an explicit
heap-backed stack, with pruning scratch shared between depths. The optional
memory-bytes=N argument budgets live vector capacity before allocation. An
allocation failure emits a resource_limit event containing the budget and peak
tracked allocation, and returns exit code 75. This event grants no exclusion
credit. Other process overhead contributes additional resident memory.
The wall-time condition is checked at each root and every 4096 search
nodes; an expensive node can exceed the requested time before the next check.
Callers should retain an external timeout with a grace interval.

Why the exclusion is complete
-----------------------------
1. Root coverage. Every nonempty support has a first coordinate r. Root r
   includes r and forbids all smaller coordinates. The unpartitioned program
   covers every r, with no circuit symmetry assumption.

2. Irreducible support suffices. Let e be a minimum-weight solution with Oe
   nonzero. If its support contains a proper nonempty detector-kernel word a,
   either Oa is nonzero or O(e+a)=Oe is nonzero. One of a and e+a would be a
   smaller solution. Thus a minimum solution can be grown without an earlier
   zero-detector partial support. When a partial support has De=0 and Oe=0,
   stopping that branch cannot discard every minimum solution.

3. Unsatisfied-check branching. A nonzero detector syndrome has an odd row.
   Every completion must add at least one available coordinate in that row.
   The program chooses an odd row with fewest available coordinates. Ordered
   siblings exclude choices already covered by earlier siblings, partitioning
   the remaining completions without duplication. Availability changes and
   syndrome/observable toggles are exactly undone on return.

4. Neutral overlap. If a verified neutral row a overlaps the selected support
   in more than half its sites, every completion has at least that overlap.
   Replacing a completed fault word e by e+a preserves De and Oe and strictly
   lowers weight. Such a completion cannot be globally minimum. Neutral rows
   need not generate all zero-detector, zero-observable faults for this rule.
   It is a minimum-distance exclusion rule, not enumeration of every fault.

5. Packing. Disjoint available neighborhoods of odd detectors each require
   a distinct additional coordinate. A small bounded search can also find a
   larger collection of disjoint neighborhoods; failure to find one never
   prunes. The elementary syndrome-weight/max-column-degree bound is also safe.

6. Integer parity bounds. For completion bits x over currently available
   coordinates, every odd row q implies sum_{v in q} x_v >= 1. Assigning
   nonnegative integer weights with every column load <= D gives a lower bound
   (sum weights)/D on additional weight. The implementation uses D=2 and checks
   the strict inequality against the remaining integer budget.

   A currently even row q additionally gives
       sum_{u in q, u != v} x_u - x_v >= 0
   for any v in its available neighborhood. The bounded repair procedure adds
   these inequalities to reduce an overloaded column while checking that no
   other column exceeds D. Failed trials are reversed. Every accepted trial
   therefore preserves a valid lower-bound inequality. No floating-point
   linear-programming decision is trusted.

Evidence and limitations
------------------------
The implementation adapts the search and bounds of native_css. It uses direct
observable parity, removes cyclic-root reduction, validates optional neutral
relations, and uses dynamic sparse storage and per-depth workspaces.

The source distribution includes circuit tests in tests/test_circuit.py,
tests/test_circuit_window_search.py and the other test*circuit*.py modules.
They compare searches on small models with known distances or exhaustive
subset enumeration, exercise weighted and neutral pruning, and verify
high-degree inputs, incomplete runs, time-window coverage and evidence audits.
From the source root, run

    python -m unittest discover -s tests -p 'test*circuit*.py' -v

The native source hashes are recorded in provenance.json.

Terminal execution records are reproducible search records, not formal proof
objects certifying every pruned branch independently of this implementation.
