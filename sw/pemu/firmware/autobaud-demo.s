; Loadable program: measure an unknown peer's bit rate, then answer at it.
;
; This is the program PE-15 exists for, and the difference it demonstrates is
; the whole of the measurement claim. Nothing in this file, in autobaud.s, or in
; uart.s names the peer's baud rate; the only number that reaches the shift
; engine is the one `autobaud` counted off the wire. Load it against a peer at
; any rate and it answers at that rate.
;
; Order matters. `autobaud` makes every uio pin an input, so TX is undriven
; while it listens and `uart_init` runs afterwards -- which is also the only
; order that obeys the PDIR rule, since uart_init sets the idle level before it
; enables the driver.
;
; Pins:  uio[0] = TX (driven), uio[1] = RX (sampled)
; Result: uo_out = the measured period's low byte, so a host can read back what
;         the chip decided the rate was, not merely that it transmitted.

.equ DEMO_BYTE, 0x37

_start:
    CALL   autobaud,          D=0       ; R2 = measured cycles per bit, 0 if silent
    CALL   uart_init,         D=0       ; idle high, then drive
    LDIL   R0, DEMO_BYTE,     D=0
    LDIH   R0, 0x00,          D=0
    CALL   uart_tx_measured,  D=0       ; ...at R2 cycles per bit
    POUT   R2,                D=0
    HALT                      D=0

.include "autobaud.s"
.include "uart.s"
