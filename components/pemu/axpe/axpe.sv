// axpe: the timed-ISA protocol emulator.
//
// Opcode constants come from axpe_isa.svh, generated from axpe-isa.json, so
// this file cannot disagree with the assembler or the golden model about what
// an encoding means. Build with +incdir+sw/pemu/isa.
//
// Program memory is read synchronously, because a fabric block RAM cannot do
// an asynchronous read and an SRAM macro will not either. `imem_addr` is
// therefore the address of the *next* fetch, presented for the memory to
// register on this edge, and `imem_data` is what the memory registered on the
// previous one. That looks fatal to a rule where a D=0 instruction occupies
// exactly one cycle, and is not: the address advances on the edge an
// instruction issues, so the next word is already there when the next
// instruction issues. A taken one-cycle branch still works, since the
// condition reads registered flags and the target is an immediate, both
// available combinationally.
//
// `pc_we` drives both the program counter and that address, from one
// expression. They are the same decision, and a fetch schedule that could
// disagree with the program counter is the kind of defect that only shows up
// as a wrong instruction after a branch.
//
// Every instruction advances the PC at issue, including the two that run for
// many cycles, so WAITE and the shift instructions outlive their own word:
// what they still need is latched below, because they cannot read `imem_data`
// again. Retirement is the same rule read backwards. A long instruction
// retires *on* the cycle it finishes and the next instruction issues on that
// same cycle; a handoff cycle of its own would make a shift cost
// n*max(D,1) + 1, which is the `1 + D` rule the ISA rejected -- it puts every
// protocol edge one cycle past its bit period, and the error accumulates.
// Issuing into a retirement is why `retire_data` and `ft_live` exist: the
// issuing instruction must read the result it is being handed on that edge.
`default_nettype none

module axpe #(
    parameter int IMEM_WORDS = 256,
    parameter int REGS       = 8,
    parameter int REG_W      = 16,
    parameter int DELAY_BITS = 16,
    parameter int UIO_PINS   = 8,
    parameter int CALL_DEPTH = 4
) (
    input  wire                          clk,
    input  wire                          rst_n,
    input  wire [7:0]                    ui_in,
    output wire [7:0]                    uo_out,
    input  wire [UIO_PINS-1:0]           uio_in,
    output wire [UIO_PINS-1:0]           uio_out,
    output wire [UIO_PINS-1:0]           uio_oe,
    output wire [$clog2(IMEM_WORDS)-1:0] imem_addr,
    input  wire [31:0]                   imem_data,
    output wire                          halted,
    output wire                          fault
);
`include "axpe_isa.svh"

    localparam int AW = $clog2(IMEM_WORDS);
    localparam int SW = $clog2(CALL_DEPTH + 1);   // holds 0..CALL_DEPTH
    localparam int DW = $clog2(CALL_DEPTH);       // indexes the stack

    localparam [1:0] S_EXEC = 2'd0, S_SHIFT = 2'd1, S_WAIT = 2'd2, S_STOP = 2'd3;

    // ---- decode -----------------------------------------------------------
    wire [4:0]  op;
    wire [2:0]  ra, rb;
    wire [4:0]  xf;
    wire [15:0] delay;
    wire [7:0]  imm8;

    axpe_decode u_decode (
        .word(imem_data), .op(op), .ra(ra), .rb(rb),
        .xf(xf), .delay(delay), .imm8(imm8)
    );

    // ---- architectural state ----------------------------------------------
    reg [AW-1:0]       pc;
    reg [REG_W-1:0]    regs [0:REGS-1];
    reg                fz, fc, ft;
    reg [UIO_PINS-1:0] pin_latch, pin_dir, pin_drain;
    reg [7:0]          out_latch;
    reg [14:0]         shcfg;
    // The shift engine's cell duration when an instruction asks for it instead
    // of the D in its own word. SHPER writes it; nothing else does, and a
    // transfer already running is unaffected, because the engine reads its
    // cell from `hold_delay` once it has started. It is DELAY_BITS wide and
    // not a literal 16: it holds the same kind of value the cell timer counts,
    // so a profile that narrows one must narrow the other or the register
    // could hold a period the timer cannot reach.
    reg [DELAY_BITS-1:0] period;
    reg [AW-1:0]       call_stack [0:CALL_DEPTH-1];
    reg [SW-1:0]       sp;
    reg [1:0]          state;
    reg                stopped, faulted, halt_pending;

    // Operands held for an instruction that is still running after its word
    // has left `imem_data`. The shift engine latches its own bit count, data
    // and direction; these are what the core and the wait still read.
    reg [DELAY_BITS-1:0] hold_delay;
    reg [2:0]            hold_ra;
    reg [3:0]            hold_wpin;
    reg [1:0]            hold_wedge;

    wire [7:0]  uio_padded = {{(8-UIO_PINS){1'b0}}, uio_in};
    wire [15:0] pad_in     = {ui_in, uio_padded};

    assign halted = stopped;
    assign fault  = faulted;
    assign uo_out = out_latch;
    // Held in reset, the core asks for word zero, so the first instruction is
    // already in `imem_data` on the first cycle it runs. A wrapper switches the
    // store's address to the core one cycle before releasing reset, and this is
    // what makes that cycle fetch the right word rather than a stale one.
    assign imem_addr = (!rst_n) ? {AW{1'b0}} : (pc_we ? next_pc : pc);

    axpe_pads #(.UIO_PINS(UIO_PINS)) u_pads (
        .latch_value(pin_latch), .direction(pin_dir), .drain(pin_drain),
        .uio_out(uio_out), .uio_oe(uio_oe)
    );

    // ---- cell timer -------------------------------------------------------
    reg                   cell_load;
    wire                  cell_last;
    axpe_timing #(.DELAY_BITS(DELAY_BITS)) u_cell (
        .clk(clk), .rst_n(rst_n),
        .load(cell_load), .delay(delay), .last(cell_last)
    );

    // ---- WAITE ------------------------------------------------------------
    // A running wait reads its pin, edge and bound from the latched copies:
    // `imem_data` now holds the instruction that will issue when this one
    // retires. The live fields are what a WAITE issuing on *this* cycle uses
    // to capture its own starting level, which is why both exist -- on a
    // retirement cycle one wait is being tested while the next one starts.
    wire [3:0] wait_pin  = imm8[3:0];
    wire [1:0] wait_edge = imm8[5:4];
    wire       wait_live = pad_in[wait_pin];
    wire       wait_now  = pad_in[hold_wpin];
    reg        wait_prev;
    reg [DELAY_BITS-1:0] wait_count;
    wire [DELAY_BITS-1:0] wait_elapsed =
        wait_count + {{(DELAY_BITS-1){1'b0}}, 1'b1};
    wire [DELAY_BITS-1:0] wait_bound =
        (hold_delay == {DELAY_BITS{1'b0}}) ? {{(DELAY_BITS-1){1'b0}}, 1'b1}
                                           : hold_delay;
    wire wait_hit = (hold_wedge == 2'd0) ? (~wait_prev &  wait_now)
                  : (hold_wedge == 2'd1) ? ( wait_prev & ~wait_now)
                  : (hold_wedge == 2'd2) ? ( wait_prev ^  wait_now)
                                         :  wait_now;
    wire wait_timeout = (wait_elapsed >= wait_bound);

    // ---- retirement and issue ---------------------------------------------
    // One gate for every instruction, whatever engine it was running in.
    wire wait_over  = (state == S_WAIT)  && (wait_hit || wait_timeout);
    wire shift_over = (state == S_SHIFT) && sh_done;
    wire issue      = (state == S_EXEC && cell_last) || wait_over || shift_over;

    // The retiring engine's result is written on the same edge the issuing
    // instruction takes effect, so that instruction has to read the value it
    // is about to be given rather than the register's stale contents. T is the
    // same hazard one bit wide: `WAITE` then `BR T` is the ordinary way to
    // test a timeout, and it issues on exactly this cycle.
    wire             retire_we   = (shift_over && sh_rx_we) || wait_over;
    wire [REG_W-1:0] retire_data = wait_over
        ? {{(REG_W-DELAY_BITS){1'b0}}, wait_elapsed} : sh_rx;
    wire             ft_live     = wait_over ? wait_timeout : ft;
    wire [REG_W-1:0] src_a = (retire_we && ra == hold_ra) ? retire_data : regs[ra];
    wire [REG_W-1:0] src_b = (retire_we && rb == hold_ra) ? retire_data : regs[rb];

    // ---- the cell a shift will actually use --------------------------------
    // One bit of the otherwise unused `b` field picks between the encoded D
    // and the period register, so the choice is per instruction rather than a
    // mode the machine is left in. Everything downstream -- the timer, the
    // clocked-cell legality rules, and what gets latched for the rest of the
    // transfer -- reads this and not `delay`, because a rule applied to the
    // wrong one of the two would only show up as a wrong bit period.
    // REG_W and DELAY_BITS are independent knobs, and neither is necessarily
    // the 16 bits the encoded delay field carries. Widen first and then take
    // the bits wanted, the same way `imm8_wide` handles a branch target
    // against AW below; slicing directly reads past the end of a narrowed
    // register at some profiles and truncates silently at others.
    /* verilator lint_off UNUSEDSIGNAL */
    wire [31:0] src_a_wide  = {{(32-REG_W){1'b0}}, src_a};
    wire [31:0] period_wide = {{(32-DELAY_BITS){1'b0}}, period};
    /* verilator lint_on UNUSEDSIGNAL */
    wire        period_sel  = rb[AXPE_SHIFT_B_P_LO];
    wire [15:0] cell_delay  = period_sel ? period_wide[15:0] : delay;

    // ---- shift engine -----------------------------------------------------
    wire [UIO_PINS-1:0] sh_set_mask, sh_set_value;
    wire [REG_W-1:0]    sh_rx;
    wire                sh_busy, sh_done, sh_rx_we;
    reg                 sh_start;
    // A cell reloads the timer from the delay of the instruction that started
    // it, which is only in `imem_data` on the issue cycle itself.
    wire [DELAY_BITS-1:0] sh_delay = issue ? cell_delay : hold_delay;
    wire                is_shift = (op == AXPE_OP_SHOUT) || (op == AXPE_OP_SHIN)
                                || (op == AXPE_OP_SHIO);

    axpe_shift #(.REG_W(REG_W), .UIO_PINS(UIO_PINS), .DELAY_BITS(DELAY_BITS)) u_shift (
        .clk(clk), .rst_n(rst_n), .start(sh_start),
        .nbits(xf), .delay(sh_delay), .shcfg(shcfg), .tx_value(src_a),
        .drive_data(op != AXPE_OP_SHIN), .take_data(op != AXPE_OP_SHOUT),
        .pad_in(pad_in),
        .set_mask(sh_set_mask), .set_value(sh_set_value), .rx_value(sh_rx),
        .busy(sh_busy), .done(sh_done), .rx_we(sh_rx_we)
    );

    // A clocked shift needs an even, non-zero cell and a clock that does not
    // alias either data line. SHCFG is loaded from a register, so this cannot
    // be an assembler error -- the machine is the only place that knows.
    wire [3:0] cfg_clk  = shcfg[3:0];
    wire [3:0] cfg_dout = shcfg[7:4];
    wire [3:0] cfg_din  = shcfg[11:8];
    wire       clocked  = (cfg_clk != 4'hF);
    wire       shift_bad =
           (op != AXPE_OP_SHIN && cfg_dout >= 4'd8)
        || (clocked && (cfg_clk >= 4'd8 || cell_delay[0] || cell_delay < 16'd2
                        || cfg_clk == cfg_dout || cfg_clk == cfg_din));
    // The rest of `b` is reserved. Refusing it is what keeps it reserved:
    // firmware that set those bits and worked would make any later use of
    // them a compatibility break rather than an addition.
    wire       encoding_bad =
           (is_shift && (xf == 5'd0 || xf > REG_W[4:0]))
        || (is_shift && |rb[AXPE_SHIFT_B_RSV_HI:AXPE_SHIFT_B_RSV_LO])
        || (op == AXPE_OP_BR && ra == 3'd7)
        || ((op == AXPE_OP_SHL || op == AXPE_OP_SHR) && xf > REG_W[4:0])
        || (op == AXPE_OP_WAITE && imm8 > 8'd63);

    // ---- ALU --------------------------------------------------------------
    wire [REG_W-1:0] imm_x = {{(REG_W-8){1'b0}}, imm8};
    wire [REG_W:0]   sum   = {1'b0, src_a} + {1'b0, (op == AXPE_OP_ADDI) ? imm_x : src_b};
    wire [REG_W-1:0] diff  = src_a - src_b;
    wire             borrow = (src_a < src_b);      // carry on subtract is a borrow

    reg  [REG_W-1:0] alu_out;
    reg              alu_we, flag_z_we, flag_c_we;
    reg              alu_z, alu_c;

    always @(*) begin
        alu_out   = src_a;
        alu_we    = 1'b0;
        flag_z_we = 1'b0;
        flag_c_we = 1'b0;
        alu_z     = 1'b0;
        alu_c     = 1'b0;
        case (op)
        AXPE_OP_MOV:  begin alu_out = src_b; alu_we = 1'b1; end
        AXPE_OP_ADD, AXPE_OP_ADDI: begin
            alu_out = sum[REG_W-1:0]; alu_we = 1'b1;
            alu_z = (sum[REG_W-1:0] == {REG_W{1'b0}}); alu_c = sum[REG_W];
            flag_z_we = 1'b1; flag_c_we = 1'b1;
        end
        AXPE_OP_SUB: begin
            alu_out = diff; alu_we = 1'b1;
            alu_z = (src_a == src_b); alu_c = borrow;
            flag_z_we = 1'b1; flag_c_we = 1'b1;
        end
        AXPE_OP_CMP: begin
            alu_z = (src_a == src_b); alu_c = borrow;
            flag_z_we = 1'b1; flag_c_we = 1'b1;
        end
        AXPE_OP_AND: begin alu_out = src_a & src_b; alu_we = 1'b1;
                            alu_z = ((src_a & src_b) == {REG_W{1'b0}}); flag_z_we = 1'b1; end
        AXPE_OP_OR:  begin alu_out = src_a | src_b; alu_we = 1'b1;
                            alu_z = ((src_a | src_b) == {REG_W{1'b0}}); flag_z_we = 1'b1; end
        AXPE_OP_XOR: begin alu_out = src_a ^ src_b; alu_we = 1'b1;
                            alu_z = ((src_a ^ src_b) == {REG_W{1'b0}}); flag_z_we = 1'b1; end
        AXPE_OP_SHL: if (xf != 5'd0) begin
            alu_out = src_a << xf; alu_we = 1'b1;
            alu_c = src_a[REG_W[3:0] - xf[3:0]]; flag_c_we = 1'b1;
        end
        AXPE_OP_SHR: if (xf != 5'd0) begin
            alu_out = src_a >> xf; alu_we = 1'b1;
            alu_c = src_a[xf[3:0] - 4'd1]; flag_c_we = 1'b1;
        end
        AXPE_OP_LDIL: begin alu_out = {src_a[REG_W-1:8], imm8}; alu_we = 1'b1; end
        AXPE_OP_LDIH: begin alu_out = {imm8, src_a[7:0]};       alu_we = 1'b1; end
        AXPE_OP_PINR: begin alu_out = pad_in[REG_W-1:0];        alu_we = 1'b1; end
        default: ;
        endcase
    end

    // ---- branch resolution ------------------------------------------------
    reg branch_taken;
    always @(*) begin
        case (ra)
        3'd0: branch_taken = 1'b1;
        3'd1: branch_taken = fz;
        3'd2: branch_taken = ~fz;
        3'd3: branch_taken = fc;
        3'd4: branch_taken = ~fc;
        3'd5: branch_taken = ft_live;
        default: branch_taken = ~ft_live;
        endcase
    end

    // AW may be narrower or wider than the eight-bit target field, so widen
    // first and then take AW bits. Slicing imm8 directly reads past its end
    // whenever IMEM_WORDS exceeds 256.
    // How many of imm8's bits survive depends on IMEM_WORDS, so some are
    // genuinely unused at most settings: a 64-word memory cannot use the top
    // two, and past 256 words the field runs out before the PC does. Neither
    // is a defect -- fetch_bad rejects a target the memory cannot reach.
    /* verilator lint_off UNUSEDSIGNAL */
    wire [15:0]   imm8_wide = {8'd0, imm8};
    /* verilator lint_on UNUSEDSIGNAL */
    wire [AW-1:0] target    = imm8_wide[AW-1:0];
    reg  [AW-1:0] next_pc;
    always @(*) begin
        next_pc = pc + {{(AW-1){1'b0}}, 1'b1};
        if (op == AXPE_OP_BR && branch_taken) next_pc = target;
        else if (op == AXPE_OP_CALL)          next_pc = target;
        else if (op == AXPE_OP_RET)           next_pc = call_stack[sp_top];
    end

    wire [DW-1:0] sp_top = sp[DW-1:0] - {{(DW-1){1'b0}}, 1'b1};
    wire stack_bad = (op == AXPE_OP_CALL && sp == CALL_DEPTH[SW-1:0])
                  || (op == AXPE_OP_RET  && sp == {SW{1'b0}});
    // BR and CALL targets are eight bits, so only the first 256 words are
    // reachable however large the program store is. A bigger memory can hold
    // words, but nothing can jump to them; widening the target field is an ISA
    // change, not a profile setting.
    localparam int   IMEM_REACH = (IMEM_WORDS < 256) ? IMEM_WORDS : 256;
    localparam [8:0] IMEM_LIMIT = IMEM_REACH[8:0];
    wire fetch_bad = (op == AXPE_OP_CALL || (op == AXPE_OP_BR && branch_taken))
                  && ({1'b0, imm8} >= IMEM_LIMIT);
    wire reject = encoding_bad || stack_bad || fetch_bad || (is_shift && shift_bad);

    // Everything that advances the program counter, in one place: an
    // instruction that issues, is not refused, and is not the HALT that stops
    // fetching. HALT leaves the counter on itself, so the address the store
    // holds while the core is halted is a word that exists.
    wire pc_we = issue && !halt_pending && !reject && (op != AXPE_OP_HALT);

    // A shift's trailing clock edge and a pin instruction issuing on that same
    // retirement cycle both write the pad latch. The instruction is later in
    // program order and wins its own bits, but it must not discard the edge:
    // it builds on what the engine leaves rather than on the stale latch.
    wire [UIO_PINS-1:0] pin_base = (sh_busy || sh_start)
        ? ((pin_latch & ~sh_set_mask) | (sh_set_value & sh_set_mask))
        : pin_latch;

    always @(*) begin
        cell_load = 1'b0;
        sh_start  = 1'b0;
        if (issue && !reject && !halt_pending) begin
            if (is_shift) sh_start = 1'b1;
            else if (op != AXPE_OP_WAITE) cell_load = 1'b1;
        end
    end

    integer i;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            pc <= {AW{1'b0}};
            for (i = 0; i < REGS; i = i + 1) regs[i] <= {REG_W{1'b0}};
            {fz, fc, ft} <= 3'b000;
            pin_latch <= {UIO_PINS{1'b0}};
            pin_dir   <= {UIO_PINS{1'b0}};
            pin_drain <= {UIO_PINS{1'b0}};
            out_latch <= 8'd0;
            shcfg     <= 15'd0;
            period    <= {DELAY_BITS{1'b0}};
            sp        <= {SW{1'b0}};
            state     <= S_EXEC;
            stopped   <= 1'b0;
            faulted   <= 1'b0;
            halt_pending <= 1'b0;
            wait_prev <= 1'b1;
            wait_count <= {DELAY_BITS{1'b0}};
            hold_delay <= {DELAY_BITS{1'b0}};
            hold_ra    <= 3'd0;
            hold_wpin  <= 4'd0;
            hold_wedge <= 2'd0;
        end else begin
            // The shift engine owns the pads while it runs.
            if (sh_busy || sh_start) pin_latch <= pin_base;

            // A wait runs until it is over; its counter is what it returns.
            if (state == S_WAIT) begin
                wait_prev  <= wait_now;
                wait_count <= wait_count + {{(DELAY_BITS-1){1'b0}}, 1'b1};
            end

            // A retiring engine writes its result first, so an instruction
            // issuing on this same edge overwrites it when they share Ra.
            // That order is program order, and the reads above are forwarded.
            if (retire_we) regs[hold_ra] <= retire_data;
            // Reaching the bound is a timeout even if the selected edge is
            // also present on that final permitted sample.
            if (wait_over)  ft <= wait_timeout;

            if (issue) begin
                if (halt_pending) begin
                    halt_pending <= 1'b0;
                    stopped <= 1'b1;
                    state <= S_STOP;
                end else if (reject) begin
                    faulted <= 1'b1;
                    state   <= S_STOP;
                end else if (is_shift) begin
                    hold_ra    <= ra;
                    hold_delay <= cell_delay;
                    state      <= S_SHIFT;
                end else if (op == AXPE_OP_WAITE) begin
                    hold_ra    <= ra;
                    hold_delay <= delay;
                    hold_wpin  <= wait_pin;
                    hold_wedge <= wait_edge;
                    wait_prev  <= wait_live;
                    wait_count <= {DELAY_BITS{1'b0}};
                    state      <= S_WAIT;
                    // A level already satisfied at entry ends on its own terms.
                    if (wait_edge == 2'd3 && wait_live) begin
                        regs[ra] <= {REG_W{1'b0}};
                        ft       <= 1'b0;
                        state    <= S_EXEC;
                    end
                end else begin
                    state <= S_EXEC;
                    if (alu_we)    regs[ra] <= alu_out;
                    if (flag_z_we) fz <= alu_z;
                    if (flag_c_we) fc <= alu_c;
                    case (op)
                    AXPE_OP_PINSET: pin_latch <= pin_base |  imm8[UIO_PINS-1:0];
                    AXPE_OP_PINCLR: pin_latch <= pin_base & ~imm8[UIO_PINS-1:0];
                    AXPE_OP_PINTOG: pin_latch <= pin_base ^  imm8[UIO_PINS-1:0];
                    AXPE_OP_PINW:   pin_latch <= src_a[UIO_PINS-1:0];
                    AXPE_OP_POUT:   out_latch <= src_a[7:0];
                    AXPE_OP_PDIR:   pin_dir   <= imm8[UIO_PINS-1:0];
                    AXPE_OP_PDRN:   pin_drain <= imm8[UIO_PINS-1:0];
                    AXPE_OP_SHCFG:  shcfg     <= src_a[14:0];
                    AXPE_OP_SHPER:  period    <= src_a_wide[DELAY_BITS-1:0];
                    AXPE_OP_CALL:   begin call_stack[sp[DW-1:0]] <= pc + {{(AW-1){1'b0}}, 1'b1};
                                           sp <= sp + {{(SW-1){1'b0}}, 1'b1}; end
                    AXPE_OP_RET:    sp <= sp - {{(SW-1){1'b0}}, 1'b1};
                    // Effects happen at issue, but HALT retires only after
                    // its full max(D,1) occupancy, like the golden model.
                    AXPE_OP_HALT:   halt_pending <= 1'b1;
                    default: ;
                    endcase
                end
            end

            if (pc_we) pc <= next_pc;
        end
    end
endmodule

`default_nettype wire
