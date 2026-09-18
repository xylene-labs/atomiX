#include "Vaxpe.h"
#include "verilated.h"

#include "axpe_trace.h"

#include <cstdint>
#include <cstdio>
#include <vector>

static uint32_t random_word(uint32_t &state)
{
    state ^= state << 13;
    state ^= state >> 17;
    state ^= state << 5;
    return state;
}

static std::vector<uint32_t> random_scalar_program(uint32_t seed)
{
    static const unsigned reg_ops[] = {
        AXPE_OP_MOV, AXPE_OP_ADD, AXPE_OP_SUB, AXPE_OP_AND,
        AXPE_OP_OR, AXPE_OP_XOR, AXPE_OP_CMP,
    };
    std::vector<uint32_t> program;
    uint32_t state = seed;
    for (unsigned i = 0; i < 32; ++i) {
        const uint32_t choice = random_word(state);
        const unsigned a = (choice >> 8) & 7u;
        const unsigned b = (choice >> 11) & 7u;
        const unsigned delay = (choice >> 16) % 5u;
        switch (choice % 12u) {
        case 0: program.push_back(encode_imm(AXPE_OP_LDIL, a, choice >> 24, delay)); break;
        case 1: program.push_back(encode_imm(AXPE_OP_LDIH, a, choice >> 24, delay)); break;
        case 2: program.push_back(encode_imm(AXPE_OP_ADDI, a, choice >> 24, delay)); break;
        case 3:
            program.push_back(encode(reg_ops[(choice >> 20) % 7u], a, b, 0, delay));
            break;
        case 4:
            program.push_back(encode((choice & 1u) ? AXPE_OP_SHL : AXPE_OP_SHR,
                                     a, 0, (choice >> 20) & 15u, delay));
            break;
        case 5: program.push_back(encode_imm(AXPE_OP_PINSET, 0, choice >> 24, delay)); break;
        case 6: program.push_back(encode_imm(AXPE_OP_PINCLR, 0, choice >> 24, delay)); break;
        case 7: program.push_back(encode_imm(AXPE_OP_PINTOG, 0, choice >> 24, delay)); break;
        case 8: program.push_back(encode_imm(AXPE_OP_PDIR, 0, choice >> 24, delay)); break;
        case 9: program.push_back(encode_imm(AXPE_OP_PDRN, 0, choice >> 24, delay)); break;
        case 10: program.push_back(encode(AXPE_OP_PINR, a, 0, 0, delay)); break;
        default: program.push_back(encode(AXPE_OP_POUT, a, 0, 0, delay)); break;
        }
        // Make register-state differences externally visible throughout the
        // run instead of comparing only timing and final pins.
        program.push_back(encode(AXPE_OP_POUT, a, 0, 0, 0));
    }
    program.push_back(encode(AXPE_OP_HALT, 0, 0, 0, (seed >> 4) % 5u));
    return program;
}

/* Randomized programs that spend most of their cycles inside the two engines,
 * including shift pairs with no instruction between them. The SHCFG values are
 * drawn legal rather than filtered afterwards: an illegal one is a machine
 * reject, which would compare fault behaviour instead of engine timing. */
