# Architecture

## The claim

Governance fails less often from absent frameworks than from absent
instrumentation. A written control is unfalsifiable: nothing in a running system
contradicts a policy document that says human oversight exists. A wired control
either fires or it does not, and the difference is observable by someone who was
not in the room.

Everything below follows from trying to make that difference observable.

## Five controls, in order

The order is load-bearing.

**1, Stop channel.** Evaluated before anything else. A system that reasons
about a request it is not allowed to perform is a system that will eventually
perform it: the reasoning path is where the exceptions accumulate. The channel
starts *engaged*, is composed disjunctively (any member engaged ⇒ stopped), and
can only be released by a named operator. Asymmetry is deliberate: engaging
costs nothing, releasing costs an identity.

**2, Policy.** Default deny. Every actuation request is matched against a rule
set held as data; the strongest matching effect wins (`deny` > `require_human` >
`allow`); no match is a refusal. The friction this produces (every new action
must be authorised before it can run) is the product, not a side effect.

**3, Human oversight.** Only for requests the policy escalated. Escalating
everything trains operators to approve everything, which is the standard way
Article 14 becomes a rubber stamp. The default confirmer is `AbsentOperator`,
which refuses: an escalation nobody answers is a refusal, not a permission.

**4, Budgets.** Checked immediately before the effect, because a budget checked
earlier can be overtaken by a concurrent spend. Budgets answer the question a
rule set cannot: not "is this action permitted?" but "is this the four-hundredth
permitted action in ninety seconds?".

**5, Actuation**, through the hardware abstraction layer, whose own relay check
is the final backstop: even with every software control bypassed, an open relay
means nothing moves.

Every step writes to the journal, including (especially) the refusals.

## The admission gate

Nothing runs until a signed model card has been evaluated against *this* device.

```
envelope ──▶ verify signatures ──▶ validate card ──▶ quorum & separation of duties
                                                  ──▶ validity window
                                                  ──▶ deployment target
                                                  ──▶ artefact digest binding
                                                  ──▶ controls enforceable here?
                                                          │
                                                    AdmissionDecision
                                                     (journalled, then raised)
```

Three properties are worth defending:

- **Fail-closed with no override.** There is no `--force`. A control that can be
  waived under operational pressure will be waived under operational pressure.
- **Decisions are data.** `admit()` returns a decision rather than raising, so
  refusals can be journalled and *counted*. Refusals you cannot count are
  refusals you cannot manage.
- **Reasons are plural.** All failed checks are reported at once. An operator
  who must re-run the gate five times to discover five problems will find a way
  around the gate.

The most consequential check is the last one. `effective_controls(card)` is the
**union** of the tier baseline and what the card requests (a provider cannot
opt out by omission), and it must be a subset of what the device declares it can
enforce. A high-risk card on a device with no stop channel is refused. That is
`test_runtime_without_stop_channel_cannot_run_a_high_risk_model`, and it is the
load-bearing test of the repository.

## The journal

An append-only JSON Lines file. Each entry commits to the hash of its
predecessor; periodic checkpoints commit a Merkle root over the entries since
the last checkpoint, signed by the device key.

```
entry(n).prev_hash = entry(n-1).hash
entry(n).hash      = H( schema, seq, timestamp, kind, prev_hash, body )
checkpoint.body    = { covers, entry_count, merkle_root, chain_head, signature }
```

What this buys: **tamper evidence**. An edited, deleted, or reordered record
breaks the chain at a determinate sequence number, and `verify_journal()` names
it. What it does not buy: **tamper resistance**, see ADR 0007.

Two design choices carry more weight than they look:

- **Digests, never payloads.** A technical file retained for ten years under the
  CRA cannot contain the images. Inference records carry input and output
  digests plus a three-field summary.
- **Merkle roots enable selective disclosure.** An auditor wants to prove that
  one inference happened, not to receive every inference the device ever made.
  An inclusion proof is logarithmic; handing over the file is not.

`verify_journal()` shares no state with `Journal`. That is the point: an auditor
runs it against a file, on their machine, with their copy of the trust store.

## Canonicalisation

Every hashed artefact is serialised through one module. Sorted keys, no
insignificant whitespace, UTF-8, non-finite floats rejected. A digest is only as
good as the determinism of the bytes beneath it, and a `NaN` that serialises
differently on two runtimes turns evidence into noise.

Time is injected. `FrozenClock` lets a scenario be replayed to byte-identical
artefacts, which is what makes the demonstration reviewable rather than
anecdotal.

## Hardware abstraction

Simulation first, boards second, for one engineering reason and one governance
reason.

*Engineering*: the controls could be written, tested, and deliberately broken
before any board was on the bench, which is how this repository was in fact
built.

*Governance*: a control whose correctness depends on the device it runs on
cannot be assessed once and deployed to a fleet. The device profile is data; the
control logic is identical everywhere.

Profiles are conservative by construction. `uno-r4-wifi` does not list
`inference_journal`, because a microcontroller with no durable append-only
storage cannot hold one, so a high-risk card is refused on it, and the test
suite pins that. A profile that overstates a device is not a documentation error
but a control failure.

## What an auditor does

```
gea demo --out ./run                                   # produce evidence
gea verify --journal ./run/journal.jsonl \             # check it, independently
           --trust-store ./run/trust-store.json
gea admit --envelope … --device uno-r4-wifi            # reproduce a refusal
gea policy --policy policies/inspection.json           # read the rules in force
```

Producing and checking are separate commands with separate inputs, so they can
be done by separate people. That separation is the only arrangement in which
verification means anything.
