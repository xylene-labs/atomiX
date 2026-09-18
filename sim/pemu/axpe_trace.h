/* What both axpe benches need in common: the pin sample they compare, and the
 * instruction encoder they build programs with.
 *
 * One copy on purpose. A second encoder in a second testbench is a second
 * instruction set, and the field it would drift in is a cycle count that
 * nobody re-reads until a protocol misbehaves on real pins. */
#ifndef AXPE_TRACE_H
#define AXPE_TRACE_H

#include "../../sw/pemu/model/axpe_model.h"

#include <cstdint>
#include <cstdio>
#include <vector>

struct Sample {
    uint8_t pins;
    uint8_t enable;
    uint8_t outputs;
};

inline bool same_sample(const Sample &a, const Sample &b)
{
    return a.pins == b.pins && a.enable == b.enable && a.outputs == b.outputs;
}

inline uint32_t encode(unsigned op, unsigned a, unsigned b, unsigned x,
                       unsigned delay)
{
    return (op << AXPE_OP_LO) | (a << AXPE_A_LO) | (b << AXPE_B_LO)
         | (x << AXPE_X_LO) | delay;
}

inline uint32_t encode_imm(unsigned op, unsigned a, unsigned imm, unsigned delay)
{
    return encode(op, a, (imm >> 5) & 7u, imm & 31u, delay);
}

inline void observe(void *opaque, const axpe_model *model)
{
    auto *trace = static_cast<std::vector<Sample> *>(opaque);
    trace->push_back({model->pins, axpe_output_enable(model), model->outputs});
}

/* The cycle-by-cycle trace the golden model produces for a program, or an
 * empty trace if the program does not reach HALT. */
inline std::vector<Sample> model_trace(const char *name,
                                       const std::vector<uint32_t> &program,
                                       axpe_input input)
{
    uint32_t stack[4] = {};
    axpe_model model;
    std::vector<Sample> trace;
    if (axpe_init(&model, program.data(), program.size(), stack, 4) != 0) {
        std::fprintf(stderr, "%s: golden model initialization failed\n", name);
        return {};
    }
    while (model.status == AXPE_OK && model.cycles < 10000)
        axpe_step(&model, input, observe, &trace);
    if (model.status != AXPE_HALTED) {
        std::fprintf(stderr, "%s: golden model stopped with status %d\n",
                     name, model.status);
        return {};
    }
    return trace;
}

#endif
