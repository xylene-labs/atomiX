; Loadable program: a complete I2C transaction against a 7-bit peer at 0x50.
;
; START, address+W, data byte, repeated START, address+R, one byte read with a
; NACK, STOP. That covers every element the board asks PE-07 to demonstrate,
; and each acknowledgement is checked rather than assumed: a peer that does not
; answer ends the transaction with a STOP and a failure code, instead of
; clocking data at nobody.

.equ DEV_ADDR,  0x50
.equ DEV_W,     DEV_ADDR << 1
.equ DEV_R,     (DEV_ADDR << 1) | 1
.equ PAYLOAD,   0x5A
.equ FAIL_CODE, 0xEE

_start:
    CALL   i2c_init,       D=0
    CALL   i2c_start,      D=0

    LDIL   R0, DEV_W,      D=0
    CALL   i2c_write,      D=0
    LDIL   R3, 0x00,       D=0
    CMP    R2, R3,         D=0
    BR     NZ, i2c_nack,   D=0

    LDIL   R0, PAYLOAD,    D=0
    CALL   i2c_write,      D=0
    CMP    R2, R3,         D=0
    BR     NZ, i2c_nack,   D=0

    CALL   i2c_restart,    D=0
    LDIL   R0, DEV_R,      D=0
    CALL   i2c_write,      D=0
    CMP    R2, R3,         D=0
    BR     NZ, i2c_nack,   D=0

    CALL   i2c_read_nack,  D=0
    POUT   R0,             D=0         ; the byte the peer sent
    CALL   i2c_stop,       D=0
    HALT                   D=0

; A peer that never acknowledged: release the bus properly and say so.
i2c_nack:
    LDIL   R0, FAIL_CODE,  D=0
    POUT   R0,             D=0
    CALL   i2c_stop,       D=0
    HALT                   D=0

.include "i2c.s"
