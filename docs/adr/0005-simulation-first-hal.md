# ADR 0005, Simulation first, boards second

**Status:** accepted · 2026-08-21

## Context

The target boards (UNO Q, VENTUNO Q, UNO R4 WiFi, Alvik, Nesso N1) were ordered
in June and August 2026. Waiting for hardware to start writing controls would
have produced controls shaped by whatever the first board happened to make easy.

## Decision

A hardware abstraction layer with a fully simulated inspection cell, plus device
*profiles* declaring what each board can actually enforce. Hardware backends
raise `NotPortedError` carrying a specific porting note rather than pretending.

## Consequences

The profiles turned out to be the most useful artefact. `uno-r4-wifi` cannot
hold the journal, so a high-risk card is refused on it, a governance
conclusion that fell out of writing the profile honestly, and that would have
been papered over had the code been written against the board first.

## Cost

The simulation is not the world. Timing, jitter, partial failure, and I2C bus
errors are all absent, and the energy models are declared estimates until a
bench measurement replaces them. Nothing here has been demonstrated on hardware.
