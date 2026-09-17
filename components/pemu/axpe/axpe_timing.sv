// The cell timer: the one place the ISA's occupancy rule exists in hardware.
//
// A cell occupies exactly max(D,1) cycles. D is the cell duration, not an
// addition to a fetch cycle, which is what lets a waveform edge land on an
// exact multiple of its bit period. Keeping the rule in a single module is
// what makes the PE-06 timing proof a property of one small block rather than
// an argument about the whole datapath.
`default_nettype none

module axpe_timing #(
    parameter int DELAY_BITS = 16
) (
    input  wire                   clk,
    input  wire                   rst_n,
    input  wire                   load,    // begin a cell this cycle
    input  wire [DELAY_BITS-1:0]  delay,   // D, straight from the encoding
    output wire                   last     // final cycle of the current cell
);
    reg [DELAY_BITS-1:0] remaining;

    // max(D,1): a zero delay is the cheapest instruction, not an illegal one.
    wire [DELAY_BITS-1:0] cell_cycles =
        (delay == {DELAY_BITS{1'b0}}) ? {{(DELAY_BITS-1){1'b0}}, 1'b1} : delay;

    assign last = (remaining == {{(DELAY_BITS-1){1'b0}}, 1'b1});

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            remaining <= {DELAY_BITS{1'b0}};
        else if (load)
            remaining <= cell_cycles;
        else if (remaining != {DELAY_BITS{1'b0}})
            remaining <= remaining - 1'b1;
    end
endmodule

`default_nettype wire
