---
name: Feature request
about: Propose a new capability or behavior change.
title: "feat: <one-line summary>"
labels: enhancement
assignees: ''
---

## What problem does this solve?

<!-- Frame as a user need or a demo that this would unlock. Features without a clear demo path tend to get deferred. -->

## Proposed behavior

<!-- What should happen? Be specific — exact commands, expected output, affected files. -->

## What's the alternative if this doesn't ship?

<!-- Is there a workaround? Or does the demo platform have to compromise without this? -->

## Scope checklist

- [ ] This fits the demo-platform scope (Spark 4.1, Kafka, Airflow, Iceberg + Delta, Unity Catalog OSS, MLflow). If it requires another catalog backend, another Spark version, or production hardening, it likely belongs upstream in `lakehouse-stack`.
- [ ] This preserves the Connect-first transport.
- [ ] This doesn't reintroduce the JDBC catalog path.

## Anything else
