# Control map

Each row is a claim. Each claim has a test. Deleting the test deletes the claim.
That is the whole discipline this document exists to enforce.

Run `python -m pytest` to re-establish every row below.

## Admission

| # | Control | Refuses | Framework | Implementation | Test |
|---|---|---|---|---|---|
| A1 | Signed model card required | An unsigned or unknown-key card | AI Act Annex IV; ISO 42001 §8.2 (AI system record) | `registry/signing.py` | `test_unknown_signing_key_is_refused` |
| A2 | Signature binds to the card | A signature transplanted from another card | ISO 27001 A.8.24 | `to_be_signed()` binds card digest + key id + time | `test_signature_cannot_be_transplanted_between_cards` |
| A3 | Tamper on the card breaks admission | The risk-tier downgrade attack | AI Act Art. 9 (risk management) | `verify_envelope()` | `test_tampered_card_breaks_the_signature` |
| A4 | Separation of duties | A high-risk model signed only by its builder | COBIT EDM01; ISO 27001 A.5.3 | `TIER_QUORUM`, role resolved from the trust store | `test_high_risk_needs_two_distinct_roles` |
| A5 | Quorum counts distinct roles | Two signatures from the same role | ISO 27001 A.5.3 | `verify_envelope()` de-duplicates key ids | `test_duplicate_signature_from_one_key_does_not_inflate_the_quorum` |
| A6 | Revocation is honoured | A card signed by a revoked key | NIST SP 800-57 | `TrustedKey.usable_at()` | `test_revoked_key_is_refused` |
| A7 | Artefact binding | Weights that are not the weights the card describes | ISO 42001 §8.3; SLSA provenance | `digest_file()` compared to `artifact_digest` | `test_artefact_digest_mismatch_is_refused` |
| A8 | Unchecked is not passed | A card admitted without the artefact ever being checked |, | absent artefact is a *failure*, not a skip | `test_absent_artefact_is_a_failure_not_a_skip` |
| A9 | Validity window | An expired card | AI Act Art. 17 (QMS) | `valid_from` / `valid_until` | `test_expired_card_is_refused` |
| A10 | Deployment target | Running a model on a device it was not authorised for | ISO 42001 §8.4 | `deployment.targets` vs device class | `test_wrong_device_class_is_refused` |
| A11 | Controls must be enforceable | A high-risk model on a device with no stop channel | **AI Act Art. 14** | `effective_controls()` ⊆ `RuntimeContext.available_controls` | `test_runtime_without_stop_channel_cannot_run_a_high_risk_model` |
| A12 | Baseline cannot be opted out of | A card asking for fewer controls than its tier requires | AI Act Art. 9 | `effective_controls()` takes the **union** | `test_admits_a_properly_signed_high_risk_model` |
| A13 | Refusals are recorded | A refusal that leaves no trace | AI Act Art. 12 | `AdmissionDecision.to_record()` journalled before raising | `test_refused_admission_is_still_journalled` |

## Journal

| # | Control | Refuses / detects | Framework | Implementation | Test |
|---|---|---|---|---|---|
| J1 | Hash chaining | An edited record | ISO 27001 A.8.15; AI Act Art. 12 | `Entry.compute_hash` over the canonical record | `test_edited_entry_is_detected` |
| J2 | Chain continuity | An edited record whose own hash was recomputed | ISO 27001 A.8.15 | `prev_hash` continuity | `test_edited_entry_with_recomputed_hash_still_breaks_the_chain` |
| J3 | Sequence integrity | A deleted or reordered record | ISO 27001 A.8.15 | monotonic `seq` check | `test_deleted_entry_is_detected`, `test_reordered_entries_are_detected` |
| J4 | Signed checkpoints | Silent truncation of committed history | ISO 27001 A.8.15 | Merkle root + Ed25519 device signature | `test_truncation_is_detected_only_against_a_checkpoint` |
| J5 | Attribution | A checkpoint from an unknown device | NIST SP 800-57 | trust-store lookup at verification | `test_checkpoint_signed_by_an_unknown_key_is_refused` |
| J6 | Fail-closed resume | Appending to a journal that already fails verification | ISO 27001 A.8.15 | `Journal._resume()` | `test_reopening_a_broken_journal_refuses_to_append` |
| J7 | Closed record vocabulary | A record kind nobody can report on | AI Act Art. 12 | `KINDS` | `test_unknown_record_kind_is_rejected_at_write_time` |
| J8 | Independent verification | Evidence only its author can check | ISO 42001 §9.2 | `verify_journal()` shares no state with `Journal` | `test_demo_then_independent_verify` |
| J9 | Retention discipline | A ten-year technical file full of payloads | CRA Annex VII (10 years); GDPR Art. 5(1)(c) | digests only, never payloads | `test_journal_records_carry_no_payload` |
| J10 | Selective disclosure | Proving one event by disclosing all of them | GDPR Art. 5(1)(c) | Merkle inclusion proofs | `test_inclusion_proof_round_trips` |

## Policy

