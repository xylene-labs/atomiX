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
#include <limits>
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

struct DemoRates {
    uint64_t clock_hz = 50000000, uart_baud = 115200;
    uint64_t spi_hz = 1000000, i2c_hz = 100000, i2c_guard_ns = 0;

    uint64_t timing_cycles(uint64_t ns) const
    {
        const __uint128_t count = (static_cast<__uint128_t>(clock_hz) * ns + 999999999) / 1000000000;
        return count > std::numeric_limits<uint64_t>::max() ? std::numeric_limits<uint64_t>::max() : count;
    }
    uint64_t i2c_period() const
    {
        if (!i2c_hz || i2c_guard_ns > std::numeric_limits<uint64_t>::max() - 4700)
            return std::numeric_limits<uint64_t>::max();
        const uint64_t low = timing_cycles((i2c_hz <= 100000 ? 4700 : 1300) + i2c_guard_ns);
        const uint64_t high = timing_cycles((i2c_hz <= 100000 ? 4000 : 600) + i2c_guard_ns);
        __uint128_t period = clock_hz / i2c_hz + (clock_hz % i2c_hz != 0);
        if (period < static_cast<__uint128_t>(low) * 2) period = static_cast<__uint128_t>(low) * 2;
        if (period < static_cast<__uint128_t>(high) * 2) period = static_cast<__uint128_t>(high) * 2;
        period = (period + 3) / 4 * 4;
        return period > std::numeric_limits<uint64_t>::max() ? std::numeric_limits<uint64_t>::max() : period;
    }

    bool read(const std::string &fw)
    {
        const unsigned delay_max = AXPE_DELAY_MASK >> AXPE_DELAY_LO;
        std::ifstream in(fw + "/clock-profile.txt");
        if (!in) return true; // Legacy, unprofiled 50 MHz payloads.
        std::string extra;
        if (!(in >> clock_hz >> uart_baud >> spi_hz >> i2c_hz)) return false;
        // Historical four-field receipts have no extra timing guard.
        if (in >> extra) {
            if (extra.empty() || extra.find_first_not_of("0123456789") != std::string::npos) return false;
            try { i2c_guard_ns = std::stoull(extra); } catch (...) { return false; }
            if (in >> extra) return false;
        }
        if (
            !clock_hz || !uart_baud || !spi_hz || !i2c_hz ||
            clock_hz / uart_baud < 2 || clock_hz / uart_baud > delay_max / 16 ||
            clock_hz / spi_hz < 2 || clock_hz / spi_hz > delay_max ||
            (clock_hz / spi_hz) % 2 || i2c_hz > 400000 ||
            i2c_period() < 4 || i2c_period() > delay_max) {
            std::fprintf(stderr, "invalid runtime clock/rate profile\n");
            return false;
        }
        return true;
    }

    // A receiver rounds its independent requested bit period to the nearest
    // cycle; it does not read the encoded transmitter delay.
    unsigned uart_receiver_period() const
    { return static_cast<unsigned>(clock_hz / uart_baud +
                                  (clock_hz % uart_baud >= (uart_baud + 1) / 2)); }
};

struct UartRatePeer : Peer {
    Peer &peer;
    bool previous = true;
    unsigned cycle = 0;
    std::vector<unsigned> edges;

    explicit UartRatePeer(Peer &receiver) : peer(receiver) {}
    uint8_t step(uint8_t out, uint8_t oe) override
    {
        const uint8_t level = peer.step(out, oe);
        const bool tx = level & 1u;
        if (tx != previous) edges.push_back(cycle);
        previous = tx;
        ++cycle;
        return level;
    }
    bool check_frame(uint8_t byte, unsigned period) const
    {
        std::vector<unsigned> expected;
        bool previous_bit = true;
        for (unsigned bit = 0; bit < 10; ++bit) {
            const bool high = bit == 9 || (bit > 0 && ((byte >> (bit - 1)) & 1u));
            if (high != previous_bit) expected.push_back(bit * period);
            previous_bit = high;
        }
        if (edges.size() != expected.size()) {
            std::fprintf(stderr, "UART: unexpected edge count %zu\n", edges.size());
            return false;
        }
        for (size_t i = 0; i < edges.size(); ++i)
            if (edges[i] - edges[0] != expected[i]) {
                std::fprintf(stderr, "UART: edge %zu at %u cycles, expected %u\n",
                             i, edges[i] - edges[0], expected[i]);
                return false;
            }
        std::printf("axpe rate: UART 8N1 edges at exactly %u cycles per bit\n", period);
        return true;
    }
};

/* Observe clock edges alongside the protocol peer. Peer correctness and a
 * requested clock rate are separate claims: decoding a byte alone tolerates
 * an arbitrarily slow SPI/I2C clock. */
/* UM10204 Rev.7 Table 11, observed at resolved digital bus levels.
 * Analog rise/fall times and pad characteristics are outside this model. */
struct I2cTimingPeer : Peer {
    Peer &peer;
    const DemoRates &rates;
    uint64_t cycle = 0, clock_edge = 0, data_edge = 0, start = 0, stop = 0;
    bool scl = true, sda = true, busy = false, first_fall = false;
    unsigned starts = 0, stops = 0;
    std::string error;

