/* Generated from axpe-isa.json. Do not edit.
 * Regenerate with: python3 tools/axpe_isa.py generate */

#ifndef AXPE_ISA_H
#define AXPE_ISA_H

#include <stdint.h>

#define AXPE_REGS  8
#define AXPE_REG_W 16

#define AXPE_OP_LO   27
#define AXPE_OP_MASK 0xf8000000u
#define AXPE_A_LO   24
#define AXPE_A_MASK 0x07000000u
#define AXPE_B_LO   21
#define AXPE_B_MASK 0x00e00000u
#define AXPE_X_LO   16
#define AXPE_X_MASK 0x001f0000u
#define AXPE_DELAY_LO   0
#define AXPE_DELAY_MASK 0x0000ffffu
/* Bits inside the b field: shift_b_layout */
#define AXPE_SHIFT_B_P_LO   0
#define AXPE_SHIFT_B_P_MASK 0x01u
#define AXPE_SHIFT_B_RSV_LO   1
#define AXPE_SHIFT_B_RSV_MASK 0x06u

typedef enum {
    AXPE_OP_DELAY = 0,
    AXPE_OP_PINSET = 1,
    AXPE_OP_PINCLR = 2,
    AXPE_OP_PINTOG = 3,
    AXPE_OP_PINW = 4,
    AXPE_OP_POUT = 5,
    AXPE_OP_PINR = 6,
    AXPE_OP_PDIR = 7,
    AXPE_OP_PDRN = 8,
    AXPE_OP_WAITE = 9,
    AXPE_OP_SHCFG = 10,
    AXPE_OP_SHOUT = 11,
    AXPE_OP_SHIN = 12,
    AXPE_OP_SHIO = 13,
    AXPE_OP_SHPER = 14,
    AXPE_OP_MOV = 16,
    AXPE_OP_ADD = 17,
    AXPE_OP_SUB = 18,
    AXPE_OP_AND = 19,
    AXPE_OP_OR = 20,
    AXPE_OP_XOR = 21,
    AXPE_OP_SHL = 22,
    AXPE_OP_SHR = 23,
    AXPE_OP_LDIL = 24,
    AXPE_OP_LDIH = 25,
    AXPE_OP_ADDI = 26,
    AXPE_OP_CMP = 27,
    AXPE_OP_BR = 28,
    AXPE_OP_CALL = 29,
    AXPE_OP_RET = 30,
    AXPE_OP_HALT = 31,
} axpe_opcode_t;

/* How each opcode spends cycles. */
typedef enum {
    AXPE_TIMING_FIXED,  /* max(D,1) */
    AXPE_TIMING_PERBIT,  /* n*max(D,1) */
    AXPE_TIMING_PERBIT_REG,  /* n*max(P,1) */
    AXPE_TIMING_BOUNDED,  /* w, 1<=w<=max(D,1) */
} axpe_timing_t;

static const axpe_timing_t axpe_timing_of[32] = {
    [0] = AXPE_TIMING_FIXED,  /* DELAY */
    [1] = AXPE_TIMING_FIXED,  /* PINSET */
    [2] = AXPE_TIMING_FIXED,  /* PINCLR */
    [3] = AXPE_TIMING_FIXED,  /* PINTOG */
    [4] = AXPE_TIMING_FIXED,  /* PINW */
    [5] = AXPE_TIMING_FIXED,  /* POUT */
    [6] = AXPE_TIMING_FIXED,  /* PINR */
    [7] = AXPE_TIMING_FIXED,  /* PDIR */
    [8] = AXPE_TIMING_FIXED,  /* PDRN */
    [9] = AXPE_TIMING_BOUNDED,  /* WAITE */
    [10] = AXPE_TIMING_FIXED,  /* SHCFG */
    [11] = AXPE_TIMING_PERBIT,  /* SHOUT */
    [12] = AXPE_TIMING_PERBIT,  /* SHIN */
    [13] = AXPE_TIMING_PERBIT,  /* SHIO */
    [14] = AXPE_TIMING_FIXED,  /* SHPER */
    [15] = AXPE_TIMING_FIXED,  /* reserved */
    [16] = AXPE_TIMING_FIXED,  /* MOV */
    [17] = AXPE_TIMING_FIXED,  /* ADD */
    [18] = AXPE_TIMING_FIXED,  /* SUB */
    [19] = AXPE_TIMING_FIXED,  /* AND */
    [20] = AXPE_TIMING_FIXED,  /* OR */
    [21] = AXPE_TIMING_FIXED,  /* XOR */
    [22] = AXPE_TIMING_FIXED,  /* SHL */
    [23] = AXPE_TIMING_FIXED,  /* SHR */
    [24] = AXPE_TIMING_FIXED,  /* LDIL */
    [25] = AXPE_TIMING_FIXED,  /* LDIH */
    [26] = AXPE_TIMING_FIXED,  /* ADDI */
    [27] = AXPE_TIMING_FIXED,  /* CMP */
    [28] = AXPE_TIMING_FIXED,  /* BR */
    [29] = AXPE_TIMING_FIXED,  /* CALL */
    [30] = AXPE_TIMING_FIXED,  /* RET */
    [31] = AXPE_TIMING_FIXED,  /* HALT */
};

static const char *const axpe_mnemonic_of[32] = {
    [0] = "DELAY",
    [1] = "PINSET",
    [2] = "PINCLR",
    [3] = "PINTOG",
    [4] = "PINW",
    [5] = "POUT",
    [6] = "PINR",
    [7] = "PDIR",
    [8] = "PDRN",
    [9] = "WAITE",
    [10] = "SHCFG",
    [11] = "SHOUT",
    [12] = "SHIN",
    [13] = "SHIO",
    [14] = "SHPER",
    [15] = 0,
    [16] = "MOV",
    [17] = "ADD",
    [18] = "SUB",
    [19] = "AND",
    [20] = "OR",
    [21] = "XOR",
    [22] = "SHL",
    [23] = "SHR",
    [24] = "LDIL",
    [25] = "LDIH",
    [26] = "ADDI",
    [27] = "CMP",
    [28] = "BR",
    [29] = "CALL",
    [30] = "RET",
    [31] = "HALT",
};

#endif /* AXPE_ISA_H */
