// Regression test for the exact conversion linked by IPFFile::fluxRead().
// This is not a Bart gameplay or FPGA simulation.
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include "ipf_index_units.h"

static void check(uint32_t overlap_bit, uint32_t trackbits)
{
    const uint32_t actual = ipf_index_byte_from_overlap_bit(overlap_bit);
    const uint32_t expected = overlap_bit / 8u + ((overlap_bit % 8u) != 0u);
    if (actual != expected) std::abort();
    if (actual >= (trackbits + 7u) / 8u) {
        std::fprintf(stderr, "Invalid test data: overlap outside track\n");
        std::abort();
    }
    // One and only one INDEX pulse within a track.
    uint32_t pulses = 0, observed = 0;
    for (uint32_t byte = 0; byte < (trackbits + 7u) / 8u; byte++) {
        if (byte == actual) { pulses++; observed = byte; }
    }
    if (pulses != 1u || observed * 8u < overlap_bit ||
        observed * 8u - overlap_bit > 7u) {
        std::fprintf(stderr, "INDEX regression: overlap=%u observed_byte=%u\n",
                     overlap_bit, observed);
        std::abort();
    }
}

int main()
{
    // These exercise the real conversion used in the patched Main.
    for (uint32_t bit = 0; bit < 100303; bit++) check(bit, 100312);
    // Nonzero index example: old code compares 1118 bits to 1118 bytes,
    // placing the pulse 7,826 bitcells late. Corrected placement is byte 140.
    if (ipf_index_byte_from_overlap_bit(1118) != 140u) std::abort();
    // Typical 100,312-cell track: once beyond the first byte boundary, no eightfold drift.
    if (ipf_index_byte_from_overlap_bit(0) != 0u) std::abort();
    if (ipf_index_byte_from_overlap_bit(1) != 1u) std::abort();
    if (ipf_index_byte_from_overlap_bit(7) != 1u) std::abort();
    if (ipf_index_byte_from_overlap_bit(8) != 1u) std::abort();
    if (ipf_index_byte_from_overlap_bit(9) != 2u) std::abort();
    std::puts("PASS: CAPS overlap bit position converts to the correct INDEX byte (0..7 bitcells late)");
    return 0;
}
