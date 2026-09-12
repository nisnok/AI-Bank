# Tenant locator bindings

Both tenant binding files refer to the same generated `get_member_balance@1.0.0` and pin its normalized model digest.

- `bank_a/1.0.0.json`: explicit identity binding.
- `bank_b/1.0.0.json`: reviewed input/search/balance/identity/business-message locator translations.

These files contain no workflow steps, runtime member IDs, balances, approval flags, or risk overrides. The binder creates only an in-memory effective artifact. It never writes a second capability or modifies a generated version.

Change binding versions deliberately when locator configuration changes. Existing files are local trusted configuration, not signed approval records. Safe label drift uses a fallback already present in the unchanged Bank B binding.

See [the tenant reuse guide](../docs/tenants.md) for schema restrictions, examples, and actual evidence.
