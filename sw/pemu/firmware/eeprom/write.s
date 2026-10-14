; AT24C256 single-byte write. The host must poll readiness after STOP; a clean
; HALT/ACK only accepts this transaction, not completion of nonvolatile write.
.equ DEV_ADDR, 0x50
.equ WORD_ADDR, 0x7F00
.equ DATA_BYTE, 0x5A
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
    LDIL R0, DATA_BYTE, D=0
    CALL send_checked, D=0
    LDIL R0, 0x80, D=0
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
