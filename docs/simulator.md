# legacy banking back-office simulator

The simulator is a separate, local Python package. It exercises the existing deterministic replay architecture; it is not discovery and never reads the Gemini API key. No additional dependencies, databases, frontend frameworks, or model integrations were added.

## Install and start

From the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
export PLAYWRIGHT_BROWSERS_PATH="$PWD/.playwright"
.venv/bin/python -m playwright install chromium
.venv/bin/python -m bank_simulator.server
```

Open **http://127.0.0.1:8765/** in a browser. The default bind address is loopback only. `--port 8766` changes the port; pass the same address to the replay runner's `--url` option. Use `127.0.0.1` consistently for the local origin check.

The employee portal starts a fresh fictional session. It has old-style tables, beveled controls, sparse/nested markup, a changing work area, and an iframe showing account-opening rules. The iframe is a reference pane; the adapter does not implement frame traversal to Surface. Forms have ordinary product attributes, not `data-testid` shortcuts. Most action controls have no IDs.

Each session stores its state in memory. Refreshing the landing page creates a fresh session; restarting the server clears all sessions. No credentials are required or collected.

| Member identifier | Fictional record | Savings balance | Opening eligibility |
|---|---|---|---|
| 48321 | Fictional Member ALPHA | 1420.75 | Eligible |
| 83921 | Fictional Member BETA | 807.20 | Eligible |
| 77777 | Fictional Member GAMMA | 65.00 | Ineligible |
| 99999 | No record | — | — |

All names, identifiers, balances, and receipts are synthetic training values.

## Run reviewed capabilities

In another terminal, from the same repository root:

```sh
export PLAYWRIGHT_BROWSERS_PATH="$PWD/.playwright"

# SUCCESS; exact Decimal output returned in memory.
.venv/bin/python examples/run_simulator.py get_member_balance --member-id 48321

# BUSINESS_OUTCOME / MEMBER_NOT_FOUND.
.venv/bin/python examples/run_simulator.py get_member_balance --member-id 99999

# BUSINESS_OUTCOME / MEMBER_INELIGIBLE.
.venv/bin/python examples/run_simulator.py prepare_new_savings_subaccount --member-id 77777

# Reaches review, then HUMAN_REQUIRED before the final confirmation is submitted.
.venv/bin/python examples/run_simulator.py prepare_new_savings_subaccount --member-id 48321 --initial-deposit 25.00

