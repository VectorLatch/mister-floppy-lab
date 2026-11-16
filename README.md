# MiSTer / Greaseweazle floppy compatibility lab

Clean public reproduction and source investigation of MiSTer Minimig core / physical-floppy Main compatibility on a MiSTer Multisystem2 with a Greaseweazle V4.1. Preserve existing stable MiSTer installation and diagnose regressions without inheriting old FPGA experiments.

## Goals and ground rules

1. Build unmodified, pinned official Minimig source and pinned Physical Floppy v1.3 Main source separately.
2. Use official v1.3 released `MiSTer_Physical-Floppy` as the **initial** Main baseline; compare a source-built Main only after the baseline is recorded.
3. Install a distinct `Minimig_Lab_20261116.rbf` in `_Unstable`, never overwrite the stable core; never replace the normal `/media/fat/MiSTer` executable.
4. Record SHA-256, Quartus container digest, chosen seed, timing warnings/reports, firmware, media type, and emulator comparison for every attempt.
5. Change *one* thing per experiment, with reproducible rollback; later experiments use the optional `patches/fpga/` and `patches/main/` overlays. Do not launch multi-seed searches until a hypothesis needs them.
6. No ROMs, disk images, copied protected games, Wi-Fi credentials, personal paths, or device logins in this public repository.

See [UPSTREAM_LOCK.md](UPSTREAM_LOCK.md) for exact starting commits.

## First-time public repository creation (Mac)

Install GitHub CLI if needed (`brew install gh`), authenticate (`gh auth login`), then from this extracted directory run:

```bash
chmod +x scripts/*.sh
./scripts/create-public-repo.sh
```

The push starts two GitHub Actions jobs. The FPGA job uses Quartus 17.0.2, one seed (1), and attaches its RBF and compilation reports. The ARM job separately builds Physical Floppy Main v1.3. **Successful Action != proven timing or hardware compatibility.** Review Quartus timing reports before a hardware conclusion.

## Download and deploy latest successful workflow run (Mac)

```bash
REPO=VectorLatch/mister-floppy-lab
gh run list --repo "$REPO" --workflow build-baseline.yml --limit 5
# Replace RUN_ID and MISTER_IP with actual values:
./scripts/download-and-deploy.sh RUN_ID MISTER_IP
```

This retrieves and SHA-checks the freshly built FPGA core, downloads and SHA-checks the official Physical Floppy v1.3 Linux binary, backs up the active MiSTer.ini and previous lab binaries, and places the new RBF in `_Unstable`. The only ini changes are `[Minimig] main=MiSTer_Physical-Floppy` and `PFLOPPY_LOG=1` inserted before any video-specific subsections. Change other ini variants manually if you actually boot with one. The script never overwrites the normal `MiSTer` executable.

In the Minimig menu, select `_GREASEWEAZLE_.adf` for **read-only flux mode** (protected originals) or `_GREASEWEAZLE_DOS_.adf` for **write-enabled AmigaDOS** mode. For baseline tests, use flux mode and keep original disks write-protected. The placeholder is made by the Main when the core runs.

Log collection (on Mac):

```bash
ssh root@MISTER_IP 'tail -n 150 /media/fat/logs/pfloppy.log'
scp root@MISTER_IP:/media/fat/logs/pfloppy.log "$HOME/Downloads/pfloppy-baseline.log"
```

## Evidence-based test matrix

| Media/test | Previous observation; *not* new-baseline result | New-baseline result |
| --- | --- | --- |
| Lemmings original floppy | Previously booted via Greaseweazle | Not tested |
| Rick Dangerous original/IPF | Previous fix required experimental FPGA logic for immediate boot | Not tested |
| Bart vs. the Space Mutants physical/IPF | Froze at Ocean splash in old Minimig experiments; worked in Amiberry with physical floppy | Not tested |
| Lotus Turbo Challenge 2 | Reported disk error 1 on old Minimig; worked in WinUAE | Not tested |
| WWF WrestleMania Ocean 1991 | Track 0 side 0 release-dependent purple-screen behaviour observed in Amiberry | Not tested |

Preferred A500 baseline: Kickstart 1.3 / OCS / 512 KB Chip + 512 KB Slow; PAL. Log physical media and IPF results separately. Prior A500+ Kickstart 2.0 Rick Dangerous failure reproduced in WinUAE and is not evidence of a physical-floppy transport fault.

## Troubleshooting and safety

- If the physical floppy has trouble, test drive power, USB cable, Greaseweazle detection, and `PFLOPPY_LOG` first; keep the core and Main versions recorded.
- The current upstream `README.md` states the flux-mode Minimig requires a core built 2026-10-10 or newer. The pinned 2026-11-09 source qualifies by date, but building and testing it are still necessary.
- Restore the previous `MiSTer.ini` and `MiSTer_Physical-Floppy` from `/media/fat/backup-floppy-lab/<timestamp>/` if rollback is needed, and launch the old known-good core.
- You may need to allow the new repository in your GitHub app installation so the connected assistant can inspect and update it.
