# Adversarial tests

Owned by security and policy evidence.

Every input in this directory is a literal adversarial string: no grammar, no
generator, no corpus files. Three modules, and they are deliberately not
interchangeable:

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
