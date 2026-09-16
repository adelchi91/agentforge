# v1 golden fixtures

`examples_checksums.json` is a sha256 manifest of every file under the three
reference example trees (`examples/lagrangia/`, `examples/minimal/`,
`examples/codex-minimal/`) as they existed at the `agentforge-v1.1.0-pre-v2`
tag. It is regenerated only when a story deliberately changes those example
trees — never silently.

`tests/test_v1_examples_fixture.py` recomputes the checksums and fails if the
current tree drifts from this manifest without the manifest being updated,
so example-tree regressions during the v2 restructuring are caught even
though the trees are not covered by any other automated check.

To regenerate after an intentional change:

```bash
python3 - <<'PY'
import hashlib, json, pathlib
root = pathlib.Path(".")
targets = ["examples/lagrangia", "examples/minimal", "examples/codex-minimal"]
manifest = {}
for t in targets:
    base = root / t
    entry = {}
    for p in sorted(
        q for q in base.rglob("*")
        if q.is_file() and "__pycache__" not in q.parts
    ):
        entry[p.relative_to(root).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    manifest[t] = entry
pathlib.Path("tests/fixtures/v1/examples_checksums.json").write_text(
    json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
PY
```
