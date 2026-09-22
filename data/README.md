# Generated data

Generated artifacts belong here only when content-addressed and intentionally
produced by a data task. Generated contents are ignored; this README is
tracked.

## `samples/seed-<seed>-<identity>/`

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
  categories counted separately from failures, and with the kept
  samples that could not have failed counted separately again. A plan
  predicting no observable change, or grading a selection that matches
  no atom, agrees with any oracle at all, so `no_op`,
  `empty_selection`, `vacuous` and `substantive` say how much weight
  the rate beside them carries. `complete` says whether every planned
  attempt was actually made: a run that fails partway still writes
  what it measured rather than discarding hours of verified work, and
  says so here rather than passing for a whole corpus.

The directory is named for the run's inputs rather than a timestamp:
the run is deterministic in them, and nothing nondeterministic is
recorded in a sample, so regenerating with the same inputs reproduces
these files byte for byte. That is what makes the seed each sample
carries worth anything.

The seed is not the whole of those inputs, so it is not the whole of
the name. The attempt budget decides how much of the enumeration is
run, and the contract versions decide what a sample even looks like;
`<identity>` is a digest over all three. Naming the directory for the
seed alone made two different corpora share it, and the second
replaced the first with no warning -- a 3,695-sample run was cut to 53
that way.

A run writes beside its destination and is moved into place in one
step once it is complete. A run that fails partway is left as
`seed-<seed>-<identity>.partial/`, with its `report.json` saying
`complete: false`, and the complete corpus it would have replaced is
untouched.

A small fixed slice of this corpus is committed under
`src/pmc_data/conformance/` -- its samples and its one ungradable
attempt, but no report, which would only restate them -- and replayed
by `bazel test`. The full run is deliberately not committed, since a
few thousand samples is a few thousand spawned PyMOL processes.
