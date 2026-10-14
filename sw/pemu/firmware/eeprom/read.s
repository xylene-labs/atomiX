; AT24C256 random single-byte read: two word-address bytes, repeated START,
; address+R, read with master NACK, STOP. Shared routines use open-drain pads.
; Return 0x80|nibble on success; 0 on NACK. RETURN_SHIFT=0 or 4 lets the host
; reconstruct every byte without confusing a data value with an error code.
.equ DEV_ADDR, 0x50
.equ WORD_ADDR, 0x7F00
.equ RETURN_SHIFT, 0
_start:
    CALL i2c_init, D=0
    LDIL R3, 0, D=0
    LDIH R3, 0, D=0
    CALL i2c_start, D=0
    LDIL R0, DEV_ADDR << 1, D=0
    CALL send_checked, D=0
    LDIL R0, (WORD_ADDR >> 8) & 0xFF, D=0
    CALL send_checked, D=0
    LDIL R0, WORD_ADDR & 0xFF, D=0
    CALL send_checked, D=0
    CALL i2c_restart, D=0
    LDIL R0, (DEV_ADDR << 1) | 1, D=0
    CALL send_checked, D=0
    CALL i2c_read_nack, D=0
    SHR R0, RETURN_SHIFT, D=0
    LDIL R4, 0x0F, D=0
    AND R0, R4, D=0
    LDIL R4, 0x80, D=0
    OR R0, R4, D=0
    POUT R0, D=0
    CALL i2c_stop, D=0
    HALT D=0
nack:
    LDIL R0, 0, D=0
    POUT R0, D=0
    CALL i2c_stop, D=0
    HALT D=0
send_checked:
    CALL i2c_write, D=0
    CMP R2, R3, D=0
    BR NZ, nack, D=0
    RET D=0
.include "../i2c.s"
