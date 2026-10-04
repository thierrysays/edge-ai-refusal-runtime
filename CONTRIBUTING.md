# Contributing

## Every claim needs a test that fails without it

`docs/CONTROL_MAP.md` maps each control to a framework provision and to the test
that proves it. A change that adds a control adds a row; deleting a test deletes
the row above it.

Prefer **negative** tests. A gate that admits a good model proves nothing; a
gate that admits a bad one manufactures assurance. Roughly three quarters of
this suite asserts that something was refused.

## Assert on the world, not on the log

A governance test that only checks that something was logged is testing the
logger. The end-to-end tests assert on the simulated cell: the belt speed did
not change, the part was not diverted, the relay is open. Keep that habit, it
is what makes the suite survive a refactor of the journal format.

## Fail closed, and leave no override

There is no `--force` and there will not be one. A control that can be waived
under operational pressure will be waived under operational pressure, and a
system that logs its own non-compliance while continuing to run is worse than no
control at all.

Two defaults are load-bearing and should not be relaxed without an ADR:

- the stop channel starts **engaged**, and only a named operator releases it;
- the default confirmer is `AbsentOperator`, which **refuses**, an escalation
  nobody answers is a refusal, not a permission.

## Device profiles are conservative by construction

`hal/devices.py` declares what each board can actually enforce. A profile that
overstates a device is not a documentation error, it is a control failure: the
admission gate consults it. If you port a backend, change the profile only once
the capability is demonstrated on the bench, and say so in the build log.

## Decisions get recorded

A choice a competent engineer could reasonably have made differently gets an ADR
in `docs/adr/`, with its **cost** stated. ADRs are immutable; a reversal is a new
ADR. The uncomfortable ones: 0006 and 0007, are the ones that make the rest
credible.

## Before opening a pull request

```
make test        # 145 test functions, five layers, fast first
make demo        # 4 refusals, 1 escalation, a verifiable journal
make verify
```

CI runs the demonstration as part of the build. If the scenario stops refusing
what it is supposed to refuse, that is a failed build and not a changed demo.
