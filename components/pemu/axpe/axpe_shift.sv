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
    output reg                    done
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
    reg         sample_due;     // capture pad_in on the next edge
    reg  [3:0]  sample_pos;   // 0..REG_W-1

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
    wire       bit_now  = tx_value[pos_now];
    wire       bit_next = tx_value[pos_next];
    wire       is_last  = (index + 5'd1 == total);

    // One pin write per cycle for the data line, one for the clock.
    task automatic write_pin(input [3:0] pin, input logic level);
        begin
            set_mask  = set_mask  | (8'd1 << pin);
            set_value = (set_value & ~(8'd1 << pin)) | (level ? (8'd1 << pin) : 8'd0);
        end
    endtask

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state      <= S_IDLE;
            index      <= 5'd0;
            total      <= 5'd0;
            rx_value   <= {REG_W{1'b0}};
            sample_due <= 1'b0;
            sample_pos <= 4'd0;
        end else begin
            // A sample issued last cycle lands now, so the captured level is
            // the pad during the first cycle of its phase, matching the model.
            if (sample_due) begin
                rx_value[sample_pos] <= pad_in[cfg_din];
                sample_due <= 1'b0;
            end

            case (state)
            S_IDLE: if (start) begin
                index <= 5'd0;
                total <= nbits;
                rx_value <= {REG_W{1'b0}};
                state <= clocked ? S_CLK_A : S_UNCLK;
                if (!clocked && take_data) begin
                    sample_due <= 1'b1;
                    sample_pos <= position(4'd0, nbits[3:0], cfg_ord);
                end
            end

            S_UNCLK: if (timer_last) begin
                if (is_last) begin
                    state <= S_IDLE;
                end else begin
                    index <= index + 5'd1;
                    if (take_data) begin
                        sample_due <= 1'b1;
                        sample_pos <= pos_next;
                    end
                end
            end

            S_CLK_A: if (timer_last) begin
                state <= S_CLK_B;
                // cpha=0 samples on the leading edge we are about to take.
                if (!cfg_cpha && take_data) begin
                    sample_due <= 1'b1;
                    sample_pos <= pos_now;
                end
            end

            S_CLK_B: if (timer_last) begin
                // cpha=1 samples on the trailing edge.
                if (cfg_cpha && take_data) begin
                    sample_due <= 1'b1;
                    sample_pos <= pos_now;
                end
                if (is_last) begin
                    state <= S_IDLE;
                end else begin
                    index <= index + 5'd1;
                    state <= S_CLK_A;
                end
            end
            default: state <= S_IDLE;
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
        done        = 1'b0;

        case (state)
        S_IDLE: if (start) begin
            timer_load  = 1'b1;
            timer_delay = clocked ? half : whole;
            if (clocked) write_pin(cfg_clk, cfg_cpol);
            if (drive_data && (!clocked || !cfg_cpha)) write_pin(cfg_dout, bit_now);
        end

        S_UNCLK: if (timer_last) begin
            done = is_last;
            if (!is_last) begin
                timer_load = 1'b1;
                if (drive_data) write_pin(cfg_dout, bit_next);
            end
        end

        S_CLK_A: if (timer_last) begin
            timer_load  = 1'b1;
            timer_delay = half;
            write_pin(cfg_clk, ~cfg_cpol);              // leading edge
            if (drive_data && cfg_cpha) write_pin(cfg_dout, bit_now);
        end

        S_CLK_B: if (timer_last) begin
            write_pin(cfg_clk, cfg_cpol);               // trailing edge
            done = is_last;
            if (!is_last) begin
                timer_load  = 1'b1;
                timer_delay = half;
                if (drive_data && !cfg_cpha) write_pin(cfg_dout, bit_next);
            end
        end
        default: ;
        endcase
    end
endmodule

`default_nettype wire
