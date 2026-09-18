// The shift engine: n bit cells of exactly max(D,1) cycles each.
//
// Unclocked (SHCFG clk == 15) is how UART borrows this engine: a bit is
// emitted or sampled at each cell's first edge and held for the cell.
//
// Clocked cells split at the half point, per axpe-isa.md 5.1: data changes at
// the cell start, or on the leading edge when cpha=1; the clock takes its
// leading edge at D/2 and returns to cpol at D; cpha selects which edge
// samples. cpol and cpha together give SPI modes 0 through 3.
//
// The caller guarantees an even, non-zero D for a clocked shift, and that the
// clock does not alias either data pin. Those are machine rejects in axpe.sv,
// because SHCFG is loaded from a register and is invisible at assembly time.
//
// A transfer outlives the instruction word that started it. The core advances
// the program counter at issue, so by the second cell `imem_data` already
// holds the next instruction; what the remaining cells need is latched here at
// `start`. The transfer also retires *on* its last cell's final cycle rather
// than a cycle later, so the next instruction -- which may be another shift --
// issues on that same cycle, and `start` is accepted while finishing.
`default_nettype none

module axpe_shift #(
    parameter int REG_W      = 16,
    parameter int UIO_PINS   = 8,
    parameter int DELAY_BITS = 16
) (
    input  wire                   clk,
    input  wire                   rst_n,
    input  wire                   start,        // one-cycle issue pulse
    input  wire [4:0]             nbits,        // 1..REG_W
    input  wire [DELAY_BITS-1:0]  delay,        // D, the cell duration
    input  wire [14:0]            shcfg,
    input  wire [REG_W-1:0]       tx_value,
    input  wire                   drive_data,   // SHOUT and SHIO emit
    input  wire                   take_data,    // SHIN and SHIO sample
    input  wire [15:0]            pad_in,       // {ui_in, uio_in}
    output reg  [UIO_PINS-1:0]    set_mask,     // pins written this cycle
    output reg  [UIO_PINS-1:0]    set_value,
    output reg  [REG_W-1:0]       rx_value,
    output wire                   busy,
    output wire                   done,
    output wire                   rx_we         // `done` carries a value for Ra
);
    localparam [1:0] S_IDLE  = 2'd0;
    localparam [1:0] S_UNCLK = 2'd1;
    localparam [1:0] S_CLK_A = 2'd2;   // first half, clock at cpol
    localparam [1:0] S_CLK_B = 2'd3;   // second half, clock at ~cpol

    wire [3:0] cfg_clk  = shcfg[3:0];
    wire [3:0] cfg_dout = shcfg[7:4];
    wire [3:0] cfg_din  = shcfg[11:8];
    wire       cfg_ord  = shcfg[12];
    wire       cfg_cpol = shcfg[13];
    wire       cfg_cpha = shcfg[14];
    wire       clocked  = (cfg_clk != 4'hF);

    reg  [1:0]  state;
    reg  [4:0]  index;          // which bit of the transfer
    reg  [4:0]  total;
    reg  [REG_W-1:0] rx_latch;
    reg  [REG_W-1:0] tx_latch;  // the operand, held for the whole transfer
    reg              drive_q, take_q;

    wire timer_last;
    reg  timer_load;
    reg  [DELAY_BITS-1:0] timer_delay;

    axpe_timing #(.DELAY_BITS(DELAY_BITS)) u_cell (
        .clk(clk), .rst_n(rst_n),
        .load(timer_load), .delay(timer_delay), .last(timer_last)
    );

    // Half a cell. D is guaranteed even and non-zero when clocked.
    wire [DELAY_BITS-1:0] half = {1'b0, delay[DELAY_BITS-1:1]};
    wire [DELAY_BITS-1:0] whole =
        (delay == {DELAY_BITS{1'b0}}) ? {{(DELAY_BITS-1){1'b0}}, 1'b1} : delay;

    assign busy = (state != S_IDLE);

    // Bit position honours the configured order.
    // A position indexes one of REG_W bits, so it is four bits wide even
    // though the count that produces it needs five to express REG_W itself.
    function automatic [3:0] position(input [3:0] which, input [3:0] count,
                                      input logic msb_first);
        logic [3:0] last_index;
        begin
            // count is 1..REG_W. At REG_W=16 the low nibble is 0, and 0-1
            // wraps to 15, which is exactly the highest bit index. The wrap is
            // the intended arithmetic, not an accident.
            last_index = count - 4'd1;
            position = msb_first ? (last_index - which) : which;
        end
    endfunction

    wire [3:0] pos_now  = position(index[3:0], total[3:0], cfg_ord);
    wire [3:0] pos_next = position(index[3:0] + 4'd1, total[3:0], cfg_ord);
    wire [3:0] pos_issue = position(4'd0, nbits[3:0], cfg_ord);
    wire       bit_now  = tx_latch[pos_now];
    wire       bit_next = tx_latch[pos_next];
    wire       bit_issue = tx_value[pos_issue];
    wire       is_last  = (index + 5'd1 == total);

    // The last cell's final cycle is this transfer's retirement and the next
    // instruction's issue at once, so a back-to-back shift starts from here as
    // well as from idle. Without that, every second shift would lose its issue
    // pulse -- and an I2C byte followed by its ACK bit is exactly that shape.
    wire finishing = (state == S_UNCLK || state == S_CLK_B)
                   && timer_last && is_last;
    wire begin_now = start && ((state == S_IDLE) || finishing);
    assign done  = finishing;
    assign rx_we = finishing && take_q;

    // One pin write per cycle for the data line, one for the clock. The mask
    // is UIO_PINS wide, not a hardcoded byte: a profile may carry fewer pins
    // than the Tiny Tapeout harness supplies.
    localparam [UIO_PINS-1:0] PIN_ONE = {{(UIO_PINS-1){1'b0}}, 1'b1};

    task automatic write_pin(input [3:0] pin, input logic level);
        begin
            set_mask  = set_mask | (PIN_ONE << pin);
            set_value = (set_value & ~(PIN_ONE << pin))
                      | (level ? (PIN_ONE << pin) : {UIO_PINS{1'b0}});
        end
    endtask

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state      <= S_IDLE;
            index      <= 5'd0;
            total      <= 5'd0;
            rx_latch   <= {REG_W{1'b0}};
            tx_latch   <= {REG_W{1'b0}};
            drive_q    <= 1'b0;
            take_q     <= 1'b0;
        end else if (begin_now) begin
            // A transfer starting while another retires overwrites this state
            // wholesale. The retiring one's result is safe: the core reads it
            // combinationally through `rx_value` on this same cycle.
            index    <= 5'd0;
            total    <= nbits;
            rx_latch <= {REG_W{1'b0}};
            tx_latch <= tx_value;
            drive_q  <= drive_data;
            take_q   <= take_data;
            state    <= clocked ? S_CLK_A : S_UNCLK;
            if (!clocked && take_data)
                rx_latch[pos_issue] <= pad_in[cfg_din];
        end else begin
            case (state)
            S_UNCLK: if (timer_last) begin
                if (is_last) begin
                    state <= S_IDLE;
                end else begin
                    index <= index + 5'd1;
                    if (take_q) rx_latch[pos_next] <= pad_in[cfg_din];
                end
            end

            S_CLK_A: if (timer_last) begin
                state <= S_CLK_B;
                // cpha=0 samples on the leading edge we are about to take.
                if (!cfg_cpha && take_q) rx_latch[pos_now] <= pad_in[cfg_din];
            end

            S_CLK_B: if (timer_last) begin
                // cpha=1 samples on the trailing edge.
                if (cfg_cpha && take_q) rx_latch[pos_now] <= pad_in[cfg_din];
                if (is_last) begin
                    state <= S_IDLE;
                end else begin
                    index <= index + 5'd1;
                    state <= S_CLK_A;
                end
            end
            default: ;   // S_IDLE waits for `start`
            endcase
        end
    end

    // Pin writes and the cell timer are driven combinationally from the state
    // we are leaving, so a level change is visible from the first cycle of the
    // phase it belongs to.
    always @(*) begin
        set_mask    = {UIO_PINS{1'b0}};
        set_value   = {UIO_PINS{1'b0}};
        timer_load  = 1'b0;
        timer_delay = whole;

        case (state)
        S_UNCLK: if (timer_last && !is_last) begin
            timer_load = 1'b1;
            if (drive_q) write_pin(cfg_dout, bit_next);
        end

        S_CLK_A: if (timer_last) begin
            timer_load  = 1'b1;
            timer_delay = half;
            write_pin(cfg_clk, ~cfg_cpol);              // leading edge
            if (drive_q && cfg_cpha) write_pin(cfg_dout, bit_now);
        end

        S_CLK_B: if (timer_last) begin
            write_pin(cfg_clk, cfg_cpol);               // trailing edge
            if (!is_last) begin
                timer_load  = 1'b1;
                timer_delay = half;
                if (drive_q && !cfg_cpha) write_pin(cfg_dout, bit_next);
            end
        end
        default: ;
        endcase

        // A starting transfer owns the timer, and its pin writes merge with
        // the retiring one's. They cannot disagree: both read the same SHCFG,
        // so the trailing clock edge above and the idle level below are the
        // same level on the same pin.
        if (begin_now) begin
            timer_load  = 1'b1;
            timer_delay = clocked ? half : whole;
            if (clocked) write_pin(cfg_clk, cfg_cpol);
            // total is latched on this same edge, so the first bit must use
            // the incoming count rather than the previous transfer's total.
            if (drive_data && (!clocked || !cfg_cpha)) write_pin(cfg_dout, bit_issue);
        end
    end

    // Usually the sampled result is already registered before `done`. In
    // CPHA=1 the last sample and `done` share the trailing edge, so forward
    // that pad value combinationally to the parent just as a pipelined ALU
    // forwards a result at retirement.
    always @(*) begin
        rx_value = rx_latch;
        if (state == S_CLK_B && timer_last && is_last && cfg_cpha && take_q)
            rx_value[pos_now] = pad_in[cfg_din];
    end
endmodule

`default_nettype wire
