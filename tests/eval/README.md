# Evaluation tests

Owned by the offline evaluation harness (master plan item 16,
`src/pmc_eval/`). No parser, policy, executor or request-graph behavior
is settled here -- those stay owned by `tests/contract`,
`tests/adversarial`, `tests/unit` and `tests/integration`. What is
settled here is that the harness measures what it claims to: that it
sends the model the prompt the model was trained on, that it runs the
runtime's own request graph rather than a copy of it, and that its
grader can both pass a correct plan and fail a wrong one.

## Where each claim is settled

| Module | What it settles |
| --- | --- |
| `test_prompt.py` | A first attempt sends each gold sample's own recorded prompt, byte for byte, through the graph's JSON round trip; the repair lines are the graph's own wording, appended after the intent. |
| `test_screen_reasons.py` | The report's copy of the hostile screen's rules agrees with `pmc_core.screen` over the adversarial corpus and model-shaped text. |
| `test_grade.py` | The TaskSuccess rules, the fully-graded and vacuous flags, and the empty-selection flag, on constructed reports. |
| `test_runner.py` | The wrapped graph behaves as the bare graph; each outcome is reached through the real graph; the grammar and the newline normalization apply exactly where they should; infrastructure failures are never scored. |
| `test_metrics.py` | Every rate counts what it says over the denominator it says, and structural zeros are labelled. |
| `test_eval_cli.py` | What a run writes and every refusal; resume; byte-identical reruns; publishing. |
| `test_reference_model_real_pymol.py` | Against real PyMOL, every gold reference plan scores a success, and each kind of wrong answer does not. |
| `test_lemonade_real.py` | Opt-in, against a real local Lemonade server: two gold samples per condition are scored end to end. |

## Findings worth knowing before changing any of this

- **`parse_pml` rejects a completion without a final newline**, and a
  chat model's completion usually has none. Without the harness's
  normalization, the ungrammared condition would measure that one
  formatting rule. The runtime has no such normalization yet.
- **The hostile screen refuses most prose**: an apostrophe, a code
  fence, or an English word such as "set" or "load" is enough. The
  report names the rule that fired so this reads as what it is.
- **A pulled Lemonade model is catalogued without its `user.` prefix**,
  and the item 9 adapter compares the catalog id exactly.
