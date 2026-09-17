; axpe autobaud: lock onto a UART whose bit rate nobody told us.
;
; This is the routine that justifies WAITE returning its elapsed count.  The
; chip is not reproducing a rate from a configuration register -- it is
; measuring a peer and then transmitting at whatever rate that peer uses.
; No host is involved.
;
; Method: on an idle-high line, the narrowest low pulse in a frame is exactly
; one bit period.  Sample several frames and keep the minimum, which rejects
; the wider multi-bit runs that a data pattern produces.  Sending 0x55 makes
; the very first low pulse already the answer, but taking a minimum means the
; routine does not depend on the peer being co-operative.
;
; Pins:  uio[1] = RX (sampled)
; Result: R2 = measured cycles per bit, or 0 if the line never spoke.

.equ RX_PIN,     1
.equ EDGE_RISE,  0
.equ EDGE_FALL,  1
.equ MAXWAIT,    50000              ; give up after this many idle cycles
.equ SAMPLES,    8                  ; low pulses to consider

.equ FALL_RX,    (EDGE_FALL << 4) | RX_PIN
.equ RISE_RX,    (EDGE_RISE << 4) | RX_PIN

autobaud:
    PDIR   0x00,            D=0     ; every uio pin an input; we only listen
    LDIL   R2, 0xFF,        D=0
    LDIH   R2, 0xFF,        D=0     ; R2 = narrowest pulse seen, start at max
    LDIL   R3, SAMPLES,     D=0     ; R3 = pulses left to sample
    LDIL   R4, 1,           D=0     ; R4 = the loop decrement

ab_loop:
    ; These two waits must stay ADJACENT. A WAITE occupies exactly the cycles
    ; it waited, so the pair measures a true interval only when nothing runs
    ; between them -- an instruction in the gap spends cycles the measurement
    ; cannot see, and the pulse reads that much narrow. The timeout check
    ; therefore comes after both; a silent line times out on both waits.
    WAITE  R0, FALL_RX,     D=MAXWAIT   ; R0 = idle time before the pulse
    WAITE  R1, RISE_RX,     D=MAXWAIT   ; R1 = width of the low pulse, in cycles
    BR     T, ab_silent,    D=0

    CMP    R1, R2,          D=0         ; C is set on borrow, so C means R1 < R2
    BR     NC, ab_next,     D=0
    MOV    R2, R1,          D=0         ; a new narrowest pulse

ab_next:
    SUB    R3, R4,          D=0
    BR     NZ, ab_loop,     D=0
    RET                     D=0         ; R2 now holds cycles per bit

ab_silent:
    LDIL   R2, 0x00,        D=0
    LDIH   R2, 0x00,        D=0
    RET                     D=0
