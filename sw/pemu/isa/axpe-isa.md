# axpe instruction set architecture

Status: **draft**, PE-03. Normative for `components/pemu/axpe/`, the golden
model, and the assembler. Where this document and an implementation disagree,
this document is right and the implementation is a bug.

See [`docs/protocol-emulator.md`](../../../docs/protocol-emulator.md) for why
this machine exists and what it is budgeted at.

## 1. The central property

> **Every instruction occupies exactly the cycle count its encoding declares.**

This is the design's reason for existing, the thing PE-06 proves, and the
constraint every decision below answers to. It means the cycle cost of a
bit-banging loop is computable from the listing — a protocol's timing is read
off the assembly rather than measured on a scope.

Three instruction groups have a declared cost that is not a constant, and each
is still a closed form:

| Group | Occupancy, in cycles | Statically known? |
|---|---|---|
| Everything not below | `max(D, 1)` | Yes |
| `SHOUT` / `SHIN` / `SHIO` of `n` bits | `n × max(D, 1)` | Yes, `n` and `D` are both encoded |
| `WAITE` | `w`, where `1 ≤ w ≤ max(D, 1)` | Bounded, not exact |

**`D` is the cell duration, not an addition to a fetch cycle.** An instruction
written `D=434` occupies exactly 434 cycles, and every instruction occupies at
least one, so `D=0` is the cheapest instruction rather than an illegal one.

This is load-bearing, and an earlier draft got it wrong. Under a `1 + D` rule a
bit cell is `BAUD + 1` cycles, so a UART frame's edges land one cycle past every
multiple of the bit period and no firmware can correct it — the offset is in the
ISA. The C golden model caught it against the platform's waveform oracle, as a
constant two-cycle lag on every edge after the first. Under `max(D, 1)` the
edges land exactly, which is what
[`research/personalities/workloads/uart-tx-8n1.json`](../../../research/personalities/workloads/uart-tx-8n1.json)
requires.

`WAITE` is the single deliberate exception: waiting for an external edge is
data-dependent by nature. It is bounded by `D` as a hard timeout, it sets the
`T` flag when it hits that bound, and the proof uses the worst case. An
instruction stream containing no `WAITE` has an exact, computable duration.

`D` is the 16-bit delay field carried by **every** instruction. Uniformity is
deliberate: one delay counter in hardware, one rule in the proof, and no
instruction that secretly costs more than it says.

## 2. Machine state

| State | Width | Notes |
|---|---|---|
| `PC` | `clog2(IMEM_WORDS)` | Program counter, word-addressed |
| `R0`–`R7` | 16 | General registers |
| `STACK` | 4 × `clog2(IMEM_WORDS)` | Call stack; `CALL` pushes, `RET` pops |
| `SHREG` | 16 | Shift engine register, aliased onto a named `Rn` per instruction |
| `SHCFG` | 15 | Shift engine wiring, see §5 |
| `PDIR` | 8 | `uio` direction, 1 = drive |
| `PDRN` | 8 | `uio` open-drain mask, 1 = open-drain |
| `Z`, `C`, `T` | 1 each | Zero, carry, timeout |

`IMEM_WORDS` is a profile knob, not a constant. Overflowing an 8-bit branch
target is an assembler error, not a silent truncation.

### Pins

The Tiny Tapeout harness supplies 8 inputs, 8 outputs and 8 bidirectional pins.
`axpe` maps them by role:

- `uio[7:0]` — the **protocol group**. Per-pin direction (`PDIR`) and open-drain
  (`PDRN`). Everything that needs to be driven and sampled lives here.
- `uo_out[7:0]` — output only, written by `POUT`. Chip selects, status, debug.
- `ui_in[7:0]` — input only, readable by `PINR`.

Open-drain is not a convenience. I2C requires `SDA` and `SCL` to be released
rather than driven high, so a pin in `PDRN` drives low on `PINCLR` and
tri-states on `PINSET`. Without it, I2C cannot be expressed at all.

## 3. Encoding

All instructions are 32 bits, one word.

```
 31   27 26  24 23  21 20   16 15                            0
+-------+------+------+-------+------------------------------+
| op[5] | a[3] | b[3] | x[5]  |           delay[16]          |
+-------+------+------+-------+------------------------------+
                \____ imm8 = {b[3], x[5]} ____/
```

- `op` — opcode, 32 encodings, §4
- `a` — destination or primary register
- `b` — source register, or the high 3 bits of `imm8`
- `x` — shift amount / bit count, or the low 5 bits of `imm8`
- `delay` — `D`, always. 0 to 65535 cycles.

