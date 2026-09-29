# Linux corpus regeneration: the oracle's conformance evidence

**What this is:** the dataset corpus regenerated on Linux (master plan
item 18), to report its per-category outcomes and, with them, how the
oracle conforms to real PyMOL. The split's own corpus was generated on
the Mac and its per-category report was never committed; only its totals
are, in [../manifest.json](../manifest.json) (3,388 of 4,000 kept).

**How it was made:** `bazel run //src/pmc_data:corpus_cli -- --config
configs/generation/corpus.json --workers 6` at commit `0eb1ca8`, on
Ubuntu 24.04.4 LTS under WSL2 (Windows 10.0.26200.9457), AMD Ryzen 5
3400G, with `pymol-open-source-whl==3.2.0.2`. It took 28 minutes. Same
config and seed as the split's own corpus (`seed=20260921`, 4,000
attempts over 149 categories), and it wrote the same corpus directory
name, `seed-20260921-5806db370de5`.

**Files:**

- `report.json`: the run's per-category report, as `corpus_cli` wrote
  it;
- `rejections.jsonl`: every attempt not kept, with its reason;
- `crash_rerun.json`: the re-run described below.

## Why this is the oracle's conformance evidence

Every attempt is a differential test. The oracle (`pmc_data.oracle`)
predicts, without PyMOL, what the plan does. The plan is then executed in
a fresh Open-Source PyMOL process, and the two resulting states are
compared by fingerprint. An attempt is:

- **kept** when they are identical;
- **rejected** when they differ, or when PyMOL itself fails;
- **unsupported** when the oracle declines to predict, naming why.

## What it found

| Outcome | Attempts |
| --- | --- |
| kept | 3,381 |
| rejected | 7 |
| unsupported | 612 |

- **No oracle disagreement.** No attempt was rejected for a fingerprint
  mismatch: the oracle and PyMOL agreed on every attempt PyMOL completed.
- **The 7 rejections are all `child_crash`:** the PyMOL child process
  died before it reported. Re-run one at a time with nothing else
  running, all 7 were kept (`crash_rerun.json`).
  - They are therefore transient infrastructure failures, not
    disagreements.
  - The likely cause is memory pressure from six concurrent PyMOL
    processes on a 7.9 GB machine. The kernel log was not readable to
    confirm it.
  - Counting them, the regeneration keeps 3,388, the Mac run's figure.
- **The 612 unsupported are the declared ungradable surfaces:**
  - every plan using the `polymer` term (`polymer_classification`);
  - every bare `orient` (`camera_view`);
  - these are the same ones the Mac run declined.

## What it is not

It is not the split's corpus, and the split is not rebuilt from it. The
79 `orient` samples record camera-view fingerprints that differ between
macOS and Linux, so a split rebuilt here would get a different id
(configs/evaluation/engine/README.md). The committed split stays the
one built on the Mac (macOS 15.6.1, MacBook Pro M2). This report
measures the oracle; it does not replace the dataset.
