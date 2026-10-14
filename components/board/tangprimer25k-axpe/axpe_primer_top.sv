// Physical FPGA adapter; the axpe core/host/store stay unchanged.
`default_nettype none
`ifndef AXPE_PRIMER_CAPTURE_MODE
`define AXPE_PRIMER_CAPTURE_MODE 0
`endif
`ifndef AXPE_PRIMER_RESET_CYCLES
`define AXPE_PRIMER_RESET_CYCLES 16
`endif

module axpe_primer_top #(
    parameter integer CAPTURE_MODE = `AXPE_PRIMER_CAPTURE_MODE,
    parameter integer RESET_CYCLES = `AXPE_PRIMER_RESET_CYCLES
) (
    input wire clk_50mhz,
    input wire capture_clk,
    input wire button_s1,
    input wire host_sclk,
    input wire host_mosi,
    input wire host_cs_n,
    input wire host_rst_n,
    input wire design_enabled,
    output wire host_miso,
    output wire clock_ref,
    inout wire [7:0] uio
);
    localparam integer RW = $clog2(RESET_CYCLES + 1);
    wire bench_clk;
    generate
        if (CAPTURE_MODE == 0) begin : normal_clock
`ifdef SYNTHESIS
            CLKDIV #(.DIV_MODE("2")) divider (
                .HCLKIN(clk_50mhz), .RESETN(1'b1), .CALIB(1'b0), .CLKOUT(bench_clk));
`else
            reg clock_model;
            initial clock_model = 1'b0;
            always @(posedge clk_50mhz) clock_model <= ~clock_model;
            assign bench_clk = clock_model;
`endif
        end else begin : capture_clock
            assign bench_clk = capture_clk;
        end
    endgenerate
    assign clock_ref = bench_clk;

    wire external_reset = button_s1 || !host_rst_n;
    reg [RW-1:0] reset_count;
    reg [1:0] enabled_sync;
    initial begin reset_count = 0; enabled_sync = 0; end
    always @(posedge bench_clk or posedge external_reset) begin
        if (external_reset) begin
            reset_count <= 0;
            enabled_sync <= 0;
        end else begin
            if (reset_count != RW'(RESET_CYCLES)) reset_count <= reset_count + 1'b1;
            enabled_sync <= {enabled_sync[0], design_enabled};
        end
    end
    wire chip_rst_n = !external_reset && reset_count == RW'(RESET_CYCLES);
    wire [7:0] protocol_out, protocol_oe, result_out, sample_value;
    axpe_chip #(
        .IMEM_WORDS(`AXPE_IMEM_WORDS), .REGS(`AXPE_REGS), .REG_W(`AXPE_REG_W),
        .DELAY_BITS(`AXPE_DELAY_BITS), .CALL_DEPTH(`AXPE_CALL_DEPTH)
    ) chip (
        .clk(bench_clk), .rst_n(chip_rst_n), .ena(enabled_sync[1]),
        .ui_in({5'b0, host_cs_n, host_mosi, host_sclk}), .uo_out(result_out),
        .uio_in(sample_value), .uio_out(protocol_out), .uio_oe(protocol_oe)
    );
    assign host_miso = result_out[0];
    axpe_primer_pads pads(.drive_value(protocol_out), .drive_enable(protocol_oe),
                         .sample_value(sample_value), .pins(uio));
    // The unused result pins remain readable through STATUS on host_miso.
    wire unused_results = &{1'b0, result_out[7:1], clk_50mhz, capture_clk};
endmodule
`default_nettype wire
