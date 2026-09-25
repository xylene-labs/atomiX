/*
 * Copyright (c) 2026 Shubhendra Gautam
 * SPDX-License-Identifier: Apache-2.0
 *
 * Tiny Tapeout boundary for axpe.  Profile values arrive as defines generated
 * from components/pemu/axpe/component.json; defaults keep this file useful to
 * standalone linters without turning the ASIC profile into hidden literals.
 */
`default_nettype none

`ifndef AXPE_IMEM_WORDS
`define AXPE_IMEM_WORDS 256
`endif
`ifndef AXPE_REGS
`define AXPE_REGS 8
`endif
`ifndef AXPE_REG_W
`define AXPE_REG_W 16
`endif
`ifndef AXPE_DELAY_BITS
`define AXPE_DELAY_BITS 16
`endif
`ifndef AXPE_CALL_DEPTH
`define AXPE_CALL_DEPTH 4
`endif

module tt_um_shubhgau_atomix_axpe (
    input  wire [7:0] ui_in,
    output wire [7:0] uo_out,
    input  wire [7:0] uio_in,
    output wire [7:0] uio_out,
    output wire [7:0] uio_oe,
    input  wire       ena,
    input  wire       clk,
    input  wire       rst_n
);
    axpe_chip #(
        .IMEM_WORDS(`AXPE_IMEM_WORDS),
        .REGS(`AXPE_REGS),
        .REG_W(`AXPE_REG_W),
        .DELAY_BITS(`AXPE_DELAY_BITS),
        .CALL_DEPTH(`AXPE_CALL_DEPTH)
    ) u_axpe_chip (
        .clk(clk), .rst_n(rst_n), .ena(ena),
        .ui_in(ui_in), .uo_out(uo_out),
        .uio_in(uio_in), .uio_out(uio_out), .uio_oe(uio_oe)
    );
endmodule

`default_nettype wire
