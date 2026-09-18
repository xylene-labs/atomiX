// The host port: what makes a fabricated axpe reprogrammable.
//
// A protocol emulator whose program arrives with the mask is not one. The
// competition's requirement is that a packaged part can be given a different
// protocol after fabrication, so the chip carries a fixed-logic loader that
// firmware can neither replace nor depend on -- firmware cannot load itself,
// which is the whole reason this block is gates rather than instructions.
//
// It is an SPI target because that costs four pins and a shift register, and
// because any host already has one: a PC's USB bridge, the Tang Primer during
// PE-09 bring-up, or the Pi Pico 2 that is already a protocol peer. Mode 0,
// MSB first: MOSI is sampled on the rising edge and MISO changes on the
// falling one. `sclk` is asynchronous to `clk` and is synchronized here, so it
// must stay at or below `clk/4`; that bound is part of the contract in
// docs/pemu-host-protocol.md, not an implementation detail.
//
// Writes are refused while the core runs, rather than arbitrated. The store is
// single-port because the SRAM macro is, so there is no cycle in which both a
// fetch and a write can happen, and a loader that pretended otherwise would
// work in simulation and fail in silicon. A refused write sets a status bit:
// silently dropping it is how a host ends up running the previous program and
// believing it loaded a new one.
`default_nettype none

module axpe_host #(
    parameter int WORDS     = 256,
    parameter int WORD_BITS = 32
) (
    input  wire                     clk,
    input  wire                     rst_n,

    // Host pads, asynchronous.
    input  wire                     sclk_pad,
    input  wire                     mosi_pad,
    input  wire                     cs_n_pad,
    output reg                      miso,
    output wire                     selected,   // drive MISO onto the pad

    // Instruction store, single port and shared with the core.
    output reg  [$clog2(WORDS)-1:0] addr,
    output wire                     we,
    output wire [WORD_BITS-1:0]     wdata,
    input  wire [WORD_BITS-1:0]     rdata,

    // Core control and observation.
    output reg                      running,
    input  wire                     core_halted,
    input  wire                     core_fault,
    input  wire [7:0]               core_out
);
    localparam int AW = $clog2(WORDS);

    localparam [7:0] CMD_WRITE  = 8'h01;
    localparam [7:0] CMD_READ   = 8'h02;
    localparam [7:0] CMD_RUN    = 8'h03;
    localparam [7:0] CMD_STOP   = 8'h04;
    localparam [7:0] CMD_STATUS = 8'h05;

    // Two flops per pad, then an edge detector. One flop would sample a signal
    // that is changing, and the failure it produces is a program loaded with
    // one wrong bit, which reads as a firmware bug for a long time.
    reg sclk_meta, sclk_s, sclk_prev;
    reg mosi_meta, mosi_s;
    reg cs_meta,   cs_s, cs_prev;

    wire sel        = ~cs_s;
    wire frame_end  = cs_s && ~cs_prev;
    wire sclk_rise  = sel &&  sclk_s && ~sclk_prev;
    wire sclk_fall  = sel && ~sclk_s &&  sclk_prev;

    assign selected = sel;

    reg [5:0]           bitcnt;     // index of the bit being received, 0..47
    reg [7:0]           cmd;
    reg [WORD_BITS-1:0] sreg;       // one register, shifted in and out
    reg                 refused;

    wire [7:0] byte_now = {sreg[6:0], mosi_s};
    wire [WORD_BITS-1:0] word_now = {sreg[WORD_BITS-2:0], mosi_s};
    // The address field is eight bits because the ISA's own branch target is:
    // a store deeper than 256 words holds instructions nothing can jump to, so
    // the host cannot address them either. See docs/protocol-emulator.md 2.1.
    // How many of those bits survive depends on WORDS, exactly as the branch
    // target's do in axpe.sv; below 256 words the top ones are genuinely
    // unused rather than dropped by accident.
    /* verilator lint_off UNUSEDSIGNAL */
    wire [15:0] addr_wide = {8'd0, byte_now};
    /* verilator lint_on UNUSEDSIGNAL */

    wire [7:0] status = {4'd0, refused, core_fault, core_halted, running};

    // A write commits on the final data bit, so a frame the host abandons
    // part way through never half-writes a word.
    assign we    = sclk_rise && (bitcnt == 6'd47) && (cmd == CMD_WRITE) && !running;
    assign wdata = word_now;

    wire load_read   = (cmd == CMD_READ)   && (bitcnt == 6'd16);
    wire load_status = (cmd == CMD_STATUS) && (bitcnt == 6'd8);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            sclk_meta <= 1'b0; sclk_s <= 1'b0; sclk_prev <= 1'b0;
            mosi_meta <= 1'b0; mosi_s <= 1'b0;
            cs_meta   <= 1'b1; cs_s   <= 1'b1; cs_prev <= 1'b1;
            bitcnt    <= 6'd0;
            cmd       <= 8'd0;
            sreg      <= {WORD_BITS{1'b0}};
            addr      <= {AW{1'b0}};
            miso      <= 1'b0;
            running   <= 1'b0;
            refused   <= 1'b0;
        end else begin
            {sclk_s, sclk_meta} <= {sclk_meta, sclk_pad};
            {mosi_s, mosi_meta} <= {mosi_meta, mosi_pad};
            {cs_s,   cs_meta}   <= {cs_meta,   cs_n_pad};
            sclk_prev <= sclk_s;
            cs_prev   <= cs_s;

            // A control command takes effect when its frame ends, not on its
            // last bit. Two reasons, and the second is the load-bearing one:
            // a frame the host abandons mid-byte commits nothing, and the core
            // never starts while the host still holds CS and is driving MISO
            // onto a pad that running firmware owns.
            if (frame_end && bitcnt >= 6'd8) begin
                if (cmd == CMD_RUN)  running <= 1'b1;
                if (cmd == CMD_STOP) begin
                    running <= 1'b0;
                    refused <= 1'b0;
                end
            end

            if (!sel) begin
                bitcnt <= 6'd0;
                cmd    <= 8'd0;
                miso   <= 1'b0;
            end else begin
                if (sclk_rise) begin
                    sreg   <= word_now;
                    bitcnt <= bitcnt + 6'd1;

                    if (bitcnt == 6'd7) cmd <= byte_now;
                    if (bitcnt == 6'd15) addr <= addr_wide[AW-1:0];
                    if (bitcnt == 6'd47 && cmd == CMD_WRITE && running)
                        refused <= 1'b1;
                end

                if (sclk_fall) begin
                    if (load_read) begin
                        sreg <= rdata;
                        miso <= rdata[WORD_BITS-1];
                    end else if (load_status) begin
                        sreg <= {status, core_out, {(WORD_BITS-16){1'b0}}};
                        miso <= status[7];
                    end else begin
                        miso <= sreg[WORD_BITS-1];
                    end
                end
            end
        end
    end
endmodule

`default_nettype wire
