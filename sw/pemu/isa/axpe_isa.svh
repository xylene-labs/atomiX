// Generated from axpe-isa.json. Do not edit.
// Regenerate with: python3 tools/axpe_isa.py generate

`ifndef AXPE_ISA_SVH
`define AXPE_ISA_SVH

// This header exports the whole instruction set. A consumer using a
// subset of it is the normal case, not a defect.
/* verilator lint_off UNUSEDPARAM */

localparam int AXPE_WORD_W = 32;
localparam int AXPE_REGS   = 8;
localparam int AXPE_REG_W  = 16;

// Field positions
localparam int AXPE_OP_HI = 31;
localparam int AXPE_OP_LO = 27;
localparam int AXPE_A_HI = 26;
localparam int AXPE_A_LO = 24;
localparam int AXPE_B_HI = 23;
localparam int AXPE_B_LO = 21;
localparam int AXPE_X_HI = 20;
localparam int AXPE_X_LO = 16;
localparam int AXPE_DELAY_HI = 15;
localparam int AXPE_DELAY_LO = 0;

// Opcodes
localparam logic [4:0] AXPE_OP_DELAY = 5'd0;
localparam logic [4:0] AXPE_OP_PINSET = 5'd1;
localparam logic [4:0] AXPE_OP_PINCLR = 5'd2;
localparam logic [4:0] AXPE_OP_PINTOG = 5'd3;
localparam logic [4:0] AXPE_OP_PINW = 5'd4;
localparam logic [4:0] AXPE_OP_POUT = 5'd5;
localparam logic [4:0] AXPE_OP_PINR = 5'd6;
localparam logic [4:0] AXPE_OP_PDIR = 5'd7;
localparam logic [4:0] AXPE_OP_PDRN = 5'd8;
localparam logic [4:0] AXPE_OP_WAITE = 5'd9;
localparam logic [4:0] AXPE_OP_SHCFG = 5'd10;
localparam logic [4:0] AXPE_OP_SHOUT = 5'd11;
localparam logic [4:0] AXPE_OP_SHIN = 5'd12;
localparam logic [4:0] AXPE_OP_SHIO = 5'd13;
localparam logic [4:0] AXPE_OP_MOV = 5'd16;
localparam logic [4:0] AXPE_OP_ADD = 5'd17;
localparam logic [4:0] AXPE_OP_SUB = 5'd18;
localparam logic [4:0] AXPE_OP_AND = 5'd19;
localparam logic [4:0] AXPE_OP_OR = 5'd20;
localparam logic [4:0] AXPE_OP_XOR = 5'd21;
localparam logic [4:0] AXPE_OP_SHL = 5'd22;
localparam logic [4:0] AXPE_OP_SHR = 5'd23;
localparam logic [4:0] AXPE_OP_LDIL = 5'd24;
localparam logic [4:0] AXPE_OP_LDIH = 5'd25;
localparam logic [4:0] AXPE_OP_ADDI = 5'd26;
localparam logic [4:0] AXPE_OP_CMP = 5'd27;
localparam logic [4:0] AXPE_OP_BR = 5'd28;
localparam logic [4:0] AXPE_OP_CALL = 5'd29;
localparam logic [4:0] AXPE_OP_RET = 5'd30;
localparam logic [4:0] AXPE_OP_HALT = 5'd31;

// Branch conditions
localparam logic [2:0] AXPE_COND_ALWAYS = 3'd0;
localparam logic [2:0] AXPE_COND_Z = 3'd1;
localparam logic [2:0] AXPE_COND_NZ = 3'd2;
localparam logic [2:0] AXPE_COND_C = 3'd3;
localparam logic [2:0] AXPE_COND_NC = 3'd4;
localparam logic [2:0] AXPE_COND_T = 3'd5;
localparam logic [2:0] AXPE_COND_NT = 3'd6;

/* verilator lint_on UNUSEDPARAM */
`endif
