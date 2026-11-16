CSS search engine

Searches physical CSS check matrices with symmetry reduction, stabilizer-overlap
pruning, packing bounds, kernel-parity reduction and weighted-check bounds.
The package supplies fractional=2 repair-depth=8 even-repairs=4 and checks these
settings in the recorded execution. Storage is sized to the input and search
frames are allocated on the heap. Sparse checks use one availability word;
larger checks use multiple words. The fixed/ subdirectory contains the fast
fixed-storage variant, selected automatically when the input and cutoff fit.
Use --large-capacity or --no-large-capacity in the public commands to choose
explicitly. See ../../docs/native-profiles.md for capacities and memory budgets.

The optional symmetry-file lists verified qubit-permutation generators.
One root per joint orbit covers product-group actions. The executable checks
both row spaces and reports its root representatives for the Python auditor.

The proposed-additions=on flag uses the parent's weighted inequality to reject
an infeasible next qubit before entering its branch. New public certify and calibrate runs
supply this flag by default. Use --no-proposed-additions to disable the test.
Resume inherits the saved setting when neither public flag is supplied.
Omitting the native flag means disabled, preserving saved command behavior.
