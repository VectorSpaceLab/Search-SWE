# Starter Index Format

The starter uses a bounded-memory binary inverted index for the set-valued
corpus. A submission may keep this layout or replace it with another persistent
format, provided that `build.sh`, `run.sh`, and the output contract remain
valid.

## Files

The starter index contains:

```text
INDEX_DIR/
├── docs.txt
├── dictionary.json
├── term_meta.npy
├── postings.docs.bin
├── block_lengths.bin
└── manifest.json
```

### `docs.txt`

UTF-8 text with one opaque external document ID per line. The zero-based line
number is the internal document number stored in postings. IDs must be unique,
and the number of lines must equal the corpus document count.

### `dictionary.json`

A JSON object mapping each retained opaque term ID to its zero-based physical
row in `term_meta.npy`:

```json
{"term-id": 123}
```

Every dictionary value must refer to an existing metadata row.

### `term_meta.npy`

One fixed-width row per indexed term. The starter fields are:

```text
old_id        source term row before filtering
offset        starting element in postings.docs.bin
length        posting count for the term
block_offset  starting row in block_lengths.bin
block_count   number of block lengths for the term
df            document frequency, equal to length
idf           log1p(document_count / max(df, 1))
```

Dictionary lookup uses the physical row. If a submission filters terms, all
dictionary, metadata, posting, and block offsets must use the same compacted
row space.

### `postings.docs.bin`

Little-endian unsigned 32-bit internal document numbers. For a metadata row
`r`, the posting list is:

```text
postings[term_meta[r].offset : term_meta[r].offset + term_meta[r].length]
```

Document numbers within each term interval are strictly increasing. Posting
intervals must not overlap, and their total length must equal the indexed
posting count.

### `block_lengths.bin`

Little-endian unsigned 32-bit block lengths. The starter uses blocks of at most
128 postings. The block lengths for one term are positive and sum to that
term's posting length. The starter search does not use block skipping; a
submission may use this metadata or replace it.

### `manifest.json`

The starter records the document count, source and indexed term counts, input
and indexed posting counts, block size, corpus/statistics checksums, build
summary, and whether the index uses the set-valued input format.

## Construction and baseline behavior

The starter builds the index with bounded-memory temporary term buckets:

1. read public term statistics;
2. stream the corpus in input order;
3. write `(term row, document number)` records to temporary buckets;
4. sort each bucket by term row;
5. append each term's document numbers and metadata; and
6. write the dictionary and manifest.

The corrected starter retains every term and every posting by default. It does
not perform DF pruning, prefix truncation, upper-bound pruning, candidate
pruning, or block skipping when used as the verifier baseline. Its search adds
the term IDF contribution for every matching posting and ranks by descending
score, breaking equal scores by ascending opaque document ID.

The optional pruning arguments present in starter code are for explicit local
experiments only. They are not part of the verifier's default baseline.