# Primary name no longer matches; the legitimate associated-label fallback succeeds.
.venv/bin/python examples/run_simulator.py get_member_balance --variant fallback
```

Add `--headed` to watch the browser. The runner closes the browser when replay returns, including HUMAN_REQUIRED; this older runner does not retain a handoff session. Use the [human handoff operator demo](handoff.md) for same-session takeover and resume. The CLI prints status, a safe result code, and the evidence path. It does not print input or output values. This is a demonstration command; business and failure statuses are in the structured result rather than separate process exit codes.

The runner loads `capabilities/simulator/get_member_balance.json` or `capabilities/simulator/prepare_new_savings_subaccount.json`, opens `PlaywrightSurface`, and calls `ReplayEngine.execute`. It uses no custom browser commands or selectors. The original `capabilities/get_member_balance.json` remains the deterministic replay fixture for the old demo and its existing tests.

## Deterministic faults

Select one fault per fresh session through `/?fault=FAULT_NAME`, or pass `--fault FAULT_NAME` to the runner. The label variation is independent: `/?variant=fallback` or `--variant fallback`.

| Mode | Injection point and behavior | Expected automation result |
|---|---|---|
| `SLOW_PAGE` | Search response delayed by 10,000 ms; configurable with server `--slow-ms` | Two bounded identity-wait attempts, then RECOVERABLE_ERROR; Search submitted once |
| `SESSION_EXPIRED` | Search returns an expired-employee-session state | Identity checkpoint cannot pass; bounded RECOVERABLE_ERROR |
| `PERMISSION_DENIED` | Opening operation returns a permission-denied message | Opening checkpoint times out; no review or confirmation |
| `UNEXPECTED_MODAL` | Member details open a native modal dialog requiring supervisor acknowledgement | Account preparation cannot click through; bounded RECOVERABLE_ERROR |
| `AMBIGUOUS_CONTROL` | Search form contains two equally plausible Search buttons | HUMAN_REQUIRED / AMBIGUOUS_TARGET; zero Search submissions |
| `STALE_MEMBER` | Search deliberately displays member 83921 regardless of request | Searching 48321 fails identity checks; no balance extraction |

Run each required fault:

```sh
.venv/bin/python examples/run_simulator.py get_member_balance --fault SLOW_PAGE
.venv/bin/python examples/run_simulator.py get_member_balance --fault SESSION_EXPIRED
.venv/bin/python examples/run_simulator.py prepare_new_savings_subaccount --fault PERMISSION_DENIED
.venv/bin/python examples/run_simulator.py prepare_new_savings_subaccount --fault UNEXPECTED_MODAL
.venv/bin/python examples/run_simulator.py get_member_balance --fault AMBIGUOUS_CONTROL
.venv/bin/python examples/run_simulator.py get_member_balance --member-id 48321 --fault STALE_MEMBER
```

Operational faults are not mislabeled as business outcomes. The simulator uses the existing checkpoint/timeout result semantics rather than adding application-specific error handling to ReplayEngine. MEMBER_NOT_FOUND and MEMBER_INELIGIBLE are recognized as normal business outcomes through stable visible messages.

The only intentional sleep is the server's configured slow-response fault. Browser tests do not use arbitrary sleeps: they use the existing semantic checkpoints. Test servers bind ephemeral ports and start serving from an already-bound socket.

## Identity, retries, and financial safety

`correct_member_loaded` compares a uniquely resolved **Loaded member identifier** with the validated `member_id` input. Expectations are bound in memory from the existing input-template syntax. The balance artifact checks identity while waiting for search, immediately before extraction, after extraction, and at the final checkpoint. A visible balance belonging to a different member cannot pass these checks. `STALE_MEMBER` deliberately leaves a plausible balance present to prove this.

Search and form submission replace the old work area with a processing state. A request generation counter discards superseded responses. The simulator renders identity and balance together from server-owned state. These controls supplement the capability's checks; they do not replace them.

Only the `verify_member` WAIT step is retried: two attempts of 750 ms, separated by 50 ms. Search is not resubmitted; irreversible confirmation is never retried. A local machine too slow for the reviewed deadlines will return a bounded error rather than guess or extract unverified data.

The account-opening capability checks identity, begins a reversible draft, fills the deposit, reaches review, checks the review member, and resolves **Confirm / Open Account** with risk IRREVERSIBLE. The runner configures the existing PolicyEngine to REQUIRE_HUMAN for that risk. The default PolicyEngine remains stricter and BLOCKs it. The final action receives no click under either policy. No human-approval bypass switch is exposed in the runner.

The final confirmation really creates one simulated sub-account, records a synthetic receipt, and posts the chosen initial deposit to that new sub-account. It does not debit the member's existing savings balance. The server rejects confirmation outside review and rejects duplicate confirmation. This is a training state transition, not a financial ledger. A single isolated integration test explicitly configures ALLOW to prove the final page is functional; all reviewer-facing preparation runs require human approval.

## Evidence and tests

```sh
.venv/bin/pyright
.venv/bin/python -m pytest -q
RUN_BROWSER_TESTS=1 .venv/bin/python -m pytest -q
```

Browser tests start their own local HTTP servers; a manually started server is not required. Existing FakeSurface tests and original browser tests remain. New tests cover seed balances, both business outcomes, identity mismatch, label fallback, ambiguity, bounded waiting, every required fault, review/deposit state, policy BLOCK/REQUIRE_HUMAN, and an explicitly allowed fictional confirmation. Domain tests cover invalid deposits, session isolation, and duplicate confirmation.

The ambiguity test asserts the server's search submission count is **zero**. The human-required test asserts stage REVIEW, the expected deposit, and **zero** confirmation submissions / opened accounts. The stale-member test asserts no extract action occurred. Server counters are inspected directly in the in-process test fixture; there is no exposed debug/control endpoint used by replay.

Actual runs write existing evidence bundles under `evidence/<run_id>/`: metadata, JSONL events, final result, and masked screenshots. Locator attempts, successful strategy indices, quality, conditions, retries, and policy decisions remain inspectable. Runtime values, bound expectations, and exception messages remain excluded. The simulator privacy profile selectively masks sensitive values while preserving workflow layout. Unknown/incomplete profiles fall back to full masking; per-image manifests record the policy. No evidence is fabricated. The curated acceptance archive selects representative actual captures.

## Files and interface changes

- `src/bank_simulator/domain.py`: typed fictional records, session transitions, counters, deposit validation.
- `src/bank_simulator/views.py`: HTML shell, forms, reference frame, CSS, and small submission script.
- `src/bank_simulator/server.py`: local HTTP server and test lifecycle helper.
- `capabilities/simulator/*.json`: reviewed balance and preparation workflows.
- `examples/run_simulator.py`: deterministic replay CLI using the existing Surface and policy.
- `tests/test_simulator_domain.py`, `tests/test_simulator_browser.py`: domain and real-browser coverage.
- Existing `models.py`, `templates.py`, and `replay.py`: validate/bind input references in condition expectations, using the same restricted template language already used for fill actions.

Surface, PlaywrightSurface, LocatorResolver, PolicyEngine, and the evidence API are unchanged. Replay depends only on domain services and Surface. Existing architecture tests still enforce that its transitive imports contain no Playwright or LLM SDK, that artifacts import only the standard library/Pydantic, and that Playwright imports remain isolated to the adapter.

## Deliberate simulator limits

This server is only for local training: it has no real authentication, durable ledger, TLS, session expiry clock, cleanup scheduler, or restart recovery. Sessions are retained until process exit. Faults are selected at session creation, not injected randomly. The threaded server intentionally favors transparency over production hosting features.

The reference iframe is meaningful to an employee but is not an automated transaction frame. General frame traversal remains out of scope. Historical screenshots are fully masked; new simulator captures use selective redaction with a full-mask fallback (see [acceptance](acceptance.md)). Application/version compatibility metadata remains descriptive. Operational faults use checkpoint errors rather than bespoke session/modal classifications. Initial-deposit comparison against the review UI is covered by the controlled simulator's server state and tests; the artifact verifies the review page and member, not an independent numeric deposit comparison. A real financial workflow should add that comparison and stronger freshness/transaction binding before deployment.

Discovery, compilation, takeover, tenant bindings, health and evaluation are separate layers described in the root README. The simulator does not invoke those layers. Automatic healing is not implemented.

The handoff workflow makes the existing supervisor-notice modal acknowledgeable and adds a semantic posted-deposit value for verified handback. The dedicated handoff demo performs the human confirmation through its audited operator controller; the original preparation runner retains its stop-before-confirmation behavior.

Tenant support provides independent `tenant=bank_a|bank_b` and `drift=none|label|structural|ambiguous` simulator parameters, plus visible product/version identity. Both tenants share the existing business domain. See [the tenant guide](tenants.md) for the generated-capability replay command.
