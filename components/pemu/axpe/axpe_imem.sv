// The writable instruction store.
//
// Single port, synchronous read, one address shared by reads and writes --
// deliberately the shape a future technology memory must preserve.  The
// pinned CMOS5L PDK has no compatible SRAM macro views, so PE-02 first measures
// a 64-word inferred-cell fallback rather than importing an SG13G2 macro into a
// different technology.  In particular there is exactly one address port, so
// the host cannot write while the core fetches; the host contract makes that a
// rule rather than a race, by refusing writes while the core is running.
//
// A write cycle does not produce read data.  `rdata` holds during a write
// instead of quietly forwarding, so firmware cannot depend on a read-during-
// write behavior that a later technology memory may not provide.
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
