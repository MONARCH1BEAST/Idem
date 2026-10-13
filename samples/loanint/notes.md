# loanint — I/O Notes

## Input order (one integer per line, no decimal point)
1. PRINCIPAL — PIC 9(7)V99, valid range 0–100000
2. RATE      — PIC 9(2)V99, valid range 0–99
3. TERM      — PIC 9(3),    valid range 0–360

COBOL implies the decimal position from the PIC clause. Do NOT include a
decimal point in stdin.

## Output labels and format
INTEREST=<PIC 9(7)V99>   left-padded to 10 characters total ("0010000.00")
TOTAL=<PIC 9(7)V99>      left-padded to 10 characters total ("0110000.00")

## Worked example
stdin:
10000
5
12

stdout:
INTEREST=0000500.00
TOTAL=0010500.00

## Verified
Compiled with cobc 3.2.0 and JDK 21. All 26 verification cases pass.