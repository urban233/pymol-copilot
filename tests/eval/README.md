# Evaluation tests

Owned by the offline evaluation harness (master plan item 16,
`src/pmc_eval/`). No parser, policy, executor or request-graph behavior
is settled here -- those stay owned by `tests/contract`,
`tests/adversarial`, `tests/unit` and `tests/integration`. What is
settled here is that the harness measures what it claims to: that it
sends the model the prompt the model was trained on, that it runs the
runtime's own request graph rather than a copy of it, and that its
grader can both pass a correct plan and fail a wrong one.
