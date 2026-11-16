#!/usr/bin/env python3
"""Add a watchdog to v1's Main-only Bart diagnostics; no FPGA or flux logic change.

Must run after patch_bart_main_v1.py. The watchdog reports when the Main loop
stops making requests and whether it is still inside ReadTrack().
"""
from pathlib import Path
import sys

def replace_once(src,needle,replacement,label):
    n=src.count(needle)
    if n!=1:
        raise RuntimeError(f"{label}: expected one occurrence, found {n}")
    return src.replace(needle,replacement,1)

def patch(root):
    p=root/"support/minimig/minimig_fdd.cpp"
    src=p.read_text()
    src=replace_once(src, "#include <time.h>", "#include <time.h>\n#include <atomic>\n#include <pthread.h>\n#include <unistd.h>", "watchdog headers")
    watcher=r'''
// Main-only Bart trace watchdog: independent of HandleFDD and ReadTrack.
// Atomic markers allow this background thread to report a stuck call safely.
static std::atomic<uint64_t> bart_watch_enter_ms{0};
static std::atomic<uint64_t> bart_watch_exit_ms{0};
static std::atomic<uint64_t> bart_watch_calls{0};
static std::atomic<int> bart_watch_in_read{0};
static std::atomic<int> bart_watch_track{-1};
static std::atomic<int> bart_watch_running{0};

static void *bart_watchdog_thread(void *)
{
    for (;;) {
        usleep(3000000);
        const uint64_t now = bart_trace_now_ms();
        const uint64_t entered = bart_watch_enter_ms.load();
        const uint64_t exited = bart_watch_exit_ms.load();
        const uint64_t age = now >= entered ? now - entered : 0;
        if (!entered) continue;
        pf_log("BARTTRACE HEARTBEAT calls=%llu track=%d in_read=%d last_enter_age_ms=%llu last_exit_age_ms=%llu",
               (unsigned long long)bart_watch_calls.load(),
               bart_watch_track.load(), bart_watch_in_read.load(),
               (unsigned long long)age,
               (unsigned long long)(exited && now >= exited ? now - exited : 0));
        if (age > 120000) break;
    }
    bart_watch_running.store(0);
    return NULL;
}

static void bart_watch_start()
{
    int expected = 0;
    if (!bart_watch_running.compare_exchange_strong(expected, 1)) return;
    pthread_t tid;
    if (pthread_create(&tid, NULL, bart_watchdog_thread, NULL)) {
        pf_log("BARTTRACE watchdog creation failed");
        bart_watch_running.store(0);
    } else {
        pthread_detach(tid);
    }
}
'''
    src=replace_once(src,"static void bart_trace_request(unsigned sel, unsigned track, unsigned char c1)",watcher+"\nstatic void bart_trace_request(unsigned sel, unsigned track, unsigned char c1)","watcher definition")
    src=replace_once(src,
        '\t\tbart_trace_request(sel, c2, c1);\n\t\tdf[sel].track = c2;\n\t\tReadTrack(&df[sel]);',
        '\t\tbart_trace_request(sel, c2, c1);\n'
        '\t\tbart_watch_start();\n'
        '\t\tconst bool track_changed = bart_watch_track.load() != (int)c2;\n'
        '\t\tbart_watch_track.store((int)c2);\n'
        '\t\tbart_watch_calls.fetch_add(1);\n'
        '\t\tbart_watch_enter_ms.store(bart_trace_now_ms());\n'
        '\t\tbart_watch_in_read.store(1);\n'
        '\t\tif (track_changed) pf_log("BARTTRACE READ_ENTER DF%u track=%u", sel, c2);\n'
        '\t\tdf[sel].track = c2;\n'
        '\t\tReadTrack(&df[sel]);\n'
        '\t\tbart_watch_in_read.store(0);\n'
        '\t\tbart_watch_exit_ms.store(bart_trace_now_ms());\n'
        '\t\tif (track_changed) pf_log("BARTTRACE READ_EXIT DF%u track=%u", sel, c2);',
        "ReadTrack entry/exit markers")
    p.write_text(src)
    print("Added Main-only ReadTrack entry/exit + 3-second heartbeat watchdog.")

if __name__=="__main__":
    if len(sys.argv)!=2:
        raise SystemExit("Usage: patch_bart_main_v2.py <Main v1-traced source>")
    patch(Path(sys.argv[1]))
