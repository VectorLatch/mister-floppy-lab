# Bart v18 — CPU /DTACK gate diagnosis

**Purpose**: v17 on original Bart IPF produced Mode 2 BUSY_WRITES=5,186,
WAIT_CANDIDATES=0, and v16 HITS=0. This proves some address cycles overlapped
Agnus busy, but does not prove a CPU write was still pending at the point of
overlap. v18 distinguishes pre-/post-ack and counts actual write strobes.

## Design

Built on v17 diagnostics, preserving the existing v15 CPU timing controls,
v16 real-busy interlock and physical floppy Main. Adds eight **32-bit**
read-only counters; does not change the CPU acknowledgement or DMA logic.
Sampling is once per CPU `/AS` transaction, with distinct event detectors:

| Counter | Interpretation |
|---|---|
| PREACK_BUSY | CPU blitter-register address transaction overlaps busy while `_ta_n=1` (not yet acknowledged) |
| POSTACK_BUSY | Such overlap while `_ta_n=0` (already acknowledged) |
| PREACK_RAW_LOW | PREACK_BUSY with the raw CPU /AS still asserted |
| PREACK_RAW_HIGH | PREACK_BUSY after raw /AS deasserted, despite the synchronised latch still showing the transaction |
| PREACK_WRITES | CPU blitter-register writes with `_ta_n=1`, whether busy or not |
| WRITE_STROBES | Blitter-register writes whose actual bridge `hwr/lwr` strobe asserted |
| BUSY_STROBES | Those actual register write strobes while Agnus is busy |
| ACTIVE_WAITS | V16 interlock actually asserted (should match v16 observations) |

The counters may overlap (one transaction can enter multiple categories).
`PREACK_BUSY` may be larger than `PREACK_RAW_LOW+PREACK_RAW_HIGH` only if
the source snapshot has changed; in a correctly functioning build the
two latter categories partition it by raw AS state.

v17 `EC00` snapshots both v17 and v18 counters on the same FPGA edge,
`EC01` clears both. v18 `ED7F` must return signature `D718`, and
`ED20..ED2F` read the frozen 16-bit halves. The matching Main checks
both `EC7F=C717` and `ED7F=D718`, and verifies the EC2E snapshot sequence.

## Mac commands

```bash
cd "$HOME/Downloads/mister-floppy-lab-starter"
bash scripts/set-bart-v15-timing.sh 1 0 0 0 0 0 mister
bash scripts/set-bart-v16-blitter.sh 2 64 mister
bash scripts/bart-v18-gates.sh clear mister
# Three Bart boots via F12 Reset
bash scripts/bart-v18-gates.sh snapshot mister
bash scripts/bart-v17-counters.sh snapshot mister
bash scripts/set-bart-v16-blitter.sh status mister
```

Do not change timeout while WAIT_CANDIDATES and HITS are zero.
If PREACK_BUSY>0 but PREACK_RAW_LOW=0, the raw-AS gate, not the
acknowledgement gate, may be causing the interlock to miss valid overlaps.
If PREACK_BUSY=0 and POSTACK_BUSY>0, the overlaps occur only after
acknowledgement and could not have been held by this v16 wait design.
If BUSY_STROBES>0 it confirms some writes were accepted while busy,
but by itself does not prove those writes violate real Amiga timing.

Strict six-seed Quartus workflow: `.github/workflows/build-bart-v18-bus-ack-gates.yml`.
Installer selects a passing seed, backs up MiSTer.ini and installs
`Minimig_v18_seedXX_Bart.rbf` and `MiSTer_Physical-Floppy_BartBusGatesV18`.
Do not install a failed-timing seed.