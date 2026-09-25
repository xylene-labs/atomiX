/* Tiny Tapeout wrapper binding for the shared axpe chip suite.
 *
 * This differs from axpe_chip_tb.cpp only at the generated top-level class.
 * Keeping every decision in axpe_cases.h means the flow wrapper earns exactly
 * the same programmability and protocol claims as the direct chip boundary. */

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

int main(int argc, char **argv)
{
    Verilated::commandArgs(argc, argv);
    const std::string fw = argc > 1 ? argv[1] : "build/fw";
    VerilatedTinyTapeoutChip device;
    Chip chip(device);
    return run_chip_suite(chip, fw);
}
