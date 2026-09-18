// The chip: core, writable instruction store and host port, in the Tiny
// Tapeout pin shape.
//
// This is the level at which "programmable after fabrication" is true or
// false, so it is the level the two-program test in sim/pemu drives. Below it
// the core has no memory of its own; above it there is nothing left to add.
//
// Pin budget, frozen in docs/pemu-host-protocol.md:
//
//   ui_in[0]  host SCLK      uo_out[0] host MISO while selected, else firmware
//   ui_in[1]  host MOSI      uo_out[1..7] firmware
//   ui_in[2]  host CS_n      uio[0..7] firmware, the protocol pins
//   ui_in[3..7] firmware
//
// The host takes three of eight inputs and borrows one output, and leaves
// every bidirectional pin to firmware -- UART, SPI and I2C need the open-drain
// path and the loader does not. MISO only reaches the pad while CS is
// asserted, so firmware keeps all eight output bits whenever the host is not
// mid-frame, rather than permanently losing one to a port it uses between
// programs.
//
// The store's address is the host's while stopped and the core's while
// running, because a single-port macro has one. `core_run` lags `running` by a
// cycle on purpose: the store switches to the core's address first, captures
// word zero, and only then is the core released, so its first instruction is
// there when it starts. Reversing those two is a chip that executes whatever
// address the loader last touched.
`default_nettype none

module axpe_chip #(
    parameter int IMEM_WORDS = 256,
    parameter int REGS       = 8,
    parameter int REG_W      = 16,
    parameter int DELAY_BITS = 16,
    parameter int CALL_DEPTH = 4
) (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       ena,
    input  wire [7:0] ui_in,
    output wire [7:0] uo_out,
    input  wire [7:0] uio_in,
    output wire [7:0] uio_out,
    output wire [7:0] uio_oe
);
    localparam int AW = $clog2(IMEM_WORDS);

    wire [AW-1:0] core_addr, host_addr, mem_addr;
    wire [31:0]   mem_rdata, host_wdata;
    wire          host_we, running, selected, miso;
    wire          core_halted, core_fault;
    wire [7:0]    core_out;
    wire [7:0]    core_uio_out, core_uio_oe;

    reg core_run;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) core_run <= 1'b0;
        else        core_run <= running;
    end

    wire core_rst_n = rst_n && ena && core_run;

    assign mem_addr = running ? core_addr : host_addr;

    axpe_imem #(.WORDS(IMEM_WORDS), .WORD_BITS(32)) u_imem (
        .clk(clk), .addr(mem_addr), .we(host_we),
        .wdata(host_wdata), .rdata(mem_rdata)
    );

    axpe_host #(.WORDS(IMEM_WORDS), .WORD_BITS(32)) u_host (
        .clk(clk), .rst_n(rst_n),
        .sclk_pad(ui_in[0]), .mosi_pad(ui_in[1]), .cs_n_pad(ui_in[2]),
        .miso(miso), .selected(selected),
        .addr(host_addr), .we(host_we), .wdata(host_wdata), .rdata(mem_rdata),
        .running(running),
        .core_halted(core_halted), .core_fault(core_fault), .core_out(core_out)
    );

    axpe #(
        .IMEM_WORDS(IMEM_WORDS), .REGS(REGS), .REG_W(REG_W),
        .DELAY_BITS(DELAY_BITS), .UIO_PINS(8), .CALL_DEPTH(CALL_DEPTH)
    ) u_core (
        .clk(clk), .rst_n(core_rst_n),
        .ui_in(ui_in), .uo_out(core_out),
        .uio_in(uio_in), .uio_out(core_uio_out), .uio_oe(core_uio_oe),
        .imem_addr(core_addr), .imem_data(mem_rdata),
        .halted(core_halted), .fault(core_fault)
    );

    assign uo_out  = {core_out[7:1], selected ? miso : core_out[0]};
    assign uio_out = core_uio_out;
    assign uio_oe  = core_uio_oe;
endmodule

`default_nettype wire
