`default_nettype none
module axpe_primer_pads (
    input wire [7:0] drive_value, drive_enable,
    output wire [7:0] sample_value,
    inout wire [7:0] pins
);
    genvar i;
    generate for (i=0;i<8;i=i+1) begin : pin_buffer
        assign pins[i] = drive_enable[i] ? drive_value[i] : 1'bz;
    end endgenerate
    assign sample_value = pins;
endmodule
`default_nettype wire
