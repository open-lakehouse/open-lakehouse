---
name: Demo proposal
about: Propose a new demo or fill one of the existing placeholders.
title: "demo: <demo-name>"
labels: demo
assignees: ''
---

## Demo name

<!-- e.g. realtime-mode, or a brand-new slot like spark-ml-tracking -->

## Slot

- [ ] Filling an existing placeholder: `demos/<existing-name>/`
- [ ] Proposing a new slot under `demos/`

If proposing a new slot, justify why it doesn't fit an existing one. We keep the demo set small on purpose.

## Demo contract

Following [`demos/_template/README.md`](../../demos/_template/README.md):

### Purpose

<!-- One sentence. What concept does this demo illustrate? -->

### Prereqs

<!-- Which services must be running? Transport (Connect / spark-pipelines / local)? -->

### Run

<!-- Outline the commands an LLM or human will execute. Detailed write-up goes in the demo README. -->

### Expected output

<!-- Concrete success criteria: tables created, metrics logged, exit codes. -->

### Teardown

<!-- How to remove all demo artifacts. Must be idempotent. -->

## Why this demo matters

<!-- Who is the audience? What story does this tell that the existing demos don't? -->
