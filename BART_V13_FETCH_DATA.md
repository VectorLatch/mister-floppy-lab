# Bart v13 — CPU program-fetch bus DATA at the Line-F divergence

## Previous evidence
Bart SPS 0884 Disk 2 standalone, A500+ KS2 ECS, original IPF.
v12 with chip wait 1/CIA wait 0 showed:
- Playable run (corrupt playfield): LF12_COUNT=589, last decoded F85F,
  internal PC 00070912, external fetch bus address 00070910.
- Late 8000000B failure: LF12_COUNT=590, last decoded FC00,
  internal PC 0007087C, external fetch bus address 0007087A.
Both CPU snapshots kept executing after the alert (FX_HALT=0).
The first 589 events are *not* known to be byte-for-byte identical;
only first and penultimate reported events match. The exception may
be deliberate protection or invalid memory/CPU execution.

## v13 mechanism (observation only)
Based on v12 with its retained v11 E8 CPU bus waits and Rick ERSY v4.
Upstreams pinned as before in UPSTREAM_LOCK.md.
The new FPGA recorder observes the actual fx68k CPU data signal
(cpu_din, wired to fx68k.iEdb) during *acknowledged, program-space READ*
cycles (FC[1:0]=10, AS asserted, R/W=read, effective DTACK asserted,
sampled on ph2). It records three latest address/16-bit data pairs
and whether each was routed through RAM. This is not asserted to be
an instruction that was eventually executed: internal fx68k prefetch
pipeline can differ. We therefore also sample the CPU's *actual*
Irc prefetch register and decoded Ir, via read-only debug outputs.
The current bus address and data at the moment of Line-F recognition
are also stored but may represent another bus cycle.

The snapshot is frozen at the latest rising-edge-qualified fx68k
Line-F sequencer event (v8/v12 trigger). The event count saturates at
65535. Existing on-demand E7 64-word transport words 0-44 are unchanged.
Slots 45-63 are REUSED from v12 (not additive). The matched FPGA/Main
signature becomes B4AF and version 13:
45/46 PC, 47/48 latest ACK read address, 49/50 previous ACK address,
51/52 third ACK address, 53/54 live bus addr at Line-F,
55/56/57 ACK data words in latest-to-oldest order, 58 live bus data,
59 decoded Ir, 60 internal Irc, 61 event count, 62 previous Ir,
63 bit flags for valid snapshots, RAM routing and bus conditions.

No CPU data, address, DTACK, instruction, RAM, DMA, floppy or graphics
functional signal is modified. Diagnostic logic may still change
FPGA fitter placement; strict timing checks are required before use.

## Build
Branch diagnostic/bart-instruction-fetch-data-v13
Workflow .github/workflows/build-bart-v13-fetch-data.yml
Initial six FPGA seeds 11,15,21,22,23,24 all missed setup (best seed 21 -0.039 ns). Retry batch: six parallel seeds 3,7,13,17,27,31, with unchanged functional HDL; one shared ARM Main job. No timing-violating FPGA should be installed by default.
The installer verifies per-seed SHA256, source SHA, matching Main,
and nonnegative setup/hold/recovery/removal/min pulse margins.
A workflow can show overall failure if four seeds fail timing, while
an individual clean seed is still installable.

## Installation after passing run
From Mac:
    cd "$HOME/Downloads/mister-floppy-lab-starter"
    git fetch origin
    git switch --track origin/diagnostic/bart-instruction-fetch-data-v13
    git pull --ff-only
    bash scripts/install-bart-v13-first-passing-seed.sh RUN_ID mister

The script saves MiSTer.ini and installs independent filenames. It
does not overwrite v11/v12 or their matching Main executables.
Reboot MiSTer, select the installed
_Unstable/Minimig_Bart_FetchData_v13_seedSEED.rbf,
keep A500+ KS2 ECS and Bart SPS0884 Disk2 original IPF.
Set experimental CPU waits to chip1/CIA0, confirm B801:
    bash scripts/set-bart-v11-waits.sh 1 0 mister
F12-reset the emulated Amiga and boot. After the late 8000000B
alert, do NOT reset; capture two snapshots:
    ssh root@mister 'rm -f /tmp/bart-snapshots.txt; touch /tmp/bart-snapshot.req; sleep 3; touch /tmp/bart-snapshot.req; sleep 3; cat /tmp/bart-snapshots.txt'
    scp root@mister:/tmp/bart-snapshots.txt "$HOME/Downloads/bart-v13-failed.txt"

Compare IF13_COUNT, IR, IRC and three IF13_FETCHn_ADDR/DATA pairs
against v12 last event and, if possible, one playable v13 capture.
No CPU fault can be attributed solely to a speculative bus snapshot.
