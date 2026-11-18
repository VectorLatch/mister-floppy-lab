# Bart v11 — live 68000 bus-wait experiment (A500+ / KS2 / ECS)

## Why this experiment

User has now **tested the same original Bart IPF successfully in Amiberry with exactly the A500+ / Kickstart 2 / ECS configuration** used on MiSTer. Under Minimig the same image still boots only intermittently (hangs, white-speckle hangs, red Amiga Software Failure 8000000B, and occasional playable game with corrupt playfield). Root-cause priority is **startup reliability**, not graphics fixes. A timing-clean Quartus fitter seed merely meets FPGA physical timing, not necessarily the original Amiga bus timing.

## Existing vs newly adjustable timing

- `MiSTer.ini` is parsed by a fixed key table in the Physical Floppy Main's `cfg.cpp` and **does not directly configure arbitrary FPGA 68000/Paula/Agnus parameters**. A new INI key requires custom HPS Main parsing + an SPI configuration register + FPGA RTL logic.
- Some options already exist through Minimig's OSD/preset system: CPU model/speed, chipset, chip/slow RAM and floppy speed. These are useful controls but are not general-purpose bit-level timing knobs.
- For **v11**, rather than editing `MiSTer.ini` (which requires restart and confounds tests), the runtime E8xx SPI control is exposed through the Linux HPS host. Mac SSH writes a one-line request file; the matching Main sends it to the FPGA and verifies the FPGA's acknowledgement. This requires **one FPGA build**, after which values change **without compiling or reloading the core**. Reset the emulated Amiga using F12 between conditions.

### The two knobs (each 0–3)

| Input | What is changed | Meaning of one increment |
|---|---|---|
| `chip` | 68000 `_DTACK` on bus accesses with `dbs` asserted (chip/slow/custom-register path), not MiSTer host cycles | One *additional eligible bus-acknowledge opportunity*; effective delay depends on Agnus bus and CCK state |
| `cia` | `_DTACK` for CPU accesses using `VPA/VMA` CIA ECLK handshaking | One additional **ECLK-qualified** acknowledge opportunity, which can be much longer than a simple 28MHz clock tick |

**0,0 (baseline)** preserves the upstream 68000 bus acknowledge condition. Nonzero values deliberately slow the selected bus transaction acknowledgements; they do **not** change PLL clock frequency, bitplane pixel clock, Agnus DMA slot order, floppy data bit timing, Paula internals, or any game code. This is a **diagnostic tool, not a confirmed fix**.

The RTL addition is localized to `rtl/minimig_m68k_bridge.v` and the runtime config forwarding in `rtl/minimig.v`, `rtl/paula.v`, `rtl/paula_floppy.v`. Other v8 CPU/Paula diagnostic readout slots and Rick ERSY v4 fix retained. Initial configuration in a freshly loaded core is 0/0; values survive emulated Amiga reset but not full FPGA reload.

### Safety/limitations

- Changing settings while a game is in progress can alter CPU bus timing immediately. **Use before starting Bart**, then reset the emulated Amiga through F12.
- Increasing CIA ECLK waits can make Workbench or games noticeably slower. Test **one knob at a time**.
- Different FPGA fitter placement might still change reliability at 0/0 even if the stock DTACK expression is logically preserved. Compare with earlier v8/v9 observations rather than attributing every difference to the dial.
- Correct FPGA and matching Physical Floppy Main are required. Do not point the E8xx controller at a stock/older Minimig core: the helper requires an exact `B8xx` FPGA readback and will fail if not acknowledged.
- The current diagnostic records bus wait **settings**, not all possible timing parameters or every machine event. The original v8 CPU/Paula on-demand diagnostic still provides CPU/halt/F-line/counters. A previously recorded *first* Line-F can be nonfatal; do not confuse that with OS error 8000000B.
- Failing to boot under all settings does not rule out timing errors in floppy, CPU internals, DMA or reset; it only tells us these two bus handshake delays didn't cure it.

## Build

Branch: `diagnostic/bart-runtime-bus-waits-v11`.

