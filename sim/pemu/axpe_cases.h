/* What the chip has to do, and how it is judged -- with no simulator in it.
 *
 * This is the half of the bench worth keeping when the device under test
 * changes. PE-11 runs these same cases against a post-synthesis and a
 * post-P&R netlist; the cases, the oracle and the peers do not change, only
 * the `Device` behind them. A netlist that passes a different list of cases
 * than the RTL did would not be evidence about the same chip. */
#ifndef AXPE_CASES_H
#define AXPE_CASES_H

#include "axpe_device.h"
#include "axpe_peers.h"
#include "axpe_trace.h"

#include <cstdint>
#include <cstdio>
#include <fstream>
#include <string>
#include <vector>

/* The pads the host does not own, held still: CS high, and no protocol peer
 * driving. The golden model must be told the same thing the chip sees. */
static const uint8_t UI_IDLE = 0x04;

inline uint16_t input_idle(void *, uint64_t)
{
    return static_cast<uint16_t>(UI_IDLE) << 8;
}

static const uint16_t ST_RUNNING = 0x0100;
static const uint16_t ST_HALTED  = 0x0200;
static const uint16_t ST_FAULT   = 0x0400;
static const uint16_t ST_REFUSED = 0x0800;

/* The assembler writes one 32-bit word per line, so the program the chip runs
 * is the program in sw/pemu/firmware -- not a second copy transcribed here. */
inline std::vector<uint32_t> load_hex(const std::string &path)
{
    std::vector<uint32_t> program;
    std::ifstream in(path);
    if (!in) {
        std::fprintf(stderr, "cannot open %s\n", path.c_str());
        return program;
    }
    std::string line;
    while (std::getline(in, line))
        if (!line.empty())
            program.push_back(static_cast<uint32_t>(std::stoul(line, nullptr, 16)));
    return program;
}

/* The chip cannot say on a pin which cycle its core started, and inventing a
 * pin for the benefit of a testbench would be the testbench designing the
 * chip. Instead the executed window is *found*: exactly one offset may match
 * the model, everything before it must be the quiet reset state, and
 * everything after must be frozen, because a halted core cannot move a pin.
 * That proves the alignment rather than assuming a latency. */
inline bool compare_run(const char *name, const std::vector<Sample> &trace,
                        const std::vector<Sample> &expected)
{
    if (expected.empty()) return false;
    if (trace.size() < expected.size()) {
        std::fprintf(stderr, "%s: collected %zu cycles, model needs %zu\n",
                     name, trace.size(), expected.size());
        return false;
    }
    const Sample idle{0, 0, 0};
    size_t found = 0, at = 0;
    for (size_t s = 0; s + expected.size() <= trace.size(); ++s) {
        bool match = true;
        for (size_t i = 0; i < expected.size() && match; ++i)
            match = same_sample(trace[s + i], expected[i]);
        if (match) { ++found; at = s; }
    }
    if (found != 1) {
        std::fprintf(stderr, "%s: %zu alignments of the model trace, expected 1\n",
                     name, found);
        std::fprintf(stderr, "  model:");
        for (size_t i = 0; i < expected.size() && i < 24; ++i)
            std::fprintf(stderr, " %02x/%02x/%02x", expected[i].pins,
                         expected[i].enable, expected[i].outputs);
        std::fprintf(stderr, "\n  chip: ");
        for (size_t i = 0; i < trace.size() && i < 24; ++i)
            std::fprintf(stderr, " %02x/%02x/%02x", trace[i].pins,
                         trace[i].enable, trace[i].outputs);
        std::fprintf(stderr, "\n");
        return false;
    }
    for (size_t i = 0; i < at; ++i)
        if (!same_sample(trace[i], idle)) {
            std::fprintf(stderr, "%s: cycle %zu moved a pin before the core ran\n",
                         name, i);
            return false;
        }
    for (size_t i = at + expected.size(); i < trace.size(); ++i)
        if (!same_sample(trace[i], expected.back())) {
            std::fprintf(stderr, "%s: cycle %zu moved a pin after HALT\n", name, i);
            return false;
        }
    std::printf("axpe chip: %s ran %zu cycles exactly, starting %zu cycles "
                "after its RUN frame\n", name, expected.size(), at);
    return true;
}

