# Generated data

Generated artifacts belong here only when content-addressed and intentionally
produced by a data task. Generated contents are ignored; this README is
tracked.

## `samples/seed-<seed>/`

The verified dataset corpus, written by

    bazel run //src/pmc_data:corpus_cli -- --workers 8

Three files, because a summary alone would let an individual rejection
disappear:

- `samples.jsonl` -- verified samples only, one JSON object per line.
  A sample is written only when the real execution boundary agreed
  with an expectation the oracle computed without PyMOL.
- `rejections.jsonl` -- every attempt that did not become a sample,
  with the reason the executor actually gave.
- `report.json` -- the rejection rate per category, with unsupported
  categories counted separately from failures.

The directory is named for the seed rather than a timestamp: the run
is deterministic in its seed, and nothing nondeterministic is recorded
in a sample, so regenerating at the same seed reproduces these files
byte for byte. That is what makes the seed each sample carries worth
anything.

A small fixed slice of this corpus is committed under
`src/pmc_data/conformance/` and replayed by `bazel test`; the full run
is deliberately not, since a few thousand samples is a few thousand
spawned PyMOL processes.