| # | Control | Refuses | Framework | Implementation | Test |
|---|---|---|---|---|---|
| P1 | Default deny | Any action no rule authorises | NIST AI RMF MANAGE 2.2 | `PolicyEngine.decide()` | `test_empty_match_is_deny` |
| P2 | Deny-overrides | An allow rule that contradicts a deny rule | XACML combining algebra | `strongest()` | `test_deny_overrides_allow` |
| P3 | Escalation ranks above allow | An allow that bypasses a required escalation | AI Act Art. 14 | `strongest()` | `test_require_human_overrides_allow_but_not_deny` |
| P4 | Rules are data | A control an auditor cannot diff | COBIT MEA02; ISO 42001 §7.5 | JSON rule sets in `policies/` | `test_shipped_inspection_policy_loads_and_is_default_deny` |
| P5 | Rules must explain themselves | An unexplained refusal (which gets overridden) | ISO 42001 §7.4 | `because` is mandatory, ≥ 8 chars | `test_invalid_policies_fail_at_load[…explain]` |
| P6 | Typos fail loudly | A misspelt operator that silently never fires |, | eager operator validation at load | `test_invalid_policies_fail_at_load[…unknown operator]` |
| P7 | No accidental coercion | `True < 1.0` evaluating as a numeric comparison |, | booleans excluded from numeric comparison | `test_boolean_is_not_a_number` |
| P8 | Operating envelope | Speeds outside the card's validated range | AI Act Art. 15 (accuracy/robustness) | `deny-excessive-speed` | `test_speed_outside_the_declared_envelope_never_reaches_the_device` |
| P9 | Scope containment | Actions on systems this runtime was not authorised for | ISO 27001 A.8.2 | `deny-foreign-targets` | `test_foreign_targets_are_refused` |
| P10 | Reviewability | An action with no stated rationale | ISO 42001 §9.2 | `deny-unexplained-requests` | `test_an_unexplained_action_is_refused` |

## Oversight

| # | Control | Refuses | Framework | Implementation | Test |
|---|---|---|---|---|---|
| O1 | Machine cannot start itself | An autonomous cold start | **AI Act Art. 14(4)(e)** | composite channel starts engaged | `test_the_cell_cannot_start_itself` |
| O2 | Release requires a named human | An anonymous or unattended release | AI Act Art. 14 | `release(operator_id)` rejects `"unattended"` | `test_release_requires_a_named_operator` |
| O3 | Deadman | Continuing after the supervisor stopped answering | IEC 61508 fail-safe | `HeartbeatStopChannel` engaged by default | `test_heartbeat_channel_starts_engaged` |
| O4 | Independent channel | A stop that depends on the software being stopped | AI Act Art. 14 | `HardwareStopChannel` reads the relay | `test_hardware_channel_follows_the_relay` |
| O5 | Monotonic composition | A channel that vetoes another channel's stop | IEC 61508 | disjunctive `CompositeStopChannel` | `test_adding_a_channel_can_only_make_stopping_easier` |
| O6 | Silence is refusal | An unanswered escalation treated as approval | AI Act Art. 14 | `AbsentOperator` is the default confirmer | `test_absent_operator_refuses` |
| O7 | Selective escalation | Escalating everything, training operators to approve everything | AI Act Art. 14 | only `require_human` decisions escalate | `test_low_confidence_diversion_requires_a_human_and_is_refused_when_absent` |
| O8 | Machine may not clear its own fault | Autonomous restart after a self-declared fault | ISO 12100 §6.2.11 | `escalate-resume` + stop-first ordering | `test_the_machine_may_not_clear_its_own_fault` |

## Budgets

| # | Control | Refuses | Framework | Implementation | Test |
|---|---|---|---|---|---|
| B1 | Allocation is finite | Unbounded repetition of legitimate actions | NIST AI RMF MANAGE 2.3 | `BudgetLedger` | `test_budget_exhaustion_stops_the_cell` |
| B2 | Undeclared resources | An agent inventing a resource name and spending freely |, | unknown kind → refusal | `test_undeclared_budget_is_refused` |
| B3 | Atomicity | A partial spend leaving a ledger that does not reconcile |, | `consume_many()` all-or-nothing | `test_consume_many_is_all_or_nothing` |
| B4 | Exhaustion stops | Degrading gracefully past the allocation | AI Act Art. 14 | exhaustion engages the stop channel | `test_budget_exhaustion_stops_the_cell` |
| B5 | Independent dimensions | Energy spent under cover of an action count | Green Software SCI | separate limits per kind | `test_energy_budget_is_enforced_separately` |

## Transparency

| # | Control | Refuses | Framework | Implementation | Test |
|---|---|---|---|---|---|
| T1 | Machine-readable marking | Unmarked synthetic output | **AI Act Art. 50(2), applicable since 2 Aug 2026; grace period to 2 Dec 2026 for systems already on the market before that date** | `OutputMarker.mark()` | `test_marking_binds_the_output` |
| T2 | Marking is checkable | A marking nobody downstream can verify | AI Act Art. 50 | `verify_marking()` | `test_marking_does_not_validate_a_different_output` |
| T3 | Provenance without disclosure | Having to publish the input to prove the provenance | GDPR Art. 5(1)(c) | manifest carries digests only | `test_manifest_carries_no_payload` |
| T4 | Human-readable disclosure | A marking only a machine can read | AI Act Art. 50 | `disclosure_text` from the card | `test_marking_binds_the_output` |

## Claims deliberately **not** made

| Not claimed | Why | Reference |
|---|---|---|
| Tamper resistance | Hash chains give evidence, not resistance | [ADR 0007](adr/0007-external-anchoring-out-of-scope.md) |
| Hardware root of trust | Keys sit in the clear on a Linux SBC | [ADR 0006](adr/0006-no-hardware-root-of-trust.md) |
| Measured energy figures | Every `energy_model` is declared `estimate` until a bench measurement replaces it | `hal/devices.py` |
| Conformity assessment | Nothing here certifies anything under any regime | README |
| Model quality | `SimulatedModel` is a stand-in, not a detector | `hal/sim.py` |
