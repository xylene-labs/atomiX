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

#include <cstdint>
#include <cstdio>
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

int main(int argc, char **argv)
{
    Verilated::commandArgs(argc, argv);

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

    std::puts("axpe chip: two different programs loaded over the host port into "
              "one unchanged design, each cycle-exact against the golden model");
    return 0;
}
