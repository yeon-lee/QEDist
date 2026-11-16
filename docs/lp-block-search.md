# Exact distance by LP tensor blocks

`lp` is an optional CSS search using the lifted-product tensor blocks. It accepts cyclic constituent inputs, the physical JSON produced by `expand-lp`, and physical checks with an explicit `lp_layout`. The last interface supports non-Abelian left/right lifted products. Binary and binary-expanded quaternary inputs, unequal constituents and rank-deficient constituents are supported. For physical matrices without a declared LP layout, use the default `css` profile. [Layout format](input-format.md#physical-lp-layouts)

```sh
qedist inspect examples/independent_qc.json --profile lp
qedist certify examples/independent_qc.json --profile lp \
  --cutoff 3 --shards 2 --workers 2 --out runs/lp-blocks
qedist audit runs/lp-blocks
```

The example has distance four. Two parts in each of its two CSS sectors, with two shards per part, give eight required shard results. A verified sector exchange permits one sector to stand for both. Each time or node budget applies to one shard of one part. A resumed campaign uses the original profile, cutoff, symmetry and partition. Runtime calibration samples the ordinary whole-code root distribution and is available for those profiles only.

## Why both parts suffice

The physical LP coordinates have two tensor blocks. A logical word either touches the second block or is supported entirely in the first.

1. **Words touching the second block.** The native search starts a word at an occupied site in this block. Sites in the first block remain available to complete it. Verified symmetry permits one root per joint orbit in the second block. Disabling symmetry searches individual roots. Ordinary pruning preserves the existence of a minimum logical representative of the full sector.
2. **Words confined to the first block.** The restricted check equations separate by column in the Z sector and by row in the X sector. Call each such column or row a stripe. Each restriction of a syndrome-free word to one stripe is itself syndrome-free. If every restriction were a stabilizer, their sum would be a stabilizer. At least one stripe of a confined logical word therefore carries a logical of equal or smaller weight.

Before searching, QEDist checks that the projected binary check spaces on all stripes agree after identifying their coordinates. It also checks that the restricted equations have no coupling between stripes. For row-equivalent presentations that mix stripes, the rank of the restricted matrix must equal the sum of its stripe ranks.

These are conditions on the physical matrices and their coordinate blocks. The same reduction applies to non-Abelian left/right lifted products when these conditions hold, including inputs with no declared symmetry. `lp_layout.block_size` describes physical coordinates per lifted block, while `cyclic_period` and `symmetry_generators` specify separately verified actions.

Write $E_j u$ for local word $u$ placed in stripe $j$, and $S$ for the full physical stabilizer space of this sector. A local word can be discarded as trivial only if it belongs to

```text
G = intersection over j of {u : E_j u belongs to S}.
```

QEDist computes each space by eliminating the physical coordinates outside its stripe, then intersects the resulting local spaces. A word outside $G$ has at least one nontrivial placement. The runner tries each placement and verifies the witness on the original physical checks. This distinction matters for unequal and rank-deficient constituents. All reported weights count physical binary coordinates.

A lower bound requires completed exclusions in **both** parts of every required sector. The auditor rederives both matrices from the input and checks their shard coverage separately. A completed stripe search on its own supplies an exclusion only for words confined to the first block. The extra matrix preparation and different search trees make the relative runtime instance-dependent.

Extra permutation generators must preserve both tensor blocks. On the first block, each must map whole stripes to whole stripes and induce the same local coordinate permutation in every stripe. QEDist derives that permutation and checks it against the local syndrome and common-stabilizer spaces. The second-block search uses the full physical generators. An incompatible action produces an explicit error with guidance to use `--profile css`, which supports arbitrary verified physical permutations. This preserves the hypotheses of the block reduction while using all compatible product-group generators.