inline bool run_program(Chip &chip, const char *name,
                        const std::vector<uint32_t> &program)
{
    const std::vector<Sample> expected = model_trace(name, program, input_idle);
    if (expected.empty()) return false;
    chip.load(program);
    chip.trace.clear();
    chip.select();
    chip.xfer(0x03, 8);
    chip.end_frame();
    chip.collect = true;
    chip.ticks(static_cast<int>(expected.size()) + 32);
    chip.collect = false;
    return compare_run(name, chip.trace, expected);
}

/* Load a firmware image over the host port, run it against its peer, and
 * return the status word once it halts. The core keeps running while the host
 * polls: the loader owns three inputs and the protocols own the bidirectional
 * pins, so the two never contend. */
inline bool run_firmware(Chip &chip, const char *name, const std::string &hex,
                         Peer &peer, unsigned max_cycles, uint16_t *status_out)
{
    const std::vector<uint32_t> program = load_hex(hex);
    if (program.empty()) {
        std::fprintf(stderr, "%s: no program at %s\n", name, hex.c_str());
        return false;
    }
    chip.stop();
    chip.load(program);
    chip.peer = &peer;
    chip.select();
    chip.xfer(0x03, 8);
    chip.end_frame();

    uint16_t status = 0;
    unsigned spent = 0;
    while (spent < max_cycles) {
        chip.ticks(1024);
        spent += 1024;
        status = chip.status();
        if (status & (ST_HALTED | ST_FAULT)) break;
    }
    chip.peer = nullptr;
    if (!(status & ST_HALTED) || (status & ST_FAULT)) {
        std::fprintf(stderr, "%s: status %04x after %u cycles, expected a clean "
                             "halt\n", name, status, spent);
        return false;
    }
    *status_out = status;
    return true;
}

inline bool complain(const char *name, const std::string &error)
{
    if (error.empty()) return true;
    std::fprintf(stderr, "%s: peer reported %s\n", name, error.c_str());
    return false;
}

/* --- what a part does before anyone talks to it --------------------------
 *
 * The first thing observable about a returned die, and the first thing a
 * bring-up engineer needs to know: with nothing loaded and nothing running,
 * the part must be silent and must not be driving any protocol pin. A chip
 * that came up driving would fight whatever it is wired to, which on a bench
 * is a short and on a shared bus is every other device's problem too.
 *
 * Nothing pinned this before. Every other case here loads a program first, so
 * the whole reset state was only ever observed as the prefix of a run that
 * `compare_run` required to be quiet -- true, but incidental to another
 * check, and it says nothing about what happens while the host is mid-frame. */
inline bool check_quiet_after_reset(Chip &chip)
{
    for (int cycle = 0; cycle < 64; ++cycle) {
        chip.tick();
        if (chip.dev.uio_oe() || chip.dev.uio_out() || chip.dev.uo_out()) {
            std::fprintf(stderr, "quiet-reset: cycle %d out of reset drives "
                                 "uio_out=%02x uio_oe=%02x uo_out=%02x, "
                                 "expected a silent part\n",
                         cycle, chip.dev.uio_out(), chip.dev.uio_oe(),
                         chip.dev.uo_out());
            return false;
        }
    }

    /* ...and still silent while the host talks. `uo_out[0]` carries MISO
     * while CS is asserted, which is the contract, so only the protocol pins
     * are held to silence through the frame. */
    chip.trace.clear();
    chip.collect = true;
    const uint16_t status = chip.status();
    chip.collect = false;
    for (size_t i = 0; i < chip.trace.size(); ++i)
        if (chip.trace[i].pins || chip.trace[i].enable) {
            std::fprintf(stderr, "quiet-reset: a host frame moved the protocol "
                                 "pins at cycle %zu: uio_out=%02x uio_oe=%02x\n",
                         i, chip.trace[i].pins, chip.trace[i].enable);
            return false;
        }
    if (status != 0) {
        std::fprintf(stderr, "quiet-reset: status %04x, expected 0000 -- not "
                             "running, not halted, no fault, no refusal, and "
                             "nothing on uo_out\n", status);
        return false;
    }
    std::puts("axpe chip: silent out of reset -- no protocol pin driven, "
              "status 0000, and a host frame does not disturb either");
    return true;
}

/* Every case, in the order they have to run: the reset state before anything
 * is loaded, then the store, then two unrelated programs through one design,
 * then the mandatory protocols, then the measured-rate reply. */
