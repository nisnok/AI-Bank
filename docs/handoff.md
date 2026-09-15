# same-session operator takeover and safe resume

Public demo commands now write organized bundles under `evidence/runs/<run-id>/`; see [evidence generation](evidence.md). Proof links below point to retained runs; original provenance is unchanged.

## Interactive demo

Install dependencies and Chromium as described in the root README, then run:

```sh
PLAYWRIGHT_BROWSERS_PATH="$PWD/.playwright" .venv/bin/python examples/run_handoff.py
```

No Gemini key or model calls are needed. Open the local operator-panel URL printed by the command in your browser. Keep that URL private while the run is active; its random path token grants control of this local demonstration.

1. Automation searches fictional member 48321 and encounters the existing unexpected supervisor-notice modal. The panel shows HUMAN_REQUIRED/PAUSED, the blocked step, reason, session identifier, and live normalized application text.
2. Click **Take control**, then **Acknowledge supervisor notice**, then **Hand back to automation**.
3. Automation freshly observes the page, verifies the notice is gone and the correct member is displayed, and continues. It enters 500.00, reaches review, and pauses because policy requires human authorization for final confirmation.
4. Inspect the review state. Click **Take control**, then **Confirm / Open Account — posts deposit**, then **Hand back to automation**.
5. Automation freshly observes the result and verifies account-opened state, requested member identity, and posted deposit. It skips the already completed confirmation, performs the remaining success checkpoint, and returns SUCCESS.
6. The live session remains available for 30 seconds after success. **Stop run** is available while a handoff is pending.

The application uses **one retained Playwright BrowserContext/Page**, opened once for the whole run. It is headless so unaudited native input cannot bypass the control lease. The panel is a real, minimal operator interface that reads live normalized state and issues supported semantic actions against that same page. It neither creates a second simulator browser/session nor reconstructs the workflow. Cookies, page state, and in-memory replay continuation remain alive throughout.

This implements the request's supported-action alternative to arbitrary native browser interaction. It does **not** capture every possible keyboard/mouse gesture or offer unrestricted remote browsing. The panel is intentionally limited to the two configured click operations; the controller additionally supports audited fill operations tested with fakes.

## Ownership and continuation

`SessionController` owns the retained Surface and a serialized control lease. `LeasedSurface` enforces the current actor on each operation. Lease changes and human action dispatch share the same lock, so transfer waits for an in-flight operation. Automation cannot click/fill/select/query through its port while HUMAN owns control. Operator actions are rejected while AUTOMATION owns control.

`HandoffManager` is separate from ReplayEngine:

- `resolve(artifact, step, result, inputs, evidence)` suspends on structured HUMAN_REQUIRED and waits for a verified handback.
- `take_control()` grants HUMAN ownership only at a pending handoff.
- `human_action(action_id, value=None)` resolves one configured semantic target uniquely, verifies preconditions, dispatches once, and records outcome.
- `handback()` returns ownership and wakes the suspended continuation.
- `cancel()` stops a pending run without pretending the checkpoint passed.
- `status()` returns transient operator-facing state.

ReplayEngine retains its original bound artifact, inputs, extracted outputs, evidence writer, run ID, and loop position on the suspended coroutine. No second execute call restarts the workflow.

Handoff states are AUTOMATION, HUMAN_REQUIRED, PAUSED, HUMAN_CONTROL, RESUMING, COMPLETED, and FAILED. Structured results include resume metadata, `handoff_occurred`, and `human_action_count`. Ordinary callers without a handoff handler still receive HUMAN_REQUIRED directly.

The default policy still blocks irreversible operations. This demo explicitly configures REQUIRE_HUMAN for final confirmation; it never grants automation ALLOW for that action. The existing unexpected supervisor-notice modal now has an acknowledgement button. No new financial workflow was invented.

## Safe handback

Resume plans are trusted application contracts separate from the capability. Templates are bound only in memory. They neither alter the capability nor create new learned steps.

Handback first performs a fresh Surface observation and rejects any remaining dialog. Then:

- **Completed step:** all declared completion checks AND the step's postcondition must pass. Output extraction steps cannot be skipped. The confirmation is skipped only after account-opened state, identity, and posted deposit are verified.
- **Blocked step still needed:** retry is allowed only for a read/reversible step blocked by ambiguity or a blocking dialog **before action dispatch**, and only after the retry checks pass. Normal resolution and policy run again.
- **Unrecognized state/advancement:** remain HUMAN_REQUIRED. There is no arbitrary forward jump or assumption that the operator fixed the workflow.

A handback before acting fails verification and leaves the execution suspended. The operator can take control again or stop. Failed resume never silently restarts the workflow.

Replay records `failure.action_attempted` to distinguish ambiguity before dispatch from ambiguity afterward. An uncertain irreversible timeout triggers outcome verification and then either continues from a verified outcome or requests human review. It never repeats the mutation, even if the artifact marked it repeatable. Ordinary bounded recoverable retries remain intact.

Human irreversible actions are marked attempted before dispatch; duplicate attempts are rejected even if the first result was uncertain. The operator must inspect state and hand back for verification. There is no “retry anyway” button.

## Evidence and actual acceptance run

For unattended acceptance:

```sh
PLAYWRIGHT_BROWSERS_PATH="$PWD/.playwright" .venv/bin/python examples/run_handoff.py --scripted
```

