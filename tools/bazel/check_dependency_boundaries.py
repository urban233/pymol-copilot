# Copyright 2026 PyMOL Copilot contributors.
"""Check that runtime dependency closures remain free of training tools."""

import os
import subprocess
import sys


FORBIDDEN = {
    "//src/pmc_agent:pmc_agent",
    "//src/pmc_data:pmc_data",
    "//src/pmc_train:pmc_train",
    # Test/developer-tooling support: the Windows short-path staging shim
    # (W2-01, issue #12). It is reached from five test targets and one
    # developer data-generation binary, and must never enter a runtime
    # closure. Keeping it out rests primarily on its enumerated visibility
    # list in tools/winstage/BUILD.bazel, which names neither root below;
    # this entry is defence in depth behind that, and makes W2-01's own
    # "Stop if" clause enforceable rather than merely stated.
    "//tools/winstage:winstage",
}
FORBIDDEN_BY_ROOT = {
    "//src/pmc_core:pmc_core": FORBIDDEN,
    "//src/pmc_agent:pmc_agent": FORBIDDEN - {"//src/pmc_agent:pmc_agent"},
}
TRAINING_NAMES = ("torch", "transformers", "peft", "trl", "unsloth")
RUNTIME_NAMES = ("langgraph", "lemonade")


def closure(label: str) -> set[str]:
    """Return a Bazel target's transitive labels.

    Args:
        label: Bazel label whose dependency closure should be queried.

    Returns:
        The labels in the target's transitive dependency closure.

    Raises:
        SystemExit: If the Bazel dependency query fails.
    """
    result = subprocess.run(
        ["bazel", "query", "--output=label", f"deps({label})"],
        check=False,
        capture_output=True,
        text=True,
        cwd=os.environ.get("BUILD_WORKSPACE_DIRECTORY"),
    )
    if result.returncode:
        print(result.stderr, file=sys.stderr)
        raise SystemExit(result.returncode)
    return set(result.stdout.splitlines())


def main() -> int:
    """Check core and agent closures and report their contents.

    Returns:
        Zero when both closures satisfy the dependency policy, or one when a
        forbidden dependency is found.
    """
    for label in ("//src/pmc_core:pmc_core", "//src/pmc_agent:pmc_agent"):
        labels = closure(label)
        print(f"{label} closure:")
        print("\n".join(sorted(labels)))
        forbidden = labels & FORBIDDEN_BY_ROOT[label]
        lowered = "\n".join(labels).lower()
        forbidden |= {
            name for name in TRAINING_NAMES + RUNTIME_NAMES if name in lowered
        }
        if forbidden:
            print(
                f"forbidden dependency closure entries: {sorted(forbidden)}",
                file=sys.stderr,
            )
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