inline int run_chip_suite(Chip &chip, const std::string &fw)
{
    /* Two programs with nothing in common but the machine they run on: one
     * publishes a byte, the other bit-bangs one out of a pin. */
    const std::vector<uint32_t> beacon = {
        encode_imm(AXPE_OP_LDIL, 0, 0xa5, 0),
        encode(AXPE_OP_POUT, 0, 0, 0, 3),
        encode(AXPE_OP_HALT, 0, 0, 0, 1),
    };
    const std::vector<uint32_t> shifter = {
        encode_imm(AXPE_OP_LDIL, 1, 0x0f, 0),  // no clock, dout = uio0
        encode_imm(AXPE_OP_LDIH, 1, 0x01, 0),  // din = uio1, LSB first
        encode(AXPE_OP_SHCFG, 1, 0, 0, 0),
        encode_imm(AXPE_OP_LDIL, 0, 0x5a, 0),
        encode(AXPE_OP_SHOUT, 0, 0, 8, 2),
        encode(AXPE_OP_POUT, 0, 0, 0, 2),
        encode(AXPE_OP_HALT, 0, 0, 0, 1),
    };

    if (!check_quiet_after_reset(chip)) return 1;

    // The store is real: what the host wrote is what the host reads back.
    chip.write_word(7, 0xdeadbeefu);
    const uint32_t echoed = chip.read_word(7);
    if (echoed != 0xdeadbeefu) {
        std::fprintf(stderr, "write/read: wrote deadbeef, read %08x\n", echoed);
        return 1;
    }

    if (!run_program(chip, "first-program", beacon)) return 1;
    uint16_t st = chip.status();
    if (!(st & ST_HALTED) || (st & ST_FAULT) || (st & 0xffu) != 0xa5u) {
        std::fprintf(stderr, "first-program: status %04x, expected halted "
                             "without fault and uo_out a5\n", st);
        return 1;
    }

    // A write while the core owns the store is refused, and says so. The
    // single-port macro is the reason; a silent drop would leave the host
    // believing it had loaded a program it had not.
    chip.write_word(0, 0x00000000u);
    st = chip.status();
    if (!(st & ST_REFUSED)) {
        std::fprintf(stderr, "refused-write: status %04x has no refusal\n", st);
        return 1;
    }
    chip.stop();
    if (chip.read_word(0) != beacon[0]) {
        std::fprintf(stderr, "refused-write: the refused word was written anyway\n");
        return 1;
    }
    if (chip.status() & ST_REFUSED) {
        std::fprintf(stderr, "refused-write: STOP did not clear the refusal\n");
        return 1;
    }

    // The same silicon, never rebuilt, running an unrelated program.
    if (!run_program(chip, "second-program", shifter)) return 1;
    st = chip.status();
    if (!(st & ST_HALTED) || (st & ST_FAULT) || (st & 0xffu) != 0x5au) {
        std::fprintf(stderr, "second-program: status %04x, expected halted "
                             "without fault and uo_out 5a\n", st);
        return 1;
    }

    std::printf("axpe chip: two different programs loaded over the host port "
                "into one unchanged design, each cycle-exact against the golden "
                "model\n");

    /* The three mandatory protocols, as runtime-loaded programs into that same
     * design, each judged by an implementation of its own specification. */
    uint16_t status = 0;

    UartReceiver uart(0, 50000000u / 115200u);
    if (!run_firmware(chip, "uart", fw + "/uart-demo.hex", uart, 60000, &status))
        return 1;
    if (!complain("uart", uart.error)) return 1;
    if (uart.bytes.size() != 1 || uart.bytes[0] != 0x41u) {
        std::fprintf(stderr, "uart: peer decoded %zu bytes, first %02x, "
                             "expected one byte 41\n",
                     uart.bytes.size(), uart.bytes.empty() ? 0 : uart.bytes[0]);
        return 1;
    }
    if ((status & 0xffu) != 0x41u) {
        std::fprintf(stderr, "uart: uo_out %02x, expected the byte it sent\n",
                     status & 0xffu);
        return 1;
    }
    std::puts("axpe chip: uart-demo transmitted 0x41, decoded by an independent "
              "8N1 receiver at 115200");

    SpiTarget spi(4, 5, 6, 7, 0x3c);
    if (!run_firmware(chip, "spi", fw + "/spi-demo.hex", spi, 20000, &status))
        return 1;
    if (!complain("spi", spi.error)) return 1;
    if (spi.frames != 1 || spi.received != 0xa5u) {
        std::fprintf(stderr, "spi: target saw %u frames, byte %02x, expected "
                             "one frame of a5\n", spi.frames, spi.received);
        return 1;
    }
    if ((status & 0xffu) != 0x3cu) {
        std::fprintf(stderr, "spi: uo_out %02x, expected the peer's 3c\n",
                     status & 0xffu);
        return 1;
    }
    std::puts("axpe chip: spi-demo exchanged a5 for 3c in mode 0, full duplex, "
              "against an independent target");

    I2cTarget i2c(2, 3, 0x50, 0x39);
    if (!run_firmware(chip, "i2c", fw + "/i2c-demo.hex", i2c, 40000, &status))
        return 1;
    if (!complain("i2c", i2c.error)) return 1;
    if (!i2c.saw_start || !i2c.saw_repeated_start || !i2c.saw_stop) {
        std::fprintf(stderr, "i2c: start=%d repeated-start=%d stop=%d, "
                             "expected all three\n",
                     i2c.saw_start, i2c.saw_repeated_start, i2c.saw_stop);
        std::fprintf(stderr, "  addressed=%u read=%d writes=%zu first=%02x "
                             "master-nack=%d uo_out=%02x (ee means the firmware "
                             "saw a NACK)\n",
                     i2c.address_bytes, i2c.read_requested, i2c.writes.size(),
                     i2c.writes.empty() ? 0 : i2c.writes[0], i2c.saw_master_nack,
                     status & 0xffu);
        return 1;
    }
    if (i2c.address_bytes != 2 || !i2c.read_requested) {
        std::fprintf(stderr, "i2c: %u addressed phases, read_requested=%d, "
                             "expected 2 and a read\n",
                     i2c.address_bytes, i2c.read_requested);
        return 1;
    }
    if (i2c.writes.size() != 1 || i2c.writes[0] != 0x5au) {
        std::fprintf(stderr, "i2c: target received %zu data bytes, first %02x, "
                             "expected one byte 5a\n",
                     i2c.writes.size(), i2c.writes.empty() ? 0 : i2c.writes[0]);
        return 1;
    }
    if (!i2c.saw_master_nack) {
        std::fprintf(stderr, "i2c: the master never refused the last byte\n");
        return 1;
    }
    if ((status & 0xffu) != 0x39u) {
        std::fprintf(stderr, "i2c: uo_out %02x, expected the peer's 39 "
                             "(ee means firmware saw a NACK)\n", status & 0xffu);
        return 1;
    }
    std::puts("axpe chip: i2c-demo ran START, address+W, data, repeated START, "
              "address+R, read and NACK, STOP against an independent target");

    /* The measurement claim, end to end and in one unchanged design: a peer
     * transmits at a rate no part of the firmware names, the chip counts it off
     * the wire, and answers at it. The peer's own receiver is the oracle, so a
     * period wrong by one cycle per bit walks the sampling point off the data
     * over ten cells and fails here rather than being reported as approximate.
     *
     * 37 and 53 cycles per bit are deliberately not round numbers and
     * deliberately odd: an odd cell is legal unclocked and would be a machine
     * reject under a clock, so this also fixes which of the two rules a UART
     * frame lives under. */
    for (unsigned peer_baud : {37u, 53u}) {
        UartAutobaudPeer autobaud(0, 1, peer_baud, 64, 4, 0x55);
        if (!run_firmware(chip, "autobaud", fw + "/autobaud-demo.hex", autobaud,
                          30000, &status))
            return 1;
        if (!complain("autobaud", autobaud.error())) return 1;
        if ((status & 0xffu) != peer_baud) {
            std::fprintf(stderr, "autobaud: uo_out %02x, expected the peer's "
                                 "%u-cycle bit period measured off the wire\n",
                         status & 0xffu, peer_baud);
            return 1;
        }
        if (autobaud.decoded().size() != 1 || autobaud.decoded()[0] != 0x37u) {
            std::fprintf(stderr, "autobaud: peer decoded %zu bytes, first %02x, "
                                 "expected one byte 37 at its own %u-cycle rate\n",
                         autobaud.decoded().size(),
                         autobaud.decoded().empty() ? 0 : autobaud.decoded()[0],
                         peer_baud);
            return 1;
        }
        std::printf("axpe chip: autobaud-demo measured an unconfigured peer at %u "
                    "cycles per bit and transmitted 0x37 back at that rate, "
                    "decoded by the peer's own receiver\n", peer_baud);
    }
    /* Two rates, one image, nothing reloaded or reconfigured between them. One
     * rate could be a constant that happened to be right; two cannot. */

    std::puts("axpe chip: UART, SPI and I2C each load into the same unchanged "
              "design and pass a peer written from the protocol, not the firmware");
    return 0;
}

#endif
