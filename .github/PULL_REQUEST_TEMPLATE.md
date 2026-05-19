<!-- Thanks for opening a PR. Keep it focused: one PR = one purpose. -->

## What's in this PR

<!-- 1-3 sentences. What changed and why. The diff shows _what_; this should explain _why_. -->

## Type

- [ ] Bug fix
- [ ] Feature
- [ ] New demo (`demos/<name>/`)
- [ ] Docs / skill update
- [ ] CI / build / chore

## How I tested this

<!-- Concrete commands you ran. "make test" doesn't count — paste the commands. -->

```bash
# e.g.
./lakehouse setup
./lakehouse start all
./lakehouse status --json | jq '.all_healthy'   # → true
poetry run pytest tests/ --ignore=tests/integration -v
```

## Scope checklist

- [ ] No JDBC catalog references added (Unity Catalog OSS is the only catalog mode).
- [ ] No Spark 4.0 references added (Spark 4.1 only).
- [ ] Connect-first transport preserved (no hardcoded `spark://master:7078` in client code that should use `sc://`).
- [ ] `.env`, `*.conf`, `*.tfvars`, JKS/PEM files not committed.
- [ ] Pre-commit hooks pass locally (`pre-commit run --all-files`).
- [ ] If this touches `.claude/skills/`, the frontmatter `description:` is updated to reflect the change.
- [ ] If this adds a demo, `demos/<name>/README.md` follows the five-section contract.

## Linked issues

<!-- Closes #N -->
