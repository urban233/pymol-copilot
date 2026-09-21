# Adversarial tests

Owned by security and policy evidence.

Every input in this directory is a literal adversarial string: no grammar, no
generator, no corpus files. The modules are deliberately not interchangeable:

- `test_parser_rejections.py` pins the rejection **categories** and the
  command index each one reports. It is the only place a category is
  asserted, so restructuring the parser breaks exactly one module.
- `test_denied_forms.py` is the specification's explicit-denial list turned
  into inputs — Python-evaluating forms, shell metacharacters, file paths,
  load/save/fetch, plugin invocations. It asserts only that each input is
  denied and that Open-Source PyMOL was never imported, never which category
  denied it.
- `test_parser_totality.py` fuzzes from a fixed seed: the parser never
  raises, and anything it accepts was already canonical.
- `test_hostile_screen.py` (docs/master_plan.md item 8) asserts
  `pmc_core.screen.screen_completion` against the exact same corpus
  `test_denied_forms.py` already proves the parser and policy deny
  (`denied_forms.py`, shared rather than re-typed): every one of those forms
  screens hostile, every valid round-trip `.pml` case screens ordinary, and
  so does a representative set of ordinary typos -- since misfiling a typo as
  hostile silently disables the one repair attempt it would otherwise get.
- `test_model_authority.py` (docs/master_plan.md item 8) is
  SPECIFICATION.md:551-552 proved against the finished request graph: a
  completion engineered to influence attempt count, status, target object,
  policy, `applicable`, plan id, expiry, or plan shape is run through the
  graph, and the protected field is checked against exactly what
  deterministic code alone produces. Two of its six attacks turn out to be
  caught by the hostile screen itself, with zero repairs, rather than
  exhausted through the ordinary repair loop -- documented rather than
  quietly assumed away.
