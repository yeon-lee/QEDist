# Inputs and physical conventions

The cyclic LP constructor supports F₂ or F₄ and any positive period P. Physical CSS matrices support codes over product and non-Abelian groups. An explicit physical LP layout enables the tensor-block reduction for these inputs. Every declared physical permutation is checked against the stabilizer spaces. General mixed-Pauli stabilizer generators use the separate `qedist.stabilizer.v1` format and `certify-stabilizer` command. [General stabilizer inputs](stabilizer-distance.md)

## Physical CSS matrices

```json
{
  "schema": "cssdist.code.v1",
  "name": "four-qubit example",
  "n": 4,
  "hx": [[0,1,2,3]],
  "hz": [[0,1,2,3]],
  "cyclic_period": 1,
  "sector_exchange": [0,1,2,3],
  "witnesses": {"Z": [[0,1]]}
}
```

Each row is a list of distinct zero-based physical qubit indices. The input must satisfy `H_X H_Z^T = 0`. `H_X` contains X-stabilizer generators and tests Z-type operators; `H_Z` contains Z generators and tests X-type operators. Rows may be dependent, duplicated or empty; coordinate indices within a row may not be repeated. Ranks and `k=n-rank(H_X)-rank(H_Z)` are computed rather than declared by the caller.

`witnesses` is optional. Each supplied support is checked for zero syndrome and nonmembership in the full corresponding stabilizer row space. In the absence of a supplied witness, Gaussian elimination supplies valid logical representatives, possibly much heavier than the distance. No supplied or constructed frame is needed to test nontriviality.

`CSSCode.from_dense(hx, hz, n=...)` converts lists of binary integers. Specify `n` if both matrices have no rows. JSON inputs always use the sparse format above.

### Plain-text sparse matrix files (`.mtx`)

`import-matrices HX.mtx HZ.mtx --output code.json` reads physical check matrices from plain-text `.mtx` files using the `coordinate integer general` or `coordinate pattern general` format. Coordinates are one-based. Integer entries must be 0 or 1, and a pattern entry means 1. Repeated coordinates are summed in F₂, so two occurrences cancel. Comments, empty rows and dependent rows are accepted. Real, complex, symmetric and dense-array formats are rejected. Expand F₄ symbols to binary physical checks before importing.

Both files must have the same positive column count, and the importer verifies CSS commutation and computes the ranks. `--period P` optionally declares the consecutive-block cyclic permutation defined below; invalid declarations are rejected. The default is P=1. Input file hashes and the modulo-two duplicate convention are retained in provenance. No sector exchange or distance witness is inferred from matrix filenames.

`export-matrices code.json --hx HX.mtx --hz HZ.mtx` writes canonical binary integer coordinate files, preserving all physical rows and their order. An export does not preserve the input JSON's witnesses or symmetry metadata; retain the JSON alongside the matrices when transferring those declarations. Import and export refuse to overwrite existing destination files.

### Optional symmetry

`cyclic_period=P` asserts the physical permutation

`block*P + t -> block*P + (t+1) mod P`

on consecutive blocks of P qubits. It defaults to 1. P must divide n, and the permutation must preserve **both stabilizer row spaces**. A row need not map to another individual row of the chosen presentation. A true invariant row space is enough.

`sector_exchange` is a list giving the image of every physical coordinate. It must be a bijection taking each stabilizer space to the other. When verified and symmetry use is enabled, only the Z sector is searched and its result transfers to X. Otherwise both sectors are searched. No symmetry is inferred merely from equal sector ranks or equal check weights.

`symmetry_generators` is a list of permutations. Each inner list has exactly n integer entries and maps old index j to new index `permutation[j]`. Each must preserve both full stabilizer row spaces. This supports independent generators of a product group, arbitrary qubit orderings, noncommuting generators, fixed points and unequal orbit sizes. The algorithm uses joint orbits of the generated physical action. It needs no declared group order or faithfulness assumption.

For the four-qubit input above, independent `C_2 × C_2` translations can be written as follows.

```json
"symmetry_generators": [[2, 3, 0, 1], [1, 0, 3, 2]]
```

`product_translation_generators((a, b, c), blocks=B)` creates three independent translations for B blocks of size abc. In each block, `(i, j, k)` has index `(i*b+j)*c+k`. Generators increment one coordinate modulo its factor size. Reorder these permutations along with the matrices if the physical qubit numbering differs. A quaternary code needs permutations of its expanded binary coordinates, including the trace-component ordering.

If both symmetry fields are supplied, their generated actions are combined. Supplying a single diagonal translation uses its cyclic subgroup. Supplied independent translations give the full product action. `inspect` reports the number of verified extra generators and the minimum-index representative of each joint orbit.

