; Loadable program: one full-duplex SPI mode 0 byte at 1 MHz.
;
; The byte the peer sends back is published with POUT, so the host reads it
; through STATUS without the chip needing a register-file read port.

.equ DEMO_BYTE, 0xA5

_start:
    LDIL   R0, DEMO_BYTE,  D=0
    CALL   spi_xfer,       D=0
    POUT   R0,             D=0         ; what the peer clocked back in
    HALT                   D=0

.include "spi.s"
