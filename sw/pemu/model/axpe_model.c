#include "axpe_model.h"
#include <string.h>

#define FIELD(w, f) (((w) & AXPE_##f##_MASK) >> AXPE_##f##_LO)

int axpe_init(axpe_model *m, const uint32_t *program, size_t words,
              uint32_t *stack, size_t depth)
{
    if (!m || !program || !words || words > UINT32_MAX || !stack || !depth)
        return -1;
    memset(m, 0, sizeof(*m));
    m->program = program;
    m->words = words;
    m->stack = stack;
    m->depth = depth;
    return 0;
}

uint8_t axpe_output_enable(const axpe_model *m)
{
    return m->direction & (uint8_t)~(m->drain & m->pins);
}

static uint16_t sample(axpe_input input, void *ctx, uint64_t cycle)
{
    return input ? input(ctx, cycle) : 0;
}

static void drive(axpe_model *m, unsigned pin, unsigned level)
{
    uint8_t mask = (uint8_t)(1u << pin);
    m->pins = (uint8_t)((m->pins & (uint8_t)~mask) | (level ? mask : 0));
}

static void tick(axpe_model *m, axpe_observe observe, void *ctx)
{
    if (observe) observe(ctx, m);
    ++m->cycles;
}

static int condition(const axpe_model *m, unsigned a)
{
    switch (a) {
    case 0: return 1;
    case 1: return m->z;
    case 2: return !m->z;
    case 3: return m->c;
    case 4: return !m->c;
    case 5: return m->t;
    case 6: return !m->t;
    default: return 0;
    }
}