The Python input validator and the native engine independently check bijectivity and row-space preservation. Campaigns preserve the generator files, their hashes and the actual root representatives. The read-only auditor regenerates the files from the original physical input, recomputes the joint orbits, and verifies every required root and shard. Calibration samples these same joint-orbit roots. [Coverage proof](algorithm.md#root-coverage-and-verified-symmetry)

## Physical LP layouts

Physical CSS inputs can select `--profile lp` by supplying the following metadata. The same dictionary can be passed as the `lp_layout` keyword of `CSSCode.from_sparse` or `CSSCode.from_dense`.

```json
"lp_layout": {
  "A_shape": [3, 5],
  "C_shape": [3, 5],
  "block_size": 21
}
```

`A_shape` and `C_shape` give `[rows, columns]` for the two constituents. All dimensions and `block_size` must be positive integers. With shapes `[r_A,s_A]` and `[r_C,s_C]`, the physical length must equal

\[
n=(s_A s_C+r_A r_C)\,\texttt{block\_size}.
\]

Coordinates first enumerate `s_A*s_C` lifted blocks in order `(a,b)`, with b varying fastest, then `r_A*r_C` blocks in order `(i,j)`, with j varying fastest. Each lifted block occupies `block_size` consecutive binary coordinates with a consistent internal ordering. For a binary left/right group-algebra LP code, `block_size=|G|`. For a binary-expanded quaternary code, `block_size=2|G|`, including both binary components of the lifted block.

The block size and the symmetry action are separate inputs. `cyclic_period` defaults to 1. Optional `symmetry_generators` use the full physical coordinate numbering and are checked individually. To use cyclic reduction in the LP profile, the period must divide `block_size`, so its consecutive cycles stay within lifted blocks. The LP profile also verifies preservation of both tensor blocks and a consistent induced action on the stripes. Use `--no-symmetry` to run the split without symmetry, or the `css` profile for an action incompatible with the split.

The layout enables a physical verification of the reduction. QEDist checks equal projected stripe kernels, absence of coupling between stripes, and the common stabilizer space used to discard local words. A false layout that violates these requirements is rejected. The checks permit dependent constituent rows and row-equivalent stabilizer presentations. [Reduction and coverage argument](lp-block-search.md)

Cyclic constructor outputs already carry their dimensions in `construction`. An additional `lp_layout`, if present, must agree with that construction. The physical layout and permutation declarations are included in the input fingerprint and rechecked when auditing or resuming a campaign.

The S₃ example uses A = `(1+r, s)` through left multiplication and C = `(1+s, r)` through right multiplication, where `r^3=s^2=1` and `srs=r^-1`. Its provenance specifies the group-element ordering. The supplied witnesses have weights 2 in X and 3 in Z. [Complete input](../examples/nonabelian_lp.json)

## Cyclic LP inputs

```json
{
  "schema": "cssdist.lp.v1",
  "name": "independent constituents",
  "field": 2,
  "period": 5,
  "A": [[1, [[0,1],[1,1],[3,1]]]],
  "C": [[1,1,0],[0,1,1]],
  "check_basis": "raw"
}
```

For A of size r_A × s_A and C of size r_C × s_C, the adapter forms

\[
H_X=[A\otimes I_{s_C}\mid I_{r_A}\otimes C^\dagger],\qquad
H_Z=[I_{s_A}\otimes C\mid A^\dagger\otimes I_{r_C}].
\]

Here dagger transposes and sends `t` to `t^-1`. The coefficient ring is `F_q[t]/(t^P-1)` with q=2 or 4. Because the ring is commutative and has characteristic two, these checks commute. No constituent-rank or pivot assumption is made. If C is omitted it equals A. If the normalized A and C are equal, tensor transposition is proposed as a sector-exchange permutation and is then independently validated by the physical input layer.

The number of physical qubits is

\[
n=bP(s_A s_C+r_A r_C),\qquad b=1\text{ for F₂},\quad b=2\text{ for F₄}.
\]

The code dimension comes from the expanded binary ranks. In particular, the adapter does not apply a full-rank formula to rank-deficient inputs. There is no restriction to prime periods or powers of two.

### Polynomial entries

An entry is either an integer constant or a list of `[exponent, coefficient]` terms. For example `[[0,1],[3,2]]` means `1+ωt³` over F₄. Exponents are reduced modulo P; repeated exponents are combined by field addition. `0` and `[]` both denote zero. For F₂ use coefficients 0 or 1. For F₄ use 0,1,2,3 for 0,1,ω,ω², with `ω²=ω+1`.

### F₄ is expanded to qubits

Distances are **binary physical weights**, not the number of nonzero F₄ symbols. The self-dual trace basis is `(ω,ω²)`. Multiplication by coefficients has binary matrices

\[
\rho(1)=I_2,\quad
\rho(\omega)=\begin{pmatrix}0&1\\1&1\end{pmatrix},\quad
\rho(\omega^2)=\begin{pmatrix}1&1\\1&0\end{pmatrix}.
\]

Each constituent term `c t^e` sends row coordinate t to column coordinate `t-e (mod P)`, with binary component coupling given by ρ(c). Coordinate order is `(b*block+component)*P+t`. Large-block order is `(a,b)` for the first `s_A*s_C` blocks and `(i,j)` for the final `r_A*r_C` blocks. Dagger leaves coefficients unchanged and reverses exponents; it is not coefficient conjugation.

For F₄, `check_basis` may be:

- `raw`: the two trace-basis rows.
- `balanced`: the two lowest-weight rows among u, v and u+v for each trace pair.
- `redundant`: all three rows u, v and u+v.

These presentations have the same stabilizer spaces but different pruning behavior. Check and column weights refer to the selected physical presentation. The adapter's balanced-row ordering need not match the original companion file ordering; the catalogue examples were compared by their full physical row spaces.

`name`, `provenance`, `witnesses` and `symmetry_generators` carry through to the expanded physical input. Provenance may mention a previously reported distance, but only independently validated witnesses and newly completed exclusions enter the computed result. Metadata is part of the code fingerprint, so editing it requires a new campaign directory.