static std::vector<uint32_t> random_engine_program(uint32_t seed)
{
    static const unsigned shift_ops[] = {
        AXPE_OP_SHOUT, AXPE_OP_SHIN, AXPE_OP_SHIO,
    };
    std::vector<uint32_t> program;
    uint32_t state = seed;
    for (unsigned i = 0; i < 10; ++i) {
        const uint32_t choice = random_word(state);
        const unsigned dout = (choice >> 3) & 7u;
        const unsigned din = (choice >> 6) & 7u;
        unsigned clk = 15u;
        if (choice & 1u) {
            clk = (choice >> 9) & 7u;
            /* A clock may not alias either data line; keep it unclocked
             * rather than skewing the draw away from that collision. */
            if (clk == dout || clk == din) clk = 15u;
        }
        const unsigned cfg = clk | (dout << 4) | (din << 8)
                           | (((choice >> 12) & 1u) << 12)    /* MSB first */
                           | (((choice >> 13) & 1u) << 13)    /* cpol */
                           | (((choice >> 14) & 1u) << 14);   /* cpha */
        const unsigned nbits = 1u + ((choice >> 16) % 8u);
        /* A clocked cell splits at its half point, so it is even and non-zero.
         * An unclocked one may be zero, which is one cycle per bit. */
        const unsigned cell = clk == 15u ? (choice >> 20) % 4u
                                         : 2u * (1u + ((choice >> 20) % 3u));
        program.push_back(encode_imm(AXPE_OP_LDIL, 1, cfg & 0xffu, 0));
        program.push_back(encode_imm(AXPE_OP_LDIH, 1, (cfg >> 8) & 0x7fu, 0));
        program.push_back(encode(AXPE_OP_SHCFG, 1, 0, 0, 0));
        program.push_back(encode_imm(AXPE_OP_LDIL, 0, choice >> 24, 0));
        /* Two transfers with nothing between them: the second issues on the
         * cycle the first retires. */
        program.push_back(encode(shift_ops[(choice >> 24) % 3u], 0, 0, nbits, cell));
        program.push_back(encode(shift_ops[(choice >> 26) % 3u], 2, 0, nbits, cell));
        program.push_back(encode(AXPE_OP_POUT, 0, 0, 0, 0));
        program.push_back(encode(AXPE_OP_POUT, 2, 0, 0, 0));
        /* A wait, then the instruction that consumes what it measured. */
        program.push_back(encode_imm(AXPE_OP_WAITE, 3,
                                     (((choice >> 28) & 3u) << 4) | ((choice >> 5) & 15u),
                                     1u + ((choice >> 17) % 4u)));
        program.push_back(encode(AXPE_OP_POUT, 3, 0, 0, 0));
        program.push_back(encode_imm(AXPE_OP_PINSET, 0, 1u << (choice % 8u),
                                     (choice >> 22) % 3u));
    }
    program.push_back(encode(AXPE_OP_HALT, 0, 0, 0, 0));
    return program;
}

static uint16_t input_at(void *, uint64_t cycle)
{
    /* A deterministic input stream with activity in both pin groups. */
    return static_cast<uint16_t>((cycle * 0x9e37u + 0x5a3cu) ^ (cycle >> 3));
}

static uint16_t input_low(void *, uint64_t)
{
    return 0;
}

/* One known pulse on uio0: low, then high for exactly five cycles. A pair of
 * adjacent waits must measure that five, which is the interval measurement
 * axpe-isa.md 4.1 makes normative and what autobaud.s depends on. */
static uint16_t input_pulse(void *, uint64_t cycle)
{
    return (cycle >= 3 && cycle < 8) ? 1u : 0u;
}

