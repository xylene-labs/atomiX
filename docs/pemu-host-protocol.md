# axpe host port — frozen contract

[Design document](protocol-emulator.md) · [Board](boards/protocol-emulator.md) ·
[Workflow](workflow.md)

This is what makes a fabricated `axpe` reprogrammable, and it is the T1
capability the competition states outright: a packaged part must accept a
different protocol after fabrication. Firmware cannot load itself, so every
word below is fixed logic — `axpe_host.sv` and `axpe_imem.sv` — that firmware
can neither replace nor depend on.

Frozen as of 2026-09-18 by PE-14. Changing anything here is an interface
change: the assembler, the loader host, the FPGA bring-up in PE-09 and the
gate-level replay in PE-11 all speak it.

## Pins

The Tiny Tapeout harness gives 8 inputs, 8 outputs, 8 bidirectionals, `clk`,
`rst_n` and `ena`. The host takes three inputs and borrows one output.

| Pin | Direction | Use |
|---|---|---|
| `ui_in[0]` | in | `SCLK` |
| `ui_in[1]` | in | `MOSI` |
| `ui_in[2]` | in | `CS_n`, active low |
| `ui_in[3..7]` | in | firmware |
| `uo_out[0]` | out | `MISO` while `CS_n` is low, firmware's otherwise |
| `uo_out[1..7]` | out | firmware |
| `uio[0..7]` | bidir | firmware — the protocol pins |

**Every bidirectional pin stays with firmware.** UART, SPI and I2C need the
open-drain path and the loader does not, so the loader is kept off the pins the
mandatory protocols need. `MISO` only reaches the pad while `CS_n` is asserted,
so firmware keeps all eight output bits whenever the host is not mid-frame
rather than permanently losing one to a port used between programs.

`ena` is the harness's design-select and gates the core's reset with `rst_n`.

## Electrical and timing

SPI mode 0, MSB first: `MOSI` is sampled on the rising edge of `SCLK`, `MISO`
changes on the falling edge. `SCLK` is asynchronous to `clk` and is synchronized
on-chip with two flip-flops per pad, so:

> **`SCLK` must not exceed `clk/4`.**

That is a contract term, not an implementation detail. A faster host clock is
not slower loading, it is a program loaded with a wrong bit, which reads as a
firmware bug for a long time.

## Frames

One command per `CS_n` assertion. All fields are MSB first.

```
WRITE   cmd 0x01 | addr(8) | data(32)      48 clocks
READ    cmd 0x02 | addr(8) | 32 clocks     48 clocks, data on MISO
RUN     cmd 0x03                            8 clocks
STOP    cmd 0x04                            8 clocks
STATUS  cmd 0x05 | 16 clocks               24 clocks, status+uo_out on MISO
```

**When a frame takes effect:**

- `WRITE` commits on its final data bit. A frame the host abandons part way
  through never half-writes a word.
- `RUN` and `STOP` take effect when `CS_n` rises, provided the command byte
  completed. A frame abandoned mid-byte commits nothing, and the core never
  starts while the host still holds `CS_n` and is driving `MISO` onto a pad that
  running firmware owns.
- `READ` presents data from the clock after the address byte: the store is
  synchronous and the `clk/4` bound guarantees the word has arrived.

The address field is **eight bits**, matching the ISA's own branch target. A
store deeper than 256 words holds instructions nothing can jump to, so the host
cannot address them either — see [§2.1](protocol-emulator.md).

## Status

`STATUS` returns two bytes: flags, then the core's `uo_out` latch.

| Bit | Meaning |
|---|---|
| 0 | `running` — the core has been started and not stopped |
| 1 | `halted` — the core reached `HALT` |
| 2 | `fault` — the core refused an instruction |
| 3 | `refused` — a `WRITE` was rejected because the core was running |
| 4-7 | reserved, zero |

**Results come back through `uo_out`, not the register file.** Firmware
publishes with `POUT` and the host reads it in status. Adding a read port to
the register file would cost a mux on the datapath's critical read path for
something one instruction already does, and against a ceiling near 7,680
flip-flops the instruction is cheaper than the port. The cost is real and worth
stating: a halted program's registers are not visible to the host, so
gate-level debugging in PE-11 sees what firmware chose to publish.

## The sequence, and why it is a rule

```
STOP  →  WRITE × n  →  RUN  →  (firmware runs, HALT)  →  STATUS
```

The instruction store is **single port**, because the IHP SRAM macro is. There
is no cycle in which a fetch and a write can both happen, so writes are refused
while the core runs and the `refused` bit says so. A loader that arbitrated
instead would work in simulation and fail in silicon; one that dropped the
write silently would leave the host running the previous program and believing
it had loaded a new one.

`STOP` is also the reset: it clears the core's registers, flags, pads and
program counter, and `RUN` always starts at word 0. There is no separate reset
command, because a stopped core that kept its register state would need a second
control path and buy nothing the host can observe — `uo_out` survives `HALT`,
which is where the result is.

## What proves it

`make pemu-chip-check` elaborates `axpe_chip` once, loads one program over these
pins, runs it, then loads an unrelated program into that same design without
rebuilding it, and checks both against the golden model cycle for cycle. It also
writes and reads back a word, and proves a refused write was actually refused.

This is host simulation. It is not an FPGA result and not a silicon result, and
PE-02 has not yet shown that the 6×4 flow accepts the SRAM macro this store is
shaped for.
