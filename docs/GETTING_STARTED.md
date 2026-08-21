# Getting started

**From a machine with nothing installed to a verified refusal, in about twenty
minutes.**

This guide assumes nothing. If you have never opened a terminal, never installed
Python and have never used git, you are the reader it was written for. Every
command is given in full, and where a step can go wrong the failure and its fix
are written next to it.

You do **not** need any hardware. Nothing here talks to a board.

If you already work in Python: `pip install -e ".[dev]" && make demo && make
verify` and skip to [What the demonstration proves](#what-the-demonstration-proves).

---

## Table of contents

- [Part 0 — What you are about to run, and why](#part-0--what-you-are-about-to-run-and-why)
- [Part 1 — Open a terminal](#part-1--open-a-terminal)
- [Part 2 — Install Python](#part-2--install-python)
- [Part 3 — Get the code](#part-3--get-the-code)
- [Part 4 — Make a virtual environment](#part-4--make-a-virtual-environment)
- [Part 5 — Install the project](#part-5--install-the-project)
- [Part 6 — Run the tests](#part-6--run-the-tests)
- [Part 7 — Run the demonstration](#part-7--run-the-demonstration)
- [What the demonstration proves](#what-the-demonstration-proves)
- [Part 8 — Verify the evidence yourself](#part-8--verify-the-evidence-yourself)
- [Part 9 — Break it on purpose](#part-9--break-it-on-purpose)
- [Part 10 — Look inside the evidence](#part-10--look-inside-the-evidence)
- [Part 11 — Try your own refusal](#part-11--try-your-own-refusal)
- [Troubleshooting](#troubleshooting)

---

## Part 0 — What you are about to run, and why

A simulated weld-inspection cell: a conveyor, a camera, a diverter that pushes
bad parts off the line, and a stop relay.

A model looks at each part and says *defect* or *no defect*. Something has to
decide whether the machine may act on that. This repository is that something,
and its output is a list of what it **refused**.

You will see five refusals. That is the point. Most governance dashboards count
what happened; almost none count what was prevented, which is the only figure
that distinguishes a control that works from one that is decorative.

Nothing here is a real model or a real machine. The simulation exists so the
controls could be built, tested, and deliberately broken before any hardware
arrived.

**Time:** about twenty minutes, most of it downloads.
**Cost:** nothing.
**Risk:** none. Everything happens in one folder you can delete afterwards.

---

## Part 1 — Open a terminal

A terminal is a window where you type commands instead of clicking.

**Windows** — press the Windows key, type `powershell`, press Enter.

**macOS** — press ⌘ + Space, type `terminal`, press Enter.

**Linux** — press Ctrl + Alt + T, or find "Terminal" in your applications.

You will see a prompt: some text ending in `>` or `$` or `%`. Commands go after
it. Type the command, press Enter, wait for the prompt to come back.

Throughout this guide, lines starting with `#` are comments — do not type them.

---

## Part 2 — Install Python

You need Python **3.10 or newer**. Check first — you may already have it.

```bash
python3 --version
```

On Windows, try this instead:

```powershell
python --version
```

If you see `Python 3.10.x` or higher, skip to Part 3.

If you see `command not found`, or a version below 3.10:

**Windows** — download from [python.org/downloads](https://www.python.org/downloads/).
Run the installer. **Tick "Add python.exe to PATH"** on the first screen; it is
easy to miss and everything afterwards fails without it. Close your terminal and
open a new one.

**macOS** — download from [python.org/downloads](https://www.python.org/downloads/)
and run the installer. Or, if you have Homebrew: `brew install python@3.12`.

**Linux (Debian/Ubuntu)** —

```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv git
```

Check again before continuing. You must see 3.10 or higher.

---

## Part 3 — Get the code

**Option A — with git** (better; you can update later with `git pull`):

```bash
git clone https://github.com/thierrysays/edge-ai-refusal-runtime
cd edge-ai-refusal-runtime
```

If `git` is not installed: `sudo apt install git` on Linux,
`brew install git` on macOS, or [git-scm.com/downloads](https://git-scm.com/downloads)
on Windows.

**Option B — without git:** open the repository page in a browser, click the
green **Code** button, choose **Download ZIP**, unzip it, then in the terminal
type `cd ` (with a space) and drag the unzipped folder onto the terminal window.
Press Enter.

Confirm you are in the right place:

```bash
ls          # Windows PowerShell: dir
```

You should see `README.md`, `pyproject.toml`, `src`, `tests`, `docs`.

---

## Part 4 — Make a virtual environment

A virtual environment is a private box for this project's dependencies, so it
cannot disturb anything else on your machine. It is one folder called `.venv`,
and deleting it undoes everything in this section.

```bash
python3 -m venv .venv
```

Now **activate** it:

```bash
# macOS / Linux
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1
```

Your prompt should now start with `(.venv)`. That is how you know it is on.

> **Windows: "running scripts is disabled on this system"**
> Run this once, then try activating again:
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
> ```

**You must activate the environment in every new terminal window.** If a command
later says "not found", this is almost always why.

---

## Part 5 — Install the project

```bash
pip install -e ".[dev]"
```

This downloads one runtime dependency — `cryptography`, which does the signing —
plus the test tools. One dependency is deliberate: every dependency is a
component someone must list in an SBOM and monitor for years, so dependency
weight is treated here as a governance property rather than only an engineering
one.

The last line should say `Successfully installed …`.

Check the command is available:

```bash
gea --version
```

---

## Part 6 — Run the tests

```bash
python -m pytest
```

Expect a row of dots and `... passed`. It takes about half a second.

Roughly three quarters of these tests assert that something was **refused**. A
gate that admits a good model proves nothing; a gate that admits a bad one
manufactures assurance. If any test fails, stop and see
[Troubleshooting](#troubleshooting) — do not continue.

---

## Part 7 — Run the demonstration

```bash
gea demo --out ./run --parts 16
```

You will see something like this:

```
  inferences   : 10
  requests     : 11
  allowed      : 7
  refused      : 4  <- the number that matters
  escalated    : 1 (1 approved)

  ✗ start_attempt_before_release       deny           stop channel engaged: stopped
  ✓ set_speed_within_envelope          allow          allow-safe-speed: …
  ✗ set_speed_outside_envelope         deny           deny-excessive-speed: …
  ✗ action_on_foreign_target           deny           deny-foreign-targets: …
  ✗ action_without_rationale           deny           deny-unexplained-requests: …
  ✓ divert_P0002                       require_human  escalate-low-confidence-diversion: …
  …
```

`✗` is a refusal. `✓` is an action that was allowed to proceed.

---

## What the demonstration proves

Read the four refusals, because each is a different kind of control.

**`start_attempt_before_release` — it cannot start itself.** The stop channel
boots *engaged*. The relay is de-energised at power-on, and releasing it takes a
named human. `""` and `"unattended"` are not names. A system that comes up
running is a system nobody authorised to be running.

**`set_speed_outside_envelope` — it cannot exceed what its paperwork claims.**
The model card declares an operating envelope. Above it, the model has no
validated accuracy, so the request is refused — by a rule, in a file, that a
risk officer can read.

**`action_on_foreign_target` — it cannot wander.** Authorised for the inspection
cell, so the paint booth is out of scope, however idle it looks.

**`action_without_rationale` — it cannot act unexplainably.** An action with no
stated reason cannot be reviewed after the fact, so it may not be taken at all.

And the escalation, `divert_P0002`: below the confidence threshold the runtime
will not decide alone. It asks a named human. **If nobody answers, that is a
refusal, not a permission** — the default operator refuses, deliberately.

The counts are fixed. If `refused` is ever not **4**, a control changed
behaviour — that is a broken build, not a changed demo.

---

## Part 8 — Verify the evidence yourself

The run wrote a journal. Check it:

```bash
gea verify --journal ./run/journal.jsonl --trust-store ./run/trust-store.json
```

```
journal verified: 34 entries, 1 checkpoint(s), head sha256:…
```

The point is *who* just checked it. `verify` shares no code and no state with
the thing that wrote the journal. It reads a file. An auditor can run it on
their own laptop, on a copy you emailed them, without your device and without
trusting it.

---

## Part 9 — Break it on purpose

This is the most useful two minutes in the guide.

```bash
make tamper
```

It re-runs the demo, edits one journal record — flipping a `deny` into an
`allow`, the edit somebody would actually want to make — and verifies again:

```
journal FAILED at seq 6: record hash does not match its content: the entry was altered
```

It names the sequence number. Each record contains the hash of the one before,
so changing any record breaks every link after it.

**What this does not do:** stop the tampering. It makes it *detectable*. Anyone
holding the device's signing key can rewrite the whole file consistently, and it
will verify. That limitation is written down in
[ADR 0007](adr/0007-external-anchoring-out-of-scope.md), and there is a test that
passes *on purpose* to prove it is still true.

Try one more:

```bash
# On macOS/Linux — empty the journal completely
: > ./run/journal.jsonl
gea verify --journal ./run/journal.jsonl
```

```
journal FAILED at ...: journal is empty: nothing to verify, and an empty file is
indistinguishable from an erased one
```

Erasing everything does not produce a clean bill of health. Saying "verified"
about an empty file would be exactly the manufactured assurance this project
exists to refuse.

---

## Part 10 — Look inside the evidence

```bash
ls ./run
```

Open `journal.jsonl` in any text editor. One JSON object per line.

Note what is **not** there: no images, no model weights, no payloads. Only
digests. A technical file retained for five years must not contain the pictures.

Two more things to try:

```bash
gea devices     # what each board can actually enforce
gea policy --policy policies/inspection.json    # the rules, as data
```

The `uno-r4-wifi` row in `gea devices` is the interesting one: it deliberately
lacks the inference journal, because a microcontroller has no durable
append-only storage. A high-risk model is therefore *refused* on it — an honest
"no" instead of a control that exists on paper only.

---

## Part 11 — Try your own refusal

Rules are data, not code, so you can change what is permitted without touching
Python.

```bash
cp policies/inspection.json policies/my-policy.json
```

Open `policies/my-policy.json` in a text editor. Find the rule named
`allow-safe-speed` and change its speed limit from `0.4` to `0.2`. Save.

```bash
gea policy --policy policies/my-policy.json
```

You have just done the thing the design is for: changed what a machine is
allowed to do, in a file, in a form a non-programmer can read and a risk officer
can diff against last month's version.

---

## Troubleshooting

**`command not found: python3`**
Windows uses `python`, not `python3`. If it still fails, Python is not on your
PATH — reinstall and tick "Add python.exe to PATH".

**`command not found: gea`**
The virtual environment is not active. Your prompt should start with `(.venv)`.
Re-run the activate command from Part 4.

**`No module named governed_edge_ai`**
Either the environment is not active, or Part 5 did not finish. Re-run
`pip install -e ".[dev]"` and read the last line.

> The package is `governed_edge_ai` while the repository is
> `edge-ai-refusal-runtime`. This is not a mistake — the identifiers are frozen
> so that a journal stays verifiable across a repository rename.
> → [ADR 0010](adr/0010-repository-name-and-frozen-schema-ids.md)

**`make: command not found`**
`make` is optional. Run the underlying command instead:
```bash
gea demo --out ./run --parts 16
gea verify --journal ./run/journal.jsonl --trust-store ./run/trust-store.json
```

**`Permission denied` on Windows when activating**
See the note in Part 4 about `Set-ExecutionPolicy`.

**The demo says something other than 4 refused**
That is a real finding, not a configuration problem. Please
[open an issue](https://github.com/thierrysays/edge-ai-refusal-runtime/issues)
with the full output.

**Starting over**
Delete the `.venv` folder and repeat from Part 4. Nothing else on your machine
was touched.

---

## Where to go next

| You are | Read |
|---|---|
| A risk or compliance reader | [Functional specification](FUNCTIONAL_SPEC.md), then [Control map](CONTROL_MAP.md) |
| An engineer | [Architecture](ARCHITECTURE.md), then [Technical reference](TECHNICAL_REFERENCE.md) |
| A security reviewer | [Threat model](THREAT_MODEL.md), then `tests/test_adversarial.py` |
| Wondering what it cannot do | [Threat model](THREAT_MODEL.md), residual risk R-1 to R-7 |
| Interested in the hardware | The sibling [`governed-edge-ai`](https://github.com/thierrysays/governed-edge-ai) repository, whose deployment guide takes you from bare metal to a wired rig |