static bool compare_case(const char *name, const std::vector<uint32_t> &program,
                         axpe_input input = input_at)
{
    const std::vector<Sample> expected = model_trace(name, program, input);
    if (expected.empty()) return false;

    Vaxpe rtl;
    rtl.clk = 0;
    rtl.rst_n = 0;
    rtl.ui_in = 0;
    rtl.uio_in = 0;
    rtl.imem_data = program[0];
    rtl.eval();
    for (unsigned reset_cycle = 0; reset_cycle < 2; ++reset_cycle) {
        rtl.clk = 1;
        rtl.eval();
        rtl.clk = 0;
        rtl.eval();
    }
    rtl.rst_n = 1;

    std::vector<Sample> actual;
    /* A synchronous-read memory: the core presents the next address, this
     * captures it on the edge, and the word appears on the cycle after. A
     * combinational array here would let the RTL pass with a fetch schedule no
     * SRAM macro or block RAM can actually provide. */
    uint32_t fetched = program[0];
    for (uint64_t cycle = 0; cycle <= expected.size() + 8 && !rtl.halted && !rtl.fault;
         ++cycle) {
        const uint16_t inputs = input(nullptr, cycle);
        rtl.uio_in = inputs & 0xffu;
        rtl.ui_in = inputs >> 8;
        rtl.imem_data = fetched;
        rtl.eval();
        const unsigned address = rtl.imem_addr;
        rtl.clk = 1;
        rtl.eval();
        fetched = address < program.size() ? program[address] : program.back();
        // The model's observations are occupied cycles, not the boundary
        // after an instruction retires. HALT rises on that boundary.
        if (!rtl.halted && !rtl.fault)
            actual.push_back({static_cast<uint8_t>(rtl.uio_out),
                              static_cast<uint8_t>(rtl.uio_oe),
                              static_cast<uint8_t>(rtl.uo_out)});
        rtl.clk = 0;
        rtl.eval();
    }

    bool samples_match = true;
    size_t first_mismatch = 0;
    const size_t common = actual.size() < expected.size() ? actual.size() : expected.size();
    for (size_t i = 0; i < common; ++i) {
        if (!same_sample(actual[i], expected[i])) {
            samples_match = false;
            first_mismatch = i;
            break;
        }
    }
    const bool exact = samples_match && rtl.halted && !rtl.fault &&
                       actual.size() == expected.size();
    /* Not an allowance: exactness is the gate. One duplicated cycle used to be
     * this design's standing defect -- a long instruction handing control back
     * through a cycle of its own -- so when it returns, say so by name instead
     * of leaving a cycle count to be diffed by hand. */
    if (!exact && rtl.halted && !rtl.fault &&
        actual.size() == expected.size() + 1) {
        for (size_t skip = 0; skip < actual.size(); ++skip) {
            bool removable = true;
            for (size_t i = 0; i < expected.size(); ++i) {
                if (!same_sample(expected[i], actual[i + (i >= skip)])) {
                    removable = false;
                    break;
                }
            }
            if (removable) {
                std::fprintf(stderr,
                             "%s: cycle %zu is an undeclared retirement "
                             "handoff; removing it makes the run exact\n",
                             name, skip);
                break;
            }
        }
    }
    if (!exact && common == 0)
        std::fprintf(stderr, "%s: no comparable cycles\n", name);
    if (!exact)
        if (!samples_match)
            std::fprintf(stderr,
                         "%s: cycle %zu expected pins=%02x oe=%02x out=%02x, "
                         "got pins=%02x oe=%02x out=%02x\n",
                         name, first_mismatch, expected[first_mismatch].pins,
                         expected[first_mismatch].enable,
                         expected[first_mismatch].outputs,
                         actual[first_mismatch].pins,
                         actual[first_mismatch].enable,
                         actual[first_mismatch].outputs);
    if (!exact)
        std::fprintf(stderr,
                     "%s: expected %zu cycles and HALT, got %zu cycles "
                     "halt=%u fault=%u\n",
                     name, expected.size(), actual.size(), rtl.halted, rtl.fault);
    return exact;
}

