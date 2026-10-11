// Capacity probes, not a replacement for the default-architecture C oracle.
// Both the expectations here and the RTL -G arguments come from the selected
// profile. Inspect the elaborated arrays as well: exercising only R6 would
// fail to distinguish seven registers from accidentally retaining eight.
#include "Vaxpe.h"
#include "Vaxpe___024root.h"
#include "verilated.h"
#include "axpe_trace.h"
#include <stdexcept>
#include <string>

static void require(bool ok, const char *message)
{
    if (!ok) throw std::runtime_error(message);
}

struct Result {
    unsigned cycles;
    unsigned output;
    unsigned pins;
    unsigned enable;
};

static Result run(const std::vector<uint32_t> &program, bool fault = false)
{
    require(program.size() <= PROFILE_IMEM_WORDS, "program exceeds selected store");
    Vaxpe rtl;
    rtl.clk = 0; rtl.rst_n = 0; rtl.ui_in = 0; rtl.uio_in = 0;
    rtl.imem_data = program.at(0);
    rtl.eval();
    require(rtl.rootp->axpe__DOT__regs.size() == PROFILE_REGS,
            "register count did not reach RTL");
    require(rtl.rootp->axpe__DOT__call_stack.size() == PROFILE_CALL_DEPTH,
            "call depth did not reach RTL");
    for (unsigned i = 0; i < 2; ++i) {
        rtl.clk = 1; rtl.eval(); rtl.clk = 0; rtl.eval();
    }
    rtl.rst_n = 1;
    uint32_t fetched = program.at(0);
    unsigned occupied = 0;
    // Bound from the selected maximum cell and capacity, not a default delay.
    const unsigned budget = ((1u << PROFILE_DELAY_BITS) + 1u) * (program.size() + 1u);
    for (unsigned edge = 0; edge < budget && !rtl.halted && !rtl.fault; ++edge) {
        rtl.imem_data = fetched;
        rtl.eval();
        const unsigned address = rtl.imem_addr;
        rtl.clk = 1; rtl.eval();
        fetched = address < program.size() ? program[address]
                    : encode(AXPE_OP_HALT, 0, 0, 0, 0);
        if (!rtl.halted && !rtl.fault) ++occupied;
        rtl.clk = 0; rtl.eval();
    }
    require(fault ? (rtl.fault && !rtl.halted) : (rtl.halted && !rtl.fault),
            fault ? "missing expected architectural fault" : "unexpected fault or cycle timeout");
    return {occupied, rtl.uo_out, rtl.uio_out, rtl.uio_oe};
}

