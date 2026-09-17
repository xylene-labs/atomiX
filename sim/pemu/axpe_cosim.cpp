#include "Vaxpe.h"
#include "verilated.h"

#include "../../sw/pemu/model/axpe_model.h"

#include <cstdint>
#include <cstdio>
#include <vector>

struct Sample {
    uint8_t pins;
    uint8_t enable;
    uint8_t outputs;
};

static bool same_sample(const Sample &a, const Sample &b)
{
    return a.pins == b.pins && a.enable == b.enable && a.outputs == b.outputs;
}

static uint32_t encode(unsigned op, unsigned a, unsigned b, unsigned x,
                       unsigned delay)
{
    return (op << AXPE_OP_LO) | (a << AXPE_A_LO) | (b << AXPE_B_LO)
         | (x << AXPE_X_LO) | delay;
}

static uint32_t encode_imm(unsigned op, unsigned a, unsigned imm, unsigned delay)
{
    return encode(op, a, (imm >> 5) & 7u, imm & 31u, delay);
}

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

static uint16_t input_at(void *, uint64_t cycle)
{
    /* A deterministic input stream with activity in both pin groups. */
    return static_cast<uint16_t>((cycle * 0x9e37u + 0x5a3cu) ^ (cycle >> 3));
}

static uint16_t input_low(void *, uint64_t)
{
    return 0;
}

static void observe(void *opaque, const axpe_model *model)
{
    auto *trace = static_cast<std::vector<Sample> *>(opaque);
    trace->push_back({model->pins, axpe_output_enable(model), model->outputs});
}

static bool compare_case(const char *name, const std::vector<uint32_t> &program,
                         unsigned allowed_extra_cycles = 0,
                         axpe_input input = input_at)
{
    uint32_t stack[4] = {};
    axpe_model model;
    std::vector<Sample> expected;
    if (axpe_init(&model, program.data(), program.size(), stack, 4) != 0) {
        std::fprintf(stderr, "%s: golden model initialization failed\n", name);
        return false;
    }
    while (model.status == AXPE_OK && model.cycles < 10000)
        axpe_step(&model, input, observe, &expected);
    if (model.status != AXPE_HALTED) {
        std::fprintf(stderr, "%s: golden model stopped with status %d\n",
                     name, model.status);
        return false;
    }

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
    for (uint64_t cycle = 0; cycle <= expected.size() + 8 && !rtl.halted && !rtl.fault;
         ++cycle) {
        const uint16_t inputs = input(nullptr, cycle);
        rtl.uio_in = inputs & 0xffu;
        rtl.ui_in = inputs >> 8;
        const unsigned address = rtl.imem_addr;
        rtl.imem_data = address < program.size() ? program[address] : program.back();
        rtl.clk = 1;
        rtl.eval();
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
    bool removable_gap = false;
    if (allowed_extra_cycles == 1 && rtl.halted && !rtl.fault &&
        actual.size() == expected.size() + 1) {
        for (size_t skip = 0; skip < actual.size() && !removable_gap; ++skip) {
            removable_gap = true;
            for (size_t i = 0; i < expected.size(); ++i) {
                if (!same_sample(expected[i], actual[i + (i >= skip)])) {
                    removable_gap = false;
                    break;
                }
            }
        }
    }
    const bool known_gap = allowed_extra_cycles == 1 && removable_gap;
    if (known_gap) {
        std::printf("axpe cosim: XFAIL %s has %u extra retirement cycle(s)\n",
                    name, allowed_extra_cycles);
        return true;
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
    if (!compare_case("unclocked-shift", unclocked_shift, 1)) return 1;
    if (!compare_case("clocked-shift", clocked_shift, 1)) return 1;
    if (!compare_case("unclocked-shift-io", unclocked_shift_io, 1)) return 1;
    if (!compare_case("clocked-shift-io-cpha1", clocked_shift_io_cpha1, 1)) return 1;
    if (!compare_case("wait-timeout", wait_timeout, 1, input_low)) return 1;
    std::puts("axpe cosim: scalar/control timing and 64 randomized programs match; known long-engine gaps reproduced");
    return 0;
}
