// axpe: the timed-ISA protocol emulator.
//
// Opcode constants come from axpe_isa.svh, generated from axpe-isa.json, so
// this file cannot disagree with the assembler or the golden model about what
// an encoding means. Build with +incdir+sw/pemu/isa.
//
// Program memory is read synchronously, because a fabric block RAM cannot do
// an asynchronous read and an SRAM macro will not either. That looks fatal to
// a rule where a D=0 instruction occupies exactly one cycle, and is not: the
// address register updates on the *last* cycle of each instruction, so the
// next word is ready at the first cycle of the next. A taken one-cycle branch
// still works, since the condition reads registered flags and the target is an
// immediate, both available combinationally.
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
    reg [AW-1:0]       call_stack [0:CALL_DEPTH-1];
    reg [SW-1:0]       sp;
    reg [1:0]          state;
    reg                stopped, faulted;

    wire [7:0]  uio_padded = {{(8-UIO_PINS){1'b0}}, uio_in};
    wire [15:0] pad_in     = {ui_in, uio_padded};

    assign halted = stopped;
    assign fault  = faulted;
    assign uo_out = out_latch;
    assign imem_addr = pc;

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

    // ---- shift engine -----------------------------------------------------
    wire [UIO_PINS-1:0] sh_set_mask, sh_set_value;
    wire [REG_W-1:0]    sh_rx;
    wire                sh_busy, sh_done;
    reg                 sh_start;
    wire                is_shift = (op == AXPE_OP_SHOUT) || (op == AXPE_OP_SHIN)
                                || (op == AXPE_OP_SHIO);

    axpe_shift #(.REG_W(REG_W), .UIO_PINS(UIO_PINS), .DELAY_BITS(DELAY_BITS)) u_shift (
        .clk(clk), .rst_n(rst_n), .start(sh_start),
        .nbits(xf), .delay(delay), .shcfg(shcfg), .tx_value(regs[ra]),
        .drive_data(op != AXPE_OP_SHIN), .take_data(op != AXPE_OP_SHOUT),
        .pad_in(pad_in),
        .set_mask(sh_set_mask), .set_value(sh_set_value), .rx_value(sh_rx),
        .busy(sh_busy), .done(sh_done)
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
        || (clocked && (cfg_clk >= 4'd8 || delay[0] || delay < 16'd2
                        || cfg_clk == cfg_dout || cfg_clk == cfg_din));
    wire       encoding_bad =
           (is_shift && (xf == 5'd0 || xf > REG_W[4:0]))
        || (op == AXPE_OP_BR && ra == 3'd7)
        || ((op == AXPE_OP_SHL || op == AXPE_OP_SHR) && xf > REG_W[4:0])
        || (op == AXPE_OP_WAITE && imm8 > 8'd63);

    // ---- WAITE ------------------------------------------------------------
    wire [3:0] wait_pin  = imm8[3:0];
    wire [1:0] wait_edge = imm8[5:4];
    wire       wait_now  = pad_in[wait_pin];
    reg        wait_prev;
    reg [DELAY_BITS-1:0] wait_count;
    wire [DELAY_BITS-1:0] wait_bound =
        (delay == {DELAY_BITS{1'b0}}) ? {{(DELAY_BITS-1){1'b0}}, 1'b1} : delay;
    wire wait_hit = (wait_edge == 2'd0) ? (~wait_prev &  wait_now)
                  : (wait_edge == 2'd1) ? ( wait_prev & ~wait_now)
                  : (wait_edge == 2'd2) ? ( wait_prev ^  wait_now)
                                        :  wait_now;
    wire wait_timeout = (wait_count >= wait_bound);

    // ---- ALU --------------------------------------------------------------
    wire [REG_W-1:0] src_a = regs[ra];
    wire [REG_W-1:0] src_b = regs[rb];
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
        3'd5: branch_taken = ft;
        default: branch_taken = ~ft;
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

    always @(*) begin
        cell_load = 1'b0;
        sh_start  = 1'b0;
        if (state == S_EXEC && cell_last && !reject) begin
            if (is_shift) sh_start = 1'b1;
            else          cell_load = 1'b1;
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
            sp        <= {SW{1'b0}};
            state     <= S_EXEC;
            stopped   <= 1'b0;
            faulted   <= 1'b0;
            wait_prev <= 1'b1;
            wait_count <= {DELAY_BITS{1'b0}};
        end else begin
            // The shift engine owns the pads while it runs.
            if (sh_busy || sh_start)
                pin_latch <= (pin_latch & ~sh_set_mask) | (sh_set_value & sh_set_mask);

            case (state)
            S_EXEC: if (cell_last) begin
                if (reject) begin
                    faulted <= 1'b1;
                    state   <= S_STOP;
                end else if (is_shift) begin
                    state <= S_SHIFT;
                end else if (op == AXPE_OP_WAITE) begin
                    wait_prev  <= wait_now;
                    wait_count <= {DELAY_BITS{1'b0}};
                    state      <= S_WAIT;
                    // A level already satisfied at entry ends on its own terms.
                    if (wait_edge == 2'd3 && wait_now) begin
                        regs[ra] <= {REG_W{1'b0}};
                        ft       <= 1'b0;
                        state    <= S_EXEC;
                        pc       <= next_pc;
                    end
                end else begin
                    if (alu_we)    regs[ra] <= alu_out;
                    if (flag_z_we) fz <= alu_z;
                    if (flag_c_we) fc <= alu_c;
                    case (op)
                    AXPE_OP_PINSET: pin_latch <= pin_latch |  imm8[UIO_PINS-1:0];
                    AXPE_OP_PINCLR: pin_latch <= pin_latch & ~imm8[UIO_PINS-1:0];
                    AXPE_OP_PINTOG: pin_latch <= pin_latch ^  imm8[UIO_PINS-1:0];
                    AXPE_OP_PINW:   pin_latch <= src_a[UIO_PINS-1:0];
                    AXPE_OP_POUT:   out_latch <= src_a[7:0];
                    AXPE_OP_PDIR:   pin_dir   <= imm8[UIO_PINS-1:0];
                    AXPE_OP_PDRN:   pin_drain <= imm8[UIO_PINS-1:0];
                    AXPE_OP_SHCFG:  shcfg     <= src_a[14:0];
                    AXPE_OP_CALL:   begin call_stack[sp[DW-1:0]] <= pc + {{(AW-1){1'b0}}, 1'b1};
                                           sp <= sp + {{(SW-1){1'b0}}, 1'b1}; end
                    AXPE_OP_RET:    sp <= sp - {{(SW-1){1'b0}}, 1'b1};
                    AXPE_OP_HALT:   begin stopped <= 1'b1; state <= S_STOP; end
                    default: ;
                    endcase
                    if (op != AXPE_OP_HALT) pc <= next_pc;
                end
            end

            S_WAIT: begin
                wait_prev  <= wait_now;
                wait_count <= wait_count + {{(DELAY_BITS-1){1'b0}}, 1'b1};
                if (wait_hit || wait_timeout) begin
                    regs[ra] <= {{(REG_W-DELAY_BITS){1'b0}},
                                 wait_count + {{(DELAY_BITS-1){1'b0}}, 1'b1}};
                    ft       <= ~wait_hit;
                    pc       <= next_pc;
                    state    <= S_EXEC;
                end
            end

            S_SHIFT: if (sh_done) begin
                if (op != AXPE_OP_SHOUT) regs[ra] <= sh_rx;
                pc    <= next_pc;
                state <= S_EXEC;
            end

            default: ;  // S_STOP is terminal until reset
            endcase
        end
    end
endmodule

`default_nettype wire
