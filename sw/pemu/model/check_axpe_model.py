#!/usr/bin/env python3
"""Compile the draft C model and exercise ISA behavior and firmware gaps."""
from __future__ import annotations

import ctypes as C
import json
import os
from pathlib import Path
import random
import shlex
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "sw/pemu/as"))
from axpe_as import assemble, ISA  # noqa: E402


class Model(C.Structure):
    _fields_ = [("r", C.c_uint16 * ISA["registers"]["count"]),
                ("pc", C.c_uint32), ("shcfg", C.c_uint16),
                ("period", C.c_uint16)] + [
        (n, C.c_uint8) for n in ("pins", "outputs", "direction", "drain", "z", "c", "t")
    ] + [("cycles", C.c_uint64), ("retired", C.c_uint64),
         ("program", C.POINTER(C.c_uint32)), ("words", C.c_size_t),
         ("stack", C.POINTER(C.c_uint32)), ("depth", C.c_size_t),
         ("sp", C.c_size_t), ("status", C.c_int)]


Input = C.CFUNCTYPE(C.c_uint16, C.c_void_p, C.c_uint64)
Observe = C.CFUNCTYPE(None, C.c_void_p, C.POINTER(Model))
OK, HALTED, FETCH, ENCODING, STACK, UNSUPPORTED = range(6)
LIB = None


class Machine:
    def __init__(self, source, *, depth=4, inputs=lambda cycle: 0, words=None,
                 path=Path("<model-test>")):
        # `path` is what `.include` resolves against, so a program that pulls
        # in a library has to be assembled from where it actually lives.
        self.insns = assemble(source, path)
        encoded = [i.word for i in self.insns] if words is None else words
        self.program = (C.c_uint32 * len(encoded))(*encoded)
        self.stack = (C.c_uint32 * depth)()
        self.m = Model()
        assert LIB.axpe_init(C.byref(self.m), self.program, len(encoded), self.stack, depth) == 0
        self.input = Input(lambda ctx, cycle: inputs(cycle))
        self.trace = []
        self.observe = Observe(lambda ctx, p: self.trace.append(
            (p.contents.cycles, p.contents.pins, LIB.axpe_output_enable(p))))

    def step(self):
        return LIB.axpe_step(C.byref(self.m), self.input, self.observe, None)

    def run(self, limit=1000):
        for _ in range(limit):
            status = self.step()
            if status != OK:
                return status
        raise AssertionError("instruction limit reached")


