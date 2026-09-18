/* The programmability test, bound to Verilator.
 *
 * The competition's requirement is that a fabricated part can be given a
 * different protocol after fabrication, and the only way to demonstrate that
 * is to load two different programs into one design that is never rebuilt
 * between them. So this bench elaborates the chip once, drives nothing but the
 * four host pins and the protocol pads, and runs two unrelated programs
 * through it -- checking each against the golden model cycle for cycle, not
 * merely that something happened.
 *
 * A preinitialised memory image would pass a weaker version of this test and
 * prove nothing, which is exactly why the board says it does not count.
 *
 * Everything that decides pass or fail lives in axpe_cases.h, and the peers in
 * axpe_peers.h; neither knows what is simulating the part. This file is only
 * the binding: six methods and a main. PE-11 writes its own binding for a
 * post-synthesis and a post-P&R netlist and runs the same cases, because a
 * netlist judged by a different list would not be evidence about the same
 * chip. */

#include "Vaxpe_chip.h"
#include "verilated.h"

#include "axpe_cases.h"
#include "axpe_device.h"

#include <cstdint>
#include <string>

/* The RTL under Verilator. Two-state, so it cannot see an uninitialised flop
 * or a timing violation. That is not a gap in this file -- it is the reason
 * the gate-level layer exists -- but it is stated here rather than left to be
 * inferred from a passing run. */
struct VerilatedChip : Device {
    Vaxpe_chip rtl;

    VerilatedChip()
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

    VerilatedChip device;
    Chip chip(device);
    return run_chip_suite(chip, fw);
}
