; axpe UART 8N1, transmit and receive.
;
; Reference: sw/pemu/isa/axpe-isa.md.  Every timing number below is declared in
; the instruction encoding, so `axpe_as.py --listing` prints this file's exact
; cycle cost rather than estimating it.
;
; Pins:  uio[0] = TX (driven), uio[1] = RX (sampled)

.equ CLK_HZ,   50000000
.equ BAUD_RATE, 115200
.equ BAUD,     CLK_HZ / BAUD_RATE      ; 434 cycles per bit
.equ HALFBIT,  BAUD / 2

.equ TX_MASK,  0x01
.equ RX_PIN,   1
.equ EDGE_FALL, 1
.equ RX_TIMEOUT, BAUD * 16

; SHCFG = {cpha, cpol, ord, din[3:0], dout[3:0], clk[3:0]}
; A clk index of 15 means "no clock pin", which is how UART borrows the shift
; engine: bits leave at the D bit period with nothing clocked alongside them.
.equ SHCFG_TX_LO, 15 | (0 << 4)        ; clk = none, dout = uio[0]
.equ SHCFG_RX_LO, 15                   ; clk = none; dout unused on this path
.equ SHCFG_RX_HI, 0x01                 ; din = uio[1], field [11:8] of SHCFG

; --- bus setup -------------------------------------------------------------
; A library, not a program: the entry point that loads into word 0 lives in
; uart-demo.s and pulls this file in, so one copy of the routine serves the
; model tests, the chip test and the submission demo.
; The latch is set before the driver is enabled, and the order is not a style
; choice. `pin_latch` resets to zero, so enabling the output first drives TX low
; for as long as it takes to raise it -- a glitch a receiver is entitled to
; latch as a start bit. An independent 8N1 receiver in sim/pemu found exactly
; that; the rule is now in the PDIR description in the ISA.
uart_init:
    PDRN   0x00,           D=0         ; push-pull; UART is not open-drain
    PINSET TX_MASK,        D=0         ; idle level first...
    PDIR   TX_MASK,        D=BAUD      ; ...then drive it. uio[1] stays an input
    RET                    D=0

; --- transmit ---------------------------------------------------------------
; R0 holds the byte.  Cost is exact: no WAITE on this path.
uart_tx:
    LDIL   R1, SHCFG_TX_LO, D=0
    LDIH   R1, 0x00,        D=0
    SHCFG  R1,              D=0
    PINCLR TX_MASK,         D=BAUD     ; start bit, held one bit time
    SHOUT  R0, 8,           D=BAUD     ; 8 data bits, BAUD cycles each
    PINSET TX_MASK,         D=BAUD     ; stop bit
    RET                     D=0

; --- receive ----------------------------------------------------------------
; Returns the byte in R0.  The WAITE makes this path bounded, not exact.
uart_rx:
    LDIL   R1, SHCFG_RX_LO, D=0
    LDIH   R1, SHCFG_RX_HI, D=0
    SHCFG  R1,              D=0
    WAITE  R3, (EDGE_FALL << 4) | RX_PIN, D=RX_TIMEOUT  ; R3 = idle cycles, unused here
    BR     T, rx_timeout,   D=0        ; T set means the line never started
    DELAY                   D=BAUD + HALFBIT   ; skip start bit, land mid-cell
    SHIN   R0, 8,           D=BAUD
    RET                     D=0

rx_timeout:
    LDIL   R0, 0x00,        D=0
    RET                     D=0

; --- transmit at a rate nobody configured -----------------------------------
; R0 holds the byte, R2 the bit period in cycles -- in practice whatever
; autobaud measured from a peer this chip was never told about.
;
; The whole 8N1 frame leaves as one 10-bit unclocked shift rather than as
; PINCLR/SHOUT/PINSET, and that is forced rather than stylistic: only the shift
; engine can take its cell duration from a register, so a start bit built from
; PINCLR would still be held for an immediate D. One cell of a frame at the
; wrong period is a framing error at the far end, and it would be the cell the
; receiver uses to find every other one.
;
; Frame, LSB-first: bit 0 is the start bit, bits 1..8 the byte, bit 9 the stop
; bit. The engine holds the last bit it drove, so the line idles high afterwards
; with no instruction needed to raise it.
;
; Cost is 10*max(P,1) and is *not* static -- `axpe_as.py --listing` prints the
; formula here where it prints a number for uart_tx. That is the honest
; difference between transmitting at a rate you were given and one you found.
uart_tx_measured:
    LDIL   R1, SHCFG_TX_LO, D=0
    LDIH   R1, 0x00,        D=0
    SHCFG  R1,              D=0
    SHL    R0, 1,           D=0         ; make room for the start bit at bit 0
    LDIL   R1, 0x00,        D=0
    LDIH   R1, 0x02,        D=0         ; R1 = 0x0200, the stop bit at bit 9
    OR     R0, R1,          D=0
    SHPER  R2,              D=0         ; every cell below now takes R2 cycles
    SHOUT  R0, 10, P                    ; start, 8 data bits, stop
    RET                     D=0
