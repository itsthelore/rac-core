# Frozen corpus snapshot (COUNCIL-REVIEW B3)

A checked-in copy of the RAC corpus (`rac/`) and the `.md` test fixtures
(`tests/**/*.md`, plus their `.rac/config.yaml` ancestry) taken at one commit.

## Why

The cargo vector suites — `resolve_vectors`, `classify_vectors`,
`validate_vectors`, `markdown_vectors`, `retrieve_vectors` — pin the Python
oracle's output over this corpus byte-for-byte. Pinning the **live** `rac/`
tree meant every ordinary docs commit invalidated ~10 MB of vectors and could
break the suite for an unrelated change. Pinning this frozen snapshot decouples
them: an edit to live `rac/` no longer touches these tests. Live-corpus
byte-identity is still refereed dynamically in the **parity tier** (the
harness runs both engines over the real `rac/`), where both engines move
together.

This mirrors `rust/spec/gen_vectors_index.py`, which already pins curated
fixture corpora and deliberately does not pin live `rac/`.

## Layout

- `rac/` — a copy of the repo's `rac/` corpus.
- `tests/` — the `.md` files under the repo's `tests/`, plus any `.rac/`
  config dirs so `validate_product`'s config walk-up resolves the same stanza.

The generators and tests run **from this directory** and reference the corpus
as the relative path `rac` / `tests/...`, so the artifact path (a BM25F field
in `resolve`/`retrieve`) tokenizes exactly as the live tree — a longer physical
prefix would leak `rust`/`fixtures`/`corpus` tokens into every document and
shift scores.

## Refreshing the snapshot

Re-copy the trees, then regenerate the vectors with the oracle venvs (see
`.github/workflows/rust-spike.yml` for the exact oracle build):

```sh
rm -rf rust/fixtures/corpus
mkdir -p rust/fixtures/corpus
cp -r rac rust/fixtures/corpus/rac
( cd tests && find . \( -name '*.md' -o -path '*/.rac/*' \) -type f -print0 \
    | tar --null -cf - -T - | ( mkdir -p ../rust/fixtures/corpus/tests \
    && tar -xf - -C ../rust/fixtures/corpus/tests ) )

for g in resolve classify validate markdown; do
  .venv-oracle/bin/python rust/spec/gen_vectors_$g.py
done
# retrieve uses the retrieval-branch oracle (ORACLE-NEXT):
.venv-oracle-next/bin/python rust/spec/gen_vectors_retrieve.py
```

`cargo test -p rac-engine` then replays the regenerated vectors over this
snapshot — a snapshot edit without a matching regenerate fails the suite, so
the two cannot silently drift.
