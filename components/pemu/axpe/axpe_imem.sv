// The writable instruction store.
//
// Single port, synchronous read, one address shared by reads and writes --
// deliberately the shape an IHP SG13G2 SRAM macro has, because PE-02 replaces
// the cells below with one and a behavioural model that is more capable than
// the macro would hide the integration cost rather than measure it. In
// particular there is exactly one address port, so the host cannot write while
// the core fetches; the host contract makes that a rule rather than a race, by
// refusing writes while the core is running.
//
// A write cycle does not produce read data. The macro does not promise it, so
// neither does this: `rdata` holds during a write instead of quietly
// forwarding, which is what would let firmware depend on behaviour the silicon
// will not have.
`default_nettype none

module axpe_imem #(
    parameter int WORDS     = 256,
    parameter int WORD_BITS = 32
) (
    input  wire                        clk,
    input  wire [$clog2(WORDS)-1:0]    addr,
    input  wire                        we,
    input  wire [WORD_BITS-1:0]        wdata,
    output reg  [WORD_BITS-1:0]        rdata
);
    reg [WORD_BITS-1:0] cells [0:WORDS-1];

    always @(posedge clk) begin
        if (we) cells[addr] <= wdata;
        else    rdata       <= cells[addr];
    end
endmodule

`default_nettype wire
