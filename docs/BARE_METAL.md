# Bare metal

From an unboxed Arduino UNO Q to a refusal you can watch happen, with a relay
that drops out when the process dies. [Getting started](GETTING_STARTED.md)
comes first and runs entirely in simulation; this guide assumes you have done
that and now want the stop channel on hardware.

**Nothing in this repository has run on hardware. Every step below is
untested.** It is written ahead of the bench so that the first session has a
plan to disagree with, and each step names what would prove it wrong. When a
step is performed for real it gets corrected here, and the correction goes in
`docs/BUILD_LOG.en.md` and `docs/BUILD_LOG.fr.md`.

The claim this guide exists to test is the one the whole repository rests on:
that a killed Python process leaves the machine stopped rather than running.
Until that is observed, `HardwareStopChannel` is an argument, not a control.

## Safety

The Modulino Latch Relay switches real loads. If the load is mains voltage,
stop and involve someone qualified. Everything here is low-voltage DC, driving
a lamp or a small motor from a bench supply, where the worst outcome of a
mistake is a dead board.

Power down before changing wiring. Assume the relay is in the state you did not
expect, and check it with a meter before touching the load side.

## What you need

| Item | Why |
|---|---|
| Arduino UNO Q 4 GB | Debian on eMMC, so it can hold the journal and run this package unchanged. |
| Modulino Latch Relay | The stop channel. Bistable, so it keeps its state without power. |
| Qwiic cable | I2C to the relay, no soldering. |
| USB-C supply, 45 W or better | An undersized supply browns the board out, which looks exactly like a software fault. |
| A DC load and its own supply | A lamp is ideal: you can see the state from across the room. |
| A second machine | To hold the shell session, and to verify the journal independently, which is the point of the journal. |

## Step 1. Boot the board and find it

```bash
ping arduino.local
ssh arduino@arduino.local
```

If `.local` resolution fails, take the address from the router, or connect a
monitor and keyboard and run `ip addr`.

**What would prove this step wrong:** the board enumerating only as a serial
device, which means the image is the microcontroller variant rather than the
Linux one.

## Step 2. Record what the image actually is

```bash
cat /etc/os-release
python3 --version        # 3.10 or higher, or the package will not install
uname -a
df -h /
```

Write these down. They belong in the build log entry for the session, because
the first hardware result is only interpretable against the image that produced
it.

## Step 3. Install the package

```bash
sudo apt update && sudo apt install -y git python3-venv python3-dev
git clone https://github.com/thierrysays/edge-ai-refusal-runtime
cd edge-ai-refusal-runtime
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
gea devices
```

This repository has one runtime dependency, `cryptography`, and on an ARM board
pip may want to build it rather than fetch a wheel, which needs `python3-dev`
and takes a while. Without a network, build the wheel on a machine of the same
architecture and copy it over:

```bash
pip download cryptography -d wheels --platform manylinux2014_aarch64 \
  --only-binary=:all: --python-version 3.11
scp -r wheels arduino@arduino.local:~/
# on the board
pip install --no-index --find-links ~/wheels -e .
```

**What would prove this step wrong:** `gea devices` refusing to run at all,
which usually means the venv is not active or Python is older than 3.10.

## Step 4. Wire the relay and prove the bus sees it

Power off. Qwiic from the UNO Q to the Modulino Latch Relay. The load and its
supply go on the relay's switched side, never through the Qwiic cable.

```bash
sudo apt install -y i2c-tools
i2cdetect -y 1
```

The Modulino should appear at its documented address. If the address differs
because the node's jumpers are set, record the actual address: it belongs in
the porting note and in the build log.

**What would prove this step wrong:** an empty `i2cdetect` table, which means
I2C is disabled, the bus number is different on this image, or the cable is in
a chained port rather than the host port.

## Step 5. Write the relay backend

`hal/devices.py::UnoQDevice.porting_note` states the intent in three sentences.
The work is to replace `_UnportedRelay` with a real one that satisfies the same
contract:

```python
class ModulinoLatchRelay:
    """Energised means running. De-energised means stopped."""

    def energised(self) -> bool: ...
    def energise(self) -> None: ...
    def de_energise(self) -> None: ...
```

Three rules that the simulation cannot enforce for you:

1. **`energised()` reads the hardware**, not a cached flag. A cached flag turns
   a stop channel into a variable that agrees with itself.
2. **`de_energise()` is idempotent and must not raise.** It is called on the
   failure path, and a stop that can fail is not a stop.
3. **The de-energised state is the resting state.** If the coil has to be held
   to keep the machine stopped, the wiring is inverted and a power cut starts
   the machine.

`HardwareStopChannel` then takes that object and needs no changes:
`engaged()` is `not relay.energised()`, which is why the wiring polarity is a
governance property rather than an electrical detail.

## Step 6. The test the milestone is actually about

Start the runtime with the relay released and the load visibly on, then kill the
process the way an operating system kills a process that is misbehaving:

```bash
# in one session
gea demo --out ./run --parts 16
# in another, while it runs
kill -9 $(pgrep -f "governed_edge_ai.cli demo")
```

**Expected:** the lamp goes out at the moment of the kill, and stays out.

**What would prove the design wrong:** the lamp staying lit. That would mean the
relay holds its last state without anything asserting it, which is exactly what
a bistable relay does when it is wired as a *latch* rather than as a hold. If
that happens, the fix is not in Python. Either the relay is driven from a line
that goes low when the process dies, or a watchdog on the STM32U585 de-energises
it when the Linux side stops beating, which is `HeartbeatStopChannel` moved onto
the microcontroller.

Repeat with the harder cases, and record each result whether it flatters the
design or not:

- pull the Qwiic cable while running;
- pull the board's power while the load is on;
- suspend the process with `kill -STOP` rather than killing it;
- fill the eMMC so the journal cannot be written.

The last one matters more than it looks: a runtime that cannot journal must
refuse to act, and this is the first chance to find out whether it does.

## Step 7. Verify the evidence somewhere else

Copy the journal off the board and verify it on your own machine. That is the
whole argument for `verify_journal()` sharing no state with `Journal`:

```bash
scp arduino@arduino.local:~/edge-ai-refusal-runtime/run/journal.jsonl .
scp arduino@arduino.local:~/edge-ai-refusal-runtime/run/trust-store.json .
gea verify --journal ./journal.jsonl --trust-store ./trust-store.json
```

An auditor with these two files and this package can re-derive every hash
without the board being reachable, or existing.

## Step 8. Change the profile only if the bench earned it

`uno-q` already claims `stop_channel` in `hal/devices.py`. If the kill test
fails, that claim is wrong and the profile must lose it until a design that
passes is in place. Invariant 9 exists for exactly this moment: a profile is
changed after a demonstration, never in anticipation of one.

Write up what happened in both build logs, including the parts that did not
work. The first hardware session of a governance project is worth more as an
honest record than as a success.
