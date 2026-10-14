`timescale 1ns/1ps
module axpe_primer_pads_tb;
    tri [7:0] pins;
    reg [7:0] latch_value=8'hff, direction=0, drain=0;
    wire [7:0] drive_value, drive_enable, sample_value;
    reg peer_sda_low=0;
    assign pins[2] = peer_sda_low ? 1'b0 : 1'bz;
    genvar i;
    generate for (i=0;i<8;i=i+1) begin pullup(pins[i]); end endgenerate
    axpe_pads control(.latch_value(latch_value), .direction(direction), .drain(drain),
                     .uio_out(drive_value), .uio_oe(drive_enable));
    axpe_primer_pads dut(.drive_value(drive_value), .drive_enable(drive_enable),
                        .sample_value(sample_value), .pins(pins));
    initial begin
        #100;
        if (pins !== 8'hff) $fatal(1,"released pins must resolve to pull-ups");
        direction=8'hff; drain=8'hff; #100;
        if (drive_enable !== 0 || pins !== 8'hff) $fatal(1,"open-drain high must release");
        peer_sda_low=1; #100;
        if (sample_value[2] !== 1'b0) $fatal(1,"external ACK must pull released SDA low");
        peer_sda_low=0; latch_value=0; #100;
        if (pins !== 0) $fatal(1,"open-drain low must drive low");
        drain=0; latch_value=8'hff; #100;
        if (pins !== 8'hff) $fatal(1,"push-pull high must drive high");
        peer_sda_low=1; #100;
        if (pins[2] !== 1'bx) $fatal(1,"push-pull contention must be visible as X");
        direction=0; #100;
        if (pins[2] !== 1'b0) $fatal(1,"release must remove contention");
        $display("axpe Primer pads: open drain/release, external ACK, push-pull and contention PASS");
        $finish;
    end
endmodule
