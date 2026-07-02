# STORY-003 — Define YAML Service Contract

## Status: READY FOR DEVELOPMENT
## Agent: architect-multiagents (model: opus)
## Phase: 2 — Extract dessia-tools + YAML contract
## Depends on: STORY-002 approved and merged
## Estimated effort: 1 session (2–3 hours)

---

## Context

After extracting `dessia-tools` into a standalone package (STORY-002), a formal YAML
service contract must be defined to describe the interface between MCP tools and the
LangGraph agents. This contract becomes the authoritative source of truth for which
tools exist, what their input schemas are, and what output types they produce.

Both the tool-serving side (`dessia-tools`) and the consuming side (`dessia-multiagents`)
will validate against this contract at startup. The contract prevents silent drift between
tool implementations and agent expectations.

**Architecture reference:** `service_contract.yaml` at repo root. Describes the canonical
list of available MCP tools, their JSON Schema input definitions, and expected output types.
The `dessia-tools/validate_contract.py` script validates that actual tool implementations
match the contract. Consumers validate on import using `dessia_tools.contract.validate()`.

---

## Scope

**May touch:**
- `service_contract.yaml` (create at repo root)
- `dessia-tools/validate_contract.py` (create)
- `dessia-tools/tests/test_contract.py` (create)
- `dessia-tools/dessia_tools/contract.py` (create — exposes `validate()`)

**Must NOT touch:**
- `dessiaworker/` — any file
- `dessia-memory/` — any file
- `code-explorer/` — any file
- `dessia-multiagents/` — any file
- Any existing tool implementation files in `dessia-tools/` (no behaviour changes)

---

## Acceptance Criteria

- `service_contract.yaml` exists at repo root and is valid YAML
- Contract defines at minimum: `name`, `description`, `input_schema` (JSON Schema),
  `output_type` for each tool
- `dessia-tools/validate_contract.py` exits 0 when contract and implementations match
- `dessia-tools/validate_contract.py` exits 1 and prints a diff when they diverge
- `dessia_tools.contract.validate()` is importable and callable
- All existing `dessia-tools` tests continue to pass
- New `test_contract.py` tests cover: valid contract loads, divergence detection

---

## Verification Commands

```bash
# Validate YAML syntax
python3 -c "
import yaml
with open('service_contract.yaml') as f:
    contract = yaml.safe_load(f)
print(f'PASS: valid YAML — {len(contract[\"tools\"])} tools defined')
"

# Run the contract validation script
cd dessia-tools && python validate_contract.py
echo "Exit code: $?"

# Run existing and new tests
cd dessia-tools && python -m pytest tests/ -v --tb=short

# Verify contract lists all tools (spot-check)
python3 -c "
import yaml
contract = yaml.safe_load(open('service_contract.yaml'))
tools = [t['name'] for t in contract['tools']]
print(f'Tools in contract: {tools}')
required_fields = {'name', 'description', 'input_schema', 'output_type'}
for t in contract['tools']:
    missing = required_fields - set(t.keys())
    if missing:
        print(f'FAIL: tool {t[\"name\"]} missing fields: {missing}')
        exit(1)
print('PASS: all tools have required fields')
"

# Verify validate() is importable
cd dessia-tools && python -c "from dessia_tools.contract import validate; print('PASS: contract.validate() importable')"
```

---

## Out of Scope

- Implementing new tools — contract describes existing tools only
- Changing tool implementations — contract must match current behaviour exactly
- Consumer-side validation in `dessia-multiagents` — that is Phase 4 (STORY-007) work
- Publishing `dessia-tools` to PyPI — that is Phase 5 work
- Defining versioning or changelog for the contract — keep it simple for now

---

## Handoff

architect-multiagents session summary → tester → final-judge
