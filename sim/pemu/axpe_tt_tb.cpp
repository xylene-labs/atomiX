/* Tiny Tapeout wrapper binding for the shared axpe chip suite.
 *
 * The shared cases earn the same protocol claims as the direct chip boundary;
 * this binding additionally exercises Tiny Tapeout design selection/reset. */

#include "Vtt_um_shubhgau_atomix_axpe.h"
#include "verilated.h"

#include "axpe_cases.h"
#include "axpe_device.h"

#include <cstdint>
#include <string>

struct VerilatedTinyTapeoutChip : Device {
    Vtt_um_shubhgau_atomix_axpe rtl;

    VerilatedTinyTapeoutChip()
    {
        rtl.clk = 0;
        rtl.rst_n = 1;
        rtl.ena = 1;
        rtl.ui_in = 0;
        rtl.uio_in = 0;
    }

    void set_ui_in(uint8_t value) override { rtl.ui_in = value; }
    void set_uio_in(uint8_t value) override { rtl.uio_in = value; }
    void set_enabled(bool enabled) { rtl.ena = enabled; }
    uint8_t uo_out() const override { return static_cast<uint8_t>(rtl.uo_out); }
    uint8_t uio_out() const override { return static_cast<uint8_t>(rtl.uio_out); }
    uint8_t uio_oe() const override { return static_cast<uint8_t>(rtl.uio_oe); }

    void cycle() override
    {
        rtl.clk = 1;
        rtl.eval();
        rtl.clk = 0;
        rtl.eval();
    }

    void reset(unsigned cycles) override
    {
        rtl.rst_n = 0;
        rtl.eval();
        for (unsigned i = 0; i < cycles; ++i) cycle();
        rtl.rst_n = 1;
    }
};

/* Exercise the board's reload sequence with a fresh simulator instance.
 * This cannot model power removal or the external harness's pad isolation.
 * It does exercise the design's ena/reset inputs and an uninitialized store;
 * no case depends on an old instruction surviving reset or deselection. */
static bool check_reload_lifecycle(const std::string &fw)
{
    VerilatedTinyTapeoutChip device;
    Chip chip(device);
    DemoRates rates;
    if (!rates.read(fw)) return false;
    if (!check_quiet_after_reset(chip)) return false;

    for (unsigned attempt = 0; attempt < 3; ++attempt) {
        UartReceiver uart(0, rates.uart_receiver_period());
        uint16_t status = 0;
        if (!run_firmware(chip, "reload-uart", fw + "/uart-demo.hex", uart,
                          60000, &status)) return false;
        if (!complain("reload-uart", uart.error) || uart.bytes.size() != 1 ||
            uart.bytes[0] != 0x41u || (status & 0xffu) != 0x41u) {
            std::fprintf(stderr, "reload-uart: attempt %u did not transmit/publish 41\n",
                         attempt);
            return false;
        }
        // Ensure deselection actually interrupts a previously driven pad.
        if (!(device.uio_oe() & 1u) || !(device.uio_out() & 1u)) {
            std::fprintf(stderr, "reload-uart: TX was not driven idle high\n");
            return false;
        }
        if (attempt == 0) {
            device.set_enabled(false);
            for (unsigned cycle = 0; cycle < 64; ++cycle) {
                chip.tick();
                if (device.uio_oe() || device.uio_out() || device.uo_out()) {
                    std::fprintf(stderr, "reload-deselect: protocol output not quiet\n");
                    return false;
                }
            }
            // ena resets the core, not the host's running latch. The board
            // procedure explicitly resets before reselecting/reloading.
            if (chip.status() != ST_RUNNING) {
                std::fprintf(stderr, "reload-deselect: unexpected host state\n");
                return false;
            }
            device.reset(4);
            chip.ticks(8);
            device.set_enabled(true);
        } else {
            // Also cover warm external reset with the design selected.
            device.reset(4);
        }
        if (!check_quiet_after_reset(chip)) return false;
    }
    std::puts("axpe lifecycle: fresh instance, deselect/reset/reselect and warm "
              "reset; each UART payload fully rewritten/read back and decoded");
    return true;
}

int main(int argc, char **argv)
{
    Verilated::commandArgs(argc, argv);
    const std::string fw = argc > 1 ? argv[1] : "build/fw";
    VerilatedTinyTapeoutChip device;
    Chip chip(device);
    if (run_chip_suite(chip, fw)) return 1;
    return check_reload_lifecycle(fw) ? 0 : 1;
}
