// Digital backplane for the real FPGA adapter. External peers supply resolved
// levels on released pins; the adapter's drive/enable pair stays observable.
module axpe_primer_sim (
    input wire clk_50mhz, capture_clk, host_rst_n, design_enabled, button_s1,
    input wire host_sclk, host_mosi, host_cs_n,
    input wire [7:0] peer_value,
    output wire clock_ref, host_miso,
    output wire [7:0] mon_out, mon_oe, mon_result
);
    wire [7:0] pads;
    axpe_primer_top dut (
        .clk_50mhz(clk_50mhz), .capture_clk(capture_clk), .host_rst_n(host_rst_n),
        .design_enabled(design_enabled), .button_s1(button_s1),
        .host_sclk(host_sclk), .host_mosi(host_mosi), .host_cs_n(host_cs_n),
        .clock_ref(clock_ref), .host_miso(host_miso), .uio(pads));
    assign mon_out = dut.protocol_out;
    assign mon_oe = dut.protocol_oe;
    assign mon_result = dut.result_out;
    genvar pin;
    generate for (pin=0; pin<8; pin=pin+1) begin
        assign pads[pin] = !mon_oe[pin] ? peer_value[pin] : 1'bz;
    end endgenerate
endmodule
