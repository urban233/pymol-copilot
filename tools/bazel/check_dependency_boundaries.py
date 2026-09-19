# Copyright 2026 PyMOL Copilot contributors.
"""Check that runtime dependency closures remain free of training tools."""

import os
import subprocess
import sys


FORBIDDEN = {
    "//src/pmc_agent:pmc_agent",
    "//src/pmc_data:pmc_data",
    # src/pmc_train is out of the Bazel graph (.bazelignore) and can never
    # appear in a bazel query closure, so this label is inert by
    # construction. Kept so the entry regains meaning if the package ever
    # returns to the graph.
    "//src/pmc_train:pmc_train",
    # Test/developer-tooling support: the Windows short-path staging shim
    # (W2-01, issue #12). It is reached from five test targets and one
    # developer data-generation binary, and must never enter a runtime
    # closure. Keeping it out rests primarily on its enumerated visibility
    # list in tools/winstage/BUILD.bazel, which names neither root below;
    # this entry is defence in depth behind that, and makes W2-01's own
    # "Stop if" clause enforceable rather than merely stated.
    "//tools/winstage:winstage",
    # The sidecar executor's PyMOL-touching child (docs/master_plan.md item
    # 4). pmc_core.executor spawns it by module name
    # ("python -m pmc_sidecar.child"), never by import, so this package must
    # never enter pmc_core's or pmc_agent's own dependency closure -- only
    # pmc_server (which actually spawns the child process) depends on it.
    "//src/pmc_sidecar:pmc_sidecar",
}
FORBIDDEN_BY_ROOT = {
    "//src/pmc_core:pmc_core": FORBIDDEN,
    "//src/pmc_agent:pmc_agent": FORBIDDEN - {"//src/pmc_agent:pmc_agent"},
}
TRAINING_NAMES = ("torch", "transformers", "peft", "trl", "unsloth")
RUNTIME_NAMES = ("langgraph", "lemonade")
NAMES_BY_ROOT = {
    # pmc_core is the shared contract layer the in-PyMOL client imports, so
    # neither the training stack nor LangGraph orchestration may reach it.
    "//src/pmc_core:pmc_core": TRAINING_NAMES + RUNTIME_NAMES,
    # Per SPECIFICATION.md:656, the managed server is exactly where
    # LangGraph belongs. Only the training stack is forbidden here.
    "//src/pmc_agent:pmc_agent": TRAINING_NAMES,
}


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
        # Match against each label's repository/package identity (everything
        # before its first `:`), not the full label text. Otherwise a source
        # file inside an unrelated package's site-packages tree -- such as
        # langgraph/stream/transformers.py -- collides with a training-tool
        # name that was never actually a dependency.
        identities = "\n".join(lbl.split(":", 1)[0] for lbl in labels).lower()
        forbidden |= {
            name for name in NAMES_BY_ROOT[label] if name in identities
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
