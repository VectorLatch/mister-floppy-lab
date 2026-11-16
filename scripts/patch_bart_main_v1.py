#!/usr/bin/env python3
"""Apply strictly read-only, rate-limited Bart Disk 2 tracing to pinned Main v1.3.

This logs flux-track requests and Main->FPGA streaming activity, not CPU PC,
Paula DMA completion or actual data integrity. Do not infer those from these logs.
"""
from pathlib import Path
import sys

def replace_once(src, original, replacement, label):
    count=src.count(original)
    if count != 1:
        raise RuntimeError(f"{label}: expected one occurrence, found {count}")
    return src.replace(original,replacement,1)

def patch(root):
    p=root / "support/minimig/minimig_fdd.cpp"
    src=p.read_text()
    src=replace_once(src,
        '#include "../physical_floppy/physical_floppy.h"',
        '#include "../physical_floppy/physical_floppy.h"\n#include "../physical_floppy/pf_drive.h"\n#include <time.h>',
        "logging header")

    telemetry=r'''
// Bart Disk 2 host-side diagnostic: no floppy data or control changes.
struct BartTrace {
    const FluxFile *source[4] = {nullptr, nullptr, nullptr, nullptr};
    int last_track[4] = {-1, -1, -1, -1};
    uint16_t last_sync[4] = {0xffff, 0xffff, 0xffff, 0xffff};
    unsigned long requests[4] = {0, 0, 0, 0};
    unsigned long blocks[4] = {0, 0, 0, 0};
    unsigned long dummy[4] = {0, 0, 0, 0};
    unsigned long select_fails[4] = {0, 0, 0, 0};
    unsigned long track_events[4] = {0, 0, 0, 0};
    unsigned long previous_requests[4] = {0, 0, 0, 0};
    uint64_t next_report_ms[4] = {0, 0, 0, 0};
};
static BartTrace bart_trace;

static uint64_t bart_trace_now_ms()
{
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return (uint64_t)t.tv_sec * 1000ULL + (uint64_t)t.tv_nsec / 1000000ULL;
}

static void bart_trace_request(unsigned sel, unsigned track, unsigned char c1)
{
    if (sel >= 4 || !df[sel].fluxFile) return;
    BartTrace &t = bart_trace;
    if (t.source[sel] != df[sel].fluxFile) {
        t.source[sel] = df[sel].fluxFile;
        t.last_track[sel] = -1;
        t.last_sync[sel] = 0xffff;
        t.requests[sel] = t.blocks[sel] = t.dummy[sel] = 0;
        t.select_fails[sel] = t.track_events[sel] = 0;
        t.previous_requests[sel] = 0;
        t.next_report_ms[sel] = 0;
        pf_log("BARTTRACE start DF%u source=%s", sel,
            pfloppy_is_amiga_placeholder(df[sel].name) ? "Greaseweazle" : "IPF/SCP");
    }
    ++t.requests[sel];
    if (t.last_track[sel] != (int)track) {
        t.last_track[sel] = (int)track;
        ++t.track_events[sel];
        if (t.track_events[sel] <= 80) {
            pf_log("BARTTRACE DF%u track=%u cyl=%u head=%u c1=%02x event=%lu",
                   sel, track, track / 2, track & 1, c1, t.track_events[sel]);
        }
    }
    const uint64_t now = bart_trace_now_ms();
    if (now >= t.next_report_ms[sel]) {
        pf_log("BARTTRACE DF%u total_requests=%lu delta=%lu track=%d flux_blocks=%lu dummy_blocks=%lu select_failures=%lu transitions=%lu",
               sel, t.requests[sel], t.requests[sel]-t.previous_requests[sel],
               t.last_track[sel], t.blocks[sel], t.dummy[sel],
               t.select_fails[sel], t.track_events[sel]);
        t.previous_requests[sel] = t.requests[sel];
        t.next_report_ms[sel] = now + 3000;
    }
}
'''
    src=replace_once(src,
        'unsigned char drives = 0; // number of active drives reported by FPGA (may change only during reset)',
        telemetry+'\nunsigned char drives = 0; // number of active drives reported by FPGA (may change only during reset)',
        "trace definition")

    src=replace_once(src,
        '\tif (fluxMode) {\n\t\tdrive->fluxFile->selectTrack(drive->track);\n\t\tsector = 0;',
        '\tif (fluxMode) {\n\t\tif (!drive->fluxFile->selectTrack(drive->track)) ++bart_trace.select_fails[drive - df];\n\t\tsector = 0;',
        "flux select")

    src=replace_once(src,
        '\t\tif (fluxMode) {\n\t\t\tif (!drive->fluxFile->fluxRead((uint16_t*)&mfm_data, sizeof(mfm_data) / sizeof(uint16_t))) {\n\t\t\t\tdrive->fluxFile->fluxDummyRead((uint16_t*)&mfm_data, sizeof(mfm_data) / sizeof(uint16_t)); // make ups some data',
        '\t\tif (fluxMode) {\n\t\t\tif (!drive->fluxFile->fluxRead((uint16_t*)&mfm_data, sizeof(mfm_data) / sizeof(uint16_t))) {\n\t\t\t\t++bart_trace.dummy[drive - df];\n\t\t\t\tdrive->fluxFile->fluxDummyRead((uint16_t*)&mfm_data, sizeof(mfm_data) / sizeof(uint16_t)); // make ups some data\n\t\t\t} else {\n\t\t\t\t++bart_trace.blocks[drive - df];',
        "flux data counters")

    src=replace_once(src,
        '\t\tif (track >= drive->tracks)\n\t\t\ttrack = drive->tracks - 1;\n\n\t\t// workaround for Copy Lock',
        '\t\tif (track >= drive->tracks)\n\t\t\ttrack = drive->tracks - 1;\n\t\tif (fluxMode && bart_trace.last_sync[drive - df] != dsksync) {\n\t\t\tbart_trace.last_sync[drive - df] = dsksync;\n\t\t\tpf_log("BARTTRACE DF%ld DSKSYNC=%04x", (long)(drive - df), dsksync);\n\t\t}\n\n\t\t// workaround for Copy Lock',
        "sync transitions")

    src=replace_once(src,
        '\t\tsel = (c1 >> 6) & 0x03;\n\t\tdf[sel].track = c2;\n\t\tReadTrack(&df[sel]);',
        '\t\tsel = (c1 >> 6) & 0x03;\n\t\tbart_trace_request(sel, c2, c1);\n\t\tdf[sel].track = c2;\n\t\tReadTrack(&df[sel]);',
        "request hook")
    p.write_text(src)
    print("Bart Main tracing instrumented (logging only).")

if __name__=="__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: patch_bart_main_v1.py <checked-out physical-floppy Main source>")
    patch(Path(sys.argv[1]))