`imm8` overlays `b` and `x`, so an instruction uses either a source register or
an 8-bit immediate, never both.

## 4. Instructions

The tables below are generated from `axpe-isa.json`, which is the only place
this instruction set is written down. Regenerate with
`python3 tools/axpe_isa.py generate`; `check` fails the build when they drift.

<!-- generated from axpe-isa.json: instructions -->

### Timing

| Op | Mnemonic | Operands | Retires in | Effect |
|---|---|---|---|---|
| `00` | `DELAY` | -- | `max(D,1)` | Nothing, for D cycles. |

### Pins

| Op | Mnemonic | Operands | Retires in | Effect |
|---|---|---|---|---|
| `01` | `PINSET` | imm8 | `max(D,1)` | uio pins in the mask go high, or release if open-drain. |
| `02` | `PINCLR` | imm8 | `max(D,1)` | uio pins in the mask go low. |
| `03` | `PINTOG` | imm8 | `max(D,1)` | uio pins in the mask invert. |
| `04` | `PINW` | reg | `max(D,1)` | uio outputs take Ra[7:0]. |
| `05` | `POUT` | reg | `max(D,1)` | uo_out takes Ra[7:0]. |
| `06` | `PINR` | reg | `max(D,1)` | Ra takes {ui_in[7:0], uio_in[7:0]}, both groups sampled with no skew. |
| `07` | `PDIR` | imm8 | `max(D,1)` | uio direction mask, 1 = drive. |
| `08` | `PDRN` | imm8 | `max(D,1)` | uio open-drain mask. Required for I2C, which cannot be expressed without it. |

### Measurement

| Op | Mnemonic | Operands | Retires in | Effect |
|---|---|---|---|---|
| `09` | `WAITE` | reg, imm8 | `w, 1<=w<=max(D,1)` | Wait for the selected edge with timeout D. Ra takes the number of cycles actually waited, and T is set if and only if the wait reached D. The returned count is what lets firmware measure an unknown peer's timing instead of only reproducing a known one. |

### Shift engine

| Op | Mnemonic | Operands | Retires in | Effect |
|---|---|---|---|---|
| `0A` | `SHCFG` | reg | `max(D,1)` | Shift engine wiring takes Ra. |
| `0B` | `SHOUT` | reg, nbits | `n*max(D,1)` | Clock n bits out of Ra, each bit occupying D cycles. |
| `0C` | `SHIN` | reg, nbits | `n*max(D,1)` | Clock n bits into Ra. |
| `0D` | `SHIO` | reg, nbits | `n*max(D,1)` | Full duplex: out and in together, which is what SPI wants. |

### ALU

| Op | Mnemonic | Operands | Retires in | Effect |
|---|---|---|---|---|
| `10` | `MOV` | reg, reg | `max(D,1)` | Ra takes Rb. |
| `11` | `ADD` | reg, reg | `max(D,1)` | Ra += Rb. |
| `12` | `SUB` | reg, reg | `max(D,1)` | Ra -= Rb. |
| `13` | `AND` | reg, reg | `max(D,1)` | Ra &= Rb. |
| `14` | `OR` | reg, reg | `max(D,1)` | Ra |= Rb. |
| `15` | `XOR` | reg, reg | `max(D,1)` | Ra ^= Rb. |
| `16` | `SHL` | reg, shift | `max(D,1)` | Ra <<= x, C takes the last bit out. |
| `17` | `SHR` | reg, shift | `max(D,1)` | Ra >>= x, C takes the last bit out. |
| `18` | `LDIL` | reg, imm8 | `max(D,1)` | Ra[7:0] takes imm8, high byte preserved. |
| `19` | `LDIH` | reg, imm8 | `max(D,1)` | Ra[15:8] takes imm8, low byte preserved. |
| `1A` | `ADDI` | reg, imm8 | `max(D,1)` | Ra += imm8. |
| `1B` | `CMP` | reg, reg | `max(D,1)` | Ra - Rb discarded, flags kept. |

### Control

| Op | Mnemonic | Operands | Retires in | Effect |
|---|---|---|---|---|
| `1C` | `BR` | cond, target | `max(D,1)` | Branch if the condition holds. Costs 1 + D whether taken or not; a branch that were cheaper untaken would break the central property. |
| `1D` | `CALL` | target | `max(D,1)` | Push PC+1 and jump. |
| `1E` | `RET` | -- | `max(D,1)` | Pop. |
| `1F` | `HALT` | -- | `max(D,1)` | Stop fetching. |

Reserved encodings: `0E`, `0F`. Held for stretch protocols.

<!-- end generated -->

