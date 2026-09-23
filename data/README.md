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
run, the contract versions decide what a sample even looks like, and
the generator decides what there is to attempt at all; `<identity>` is
a digest over all of them, the generator included as the structures it
built and the plans it enumerated rather than as a version someone has
to remember to bump. Naming the directory for the seed alone made two
different corpora share it, and the second replaced the first with no
warning -- a 3,695-sample run was cut to 53 that way.

A run writes beside its destination, under a staging name of its own,
and is moved into place in one step once it is complete. The move
never deletes what is already there: an identity whose corpus already
exists keeps it, a rerun that reproduces it is simply discarded, and a
rerun that does *not* reproduce it is kept as
`seed-<seed>-<identity>.<token>.rerun/` and reported as a failure --
the identity promised those bytes, so a disagreement is a finding
about the generator and not something to overwrite. A run that fails
partway is left as `seed-<seed>-<identity>.<token>.partial/`, with its
`report.json` saying `complete: false`, and the complete corpus it
would have replaced is untouched.

A small fixed slice of this corpus is committed under
`src/pmc_data/conformance/` -- its samples and its ungradable
attempts, but no report, which would only restate them -- and replayed
by `bazel test`. The full run is deliberately not committed, since a
few thousand samples is a few thousand spawned PyMOL processes.

## `splits/split-<id>/`

The held-out split (master plan item 15), written by

    bazel run //src/pmc_data:split_cli -- build \
        --corpus data/samples/seed-<seed>-<identity>

- `train.jsonl` -- corpus samples on training structures, after
  decontamination.
- `test_gold.jsonl` -- the reviewed gold set: the test split.
- `heldout_synthetic.jsonl` -- corpus samples on held-out structures,
  a secondary evaluation set with templated intents.
- `decontam_dropped.jsonl` -- training samples dropped as
  near-duplicates of a gold intent, each with the gold item it matched.
- `manifest.json` and `DATASHEET.md` -- content hashes, provenance,
  license record, regeneration commands, and the rendered datasheet.
- `audit/` -- after the label audit: the sheet, and its scored result.

The id is a digest of the four data files, so the same inputs always
land in the same directory, and an existing split is never
overwritten. The manifest, datasheet and filled audit are copied to
`docs/dataset/`, which is tracked; the split itself is not.