int main(int argc, char **argv)
{
    Verilated::commandArgs(argc, argv);
    try {
        const unsigned last_reg = PROFILE_REGS - 1u;
        const unsigned pin_mask = (1u << PROFILE_UIO_PINS) - 1u;
        const unsigned max_delay = (1u << PROFILE_DELAY_BITS) - 1u;
        const uint32_t halt = encode(AXPE_OP_HALT, 0, 0, 0, 1);
        auto reg = run({encode_imm(AXPE_OP_LDIL, last_reg, 0xa5, 0),
                        encode(AXPE_OP_POUT, last_reg, 0, 0, 0), halt});
        require(reg.output == 0xa5, "last declared register is not writable/readable");
        auto width = run({encode_imm(AXPE_OP_LDIL, last_reg, 255, 0),
                          encode_imm(AXPE_OP_LDIH, last_reg, (1u << (PROFILE_REG_W - 8u)) - 1u, 0),
                          encode_imm(AXPE_OP_ADDI, last_reg, 1, 0),
                          encode(AXPE_OP_SHR, last_reg, 0, 8, 0),
                          encode(AXPE_OP_POUT, last_reg, 0, 0, 0), halt});
        require(width.output == 0, "register arithmetic did not wrap at selected width");
        auto pins = run({encode_imm(AXPE_OP_PINSET, 0, 255, 0),
                         encode_imm(AXPE_OP_PDIR, 0, 255, 0), halt});
        require(pins.pins == pin_mask && pins.enable == pin_mask,
                "pad mask differs from selected pin count");
        auto drain = run({encode_imm(AXPE_OP_PINSET, 0, 255, 0),
                          encode_imm(AXPE_OP_PDIR, 0, 255, 0),
                          encode_imm(AXPE_OP_PDRN, 0, 255, 0), halt});
        require(drain.enable == 0, "open-drain high did not release every selected pin");
        auto delay = run({encode(AXPE_OP_DELAY, 0, 0, 0, max_delay), halt});
        require(delay.cycles == max_delay + 1u, "maximum delay duration is not exact");
        auto wait = run({encode_imm(AXPE_OP_WAITE, last_reg, 0, max_delay),
                         encode(AXPE_OP_POUT, last_reg, 0, 0, 0), halt});
        require(wait.cycles == max_delay + 2u && wait.output == (max_delay & 255u),
                "maximum wait duration or returned count is wrong");
        std::vector<uint32_t> high(PROFILE_IMEM_WORDS, halt);
        high[0] = encode_imm(AXPE_OP_CALL, 0, PROFILE_IMEM_WORDS - 2u, 0);
        high[1] = encode(AXPE_OP_POUT, last_reg, 0, 0, 0);
        high[PROFILE_IMEM_WORDS - 2u] = encode_imm(AXPE_OP_LDIL, last_reg, 0x39, 0);
        high.back() = encode(AXPE_OP_RET, 0, 0, 0, 0);
        require(run(high).output == 0x39, "last two instruction slots not reachable");
        if (PROFILE_IMEM_WORDS < 256) {
            auto bad = run({encode_imm(AXPE_OP_BR, 0, PROFILE_IMEM_WORDS, 0)}, true);
            require(bad.cycles == 0, "out-of-range branch executed before faulting");
        }
        std::vector<uint32_t> nested(2u * PROFILE_CALL_DEPTH + 3u, halt);
        for (unsigned i = 0; i < PROFILE_CALL_DEPTH; ++i) {
            nested[2u * i] = encode_imm(AXPE_OP_CALL, 0, 2u * (i + 1u), 0);
            if (i) nested[2u * i + 1u] = encode(AXPE_OP_RET, 0, 0, 0, 0);
        }
        nested[2u * PROFILE_CALL_DEPTH] = encode_imm(AXPE_OP_LDIL, last_reg, 0x76, 0);
        nested[2u * PROFILE_CALL_DEPTH + 1u] = encode(AXPE_OP_RET, 0, 0, 0, 0);
        nested[1] = encode(AXPE_OP_POUT, last_reg, 0, 0, 0);
        // Return from the outer call to POUT then branch over the subroutines.
        // Put the outer body at the high end to keep each inner return intact.
        nested[0] = encode_imm(AXPE_OP_BR, 0, PROFILE_IMEM_WORDS - 3u, 0);
        nested.resize(PROFILE_IMEM_WORDS, halt);
        nested[PROFILE_IMEM_WORDS - 3u] = encode_imm(AXPE_OP_CALL, 0, 2, 0);
        nested[PROFILE_IMEM_WORDS - 2u] = encode(AXPE_OP_POUT, last_reg, 0, 0, 0);
        require(run(nested).output == 0x76, "full selected call stack failed to unwind");
        auto overflow = run({encode_imm(AXPE_OP_CALL, 0, 0, 0)}, true);
        require(overflow.cycles == PROFILE_CALL_DEPTH, "stack overflow boundary is wrong");
        require(run({encode(AXPE_OP_RET, 0, 0, 0, 0)}, true).cycles == 0,
                "empty stack did not fault immediately");
        std::printf("axpe profile: PASS words=%u regs=%u width=%u delay=%u pins=%u stack=%u\n",
                    PROFILE_IMEM_WORDS, PROFILE_REGS, PROFILE_REG_W,
                    PROFILE_DELAY_BITS, PROFILE_UIO_PINS, PROFILE_CALL_DEPTH);
        return 0;
    } catch (const std::exception &error) {
        std::fprintf(stderr, "axpe profile: FAIL: %s\n", error.what());
        return 1;
    }
}
