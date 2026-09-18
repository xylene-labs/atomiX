/* Host reference model for the draft ISA; see README.md for timing limits. */
#ifndef AXPE_MODEL_H
#define AXPE_MODEL_H
#include <stddef.h>
#include <stdint.h>
#include "../isa/axpe_isa.h"

typedef enum {
    AXPE_OK, AXPE_HALTED, AXPE_FETCH, AXPE_ENCODING, AXPE_STACK,
    AXPE_UNSUPPORTED
} axpe_result;

typedef struct {
    uint16_t r[AXPE_REGS];
    uint32_t pc;
    uint16_t shcfg;
    /* The shift engine's cell duration when an instruction selects it instead
     * of the D in its own word. This is the only path from a measured value
     * to the timing counter, which is what makes a rate the chip discovered
     * usable rather than merely readable. */
    uint16_t period;
    uint8_t pins, outputs, direction, drain, z, c, t;
    uint64_t cycles, retired;
    const uint32_t *program;
    size_t words;
    uint32_t *stack;
    size_t depth, sp;
    axpe_result status;
} axpe_model;

/* Inputs are physical pad levels, {ui_in,uio_in}; caller resolves pull-ups.
 * Observe is called once per elapsed cycle, after output changes at that edge.
 * The model never infers input levels from its output latch. */
typedef uint16_t (*axpe_input)(void *context, uint64_t cycle);
typedef void (*axpe_observe)(void *context, const axpe_model *m);

int axpe_init(axpe_model *m, const uint32_t *program, size_t words,
              uint32_t *stack, size_t depth);
uint8_t axpe_output_enable(const axpe_model *m);
axpe_result axpe_step(axpe_model *m, axpe_input input,
                      axpe_observe observe, void *context);
#endif
