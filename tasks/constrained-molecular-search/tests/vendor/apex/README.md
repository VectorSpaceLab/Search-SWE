# APEX
Code for the paper APEX: Approximate-but-exhaustive search for ultra-large combinatorial synthesis libraries.

### Setup

The `apex` package and `apex_topk` extension are installed in the task environment.

### Usage

An APEX model can be set up in a few steps:
1. Train an APEX-compatible surrogate model (comprised of a molecular encoder and linear probes) on a labeled molecular dataset.
2. Train an APEX factorizer to reconstruct embeddings of the trained surrogate model on an unlabeled CSL.
3. Carry out necessary pre-calculations to enable accelerated approximate-but-exhaustive search on a given CSL.
4. Search!

In the paper, we (1) train a simple 2D GNN surrogate model on 80% of the `brics_csl_1M` library, (2) train a factorizer on the `brics_csl_12M` and `brics_csl_10B` libraries, and (3) carried out necessary pre-calculations for carrying out an APEX search.

#### 1. Train the surrogate

```
train_surrogate \
--config configs/apex.yaml \
--parquet_path ../brics_csl_1M/enumerated_and_scored.parquet \
--training_folds 0 \
--validation_folds 1 \
--property_columns fraction_cs_p3 logp max_ring_size mol_wt mr n_aliphatic_rings n_aromatic_ring n_atoms n_bridgehead_atoms n_hba n_hbd n_heavy_atom n_heterocycles n_ring n_rotatable_bonds n_stereocenter n_unspecified_stereocenter qed qeppi score_DRD2 score_ESR1 score_F10 score_MET score_PARP1 sps synthetic_accessibility_score tpsa weird_fragment_score \
--output_dir $OUTPUT_DIR \
--run_id $SURROGATE_RUN_ID
```

#### 2. Train the factorizer

```
train_factorizer \
--config configs/apex.yaml \
--encoder_weights_path $OUTPUT_DIR/$SURROGATE_RUN_ID/checkpoints/encoder.pt \
--probe_weights_path $OUTPUT_DIR/$SURROGATE_RUN_ID/checkpoints/probe.pt \
--library_path ../brics_csl/brics_csl_12M/ \
--output_dir $OUTPUT_DIR \
--run_id $FACTORIZER_RUN_ID
```

#### 3. Prepare a CSL for search with APEX

```
prepare_library \
--config configs/apex.yaml \
--encoder_weights_path $OUTPUT_DIR/$FACTORIZER_RUN_ID/checkpoints/encoder.pt \
--probe_weights_path $OUTPUT_DIR/$FACTORIZER_RUN_ID/checkpoints/probe.pt \
--factorizer_weights_path $OUTPUT_DIR/$FACTORIZER_RUN_ID/checkpoints/factorizer.pt \
--library_path ../brics_csl/brics_csl_12M/ \
--output_dir $OUTPUT_DIR \
--run_id $APEX_RUN_ID
```

#### 4. Search the CSL with APEX

```
run_search \
--config configs/apex.yaml \
--queries configs/queries.yaml \
--encoder_weights_path $OUTPUT_DIR/$FACTORIZER_RUN_ID/checkpoints/encoder.pt \
--probe_weights_path $OUTPUT_DIR/$FACTORIZER_RUN_ID/checkpoints/probe.pt \
--factorizer_weights_path $OUTPUT_DIR/$FACTORIZER_RUN_ID/checkpoints/factorizer.pt \
--apex_weights_path $OUTPUT_DIR/$APEX_RUN_ID/checkpoints/apex.pt \
--library_path ../brics_csl/brics_csl_12M/ \
--output_dir $OUTPUT_DIR \
--run_id $SEARCH_RUN_ID
```
