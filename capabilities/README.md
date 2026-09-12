# Capability artifacts

- `get_member_balance.json`: hand-authored Milestone 1 example.
- `simulator/*.json`: hand-authored Milestone 2 examples and fault-test contracts.
- `generated/<capability_id>/<version>/draft.json`: compiler output from an actual successful discovery.
- `generated/<capability_id>/<version>/validated.json`: immutable workflow snapshot with successful different-input replay provenance.
- `generated/<capability_id>/<version>/validations/*.json`: validation result references, without invocation values or balances.

The compiler never reads the manual examples. Existing paths remain stable for their demos/tests. New versions use exclusive file creation; changing a workflow requires a new version. See [the full-loop guide](../docs/compiler.md).
