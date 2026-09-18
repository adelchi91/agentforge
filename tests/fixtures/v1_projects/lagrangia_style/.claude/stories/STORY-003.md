# STORY-003 — Define YAML Service Contract

## Status: READY FOR DEVELOPMENT
## Agent: architect-multiagents (model: opus)
## Phase: 2 — Extract dessia-tools + YAML contract
## Depends on: STORY-002 approved and merged
## Estimated effort: 1 session (2–3 hours)

---

## Context

After extracting `dessia-tools` into a standalone package (STORY-002), a formal YAML
service contract must be defined.

---

## Scope

**May touch:**
- `service_contract.yaml` (create at repo root)
- `dessia-tools/validate_contract.py` (create)

**Must NOT touch:**
- `dessiaworker/` — any file
- `dessia-memory/` — any file

---

## Acceptance Criteria

- `service_contract.yaml` exists at repo root and is valid YAML
- `dessia-tools/validate_contract.py` exits 0 when contract and implementations match

---

## Verification Commands

```bash
python3 -c "import yaml; yaml.safe_load(open('service_contract.yaml'))"
cd dessia-tools && python validate_contract.py
```

---

## Out of Scope

- Implementing new tools — contract describes existing tools only.

---

## Handoff

architect-multiagents session summary → tester → final-judge
