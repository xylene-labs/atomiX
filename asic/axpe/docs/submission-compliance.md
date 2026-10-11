# Submission compliance audit

This draft tracks the organizer follow-up recorded on 2026-10-10. It does not
certify submission readiness or maintainer approval. The external deadline is
2027-01-18; the internal package target is 2027-01-14.

| Requirement | Current evidence / remaining work |
|---|---|
| Official CMOS5L template and area | Pinned 6×4 source baseline and selected 64-word profile; no 8×4 upgrade claimed |
| Programmable after fabrication | Shared RTL and mapped suites load two unrelated programs through the host pins into unchanged hardware; simulation only |
| UART, SPI and I2C examples | Independent peers and clock-cell checks pass for all supplied 40 MHz runtime profiles on RTL and the selected mapped netlist at seeds 1, 17 and 91 |
| Passing exact-GDS Tiny Tapeout precheck | All nine pinned checks pass for the selected GDS. A submission candidate must include the manifest's bound `precheck` receipt/raw reports; a source export alone carries only historical evidence |
| Tiny Tapeout flow reproduction | Fresh preparation, routing and full Magic/Netgen signoff pass. Routed ODB/DEF/netlist and all final metrics match the selected candidate exactly; GDS non-timestamp bytes match. Reproduction begins at the pinned parent checkpoint. The default exported GDS workflow does not perform this ECO |
| Reset, selection and lost-state reload | The shared suite reads every loaded word back before RUN. Exported RTL covers fresh-instance UART loads, deselection of driven TX, reset/reselection, warm reset and full reload at three seeds. Mapped lifecycle replay is separately recorded; carrier isolation and physical power loss remain untested |
| Demo wiring and external hardware | [Wiring/reload draft](demo-wiring.md) specifies logical connections, pinout adapters, pull-ups, peer requirements and host timing. The pinned ETR v3 Rev 3.2 reference connector mapping is documented; delivered-board revision and electrical/physical validation remain open |
| Architecture, ISA and software | Generated ISA, assembler, runtime loader contract and example payloads are included; no firmware is a synthesis identity input |
| Verification and AI use | [Verification](verification.md) and [AI-use disclosure](ai-use.md) drafts are included; human review remains owed |
| Public repository and submission form | Final repository contents/link, publication and submission remain maintainer actions; registration is recorded, submission is not |

## Clock assumptions and runtime profiles

The selected candidate closes STA at a 25 ns period, corresponding to a
nominal 40 MHz supplied clock. This is a P&R target, not a measurement of an
oscillator or of physical protocol operation. The legacy default firmware
was assembled for a nominal 50 MHz clock. Its exact periods remain valid
instruction counts at either frequency; the absolute rates change:

| Payload | Cycles per bit | At 50 MHz | At 40 MHz |
|---|---:|---:|---:|
| UART 8N1 | 434 | 115,207.4 baud | 92,165.9 baud |
| SPI mode 0 | 50 | 1 MHz SCK | 800 kHz SCK |
| I2C | 500 | 100 kHz SCL | 80 kHz SCL |

These are `clock_hz / cycles_per_bit`, with no physical pad or rise-time
guarantee. I2C instruction handoffs can add idle time between byte/ACK cells;
the table describes the shift engine's cell rate, not transaction throughput.
UART's integer divider approximates the requested 115200 baud at 50 MHz.
An external UART receiver configured for 115200 at a 40 MHz chip clock is not
the demonstrated setting for those legacy words. The supplied runtime profiles
now retime the same routines without changing the GDS:

| Runtime profile | UART requested / cycles / actual | SPI SCK / cycles | I2C cell rate / cycles |
|---|---|---|---|
| `40mhz-standard` | 115200 / 347 / 115273.8 baud | 1 MHz / 40 | 100 kHz / 400 |
| `40mhz-fast-i2c` | 57600 / 694 / 57636.9 baud | 2 MHz / 20 | 357.143 kHz / 112 (400 kHz ceiling) |
| `40mhz-slow` | 115200 / 347 / 115273.8 baud | 10 kHz / 4000 | 10 kHz / 4000 |

`make -C demo rate-check` and `mapped-rate-check` repeat independent protocol
and reload cases at three seeds for each profile. The UART receiver rounds
its requested bit centres independently of the transmitter encoding. SPI
checks all eight rising-edge spacings; I2C checks complete eight-bit clock
trains and nominal resolved-bus low/high, START/STOP, bus-free and data setup
timing against NXP UM10204 Rev. 7 Table 11. Analog rise/fall, data hold, pad
thresholds and clock stretching remain outside this evidence.
Deliberately mislabeled old UART/SPI and wrong-rate I2C images fail the oracle.
SPI firmware demonstrates mode 0; four-mode shifter model/cosimulation evidence
does not claim additional physical or firmware demos. The autobaud payload measures its peer's
period in chip cycles and uses that value; it assumes no absolute baud rate.

Runtime knob defaults/docs live in `sw/pemu/firmware/demo.json`; the JSON profiles
select values. The builder bounds periods against the ISA, rejects odd SPI
cells and rounds symmetric I2C periods up to multiples of four while satisfying
Standard/Fast-mode low/high minima plus the firmware-owned `i2c_guard_ns`, checks the selected instruction
capacity, and refuses stale or modified images. Legacy demo assembly and mapped
replay also pass the resolved instruction capacity explicitly; legacy images
rebuild when the profile or recipe changes. A 16-word legacy assembly refuses
the I2C payload; 64 words accept byte-identical payload words. Its listings and profile receipt
record inputs, requested rates, integer periods and payload hashes. The assembler
also accepts explicit `--define NAME=INTEGER` overrides of declared `.equ`
constants, rejecting misspellings and duplicate overrides.

The timing audit rejected the earlier 100-cycle fast payload: its 50-cycle
SCL low interval at 40 MHz was 1.25 µs, below Fast-mode's 1.3 µs minimum.
It also rejected the earlier Standard-mode STOP/repeated-START handoffs:
a quarter-cell low interval was too short. The runtime library now holds
SCL low for a half cell at those handoffs. These changes affect the I2C
payload words, including the default 50 MHz payload; UART/SPI default words
and hardware identity are unchanged. Earlier functional-only receipts remain
historical and do not establish bus timing. The fast profile's 100 ns guard
selects a 112-cycle cell, giving 1.4 µs nominal low/high intervals. The
standard profile's default guard is 50 ns. The timing limits come from
[NXP UM10204, Table 11](https://www.nxp.com/docs/en/user-guide/UM10204.pdf).

The slow profile also exposes and fixes the earlier fixed case timeouts: a
valid SPI byte required at least 32000 cycles but its test stopped at 20480;
slow I2C likewise exceeded the old 40000-cycle limit. Case budgets now scale
with their bit periods. Both old failures remain recorded.

The 4 ns external I/O budget remains provisional. The organizer update supplies
no characterized CMOS5L pad numbers. No FPGA or measured-silicon result is
included, and passing layout checks would not establish either.