This driver exercises the operator controller against real Chromium and the real local simulator. It is an **automated operator simulation**, not a physical person's clicks. Records retain `actor=HUMAN` for the control role and explicitly identify `input_source=scripted_acceptance`. Interactive records use `input_source=operator_panel`. The real-browser test separately exercises the panel's HTTP endpoints.

The final actual run produced:

```text
HUMAN_REQUIRED: UNEXPECTED_BLOCKING_UI
acknowledge_notice: VERIFIED
HUMAN_REQUIRED: RISK_REQUIRE_HUMAN
confirm_account: VERIFIED
SUCCESS; handoff_occurred=true; human_action_count=2; model_calls=0
One simulator session; search=1; confirm=1; accounts_opened=1
Automation actions during each HUMAN lease: 0
```

Evidence: [retained replay handoff](../evidence/current/handoff/replay-handoff.json). The adjacent files contain the full timeline and action records.

- `metadata.json`: original capability identity and replay mode.
- `events.jsonl`: replay actions, handoff_requested, automation_paused, control_transferred, human_action, handback_requested, control_returned, resume_observation, resume_checkpoint_verified, resumed, final_result.
- `handoff-1.json`, `handoff-2.json`: structured HUMAN_REQUIRED results with step, reason, safe checkpoint IDs, and evidence reference.
- `human-action-1.json`, `human-action-2.json`: timestamp, actor/source, semantic action ID, run/session ID, redacted before/after state, verified condition IDs, outcome, and screenshot reference.
- `control-summary.json`: the stable session identifier, per-owner action counts, and checked zero-automation-action intervals.
- `result.json`: final SUCCESS with two operator actions and zero model calls.
- `screenshots/`: selected selectively-redacted captures around handoff, human actions, handback, and final state, plus an explicitly documented full-mask fallback.

Live page text is displayed locally in memory; it is not written into evidence. Typed values, member identity, deposit, cookies, raw URLs, credentials, and arbitrary selector text are excluded from action records. No hidden model reasoning exists on this path. Human action intent is persisted before dispatch; a process crash may leave intent without a completion record, which must be treated as uncertain.

Existing artifacts, including generated validated versions, remain unchanged. There is no automatic learning, artifact editing, or capability improvement promotion.

## Tests and architecture boundaries

```sh
.venv/bin/pyright
RUN_BROWSER_TESTS=1 PLAYWRIGHT_BROWSERS_PATH="$PWD/.playwright" .venv/bin/python -m pytest -q
```

Coverage includes policy and ambiguity escalation, ownership enforcement in both directions, in-flight lease serialization, redacted human fill/action records, valid/invalid handback, fresh observation, continuation without restart, no repeated human mutation, uncertain irreversible execution, post-dispatch ambiguity, business outcomes, ordinary recovery, and the evidence timeline.

The real-browser panel test preserves the original simulator session object through both handoffs, checks the final posted deposit, and verifies one search, one confirmation, and one new account. It also tests duplicate confirmation rejection and cross-origin request rejection.

Replay imports only its abstract handoff continuation port and domain services. Neither ReplayEngine nor the handoff/control layer imports Gemini, ModelClient, DiscoveryOrchestrator, or Playwright. Only the existing PlaywrightSurface adapter owns browser objects. Existing transitive dependency tests remain in force; capability schemas remain provider-independent.

## Deliberate limits

- The local random-token panel has basic loopback/Host/Origin checks, not production authentication, role management, or a network security boundary.
- Ownership is enforced through the supplied ports. Trusted Python code that deliberately accesses private underlying adapter state can bypass them; the application page is headless to prevent native operator bypass.
- Supported semantic operations are audited; arbitrary browser gestures, navigation, file uploads, and downloads are not provided.
- Only configured resume contracts are supported. Unknown states stay paused; complex cross-step advancement and output recovery are deferred.
- Resume conditions are separate UI reads, not an atomic financial transaction. The simulator is controlled and fictional; production freshness/reconciliation would need stronger application guarantees.
- Continuations are in memory. Process loss closes the browser and requires reconciliation; no durable resume, crash recovery, or persistent session service is implemented.
- Evidence is file-backed; new simulator screenshots use selective masking with conservative fallback. A browser failure during an action may leave only its pre-dispatch intent event.
- The automated acceptance run proves the mechanism; a person can exercise the interactive command above. No physical human participation is claimed.

[Multi-tenant reuse](tenants.md) provides locator-only tenant reuse separately. Capability health is implemented separately. Automatic healing, LLM repair, and distributed services remain out of scope.

[Capability health](health.md) now derives explainable assessments from replay evidence. [Automated evaluation](evaluation.md) adds controlled failure scenarios separately; automatic repair/healing remains unimplemented.

## Discovery integration

Discovery now calls `HandoffManager.resolve_discovery`, which delegates to the same internal pause/transfer/audit/checkpoint loop used by replay. It supplies a trusted discovery resume plan, not model-authored operator actions. The existing supervisor-notice action is reused. A no-action handback and a handback with incorrect member identity are rejected. Once verified, discovery makes a fresh observation/decision rather than retrying the suspended proposal. Non-interactive discovery may still stop cleanly on HUMAN_REQUIRED.

Human assistance is recorded separately and does not automatically enter a compiled capability. Control state remains in memory, and the total discovery deadline includes operator time. See [discovery demo commands](../README.md#discovery-time-intervention).
