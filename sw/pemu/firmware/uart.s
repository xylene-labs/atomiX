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

_start:
    PDIR   TX_MASK,        D=0         ; uio[0] drives, uio[1] stays an input
    PDRN   0x00,           D=0         ; push-pull; UART is not open-drain
    PINSET TX_MASK,        D=0         ; idle line is high
    HALT                   D=0

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
