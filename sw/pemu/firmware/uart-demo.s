; Loadable program: bring up the line and transmit one byte at 115200 8N1.
;
; This is what the host loads over the port in docs/pemu-host-protocol.md, and
; what an independent UART receiver decodes in sim/pemu. The routine itself
; lives in uart.s and is included rather than copied, because a protocol
; written twice is two protocols.

.equ DEMO_BYTE, 0x41                   ; 'A': 0100_0001, so both levels appear

_start:
    CALL   uart_init,      D=0
    LDIL   R0, DEMO_BYTE,  D=0
    CALL   uart_tx,        D=0
    POUT   R0,             D=0         ; publish the byte the host can read back
    HALT                   D=0

.include "uart.s"
