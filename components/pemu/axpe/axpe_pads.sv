// uio pad control: direction and open-drain, resolved into a Tiny Tapeout
// {out, oe} pair.
//
// Open-drain is not a convenience. I2C requires SDA and SCL to be released
// rather than driven high, so a pin in the drain mask drives low and
// tri-states instead of driving high. Without it I2C cannot be expressed at
// all, which is why this sits in the pad path rather than in firmware.
`default_nettype none

module axpe_pads #(
    parameter int UIO_PINS = 8
) (
    input  wire [UIO_PINS-1:0] latch_value,   // what firmware wrote
    input  wire [UIO_PINS-1:0] direction,     // 1 = drive
    input  wire [UIO_PINS-1:0] drain,         // 1 = open-drain
    output wire [UIO_PINS-1:0] uio_out,
    output wire [UIO_PINS-1:0] uio_oe
);
    // An open-drain pin releases when its latch is high, so it is only enabled
    // while driving low. This mirrors axpe_output_enable() in the golden model.
    assign uio_oe  = direction & ~(drain & latch_value);
    assign uio_out = latch_value;
endmodule

`default_nettype wire
