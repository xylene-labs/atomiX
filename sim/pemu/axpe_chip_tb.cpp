/* The programmability test.
 *
 * The competition's requirement is that a fabricated part can be given a
 * different protocol after fabrication, and the only way to demonstrate that
 * is to load two different programs into one design that is never rebuilt
 * between them. So this bench elaborates the chip once, drives nothing but the
 * four host pins and the protocol pads, and runs two unrelated programs
 * through it -- checking each against the golden model cycle for cycle, not
 * merely that something happened.
 *
 * A preinitialised memory image would pass a weaker version of this test and
 * prove nothing, which is exactly why the board says it does not count. */

#include "Vaxpe_chip.h"
#include "verilated.h"

#include "axpe_trace.h"
#include "axpe_peers.h"

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <string>
#include <vector>

/* The pads the host does not own, held still: CS high, and no protocol peer
 * driving. The golden model must be told the same thing the chip sees. */
static const uint8_t UI_IDLE = 0x04;

static uint16_t input_idle(void *, uint64_t)
{
    return static_cast<uint16_t>(UI_IDLE) << 8;
}

struct Chip {
    Vaxpe_chip rtl;
    std::vector<Sample> trace;
    bool collect = false;
    bool sclk = false, mosi = false, cs_n = true;
    /* When a peer is attached it owns the bidirectional bus, resolving what
     * the chip drives against its own pull-downs and the pull-ups. */
    Peer *peer = nullptr;

    Chip()
    {
        rtl.clk = 0;
        rtl.rst_n = 0;
        rtl.ena = 1;
        rtl.uio_in = 0;
        drive();
        for (int i = 0; i < 4; ++i) { rtl.clk = 1; rtl.eval(); rtl.clk = 0; rtl.eval(); }
        rtl.rst_n = 1;
    }

    void drive()
    {
        rtl.ui_in = static_cast<uint8_t>((sclk ? 1u : 0u) | (mosi ? 2u : 0u)
                                       | (cs_n ? 4u : 0u));
    }

    void tick()
    {
        drive();
        rtl.uio_in = peer ? peer->step(static_cast<uint8_t>(rtl.uio_out),
                                       static_cast<uint8_t>(rtl.uio_oe))
                          : 0u;
        rtl.clk = 1;
        rtl.eval();
        if (collect)
            trace.push_back({static_cast<uint8_t>(rtl.uio_out),
                             static_cast<uint8_t>(rtl.uio_oe),
                             static_cast<uint8_t>(rtl.uo_out)});
        rtl.clk = 0;
        rtl.eval();
    }

    void ticks(int n) { while (n-- > 0) tick(); }

    /* SPI mode 0 at clk/8, inside the clk/4 bound the host contract sets.
     * MISO is sampled at the end of the low phase, where the target has
     * already presented it on the previous falling edge. */
    uint64_t xfer(uint64_t out, int nbits)
    {
        uint64_t in = 0;
        for (int i = nbits - 1; i >= 0; --i) {
            mosi = (out >> i) & 1u;
            sclk = false;
            ticks(4);
            in = (in << 1) | (rtl.uo_out & 1u);
            sclk = true;
            ticks(4);
        }
        sclk = false;
        ticks(4);
        return in;
    }

    void select()   { cs_n = false; ticks(8); }
    void deselect() { cs_n = true;  ticks(8); }

    void write_word(unsigned addr, uint32_t data)
    {
        select();
        xfer(0x01, 8);
        xfer(addr, 8);
        xfer(data, 32);
        deselect();
    }

    uint32_t read_word(unsigned addr)
    {
        select();
        xfer(0x02, 8);
        xfer(addr, 8);
        const uint32_t value = static_cast<uint32_t>(xfer(0, 32));
        deselect();
        return value;
    }

    /* Ends the frame without advancing time, so a caller can start watching
     * the pads on the very cycle the chip is allowed to start running. */
    void end_frame() { cs_n = true; drive(); }

    void run()  { select(); xfer(0x03, 8); deselect(); }
    void stop() { select(); xfer(0x04, 8); deselect(); }

    uint16_t status()
    {
        select();
        xfer(0x05, 8);
        const uint16_t value = static_cast<uint16_t>(xfer(0, 16));
        deselect();
        return value;
    }

    void load(const std::vector<uint32_t> &program)
    {
        for (unsigned i = 0; i < program.size(); ++i) write_word(i, program[i]);
    }
};

/* The assembler writes one 32-bit word per line, so the program the chip runs
 * is the program in sw/pemu/firmware -- not a second copy transcribed here. */
static std::vector<uint32_t> load_hex(const std::string &path)
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

static const uint16_t ST_RUNNING = 0x0100;
static const uint16_t ST_HALTED  = 0x0200;
static const uint16_t ST_FAULT   = 0x0400;
static const uint16_t ST_REFUSED = 0x0800;

/* The chip cannot say on a pin which cycle its core started, and inventing a
 * pin for the benefit of a testbench would be the testbench designing the
 * chip. Instead the executed window is *found*: exactly one offset may match
 * the model, everything before it must be the quiet reset state, and
 * everything after must be frozen, because a halted core cannot move a pin.
 * That proves the alignment rather than assuming a latency. */
static bool compare_run(const char *name, const std::vector<Sample> &trace,
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

static bool run_program(Chip &chip, const char *name,
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
static bool run_firmware(Chip &chip, const char *name, const std::string &hex,
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

static bool complain(const char *name, const std::string &error)
{
    if (error.empty()) return true;
    std::fprintf(stderr, "%s: peer reported %s\n", name, error.c_str());
    return false;
}

int main(int argc, char **argv)
{
    Verilated::commandArgs(argc, argv);
    const std::string fw = argc > 1 ? argv[1] : "build/fw";

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

    Chip chip;

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

    std::puts("axpe chip: UART, SPI and I2C each load into the same unchanged "
              "design and pass a peer written from the protocol, not the firmware");
    return 0;
}
