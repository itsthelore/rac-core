# results/ — append-only

This directory is **append-only**. Every run writes a new timestamped report
file (`run-<UTC>-<label>.json`) and the crossover artifacts
(`crossover_dataset.json`, `crossover.{png,svg}`). Existing run files are never
mutated or deleted; a re-run produces a new file.

Each report records the pinned answering model, version, temperature, and seed,
so any run reproduces from seed + pinned model versions.

Reports written with the offline `offline-stub` answering model are **harness
illustrations, not benchmark results** — they exercise the plumbing on a tiny
synthetic corpus. Published benchmark results require the pinned Claude
answering model and real/public-derived corpora (see `../CONTRIBUTING.md`).
