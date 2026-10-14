; START, address+W, ACK/NACK, STOP; no word address or data is transmitted.
; 0x80 = ready; 0 = busy/absent/NACK. Deadline/retry interval belong to host.
.equ DEV_ADDR, 0x50
_start:
    CALL i2c_init, D=0
    LDIL R3, 0, D=0
    LDIH R3, 0, D=0
    CALL i2c_start, D=0
    LDIL R0, DEV_ADDR << 1, D=0
    CALL i2c_write, D=0
    CMP R2, R3, D=0
    BR NZ, nack, D=0
    LDIL R0, 0x80, D=0
    POUT R0, D=0
    CALL i2c_stop, D=0
    HALT D=0
nack:
    LDIL R0, 0, D=0
    POUT R0, D=0
    CALL i2c_stop, D=0
    HALT D=0
.include "../i2c.s"
