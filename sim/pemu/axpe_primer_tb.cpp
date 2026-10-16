#include "Vaxpe_primer_sim.h"
#include "verilated.h"
#include "axpe_cases.h"
#include "axpe_device.h"
#include "axpe_eeprom_cases.h"
#include <string>
#include <cstdlib>

#ifndef PRIMER_DIVISOR
#error resolved board divisor is required
#endif
#ifndef PRIMER_RESET_CYCLES
#error resolved reset interval is required
#endif

struct PrimerDevice : Device {
    Vaxpe_primer_sim rtl;
    PrimerDevice() {
        rtl.clk_50mhz = 0; rtl.capture_clk = 0; rtl.host_rst_n = 0; rtl.button_s1 = 0;
        rtl.design_enabled = 1; rtl.host_sclk = 0; rtl.host_mosi = 0;
        rtl.host_cs_n = 1; rtl.peer_value = 0; rtl.eval();
    }
    void set_ui_in(uint8_t value) override {
        rtl.host_sclk = value & 1u; rtl.host_mosi = (value >> 1) & 1u;
        rtl.host_cs_n = (value >> 2) & 1u;
    }
    void set_uio_in(uint8_t value) override { rtl.peer_value = value; }
    uint8_t uo_out() const override { return (rtl.mon_result & 0xfeu) | rtl.host_miso; }
    uint8_t uio_out() const override { return rtl.mon_out; }
    uint8_t uio_oe() const override { return rtl.mon_oe; }
    unsigned capture_count=0;
    void oscillator_tick() {
        if (++capture_count == PRIMER_CAPTURE_DIVISOR/2) {
            capture_count=0; rtl.capture_clk = !rtl.capture_clk;
        }
        rtl.clk_50mhz = 1; rtl.eval();
        rtl.clk_50mhz = 0; rtl.eval();
    }
    void cycle() override {
        if (PRIMER_CAPTURE_MODE) {
            // Capture RTL uses only this external clock. Elide the unused Dock
            // oscillator between its edges; oscillator_tick still measures the
            // resolved clock ratio explicitly below.
            rtl.capture_clk = 0; rtl.eval();
            rtl.capture_clk = 1; rtl.eval();
            return;
        }
        bool seen_low = !rtl.clock_ref;
        for (unsigned i=0; i<2u * PRIMER_DIVISOR; ++i) {
            oscillator_tick();
            if (!rtl.clock_ref) seen_low = true;
            if (seen_low && rtl.clock_ref) return;
        }
        std::fputs("board clock stopped\n", stderr); std::abort();
    }
    void reset(unsigned cycles) override {
        rtl.host_rst_n = 0; rtl.eval();
        for (unsigned i=0; i<cycles; ++i) cycle();
        rtl.host_rst_n = 1; rtl.eval();
        for (unsigned i=0; i<PRIMER_RESET_CYCLES+2; ++i) cycle();
    }
};

int main(int argc, char **argv) {
    Verilated::commandArgs(argc, argv);
    if (argc<2) return 2;
    PrimerDevice device;
    Chip chip(device);
    if (run_chip_suite(chip, std::string(argv[1]))) return 1;
    if (argc > 2 && !run_eeprom_suite(chip, std::string(argv[2]))) return 1;
    // Every observed reference-clock period equals the resolved divisor.
    for (unsigned check=0; check<8; ++check) {
        unsigned period=0;
        do { device.oscillator_tick(); ++period; } while (device.rtl.clock_ref);
        do { device.oscillator_tick(); ++period; } while (!device.rtl.clock_ref);
        if (period != PRIMER_DIVISOR) return 1;
    }
    device.rtl.design_enabled = 0;
    chip.ticks(8);
    if (device.uio_oe()) return 1;
    device.reset(4); device.rtl.design_enabled = 1; chip.ticks(8);
    if (!check_quiet_after_reset(chip)) return 1;
    std::printf("axpe Primer: all shared suites, clock divisor %u, reset %u and deselection pass\n",
                unsigned(PRIMER_DIVISOR), unsigned(PRIMER_RESET_CYCLES));
    return 0;
}