class ModelTests(unittest.TestCase):
    def test_reset_halt_and_delay(self):
        m = Machine("DELAY D=65535\nHALT D=3")
        self.assertEqual(list(m.m.r), [0] * 8)
        self.assertEqual(m.run(), HALTED)
        self.assertEqual((m.m.cycles, m.m.retired), (65538, 2))
        self.assertEqual(m.step(), HALTED)
        self.assertEqual(len(m.trace), 65538)

    def test_alu_randomized(self):
        rng = random.Random(0xA4FE)
        for _ in range(100):
            a, b = rng.randrange(65536), rng.randrange(65536)
            for op in ("ADD", "ADDI", "SUB", "CMP", "AND", "OR", "XOR", "MOV"):
                operand = b & 255 if op == "ADDI" else b
                m = Machine(f"{op} R0, {operand if op == 'ADDI' else 'R1'}, D=2")
                m.m.r[0], m.m.r[1] = a, b
                m.m.z, m.m.c, m.m.t = 1, 1, 1
                self.assertEqual(m.step(), OK)
                result = {"ADD": a+b, "ADDI": a+operand, "SUB": a-b,
                          "CMP": a-b, "AND": a&b, "OR": a|b,
                          "XOR": a^b, "MOV": b}[op] & 65535
                self.assertEqual(m.m.r[0], a if op == "CMP" else result)
                self.assertEqual(m.m.z, 1 if op == "MOV" else int(result == 0))
                carry = int(a+operand > 65535) if op in ("ADD", "ADDI") else (
                    int(a < b) if op in ("SUB", "CMP") else 1)
                self.assertEqual((m.m.c, m.m.t, m.m.cycles), (carry, 1, 2))

    def test_constants_shifts_flags(self):
        m = Machine("LDIL R0, 0xa5\nLDIH R0, 0x81\nSHL R0, 0\nSHR R0, 16")
        m.m.c, m.m.z = 1, 1
        for _ in range(3): self.assertEqual(m.step(), OK)
        self.assertEqual((m.m.r[0], m.m.c, m.m.z), (0x81a5, 1, 1))
        m.step()
        self.assertEqual((m.m.r[0], m.m.c, m.m.z), (0, 1, 1))
        for op in ("SHL", "SHR"):
            for n in range(1, 17):
                m = Machine(f"{op} R0, {n}")
                m.m.r[0] = 0x8123
                m.step()
                value = (0x8123 << n) & 65535 if op == "SHL" else 0x8123 >> n
                carry = (0x8123 >> (16-n if op == "SHL" else n-1)) & 1
                self.assertEqual((m.m.r[0], m.m.c), (value, carry))

    def test_pads(self):
        m = Machine("PDIR 0x0f\nPDRN 0x05\nPINSET 0x0f\nPINCLR 1\nPINTOG 2\nPINR R0\nPOUT R0\nPINW R0",
                    inputs=lambda cycle: 0xabc5)
        for _ in range(3): m.step()
        self.assertEqual(LIB.axpe_output_enable(C.byref(m.m)), 0x0a)
        m.step()
        self.assertEqual(LIB.axpe_output_enable(C.byref(m.m)), 0x0b)
        m.step()
        self.assertEqual(m.m.pins, 0x0c)
        for _ in range(3): m.step()
        self.assertEqual((m.m.r[0], m.m.outputs, m.m.pins), (0xabc5, 0xc5, 0xc5))

    def test_wait_boundaries(self):
        for edge in range(4):
            for pin in (0, 7, 8, 15):
                for at in (0, 1, 4, 5, 6):
                    def inputs(cycle, at=at, edge=edge, pin=pin):
                        level = int(cycle >= at)
                        return (level ^ (edge == 1)) << pin
                    m = Machine(f"WAITE R2, {edge*16+pin}, D=5", inputs=inputs)
                    m.step()
                    waited = (0 if edge == 3 else 5) if at == 0 else min(at, 5)
                    self.assertEqual((m.m.r[2], m.m.t, m.m.cycles),
                                 (waited, int(waited == 5), max(waited, 1)))
        m = Machine("WAITE R0, 48, D=0", inputs=lambda cycle: 1)
        m.step()
        # The level was already high, so the wait ended on its own terms.
        # That is not a timeout, and the effective bound is one cycle.
        self.assertEqual((m.m.r[0], m.m.t, m.m.cycles), (0, 0, 1))

    def test_branch_timing(self):
        for cond in ISA["conditions"]:
            for flag in (0, 1):
                m = Machine(f"BR {cond}, 0, D=7\nHALT")
                m.m.z = m.m.c = m.m.t = flag
                taken = cond == "ALWAYS" or bool(flag) == (cond in ("Z", "C", "T"))
                m.step()
                self.assertEqual((m.m.pc, m.m.cycles), (0 if taken else 1, 7))

    def test_memory_and_stack_bounds(self):
        for depth in (1, 4, 7):
            m = Machine("CALL 0", depth=depth)
            for _ in range(depth): self.assertEqual(m.step(), OK)
            self.assertEqual(m.step(), STACK)
            self.assertEqual((m.m.sp, m.m.cycles), (depth, depth))
        m = Machine("CALL 2\nHALT\nRET")
        self.assertEqual(m.run(), HALTED)
        self.assertEqual((m.m.sp, m.m.cycles), (0, 3))
        for size in (1, 16, 64):
            m = Machine("DELAY\n" * size)
            self.assertEqual(m.run(), FETCH)
            self.assertEqual(m.m.cycles, size)
        for source, status in (("RET", STACK), ("CALL 4", FETCH), ("BR ALWAYS, 4", FETCH)):
            m = Machine(source)
            self.assertEqual(m.step(), status)
            self.assertEqual(m.m.cycles, 0)

    def test_reject_invalid_and_unsupported(self):
        for w in (15 << 27, (28 << 27) | (7 << 24),
                  (9 << 27) | (64 << 16), (22 << 27) | (17 << 16),
                  11 << 27, (11 << 27) | (17 << 16),
                  # b beyond the period-select bit is reserved on a shift.
                  (11 << 27) | (2 << 21) | (8 << 16),
                  (13 << 27) | (4 << 21) | (8 << 16)):
            m = Machine("", words=[w])
            self.assertEqual(m.step(), ENCODING)
            self.assertEqual((m.m.cycles, m.m.retired, m.m.pc), (0, 0, 0))
        # SHCFG is loaded from a register, so the machine is the only place
        # that can enforce these; the assembler never sees the configuration.
        clocked = 4 | (5 << 4) | (6 << 8)
        for config, period in (
            (clocked, 3),                  # odd period cannot split at its half
            (clocked, 0),                  # zero period cannot carry a clock
            (5 | (5 << 4), 4),             # clock aliased onto the data-out pin
            (6 | (5 << 4) | (6 << 8), 4),  # clock aliased onto the data-in pin
            (9 | (5 << 4), 4),             # clock on an input-only pin
            (15 | (8 << 4), 3),            # unclocked, data-out not drivable
        ):
            m = Machine(f"SHOUT R0, 8, D={period}")
            m.m.shcfg = config
            self.assertEqual(m.step(), UNSUPPORTED)
            self.assertEqual(m.m.cycles, 0)

        # An unclocked zero-period shift is well defined under max(D,1): one
        # cycle per bit. It is the fastest shift, not an error.
        m = Machine("SHOUT R0, 8, D=0")
        m.m.shcfg = 15
        self.assertEqual(m.step(), OK)
        self.assertEqual(m.m.cycles, 8)

        # din == dout is legal, and is exactly what I2C's SDA needs.
        m = Machine("SHIO R0, 8, D=4")
        m.m.shcfg = 4 | (5 << 4) | (5 << 8)
        self.assertEqual(m.step(), OK)

    def test_period_register_times_the_shift(self):
        """A shift with P set costs n*max(P,1) and looks identical on the pins.

        Where the number came from must change nothing: the same cell duration
        reached through the register has to produce the same waveform and the
        same cycle count as the same duration written into D. If it did not,
        firmware could not substitute one for the other, which is the only
        reason the feature is worth its bit.
        """
        for op in ("SHOUT", "SHIN", "SHIO"):
            for period in (1, 2, 3, 7, 434):
                for count in (1, 8, 16):
                    reference = Machine(f"{op} R0, {count}, D={period}",
                                        inputs=lambda cycle: 0x8000)
                    reference.m.shcfg = 15 | (15 << 8)
                    reference.m.r[0] = 0xa531
                    self.assertEqual(reference.step(), OK)

                    m = Machine(f"SHPER R2\n{op} R0, {count}, P",
                                inputs=lambda cycle: 0x8000)
                    m.m.shcfg = 15 | (15 << 8)
                    m.m.r[0], m.m.r[2] = 0xa531, period
                    self.assertEqual(m.step(), OK)      # SHPER
                    self.assertEqual(m.m.period, period)
                    self.assertEqual(m.step(), OK)      # the transfer
                    self.assertEqual(m.m.cycles - 1, reference.m.cycles,
                                     f"{op} n={count} P={period} cycle count")
                    self.assertEqual(m.m.r[0], reference.m.r[0])
                    self.assertEqual([row[1] for row in m.trace[1:]],
                                     [row[1] for row in reference.trace],
                                     f"{op} n={count} P={period} pin trace")

        # Zero is max(P,1), the same one-cycle cell an unclocked D=0 gives, so
        # a period register nobody loaded shifts at full rate rather than
        # stalling the engine forever.
        m = Machine("SHOUT R0, 8, P")
        m.m.shcfg = 15
        self.assertEqual(m.step(), OK)
        self.assertEqual((m.m.period, m.m.cycles), (0, 8))

        # Reloading retimes the next transfer, not one that already ran.
        m = Machine("SHPER R2\nSHOUT R0, 8, P\nSHPER R3\nSHOUT R0, 8, P")
        m.m.shcfg, m.m.r[2], m.m.r[3] = 15, 3, 9
        for _ in range(4):
            self.assertEqual(m.step(), OK)
        self.assertEqual(m.m.cycles, 1 + 8 * 3 + 1 + 8 * 9)

    def test_period_register_obeys_the_clocked_cell_rules(self):
        """An odd or too-short period is refused however it reached the engine.

        A clocked cell splits at its half point, and a measured value is the
        most likely source of one that cannot. Refusing only the immediate
        would leave the reachable case -- the one a peer's timing produced --
        as the one that silently ran with an asymmetric duty cycle.
        """
        clocked = 4 | (5 << 4) | (6 << 8)
        for period, status in ((0, UNSUPPORTED), (1, UNSUPPORTED),
                               (3, UNSUPPORTED), (2, OK), (6, OK)):
            m = Machine("SHPER R2\nSHIO R0, 8, P")
            m.m.shcfg, m.m.r[2] = clocked, period
            self.assertEqual(m.step(), OK)
            self.assertEqual(m.step(), status, f"clocked period {period}")

    def test_autobaud_demo_transmits_at_the_measured_rate(self):
        """The whole feature, against a peer whose rate is nowhere in the text.

        The oracle is the transmitted waveform itself: every edge the chip
        places must land on a multiple of the period it measured, and the frame
        must be ten cells of it -- start bit included, which is why the routine
        sends the frame as one shift rather than a PINCLR and eight bits.
        """
        demo = ROOT / "sw/pemu/firmware/autobaud-demo.s"
        for width in (37, 53):
            def peer(cycle, width=width):
                # 0x55 at `width` cycles per bit: every low run is one bit.
                if cycle < 40:
                    return 2
                frame = (cycle - 40) // (10 * width)
                if frame >= 6:
                    return 2
                bit = ((cycle - 40) // width) % 10
                level = 0 if bit == 0 else (1 if bit > 8 else (0x55 >> (bit - 1)) & 1)
                return level << 1

            m = Machine(demo.read_text(), inputs=peer, path=demo)
            self.assertEqual(m.run(limit=4000), HALTED)
            self.assertEqual(m.m.r[2], width, "measured bit period")
            self.assertEqual(m.m.outputs, width & 0xff, "published measurement")

            # TX is uio[0]. Transitions after the routine starts driving it must
            # be exactly the 8N1 frame for 0x37 at `width` cycles a bit.
            edges = []
            last = None
            for cycle, pins, enable in m.trace:
                if not (enable & 1):
                    continue
                level = pins & 1
                if last is None:
                    last = level
                    start = cycle
                elif level != last:
                    edges.append(cycle - start)
                    last = level
            frame = [0] + [(0x37 >> n) & 1 for n in range(8)] + [1]
            expected = [i * width for i in range(1, 10) if frame[i] != frame[i - 1]]
            # TX idles high while the driver is enabled, so the first edge is
            # the start bit falling: frame time zero. Every later edge must
            # land on an exact multiple of the measured period from it, with no
            # constant offset and nothing accumulated across the ten cells.
            self.assertTrue(edges, "the demo never moved TX")
            self.assertEqual([e - edges[0] for e in edges[1:]], expected,
                             f"edge placement at {width} cycles per bit")

    def test_spi_firmware_full_duplex(self):
        """spi.s moves a byte both ways in one SHIO, in SPI mode 0.

        The bit period and the SHIO start cycle are derived from the assembled
        listing rather than hardcoded, so the test follows the firmware if its
        setup sequence changes.
        """
        source = (ROOT / "sw/pemu/firmware/spi.s").read_text()
        sent, miso = 0xA5, [1, 1, 0, 1, 0, 0, 1, 0]

        probe = Machine("CALL spi_xfer\nHALT\n" + source)
        shio = next(i for i, x in enumerate(probe.insns) if x.mnemonic == "SHIO")
        period = probe.insns[shio].cycles // 8
        # CALL runs, then the routine body up to the SHIO.
        start = probe.insns[0].cycles + sum(x.cycles for x in probe.insns[2:shio])

        def peer(cycle, start=start, period=period):
            return miso[min(max(0, (cycle - start) // period), 7)] << 6

        m = Machine("CALL spi_xfer\nHALT\n" + source, inputs=peer)
        m.m.r[0] = sent
        self.assertEqual(m.run(), HALTED)

        pins = {cycle: value for cycle, value, _ in m.trace}
        for bit in range(8):
            base = start + bit * period
            self.assertEqual((pins[base] >> 4) & 1, 0, f"SCK idles low, bit {bit}")
            self.assertEqual((pins[base + period // 2] >> 4) & 1, 1,
                             f"SCK leading edge at the half point, bit {bit}")
            self.assertEqual((pins[base + period // 2] >> 5) & 1, (sent >> (7 - bit)) & 1,
                             f"MOSI is MSB-first, bit {bit}")
            self.assertEqual((pins[base] >> 7) & 1, 0, f"CS stays asserted, bit {bit}")

        self.assertEqual(m.m.r[0], sum(b << (7 - n) for n, b in enumerate(miso)))
        self.assertEqual((m.m.pins >> 7) & 1, 1, "CS released at the end")

    def test_clocked_shift_phase_and_modes(self):
        """The cell splits at its half point in all four SPI modes.

        Data changes at the cell start, the clock takes its leading edge at
        D/2, and cpha selects which edge samples. Expectations are derived
        from that rule, not from a recorded run.
        """
        value, pattern = 0xA5, [1, 0, 0, 1, 0, 1, 1, 0]
        for cpol in (0, 1):
            for cpha in (0, 1):
                cfg = 4 | (5 << 4) | (6 << 8) | (cpol << 13) | (cpha << 14)

                m = Machine("SHOUT R0, 8, D=4")
                m.m.shcfg, m.m.r[0] = cfg, value
                self.assertEqual(m.step(), OK)
                self.assertEqual(m.m.cycles, 8 * 4)
                clk = [(row[1] >> 4) & 1 for row in m.trace]
                dat = [(row[1] >> 5) & 1 for row in m.trace]
                for bit in range(8):
                    base = bit * 4
                    self.assertEqual(clk[base], cpol, f"idle level, bit {bit}")
                    self.assertEqual(clk[base + 2], 1 - cpol, f"leading edge, bit {bit}")
                    # Valid across the second half under either phase.
                    self.assertEqual(dat[base + 2], (value >> bit) & 1, f"data, bit {bit}")
                # The clock returns to idle and stays there.
                self.assertEqual((m.m.pins >> 4) & 1, cpol)

                # A peer that presents bit k where this phase samples it.
                def peer(cycle, cpha=cpha):
                    index = max(0, (cycle - 2 * cpha)) // 4
                    return pattern[min(index, 7)] << 6
                m = Machine("SHIN R0, 8, D=4", inputs=peer)
                m.m.shcfg = cfg
                self.assertEqual(m.step(), OK)
                expected = sum(bit << n for n, bit in enumerate(pattern))
                self.assertEqual(m.m.r[0], expected, f"cpol={cpol} cpha={cpha}")

    def test_unclocked_shift(self):
        for op in ("SHOUT", "SHIN", "SHIO"):
            for count in (1, 8, 16):
                for msb in (0, 1):
                    for period in (1, 3):
                        m = Machine(f"{op} R0, {count}, D={period}", inputs=lambda cycle: 0x8000)
                        m.m.shcfg = 15 | (15 << 8) | (msb << 12)
                        m.m.r[0] = 0xa531
                        self.assertEqual(m.step(), OK)
                        self.assertEqual(m.m.cycles, count*period)
                        self.assertEqual(m.m.r[0], 0xa531 if op == "SHOUT" else (1 << count)-1)
                        if op != "SHIN":
                            bits = [(row[1] & 1) for row in m.trace[0::period]]
                            expected = [(0xa531 >> n) & 1 for n in range(count)]
                            self.assertEqual(bits, expected[::-1] if msb else expected)

    def test_shift_receive_phase_and_order(self):
        for op in ("SHIN", "SHIO"):
            for msb in (0, 1):
                for period in (2, 3):
                    pattern = [1, 0, 0, 1, 0, 1, 1, 0]
                    def peer(cycle, period=period, pattern=pattern):
                        bit, phase = divmod(cycle, period)
                        return (pattern[min(bit, 7)] ^ (phase != 0)) << 10
                    m = Machine(f"{op} R0, 8, D={period}", inputs=peer)
                    m.m.shcfg = 15 | (10 << 8) | (msb << 12)
                    m.m.r[0], m.m.z, m.m.c, m.m.t = 0xffa5, 1, 1, 1
                    self.assertEqual(m.step(), OK)
                    self.assertEqual(m.m.r[0], 0x96 if msb else 0x69)
                    self.assertEqual((m.m.z, m.m.c, m.m.t), (1, 1, 1))
                    emitted = [pins & 1 for _, pins, _ in m.trace[0::period]]
                    bits = [(0xa5 >> n) & 1 for n in range(8)]
                    self.assertEqual(emitted, (bits[::-1] if msb else bits)
                                     if op == "SHIO" else [0]*8)

    def test_init_rejects_missing_storage(self):
        m = Model()
        word, stack = (C.c_uint32 * 1)(0), (C.c_uint32 * 1)()
        for program, words, storage, depth in ((None, 1, stack, 1),
                                              (word, 0, stack, 1),
                                              (word, 1, None, 1),
                                              (word, 1, stack, 0)):
            self.assertEqual(LIB.axpe_init(C.byref(m), program, words, storage, depth), -1)
        m = Machine("BR Z, 255\nHALT")
        self.assertEqual(m.run(), HALTED)  # unused target is not a fetch

    def test_shcfg_mask(self):
        m = Machine("SHCFG R0")
        m.m.r[0] = 65535
        m.step()
        self.assertEqual(m.m.shcfg, 32767)

    def test_uart_firmware_matches_platform_oracle(self):
        source = (ROOT / "sw/pemu/firmware/uart.s").read_text()
        cases = json.loads((ROOT / "research/personalities/workloads/uart-tx-8n1.json").read_text())["cases"]
        for case in cases:
            m = Machine("CALL uart_tx\nHALT\n" + source)
            m.m.pins, m.m.direction, m.m.r[0] = 1, 1, case["parameters"]["byte"]
            self.assertEqual(m.run(), HALTED)
            self.assertEqual(m.m.cycles, 4346)  # 4344-cycle routine plus CALL/HALT
            edges, last = [], 1
            for cycle, pins, _ in m.trace:
                if pins & 1 != last:
                    last = pins & 1
                    edges.append([cycle, last])
            start = edges[0][0]
            edges = [[cycle-start, level] for cycle, level in edges]
            # Exact equality with the platform oracle in research/personalities.
            # Under max(D,1) each cell is exactly its bit period, so every edge
            # lands on a multiple of it with no accumulated or constant offset.
            self.assertEqual(edges, case["expected"]["transitions"], case["name"])

    def test_autobaud_measures_pulse_width_exactly(self):
        source = (ROOT / "sw/pemu/firmware/autobaud.s").read_text()
        for width in (20, 53):
            def peer(cycle, width=width):
                return (0 if cycle >= 20 and (cycle-20) % 100 < width else 2)
            m = Machine("CALL autobaud\nHALT\n" + source, inputs=peer)
            self.assertEqual(m.run(), HALTED)
            # Adjacent waits, so the measurement is the true pulse width with
            # no bias. An instruction between them would read this much narrow.
            self.assertEqual(m.m.r[2], width)
        m = Machine("CALL autobaud\nHALT\n" + source, inputs=lambda cycle: 2)
        self.assertEqual(m.run(), HALTED)
        self.assertEqual(m.m.r[2], 0)


def main():
    global LIB
    with tempfile.TemporaryDirectory(prefix="axpe-model-") as tmp:
        library = Path(tmp) / "axpe.so"
        subprocess.run(shlex.split(os.environ.get("CC", "cc")) +
                       ["-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic", "-fPIC", "-shared",
                        str(ROOT / "sw/pemu/model/axpe_model.c"), "-o", str(library)], check=True)
        LIB = C.CDLL(str(library))
        LIB.axpe_init.argtypes = [C.POINTER(Model), C.POINTER(C.c_uint32), C.c_size_t,
                                 C.POINTER(C.c_uint32), C.c_size_t]
        LIB.axpe_step.argtypes = [C.POINTER(Model), Input, Observe, C.c_void_p]
        LIB.axpe_output_enable.argtypes = [C.POINTER(Model)]
        LIB.axpe_output_enable.restype = C.c_uint8
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ModelTests))
        return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
