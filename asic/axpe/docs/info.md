## How it works

axpe executes a 32-bit timed instruction set designed for protocol I/O.  Its
fixed SPI target loads and reads the writable instruction store while the core
is stopped, then starts or stops the core without changing the hardened design.
Firmware controls eight push-pull/open-drain bidirectional pads and eight
outputs; instructions can shift, wait for measured edges and use a measured
period for a later transfer.

The exported early-flow profile has 64 instruction words.  It holds every
mandatory demo currently shipped by atomiX, but it is intentionally a measured
fallback: the pinned CMOS5L PDK does not provide a compatible SRAM macro view.

## How to test

Hold `ui_in[2]` high during reset.  The host port is SPI mode 0, MSB first:
`ui_in[0]` is SCLK, `ui_in[1]` is MOSI, `ui_in[2]` is active-low CS, and
`uo_out[0]` is MISO while selected.  Commands are WRITE `0x01` + 8-bit address
+ 32-bit word, READ `0x02` + address + 32 clocks, RUN `0x03`, STOP `0x04`, and
STATUS `0x05` + 16 clocks.  SCLK must not exceed `clk/4`.

## External hardware

A 3.3 V SPI controller is sufficient to load programs.  Protocol-specific
pull-ups and level shifting depend on the firmware and external bus.
