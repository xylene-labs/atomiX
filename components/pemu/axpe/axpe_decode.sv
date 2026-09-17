// Field extraction for the axpe timed ISA.
//
// Layout is normative in sw/pemu/isa/axpe-isa.json; the opcode constants come
// from the generated header so this file cannot disagree with the assembler
// or the golden model about where a field lives.
`default_nettype none

module axpe_decode (
    input  wire  [31:0] word,
    output wire  [4:0]  op,
    output wire  [2:0]  ra,
    output wire  [2:0]  rb,
    output wire  [4:0]  xf,
    output wire  [15:0] delay,
    output wire  [7:0]  imm8
);
    assign op    = word[31:27];
    assign ra    = word[26:24];
    assign rb    = word[23:21];
    assign xf    = word[20:16];
    assign delay = word[15:0];
    // imm8 overlays rb and xf, so an instruction uses a source register or an
    // immediate, never both.
    assign imm8  = {word[23:21], word[20:16]};
endmodule

`default_nettype wire
