# AT24C256 byte operations for the axpe bench

These runtime programs extend PE-09 for the confirmed AT24C256 module. They
fit the selected 64-word store without changing FPGA or ASIC hardware:

| Program | Words | Result after clean HALT |
|---|---|---|
| write | 54 | `0x80` if address and data were ACKed; `0` on NACK |
| poll | 46 | `0x80` if the device ACKed its write address; `0` if busy/absent |
| read-low | 60 | `0x80 | (byte & 15)`; `0` on NACK |
| read-high | 60 | `0x80 | (byte >> 4)`; `0` on NACK |

A random read sends address+W, two word-address bytes, repeated START,
address+R, one byte with master NACK, then STOP. Byte write sends the two
address bytes and one data byte, then STOP. Every ACK is checked; NACK paths
emit STOP and release SDA/SCL. The two tagged reads distinguish all 256 data
values from failure using the existing eight-bit host result. The host performs
two random-read transactions per reconstructed byte. Reserve exclusive access
to the test location while they run.

The shared `../i2c.s` routines provide open-drain timing; clocks/rates use the
existing runtime profile and period builder. Only byte operations are tested.
Clock stretching, arbitration, bus-clear recovery and page-write behavior
remain outside this slice. The generic `i2c-demo.s` continues to target a
synthetic peer and is not relabelled as an EEPROM driver.

## Device references and limits

The [legacy AT24C128/256 datasheet, doc0670T](https://ww1.microchip.com/downloads/en/devicedoc/doc0670.pdf)
describes two-byte word addressing, byte writes, ACK polling and random reads.
It uses A1/A0 device selection (addresses 0x50–0x53). Its write-cycle limits
vary with supply and process marking; 5 ms applies to its marked B process.
The [AT24C256C reference](https://ww1.microchip.com/downloads/aemDocuments/documents/MPD/ProductDocuments/DataSheets/AT24C256C-I%C2%B2C-Compatible-%28Two-Wire%29-Serial-EEPROM-256-Kbit-%2832%2C768x8%29-Data-Sheet-DS20006042.pdf)
uses A2/A1/A0 (0x50–0x57). Both provide 32768 bytes. The reported bare
AT24C256 marking does not resolve vendor/process/suffix or module pull-ups/WP;
match those before physical testing. Firmware validates the family address
superset; an unmatched address produces NACK and a failed operation.

`parameters.json` owns defaults/docs for the target address, word address,
data byte, host deadlines and repetition counts. Clock/rate profiles remain
separate runtime inputs. The default word address is a planning value, not a
reserved location on the delivered module. The lab CLI requires an explicitly
selected scratch address and defaults to reads. Writes require `--write-test`.

## Host polling and preservation

The [PC runner](../../host/eeprom.py) uses the existing Pico loader: STOP,
write every instruction, compare every instruction, RUN, bounded HALT poll.
After a byte write, it loads an ACK-only program until ready or the deadline.
The default host readiness deadline is 1000 ms and includes program reload,
USB/SPI transport and probe execution; it does not measure or certify tWR.
A probe can arrive after the physical write cycle has already ended. The
independent simulation peer deliberately stays busy long enough to exercise
NACK, using the bench-owned `sim/pemu/eeprom.json` latency setting.

Before the first write, the runner reads the original byte and durably saves
`backup.json`. Test patterns differ from the original byte even when the configured base
byte equals it, so an unchanged write-protected cell cannot pass a one-write
test. It verifies repeated reads, writes/test reads, then rewrites and
verifies the original in `finally`, including after a lost write reply. Backup
failure prevents writes. Transport loss, changed source inputs, power loss or
interruption can prevent restoration: the receipt remains failed and the
backup stays available. A caught interrupt is recorded as a failed run after
restoration is attempted; abrupt process/host power loss can leave only the
backup. Reconnect and restore that recorded byte before
repeating a write test. Restoration itself performs one additional byte write.

Custom host settings can be supplied as `--parameters <profile.json>` using
schema `org.atomix.axpe-eeprom-profile.v1` and a `settings` object. For example,
`{"schema":"org.atomix.axpe-eeprom-profile.v1","settings":{"read_iterations":3,"write_iterations":2,"poll_interval_ms":2}}`.
Unknown/out-of-range values fail. The lab command requires a passing Gowin
image receipt matching the board profile. That records the operator-supplied
image hash; the loader cannot attest which image is actually programmed.
Record wiring, module/WP/pull-ups, actual clock and captures separately.

## Verification

The [workflow](../../../../docs/workflow.md) owns commands. Host checks cover
all byte tags, deadline/busy/late replies, non-default settings, word counts,
capacity/profile refusal, read-only behavior, backup ordering, restoration and
failure to restore. Both Primer adapters run the same independent EEPROM peer
at seeds 1, 17 and 91, with default/non-default addressing/data and first/last
memory bytes. Tests cover busy/deferred writes, wrong address, each write ACK,
each random-read ACK, final master NACK, STOP/release and write protection.
The existing digital I2C observer checks low/high, START/STOP, bus-free and data
setup minima. Mutants with a wrong address byte and final read ACK must fail
with the peer's intended oracle diagnostic. No physical EEPROM access or
analog measurement has been performed by these checks.
