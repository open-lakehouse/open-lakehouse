---
name: Bug report
about: Something broke. Help us reproduce.
title: "bug: <one-line summary>"
labels: bug
assignees: ''
---

## What broke

<!-- Describe the bug in one paragraph. What did you expect to happen, what actually happened? -->

## How to reproduce

```bash
# Exact commands you ran, in order
```

## Environment

- OS: <!-- macOS 14.5 / Ubuntu 24.04 / etc. -->
- Docker: <!-- output of `docker version --format '{{.Server.Version}}'` -->
- Branch / commit: <!-- output of `git rev-parse HEAD` -->

## Stack state at time of failure

<details>
<summary><code>./lakehouse status --json</code></summary>

```json
<!-- paste output here -->
```

</details>

<details>
<summary>Logs for the failing service</summary>

```
<!-- docker logs <container> --tail 100 -->
```

</details>

## Anything else
