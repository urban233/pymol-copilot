# How to contribute
### Development setup and workflow

See our [Development Setup](./docs/development_setup.md) guide for instructions
on how to set up your development environment.

### Code reviews

All submissions, including submissions by project members, require review. We
use [GitHub pull requests](https://docs.github.com/articles/about-pull-requests)
for this purpose.

Authors are encouraged to run a Gemini CLI code-review on their own PRs for self-review, and reviewers should use it to
augment their manual review process.
Every PR should be reviewed by at least one other author before being merged.

### Pull request guidelines
To help us review and merge your PRs quickly, please follow these guidelines.
PRs that do not meet these standards may be closed.

#### 1. Link to an existing issue
All PRs should be linked to an existing issue in our tracker. This ensures that
every change has been discussed and is aligned with the project's goals before
any code is written.

- **For bug fixes:** The PR should be linked to the bug report issue.
- **For features:** The PR should be linked to the feature request or proposal
  issue that has been approved by a maintainer.

If an issue for your change doesn't exist, we will automatically close your PR
along with a comment reminding you to associate the PR with an issue. The ideal
workflow starts with an issue that has been reviewed and approved by a
maintainer. Please **open the issue first** and wait for feedback before you
start coding.

#### 2. Keep it small and focused
We favor small, atomic PRs that address a single issue or add a single,
self-contained feature.

- **Do:** Create a PR that fixes one specific bug or adds one specific feature.
- **Don't:** Bundle multiple unrelated changes (e.g., a bug fix, a new feature,
  and a refactor) into a single PR.

Large changes should be broken down into a series of smaller, logical PRs that
can be reviewed and merged independently.

#### 3. Working with Dependent (Stacked) PRs
If you are working on a feature (**Feature B**) that depends on code in a PR that is still open (**Feature A**), do not wait for the first one to merge. Instead, "stack" your branches:

1.  **Branch off your first feature:** While on `feature-A`, run `git checkout -b feature-B`.
2.  **Open the second PR:** On GitHub, set the **base branch** of your `feature-B` PR to `feature-A` (instead of `main`).
3.  **When Feature A merges:**
  *   Switch to your local main: `git checkout main`
  *   Update it: `git pull origin main`
  *   Go to your second branch: `git checkout feature-B`
  *   Rebase onto main: `git rebase main`
  *   Force push the update: `git push origin feature-B --force-with-lease`
  *   **Crucial:** Go to the GitHub UI and change the PR base branch from `feature-A` to `main`.

#### 4. Use draft PRs for work in progress
If you'd like to get early feedback on your work, please use GitHub's **Draft
Pull Request** feature. This signals to the maintainers that the PR is not yet
ready for a formal review but is open for discussion and initial feedback.

#### 5. Update documentation
If your PR introduces a user-facing change (e.g., a new command, a modified
flag, or a change in behavior), you must also update the relevant documentation
in the `/docs` directory.

#### 6. Write clear commit messages and a good PR description
Your PR should have a clear, descriptive title and a detailed description of the
changes. Follow the [Conventional Commits](https://www.conventionalcommits.org/)
standard for your commit messages.

- **Good PR title:** `feat(cli): Add --json flag to 'config get' command`
- **Bad PR title:** `Made some changes`

In the PR description, explain the "why" behind your changes and link to the
relevant issue (e.g., `Fixes #123`).

#### 7. Merging and closing pull requests
When a main contributor of the project opens a pull request, it must be reviewed by another repository contributor. However, **only the person who opened the PR is allowed to merge or close it.**

The only exception to this rule is for pull requests opened by foreign (external) contributors. In those cases, a main contributor is allowed to review and merge the PR on their behalf once it meets all project standards.