axpe_result axpe_step(axpe_model *m, axpe_input input,
                      axpe_observe observe, void *ctx)
{
    if (m->status != AXPE_OK) return m->status;
    if (m->pc >= m->words) return m->status = AXPE_FETCH;
    uint32_t w = m->program[m->pc];
    unsigned op = FIELD(w, OP), a = FIELD(w, A), b = FIELD(w, B);
    unsigned x = FIELD(w, X), d = FIELD(w, DELAY), imm = (b << 5) | x;
    unsigned next = m->pc + 1;
    /* A shift's cell duration: the encoded D, or the period register when the
     * instruction's P bit selects it. Both are max(.,1), so the shortest cell
     * is one cycle either way and a period register left at zero shifts at
     * full rate rather than stalling. */
    const unsigned psel = (axpe_timing_of[op] == AXPE_TIMING_PERBIT) &&
                          ((b & AXPE_SHIFT_B_P_MASK) >> AXPE_SHIFT_B_P_LO);
    const unsigned shift_cell = (psel ? (m->period ? m->period : 1u)
                                      : (d ? d : 1u));
    uint32_t value = m->r[a];
    uint32_t rhs = m->r[b];
    int halt = 0;

    /* Reject unsupported/invalid instructions before changing observable state. */
    if (!axpe_mnemonic_of[op] ||
        (op == AXPE_OP_BR && a == 7) ||
        ((op == AXPE_OP_SHL || op == AXPE_OP_SHR) && x > AXPE_REG_W) ||
        (op == AXPE_OP_WAITE && imm > 63))
        return m->status = AXPE_ENCODING;
    if (axpe_timing_of[op] == AXPE_TIMING_PERBIT) {
        if (!x || x > AXPE_REG_W) return m->status = AXPE_ENCODING;
        /* The rest of b is reserved. Refusing it now is what keeps those bits
         * available: firmware that set them meaninglessly and worked would
         * make any later use of them a compatibility break. */
        if (b & AXPE_SHIFT_B_RSV_MASK) return m->status = AXPE_ENCODING;
        unsigned cfg_clk = m->shcfg & 15;
        unsigned cfg_dout = (m->shcfg >> 4) & 15;
        unsigned cfg_din = (m->shcfg >> 8) & 15;
        /* Anything that emits needs a drivable pin; uio is 0..7. */
        if (op != AXPE_OP_SHIN && cfg_dout >= 8)
            return m->status = AXPE_UNSUPPORTED;
        if (cfg_clk != 15) {
            /* A clocked cell splits at its half point, so it needs an even,
             * non-zero period. SHCFG is loaded from a register, so neither
             * this nor the aliasing rule below can be an assembler error --
             * the machine is the only place that knows the configuration.
             * The test is against the cell the transfer will actually use, so
             * a period register holding an odd or too-short value is refused
             * exactly as an odd D is. That value came from measuring a peer,
             * which makes it a reachable case rather than a theoretical one. */
            if (cfg_clk >= 8 || (shift_cell & 1u) || shift_cell < 2u)
                return m->status = AXPE_UNSUPPORTED;
            /* din == dout is legal and is what I2C's SDA is. A clock sharing
             * a pin with either data line is not. */
            if (cfg_clk == cfg_dout || cfg_clk == cfg_din)
                return m->status = AXPE_UNSUPPORTED;
        }
    }
    if ((op == AXPE_OP_CALL && m->sp == m->depth) ||
        (op == AXPE_OP_RET && !m->sp))
        return m->status = AXPE_STACK;
    if ((op == AXPE_OP_CALL || (op == AXPE_OP_BR && condition(m, a))) &&
        imm >= m->words) return m->status = AXPE_FETCH;

    if (op == AXPE_OP_WAITE) {
        unsigned pin = imm & 15, edge = imm >> 4, waited = 0;
        unsigned timeout = d ? d : 1u;
        unsigned prev = (sample(input, ctx, m->cycles) >> pin) & 1;
        while (waited < timeout) {
            if (edge == 3 && prev) break;
            tick(m, observe, ctx);
            ++waited;
            unsigned now = (sample(input, ctx, m->cycles) >> pin) & 1;
            int hit = edge == 0 ? (!prev && now) :
                      edge == 1 ? (prev && !now) :
                      edge == 2 ? (prev != now) : now;
            prev = now;
            if (hit) break;
        }
        m->r[a] = (uint16_t)waited;
        m->t = waited == timeout;
        if (!waited) tick(m, observe, ctx);
    } else if (axpe_timing_of[op] == AXPE_TIMING_PERBIT) {
        unsigned din = (m->shcfg >> 8) & 15;
        unsigned dout = (m->shcfg >> 4) & 15;
        unsigned msb = (m->shcfg >> 12) & 1;
        unsigned clk = m->shcfg & 15;
        unsigned cpol = (m->shcfg >> 13) & 1;
        unsigned cpha = (m->shcfg >> 14) & 1;
        const unsigned cell = shift_cell;
        uint16_t received = 0;
        if (clk == 15) {
            /* Unclocked: emit or sample at each cell's first edge and hold. */
            for (unsigned bit = 0; bit < x; ++bit) {
                unsigned pos = msb ? x - 1 - bit : bit;
                if (op != AXPE_OP_SHIN) drive(m, dout, (value >> pos) & 1);
                if (op != AXPE_OP_SHOUT)
                    received |= ((sample(input, ctx, m->cycles) >> din) & 1) << pos;
                for (unsigned hold = 0; hold < cell; ++hold) tick(m, observe, ctx);
            }
        } else {
            /* Clocked: the cell splits at its half point. Data changes at the
             * cell start, the clock takes its leading edge at d/2, and cpha
             * selects which edge samples. cpol is the clock's idle level.
             * Guaranteed even and non-zero by the guard above. */
            unsigned half = cell / 2u;
            drive(m, clk, cpol);
            for (unsigned bit = 0; bit < x; ++bit) {
                unsigned pos = msb ? x - 1 - bit : bit;
                if (!cpha && op != AXPE_OP_SHIN) drive(m, dout, (value >> pos) & 1);
                for (unsigned hold = 0; hold < half; ++hold) tick(m, observe, ctx);
                drive(m, clk, !cpol);                        /* leading edge */
                if (cpha) {
                    if (op != AXPE_OP_SHIN) drive(m, dout, (value >> pos) & 1);
                } else if (op != AXPE_OP_SHOUT) {
                    received |= ((sample(input, ctx, m->cycles) >> din) & 1) << pos;
                }
                for (unsigned hold = 0; hold < half; ++hold) tick(m, observe, ctx);
                drive(m, clk, cpol);                         /* trailing edge */
                if (cpha && op != AXPE_OP_SHOUT)
                    received |= ((sample(input, ctx, m->cycles) >> din) & 1) << pos;
            }
        }
        if (op != AXPE_OP_SHOUT) m->r[a] = received;
    } else {
        switch (op) {
        case AXPE_OP_DELAY: break;
        case AXPE_OP_PINSET: m->pins |= imm; break;
        case AXPE_OP_PINCLR: m->pins &= (uint8_t)~imm; break;
        case AXPE_OP_PINTOG: m->pins ^= imm; break;
        case AXPE_OP_PINW: m->pins = value; break;
        case AXPE_OP_POUT: m->outputs = value; break;
        case AXPE_OP_PINR: m->r[a] = sample(input, ctx, m->cycles); break;
        case AXPE_OP_PDIR: m->direction = imm; break;
        case AXPE_OP_PDRN: m->drain = imm; break;
        case AXPE_OP_SHCFG: m->shcfg = value & 0x7fff; break;
        case AXPE_OP_SHPER: m->period = value; break;
        case AXPE_OP_MOV: m->r[a] = rhs; break;
        case AXPE_OP_ADD:
        case AXPE_OP_ADDI:
            value += op == AXPE_OP_ADDI ? imm : rhs;
            m->r[a] = value; m->z = m->r[a] == 0; m->c = value > UINT16_MAX;
            break;
        case AXPE_OP_SUB:
        case AXPE_OP_CMP:
            m->c = value < rhs; m->z = value == rhs;
            if (op == AXPE_OP_SUB) m->r[a] = value - rhs;
            break;
        case AXPE_OP_AND: m->r[a] &= rhs; m->z = m->r[a] == 0; break;
        case AXPE_OP_OR: m->r[a] |= rhs; m->z = m->r[a] == 0; break;
        case AXPE_OP_XOR: m->r[a] ^= rhs; m->z = m->r[a] == 0; break;
        case AXPE_OP_SHL:
            if (x) { m->c = (value >> (AXPE_REG_W - x)) & 1; m->r[a] = value << x; }
            break;
        case AXPE_OP_SHR:
            if (x) { m->c = (value >> (x - 1)) & 1; m->r[a] = value >> x; }
            break;
        case AXPE_OP_LDIL: m->r[a] = (value & 0xff00) | imm; break;
        case AXPE_OP_LDIH: m->r[a] = (value & 0xff) | (imm << 8); break;
        case AXPE_OP_BR: if (condition(m, a)) next = imm; break;
        case AXPE_OP_CALL: m->stack[m->sp++] = next; next = imm; break;
        case AXPE_OP_RET: next = m->stack[--m->sp]; break;
        case AXPE_OP_HALT: halt = 1; break;
        default: return m->status = AXPE_ENCODING;
        }
        for (unsigned hold = 0; hold < (d ? d : 1u); ++hold) tick(m, observe, ctx);
    }
    m->pc = next;
    ++m->retired;
    if (halt) m->status = AXPE_HALTED;
    return m->status;
}
