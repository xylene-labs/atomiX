; axpe SPI mode 0, full duplex, MSB-first.
;
; One SHIO instruction carries the whole byte in both directions, because the
; clocked cell (see axpe-isa.md 5.1) puts the clock edge and the sample point
; where SPI mode 0 wants them. The bit period is the instruction's delay field,
; so the listing states the SCK frequency rather than implying it.
;
; Pins:  uio[4] = SCK, uio[5] = MOSI, uio[6] = MISO, uio[7] = CS (active low)
;
; R0 in  = byte to send
; R0 out = byte received

.equ SCK_PIN,    4
.equ MOSI_PIN,   5
.equ MISO_PIN,   6
.equ CS_MASK,    0x80

; SCK, MOSI and CS are driven; MISO stays an input.
.equ DRIVEN,     (1 << SCK_PIN) | (1 << MOSI_PIN) | CS_MASK

; A clocked cell splits at its half point, so the period must be even and
; non-zero. 50 cycles at 50 MHz is 1 MHz SCK.
.equ SPI_PERIOD, 50

; SHCFG = {cpha, cpol, ord, din[3:0], dout[3:0], clk[3:0]}
; Mode 0 is cpol=0, cpha=0; ord=1 selects MSB-first, as SPI expects.
.equ SHCFG_W,    SCK_PIN | (MOSI_PIN << 4) | (MISO_PIN << 8) | (1 << 12)

spi_xfer:
    LDIL   R1, SHCFG_W & 0xFF,        D=0
    LDIH   R1, (SHCFG_W >> 8) & 0xFF, D=0
    SHCFG  R1,                        D=0
    PDRN   0x00,                      D=0            ; push-pull; SPI is not open-drain
    ; Idle levels before the driver, because pin_latch resets to zero: enabling
    ; the outputs first would assert CS and pulse SCK inside it, and a target
    ; would clock in a bit that no master sent.
    PINSET CS_MASK,                   D=0            ; CS idle is high
    PINCLR (1 << SCK_PIN),            D=0            ; SCK idles at cpol=0
    PDIR   DRIVEN,                    D=0
    PINCLR CS_MASK,                   D=SPI_PERIOD   ; assert CS, one bit time of setup
    SHIO   R0, 8,                     D=SPI_PERIOD   ; send and receive together
    PINSET CS_MASK,                   D=SPI_PERIOD   ; release CS
    RET                               D=0
