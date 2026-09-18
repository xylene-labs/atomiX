; axpe I2C master, standard mode.
;
; I2C is the protocol that cannot be expressed without the open-drain pad path:
; a master never drives SDA or SCL high, it releases them and lets the bus
; pull-ups do it. `PDRN` is what makes a written 1 a release rather than a
; drive, which is why it sits in the pad path rather than in firmware.
;
; The clocked shift cell is already I2C's bit cell. Per axpe-isa.md 5.1 data
; changes at the cell start and the clock takes its leading edge at D/2, so
; with cpol=0 and cpha=0 the data moves while SCL is low and the peer samples
; it while SCL is high -- which is the I2C bit, not an approximation of it.
; SDA is both the data output and the data input, and `din == dout` is legal
; for exactly this reason.
;
; Pins:  uio[2] = SDA (open-drain), uio[3] = SCL (open-drain)
;
; What this file does not do: clock stretching. A peer that holds SCL low is
; not waited for, because the shift engine drives the clock from its own timer.
; Supporting it needs a WAITE on SCL between cells, which is a different
; routine and is not claimed here.

.equ CLK_HZ,      50000000
.equ SCL_HZ,      100000
.equ BIT_PERIOD,  CLK_HZ / SCL_HZ      ; 500 cycles, even as a clocked cell must be
.equ HALF,        BIT_PERIOD / 2
.equ QUARTER,     BIT_PERIOD / 4

.equ SDA_PIN,     2
.equ SCL_PIN,     3
.equ SDA_MASK,    1 << SDA_PIN
.equ SCL_MASK,    1 << SCL_PIN
.equ BUS_MASK,    SDA_MASK | SCL_MASK

; SHCFG = {cpha, cpol, ord, din[3:0], dout[3:0], clk[3:0]}
; ord=1 is MSB first, which is the only order I2C has. cpol=0 and cpha=0 put
; the sample point on the rising edge, where the peer expects it.
.equ SHCFG_W,     SCL_PIN | (SDA_PIN << 4) | (SDA_PIN << 8) | (1 << 12)

.equ RELEASED,    0x01                 ; one bit, high: the master lets go of SDA

; --- bus setup --------------------------------------------------------------
; Leaves both lines released and the shift engine configured.
i2c_init:
    PDRN   BUS_MASK,                  D=0        ; open-drain: 1 releases, 0 drives low
    ; Release before enabling the pads. pin_latch resets to zero, so the other
    ; order pulls both lines down for as long as it takes to raise them, which
    ; on a shared bus is this master claiming a bus it has not started.
    PINSET BUS_MASK,                  D=0
    PDIR   BUS_MASK,                  D=QUARTER  ; idle bus is high on both lines
    LDIL   R1, SHCFG_W & 0xFF,        D=0
    LDIH   R1, (SHCFG_W >> 8) & 0xFF, D=0
    SHCFG  R1,                        D=0
    RET                               D=0

; --- START: SDA falls while SCL is high --------------------------------------
i2c_start:
    PINSET SDA_MASK,                  D=QUARTER
    PINSET SCL_MASK,                  D=QUARTER
    PINCLR SDA_MASK,                  D=HALF
    PINCLR SCL_MASK,                  D=QUARTER  ; SCL low, ready for the first cell
    RET                               D=0

; --- repeated START: release SDA while SCL is low, then start again ----------
; The bus is not given up in between, which is the whole point: an addressed
; peer stays addressed across the turnaround from write to read.
i2c_restart:
    PINSET SDA_MASK,                  D=QUARTER
    PINSET SCL_MASK,                  D=HALF
    PINCLR SDA_MASK,                  D=HALF
    PINCLR SCL_MASK,                  D=QUARTER
    RET                               D=0

; --- STOP: SDA rises while SCL is high, then the bus is released -------------
i2c_stop:
    PINCLR SDA_MASK,                  D=QUARTER
    PINSET SCL_MASK,                  D=HALF
    PINSET SDA_MASK,                  D=HALF
    RET                               D=0

; --- write R0, returning the peer's answer in R2 (0 = acknowledged) ----------
; The ninth cell is the acknowledgement: the master releases SDA and clocks
; once more, so what it reads back is the peer pulling the line down, or the
; pull-up leaving it high when nothing did.
i2c_write:
    SHOUT  R0, 8,                     D=BIT_PERIOD
    LDIL   R2, RELEASED,              D=0
    SHIO   R2, 1,                     D=BIT_PERIOD
    RET                               D=0

; --- read a byte into R0 and refuse it, which is what a master does last -----
; Releasing SDA for all eight cells is what lets the peer drive them; leaving
; it released for the ninth is the NACK that tells the peer to stop sending.
i2c_read_nack:
    LDIL   R0, 0xFF,                  D=0
    SHIO   R0, 8,                     D=BIT_PERIOD
    LDIL   R2, RELEASED,              D=0
    SHIO   R2, 1,                     D=BIT_PERIOD
    RET                               D=0