    I2cTimingPeer(Peer &target, const DemoRates &r) : peer(target), rates(r) {}
    void require(const char *name, uint64_t elapsed, uint64_t ns)
    {
        const uint64_t minimum = rates.timing_cycles(ns + rates.i2c_guard_ns);
        if (elapsed < minimum && error.empty()) {
            error = std::string(name) + ": " + std::to_string(elapsed) +
                    " cycles, minimum " + std::to_string(minimum);
            std::fprintf(stderr, "I2C timing: %s\n", error.c_str());
        }
    }
    uint8_t step(uint8_t out, uint8_t oe) override
    {
        const uint8_t level = peer.step(out, oe);
        const bool clock = level & 8u, data = level & 4u;
        const bool standard = rates.i2c_hz <= 100000;
        if (clock && scl && sda && !data) {
            require("START setup", cycle - clock_edge, standard ? 4700 : 600);
            if (!busy) require("bus free", cycle - stop, standard ? 4700 : 1300);
            busy = true; first_fall = true; start = cycle; ++starts;
        }
        if (clock && scl && !sda && data) {
            require("STOP setup", cycle - clock_edge, standard ? 4000 : 600);
            busy = false; stop = cycle; ++stops;
        }
        if (busy && !scl && clock) {
            require("SCL low", cycle - clock_edge, standard ? 4700 : 1300);
            require("data setup", cycle - data_edge, standard ? 250 : 100);
        }
        if (busy && scl && !clock) {
            require("SCL high", cycle - clock_edge, standard ? 4000 : 600);
            if (first_fall) { require("START hold", cycle - start, standard ? 4000 : 600); first_fall = false; }
        }
        if (clock != scl) clock_edge = cycle;
        if (data != sda) data_edge = cycle;
        scl = clock; sda = data; ++cycle;
        return level;
    }
    bool check() const
    {
        if (!error.empty() || starts < 2 || stops < 1) return false;
        std::printf("axpe I2C timing: nominal low/high, START/STOP, bus-free and data setup PASS\n");
        return true;
    }
};

struct ClockRatePeer : Peer {
    Peer &peer;
    unsigned pin, cycle = 0;
    int select_pin;
    bool previous = true;
    std::vector<unsigned> rises;

    ClockRatePeer(Peer &target, unsigned clock_pin, int cs_pin = -1)
        : peer(target), pin(clock_pin), select_pin(cs_pin) {}

    uint8_t step(uint8_t out, uint8_t oe) override
    {
        const uint8_t level = peer.step(out, oe);
        const bool high = (level >> pin) & 1u;
        const bool selected = select_pin < 0 || !((level >> select_pin) & 1u);
        if (selected && !previous && high) rises.push_back(cycle);
        previous = high;
        ++cycle;
        return level;
    }

    bool check_cells(const char *name, unsigned period, bool spi) const
    {
        unsigned consecutive = 0, longest = 0;
        for (size_t i = 1; i < rises.size(); ++i) {
            const unsigned interval = rises[i] - rises[i - 1];
            if (spi && interval != period) {
                std::fprintf(stderr, "%s: rising-edge interval %u, expected %u\n",
                             name, interval, period);
                return false;
            }
            consecutive = interval == period ? consecutive + 1 : 0;
            if (consecutive > longest) longest = consecutive;
        }
        if (longest < 7) {
            std::fprintf(stderr, "%s: no complete eight-bit cell train at %u cycles\n",
                         name, period);
            return false;
        }
        std::printf("axpe rate: %s eight-bit clock train at %u cycles per cell\n", name, period);
        return true;
    }
};

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
    if (!chip.load_verified(program)) return false;
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
    if (!chip.load_verified(program)) return false;
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
    DemoRates rates;
    if (!rates.read(fw)) return 1;
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

    UartReceiver uart(0, rates.uart_receiver_period());
    UartRatePeer uart_rate(uart);
    if (!run_firmware(chip, "uart", fw + "/uart-demo.hex", uart_rate,
                      static_cast<unsigned>(10 * (rates.clock_hz / rates.uart_baud) + 4096), &status))
        return 1;
    if (!complain("uart", uart.error)) return 1;
    if (!uart_rate.check_frame(0x41, static_cast<unsigned>(rates.clock_hz / rates.uart_baud)))
        return 1;
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
    std::printf("axpe chip: uart-demo transmitted 0x41, decoded by an independent "
                "8N1 receiver targeting %llu baud at %llu Hz\n",
                static_cast<unsigned long long>(rates.uart_baud),
                static_cast<unsigned long long>(rates.clock_hz));

    SpiTarget spi(4, 5, 6, 7, 0x3c);
    ClockRatePeer spi_rate(spi, 4, 7);
    if (!run_firmware(chip, "spi", fw + "/spi-demo.hex", spi_rate,
                      static_cast<unsigned>(8 * (rates.clock_hz / rates.spi_hz) + 4096), &status))
        return 1;
    if (!complain("spi", spi.error)) return 1;
    if (!spi_rate.check_cells("SPI", static_cast<unsigned>(rates.clock_hz / rates.spi_hz), true))
        return 1;
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

    // 36 shifted cells plus bus setup/handoffs fit below 44 cell periods;
    // allow host polling/straight-line instruction overhead separately.
    I2cTarget i2c(2, 3, 0x50, 0x39);
    I2cTimingPeer i2c_timing(i2c, rates);
    ClockRatePeer i2c_rate(i2c_timing, 3);
    if (!run_firmware(chip, "i2c", fw + "/i2c-demo.hex", i2c_rate,
                      static_cast<unsigned>(44 * rates.i2c_period() + 4096), &status))
        return 1;
    if (!complain("i2c", i2c.error)) return 1;
    if (!i2c_timing.check() ||
        !i2c_rate.check_cells("I2C", static_cast<unsigned>(rates.i2c_period()), false))
        return 1;
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