### Notes the tables cannot carry

`PINR` returns both input groups in one 16-bit register, so a protocol that
samples a data line and a clock line reads them in a single instruction with no
skew between them.

`WAITE`'s `imm8` is `{edge[1:0], pin[3:0]}`. `pin` indexes `uio[7:0]` as 0-7 and
`ui_in[7:0]` as 8-15. `edge` is `00` rising, `01` falling, `10` either, `11`
level-high. See §4.1 for what it returns.

For `SHOUT`, `SHIN` and `SHIO`, `D` is the **bit period**, not a trailing hold.
`SHOUT R0, 8, D=BAUD` is eight bits, each occupying exactly `BAUD` cycles.
Timing lives in the instruction; wiring lives in `SHCFG`. That split is what
keeps the retirement cost readable at the call site.

A 16-bit constant costs two instructions, `LDIL` then `LDIH`. That is the price
of every instruction carrying a full delay field, and it is worth it.

Branch conditions in the `a` field: `0` always, `1` `Z`, `2` `NZ`, `3` `C`,
`4` `NC`, `5` `T`, `6` `NT`, `7` reserved.

**Carry on subtraction is a borrow.** `SUB` and `CMP` set `C` when the
subtrahend exceeds the minuend, so after `CMP Ra, Rb` the condition `C` reads
as "`Ra` was less than `Rb`". `sw/pemu/firmware/autobaud.s` depends on this to
keep a running minimum, so the convention is normative rather than incidental.

### 4.1 `WAITE` returns the time it waited

This is the instruction that makes `axpe` more than a transmitter, and it is
the design's main functional bet.

`WAITE Ra, {edge,pin}, D` waits for the edge, and then writes into `Ra` **the
number of cycles it actually waited**. `T` is set if and only if the wait
reached `D`.

The counter that produces that number already exists: it is the same delay
counter every other instruction uses to honour its declared cost. Returning its
value costs one 16-bit read path and no new state. The `a` field was unused by
`WAITE` before, so it costs nothing in the encoding either.

What it buys is the difference between a chip that speaks protocols and a chip
that can **listen to one it has never seen**:

- **Measure** an unknown peer. Two `WAITE`s around a pulse give its width in
  cycles, directly — provided they are **adjacent**. A `WAITE` occupies exactly
  the cycles it waited, so a pair measures a true interval only when nothing
  runs between them; an instruction in the gap spends cycles the measurement
  cannot see, and the pulse reads that much narrow. Put the timeout check after
  both waits, as `autobaud.s` does.
- **Autobaud.** The narrowest low pulse on an idle-high line is one bit period.
  Ten instructions, no host involvement. See `sw/pemu/firmware/autobaud.s`.
- **Self-calibrate.** Firmware writes a measured period into its own `D` fields
  and then transmits at a rate nobody configured.
- **Timestamp edges** for protocol identification, rather than only waiting on
  them.

The article that set this competition names hardware debugging and reverse
engineering as the purpose. A reverse engineer is rarely speaking a protocol
whose timing they already know; they are trying to find out what the timing is.
An emulator that can only emit has answered the easier half of that problem.

There is a symmetry worth stating plainly: the same counter that makes this
chip's own timing provably exact (§1) is what lets it measure everyone else's.
One piece of hardware, both directions.

## 5. `SHCFG` layout

```
 15   14    13   12  11   8 7    4 3    0
+----+-----+-----+---+------+------+------+
| -  | cpha| cpol|ord| din  | dout | clk  |
+----+-----+-----+---+------+------+------+
```

- `clk`, `dout`, `din` — pin indices, same numbering as `WAITE`
- `ord` — 0 LSB-first, 1 MSB-first
- `cpol` — idle clock level
- `cpha` — 0 samples on the leading edge, 1 on the trailing edge

A `clk` index of 15 means **no clock pin**, which is how UART uses the shift
engine: bits are emitted at the `D` bit period with nothing clocked out.

### 5.1 The clocked cell

A clocked shift's bit cell of `D` cycles **splits at its half point**:

```
  D = 8 cycle cell, cpol=0 cpha=0

  cycle  0  1  2  3  4  5  6  7
  data   X-----------------------
  clk    ___________|‾‾‾‾‾‾‾‾‾‾‾‾
                    ^ sample (cpha=0)
                                 ^ sample (cpha=1)
```

- Data changes at the cell start when `cpha=0`, and on the leading edge when
  `cpha=1`, which is what the SPI mode definitions mean by those numbers.