int main(int argc, char **argv)
{
    Verilated::commandArgs(argc, argv);
    const std::vector<uint32_t> scalar = {
        encode(AXPE_OP_LDIL, 0, 5, 5, 0),   // R0.low = 0xa5
        encode(AXPE_OP_POUT, 0, 0, 0, 3),
        encode(AXPE_OP_PDIR, 0, 0, 3, 0),
        encode(AXPE_OP_PINSET, 0, 0, 1, 2),
        encode(AXPE_OP_HALT, 0, 0, 0, 1),
    };
    const std::vector<uint32_t> control = {
        encode_imm(AXPE_OP_LDIL, 0, 1, 0),
        encode(AXPE_OP_CMP, 0, 0, 0, 0),
        encode_imm(AXPE_OP_BR, 1, 5, 3),       // Z -> word 5
        encode_imm(AXPE_OP_LDIL, 1, 0xee, 0),  // unreachable
        encode(AXPE_OP_HALT, 0, 0, 0, 0),
        encode_imm(AXPE_OP_LDIL, 1, 0x42, 0),
        encode_imm(AXPE_OP_CALL, 0, 9, 2),
        encode(AXPE_OP_POUT, 1, 0, 0, 0),
        encode(AXPE_OP_HALT, 0, 0, 0, 2),
        encode_imm(AXPE_OP_ADDI, 1, 1, 0),
        encode(AXPE_OP_RET, 0, 0, 0, 3),
    };
    const std::vector<uint32_t> unclocked_shift = {
        encode_imm(AXPE_OP_LDIL, 1, 0x0f, 0),  // no clock, dout=uio0
        encode_imm(AXPE_OP_LDIH, 1, 0x01, 0),  // din=uio1, LSB first
        encode(AXPE_OP_SHCFG, 1, 0, 0, 0),
        encode_imm(AXPE_OP_LDIL, 0, 0xa5, 0),
        encode(AXPE_OP_SHOUT, 0, 0, 8, 2),
        encode(AXPE_OP_HALT, 0, 0, 0, 0),
    };
    const std::vector<uint32_t> clocked_shift = {
        encode_imm(AXPE_OP_LDIL, 1, 0x54, 0),  // clk4, dout5
        encode_imm(AXPE_OP_LDIH, 1, 0x16, 0),  // din6, MSB first
        encode(AXPE_OP_SHCFG, 1, 0, 0, 0),
        encode_imm(AXPE_OP_LDIL, 0, 0xa5, 0),
        encode(AXPE_OP_SHOUT, 0, 0, 8, 4),
        encode(AXPE_OP_HALT, 0, 0, 0, 0),
    };
    const std::vector<uint32_t> unclocked_shift_io = {
        encode_imm(AXPE_OP_LDIL, 1, 0x0f, 0),
        encode_imm(AXPE_OP_LDIH, 1, 0x01, 0),
        encode(AXPE_OP_SHCFG, 1, 0, 0, 0),
        encode_imm(AXPE_OP_LDIL, 0, 0xa5, 0),
        encode(AXPE_OP_SHIO, 0, 0, 8, 2),
        encode(AXPE_OP_POUT, 0, 0, 0, 0),
        encode(AXPE_OP_HALT, 0, 0, 0, 0),
    };
    const std::vector<uint32_t> clocked_shift_io_cpha1 = {
        encode_imm(AXPE_OP_LDIL, 1, 0x54, 0),
        encode_imm(AXPE_OP_LDIH, 1, 0x56, 0), // MSB first, CPHA=1
        encode(AXPE_OP_SHCFG, 1, 0, 0, 0),
        encode_imm(AXPE_OP_LDIL, 0, 0xa5, 0),
        encode(AXPE_OP_SHIO, 0, 0, 8, 4),
        encode(AXPE_OP_POUT, 0, 0, 0, 0),
        encode(AXPE_OP_HALT, 0, 0, 0, 0),
    };
    // Two transfers with nothing between them. The second issues on the cycle
    // the first retires, and the POUT on the cycle the second does.
    const std::vector<uint32_t> back_to_back_shift = {
        encode_imm(AXPE_OP_LDIL, 1, 0x0f, 0),  // no clock, dout=uio0
        encode_imm(AXPE_OP_LDIH, 1, 0x01, 0),  // din=uio1, LSB first
        encode(AXPE_OP_SHCFG, 1, 0, 0, 0),
        encode_imm(AXPE_OP_LDIL, 0, 0xa5, 0),
        encode(AXPE_OP_SHOUT, 0, 0, 8, 2),
        encode(AXPE_OP_SHIN, 2, 0, 8, 2),
        encode(AXPE_OP_POUT, 2, 0, 0, 0),
        encode(AXPE_OP_HALT, 0, 0, 0, 0),
    };
    // A clocked transfer's trailing clock edge and a pin instruction land on
    // the same edge. The instruction owns its own bit and must leave the
    // clock's alone, which a latch overwrite would not.
    const std::vector<uint32_t> shift_then_pin = {
        encode_imm(AXPE_OP_LDIL, 1, 0x54, 0),  // clk4, dout5
        encode_imm(AXPE_OP_LDIH, 1, 0x16, 0),  // din6, MSB first
        encode(AXPE_OP_SHCFG, 1, 0, 0, 0),
        encode_imm(AXPE_OP_LDIL, 0, 0xa5, 0),
        encode(AXPE_OP_SHOUT, 0, 0, 8, 4),
        encode_imm(AXPE_OP_PINSET, 0, 0x01, 2),
        encode(AXPE_OP_HALT, 0, 0, 0, 0),
    };
    // The received value is written on the edge the next instruction issues,
    // so that instruction reads what it is being handed, not the old register.
    const std::vector<uint32_t> shift_result_used = {
        encode_imm(AXPE_OP_LDIL, 1, 0x0f, 0),
        encode_imm(AXPE_OP_LDIH, 1, 0x01, 0),
        encode(AXPE_OP_SHCFG, 1, 0, 0, 0),
        encode(AXPE_OP_SHIN, 0, 0, 8, 2),
        encode_imm(AXPE_OP_ADDI, 0, 1, 0),
        encode(AXPE_OP_POUT, 0, 0, 0, 0),
        encode(AXPE_OP_HALT, 0, 0, 0, 0),
    };
    // Adjacent waits measure a true interval: five cycles of pulse, read off
    // the second WAITE's own return value. A cycle between them, inserted by
    // hardware rather than by the listing, is exactly what this catches.
    const std::vector<uint32_t> wait_interval = {
        encode_imm(AXPE_OP_WAITE, 0, 0x00, 6), // rising uio0
        encode_imm(AXPE_OP_WAITE, 1, 0x10, 6), // falling uio0, adjacent
        encode(AXPE_OP_POUT, 1, 0, 0, 0),
        encode(AXPE_OP_HALT, 0, 0, 0, 0),
    };
    // Testing T on the instruction immediately after the wait that set it.
    const std::vector<uint32_t> wait_flag_branch = {
        encode_imm(AXPE_OP_WAITE, 0, 0x00, 2), // rising uio0, held low
        encode_imm(AXPE_OP_BR, 5, 4, 0),       // T -> word 4
        encode_imm(AXPE_OP_LDIL, 1, 0xee, 0),  // unreachable
        encode(AXPE_OP_POUT, 1, 0, 0, 0),      // unreachable
        encode(AXPE_OP_POUT, 0, 0, 0, 1),      // the measured count
        encode(AXPE_OP_HALT, 0, 0, 0, 0),
    };
    const std::vector<uint32_t> wait_timeout = {
        encode_imm(AXPE_OP_WAITE, 0, 0x00, 4), // rising uio0, held low
        encode(AXPE_OP_POUT, 0, 0, 0, 0),
        encode_imm(AXPE_OP_BR, 5, 4, 0),       // T -> HALT
        encode_imm(AXPE_OP_LDIL, 1, 0xee, 0),  // timeout flag failure
        encode(AXPE_OP_HALT, 0, 0, 0, 0),
    };

    if (!compare_case("scalar-timing", scalar)) return 1;
    if (!compare_case("branch-call-ret", control)) return 1;
    for (uint32_t seed = 1; seed <= 64; ++seed) {
        const auto program = random_scalar_program(seed * 0x9e3779b9u);
        char name[40];
        std::snprintf(name, sizeof(name), "random-scalar-%u", seed);
        if (!compare_case(name, program)) return 1;
    }
    if (!compare_case("unclocked-shift", unclocked_shift)) return 1;
    if (!compare_case("clocked-shift", clocked_shift)) return 1;
    if (!compare_case("unclocked-shift-io", unclocked_shift_io)) return 1;
    if (!compare_case("clocked-shift-io-cpha1", clocked_shift_io_cpha1)) return 1;
    if (!compare_case("back-to-back-shift", back_to_back_shift)) return 1;
    if (!compare_case("shift-then-pin", shift_then_pin)) return 1;
    if (!compare_case("shift-result-used", shift_result_used)) return 1;
    if (!compare_case("wait-timeout", wait_timeout, input_low)) return 1;
    if (!compare_case("wait-interval", wait_interval, input_pulse)) return 1;
    if (!compare_case("wait-flag-branch", wait_flag_branch, input_low)) return 1;
    for (uint32_t seed = 1; seed <= 48; ++seed) {
        const auto program = random_engine_program(seed * 0x85ebca6bu);
        char name[40];
        std::snprintf(name, sizeof(name), "random-engine-%u", seed);
        if (!compare_case(name, program)) return 1;
    }
    std::puts("axpe cosim: scalar, control, shift and wait timing match "
              "cycle for cycle across 112 randomized programs");
    return 0;
}