Workflow: `.github/workflows/build-bart-v11-runtime-waits.yml`. Six seeds compiled in parallel: **11, 15, 21, 22, 23, 24**. One shared Main reader/writer. Each compiled RBF is retained with SHA256 and all five timing margins before the strict gate; prefer best timing-clean seed and do not silently bypass timing failures.

Source: pinned upstream FPGA `7d5d3c2f685af4ce3eb361c22893fccd153f2d87`, Rick ERSY v4, Bart v1/v2/v3/v6/v8, then `scripts/patch_bart_fpga_runtime_bus_v11.py`. Physical Main pinned `d2757b2c420b1336f51c0ff641f3bad4d3c2c3c2`, Bart v1/v2/v3/v6/v8 then `scripts/patch_bart_main_runtime_bus_v11.py`.

## Install (after build finishes and timing-clean seed verified)

```bash
cd "$HOME/Downloads/mister-floppy-lab-starter"
git fetch origin
git switch diagnostic/bart-runtime-bus-waits-v11 2>/dev/null || \
  git switch --track origin/diagnostic/bart-runtime-bus-waits-v11
git pull --ff-only
bash scripts/install-bart-v11-selected-seed.sh <RUN_ID> <TIMING_PASS_SEED> mister
```

No `--allow-timing-fail` when selecting a valid seed. Installer preserves existing MiSTer.ini and copies unique `_Unstable/Minimig_Bart_BusWaits_v11_seedN.rbf` and `MiSTer_Physical-Floppy_BartBusWaitsV11`. Restart MiSTer, select installed RBF, retain **A500+ / KS2 / ECS** and same original Bart IPF.

## Adjust live without FPGA rebuild

All commands run on your Mac. Confirm that v11 Main and v11 FPGA are active.

```bash
cd "$HOME/Downloads/mister-floppy-lab-starter"

# Original (stock) CPU/chip/CIA acknowledge timing:
bash scripts/set-bart-v11-waits.sh 0 0 mister

# Extra single eligible chip/custom-register bus wait:
bash scripts/set-bart-v11-waits.sh 1 0 mister

# Extra two eligible chip/custom-register waits:
bash scripts/set-bart-v11-waits.sh 2 0 mister

# CIA ECLK wait only (try separately after baseline):
bash scripts/set-bart-v11-waits.sh 0 1 mister
```

For each command the helper waits for `/tmp/bart-v11-waits.last` and requires output like `OK BART_V11 CHIP_WAIT=1 CIA_WAIT=0 FPGA_ACK=B801`. **If there is no matching ack, do not trust the experiment.** Once acknowledged, press F12, reset the emulated Amiga, then boot Bart. There is **no recompile or FPGA reload** between settings.

Try a modest number of repeat starts at each setting and record four outcomes: `boot/play`, `hang`, `white speckles`, `red Software Failure`. Do not change the ROM/preset/memory configuration/disk or the other knob simultaneously. Start with 0/0 before trying other settings. If a setting seems materially better, confirm with more tries; 3–5 tries is a screening test, not statistically decisive when baseline success is rare.

If a hang or red alert recurs, existing v8 on-demand snapshot remains:
```bash
ssh root@mister 'rm -f /tmp/bart-snapshots.txt; touch /tmp/bart-snapshot.req; sleep 3; touch /tmp/bart-snapshot.req; sleep 3; cat /tmp/bart-snapshots.txt'
scp root@mister:/tmp/bart-snapshots.txt "$HOME/Downloads/bart-v11-startup-failure.txt"
```

Always retain `/tmp/bart-v11-waits.last` alongside the two snapshots as proof of the active parameter values.

## What we can conclude

A reproducible improvement with additional chip-bus or CIA ECLK waits would implicate that **class of CPU-peripheral handshake**, warranting a deeper read of the precise bus state. If no improvement, do not conclude 'timing is fine': test a different category (floppy/DMA, CPU reset/exception, RAM timing) **after evidence**, rather than exposing dozens of arbitrary dials.