- The clock's **leading** edge falls at `D/2`; it returns to `cpol` at `D`.
- `cpha=0` samples on the leading edge, `cpha=1` on the trailing edge.
- `cpol` is the idle level, so the four `cpol`/`cpha` combinations are SPI
  modes 0 through 3.

Three rules the machine enforces, rejecting the instruction before issue
without consuming a cycle:

1. **`D` must be even and non-zero.** A cell that cannot split at its half
   point has no defined clock position. Flooring would give an asymmetric duty
   cycle that the listing no longer tells you, so it is refused instead.
2. **The clock may not share a pin with either data line,** and must be a
   drivable `uio` pin.
3. **`din` may equal `dout`.** A single bidirectional data line is exactly
   what I2C's `SDA` is, so this is legal and `SHIO` on it is how an I2C byte
   and its ACK are driven.

None of these can be an assembler error. `SHCFG` is loaded from a register, so
the configuration is not visible at assembly time and the machine is the only
place that knows it. An unclocked shift has no half point to find, so it
accepts any `D`, including `0` for one cycle per bit.

## 6. Worked examples

These exist to prove the ISA can express the mandatory protocols before any RTL
is written. PE-04 runs them against the golden model.

### UART transmit, 8N1

```asm
; R0 = byte to send. TX is uio[0]. BAUD = cycles per bit.
uart_tx:
    LDIL  R1, (15<<0)|(0<<4)      ; clk = none, dout = uio[0]
    LDIH  R1, 0x00                ; LSB-first, cpol/cpha unused
    SHCFG R1,        D=0
    PINCLR 0x01,     D=BAUD       ; start bit, held one bit time
    SHOUT R0, 8,     D=BAUD       ; 8 data bits, BAUD cycles each
    PINSET 0x01,     D=BAUD       ; stop bit
    RET
```

Total, exactly: `1 + 1 + 1 + BAUD + 8×BAUD + BAUD + 1 = 4 + 10×BAUD` cycles,
the trailing `1` being the `RET`. At 50 MHz and 115200 baud, `BAUD` is 434 and
the routine is 4,344 cycles — a number read off the listing rather than measured.
`sw/pemu/as/check_axpe_as.py` derives that figure from the rule above and fails
if the assembler and this paragraph ever disagree, and
`sw/pemu/model/check_axpe_model.py` runs this exact firmware against the
platform oracle for all five of its cases.

### UART receive, 8N1

```asm
uart_rx:
    WAITE (1<<4)|1,  D=TIMEOUT    ; falling edge on uio[1] = start bit
    BR    T, rx_timeout, D=0
    DELAY            D=BAUD+BAUD/2 ; skip start bit, land mid-cell
    SHIN  R0, 8,     D=BAUD
    RET
```

### I2C start condition and address byte

```asm
; SDA = uio[2], SCL = uio[3], both open-drain.
i2c_start:
    PDRN  0x0C,      D=0          ; both pins open-drain
    PDIR  0x0C,      D=0
    PINSET 0x0C,     D=THALF      ; both released high
    PINCLR 0x04,     D=THALF      ; SDA low while SCL high == START
    PINCLR 0x08,     D=THALF      ; SCL low, ready for data
    LDIL  R1, (3<<0)|(2<<4)       ; clk = uio[3], dout = uio[2]
    LDIH  R1, 0x01                ; MSB-first
    SHCFG R1,        D=0
    SHOUT R0, 8,     D=THALF      ; address + R/W
    SHIN  R2, 1,     D=THALF      ; ACK from the target
    RET
```

The open-drain mask is what makes this legal: `PINSET` releases the line for the
target to pull, rather than fighting it.

### SPI mode 0, full duplex

```asm
spi_xfer:
    LDIL  R1, (4<<0)|(5<<4)       ; clk = uio[4], dout = uio[5]
    LDIH  R1, 0x01|(6<<0)         ; din = uio[6], MSB-first, cpol=0 cpha=0
    SHCFG R1,        D=0
    PINCLR 0x80,     D=THALF      ; assert CS on uio[7]
    SHIO  R0, 8,     D=THALF      ; send and receive in one instruction
    PINSET 0x80,     D=THALF
    RET
```

## 7. Open questions

- `IMEM_WORDS` default, pending the PE-02 flow trial. 256 costs 6.9% of the die
  as an SRAM macro, 512 costs 11.1%.
- Whether `SHIO` earns its opcode or SPI should compose `SHOUT` and `SHIN`.
  Decide by measuring both in PE-05, not by argument.
- Target clock, which sets the fastest reachable bit rate for every protocol.
- Whether the two reserved opcodes are enough for a stretch protocol, or whether
  low-speed USB needs more than the shift engine can express.
