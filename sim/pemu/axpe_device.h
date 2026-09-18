/* The bench's view of an axpe chip, with no simulator in it.
 *
 * PE-11 has to run the same firmware against a post-synthesis and a post-P&R
 * netlist, and the expensive half of a bench is never the clock wiggling -- it
 * is the host-port protocol, the peers, and the oracle that decides pass or
 * fail. Those are here and in axpe_cases.h, written against an abstract
 * `Device`, so a second harness implements six small methods and reuses
 * everything else rather than growing a second copy of the protocol that can
 * disagree with this one.
 *
 * What ports and what does not, stated plainly rather than discovered in
 * December: a Verilator run over a gate netlist implements `Device` directly.
 * An event-driven simulator carrying SDF delays needs its own driver -- a VPI
 * shim implementing `Device`, or cocotb, in which case this file does not port
 * but axpe_peers.h and the oracle's expectations still do. The peers are pure
 * C++ and depend on nothing here at all. */
#ifndef AXPE_DEVICE_H
#define AXPE_DEVICE_H

#include "axpe_peers.h"
#include "axpe_trace.h"

#include <cstdint>

/* Everything a bench needs of the part, and nothing about how it is simulated.
 *
 * `cycle()` advances one whole clock cycle and leaves the outputs at their
 * post-edge values. axpe has no negedge logic, so a sample taken after it
 * returns is the same sample a bench taken between the two edges would read;
 * a device whose implementation makes that untrue must sample inside `cycle()`
 * and say so. */
struct Device {
    virtual ~Device() = default;
    virtual void set_ui_in(uint8_t value) = 0;
    virtual void set_uio_in(uint8_t value) = 0;
    virtual uint8_t uo_out() const = 0;
    virtual uint8_t uio_out() const = 0;
    virtual uint8_t uio_oe() const = 0;
    virtual void cycle() = 0;
    /* Hold reset asserted for `cycles`, then release it. */
    virtual void reset(unsigned cycles) = 0;
};

/* The host port in docs/pemu-host-protocol.md, driven against a Device.
 *
 * One copy of the frame shapes on purpose. A second bench that transcribed
 * them would be a second protocol, and the field it would drift in is a bit
 * count that only shows up as a program loaded one bit wrong. */
struct Chip {
    Device &dev;
    std::vector<Sample> trace;
    bool collect = false;
    bool sclk = false, mosi = false, cs_n = true;
    /* When a peer is attached it owns the bidirectional bus, resolving what
     * the chip drives against its own pull-downs and the pull-ups. */
    Peer *peer = nullptr;

    explicit Chip(Device &device) : dev(device)
    {
        dev.set_uio_in(0);
        drive();
        dev.reset(4);
    }

    void drive()
    {
        dev.set_ui_in(static_cast<uint8_t>((sclk ? 1u : 0u) | (mosi ? 2u : 0u)
                                          | (cs_n ? 4u : 0u)));
    }

    void tick()
    {
        drive();
        dev.set_uio_in(peer ? peer->step(dev.uio_out(), dev.uio_oe()) : 0u);
        dev.cycle();
        if (collect)
            trace.push_back({dev.uio_out(), dev.uio_oe(), dev.uo_out()});
    }

    void ticks(int n) { while (n-- > 0) tick(); }

    /* SPI mode 0 at clk/8, inside the clk/4 bound the host contract sets.
     * MISO is sampled at the end of the low phase, where the target has
     * already presented it on the previous falling edge. */
    uint64_t xfer(uint64_t out, int nbits)
    {
        uint64_t in = 0;
        for (int i = nbits - 1; i >= 0; --i) {
            mosi = (out >> i) & 1u;
            sclk = false;
            ticks(4);
            in = (in << 1) | (dev.uo_out() & 1u);
            sclk = true;
            ticks(4);
        }
        sclk = false;
        ticks(4);
        return in;
    }

    void select()   { cs_n = false; ticks(8); }
    void deselect() { cs_n = true;  ticks(8); }

    void write_word(unsigned addr, uint32_t data)
    {
        select();
        xfer(0x01, 8);
        xfer(addr, 8);
        xfer(data, 32);
        deselect();
    }

    uint32_t read_word(unsigned addr)
    {
        select();
        xfer(0x02, 8);
        xfer(addr, 8);
        const uint32_t value = static_cast<uint32_t>(xfer(0, 32));
        deselect();
        return value;
    }

    /* Ends the frame without advancing time, so a caller can start watching
     * the pads on the very cycle the chip is allowed to start running. */
    void end_frame() { cs_n = true; drive(); }

    void run()  { select(); xfer(0x03, 8); deselect(); }
    void stop() { select(); xfer(0x04, 8); deselect(); }

    uint16_t status()
    {
        select();
        xfer(0x05, 8);
        const uint16_t value = static_cast<uint16_t>(xfer(0, 16));
        deselect();
        return value;
    }

    void load(const std::vector<uint32_t> &program)
    {
        for (unsigned i = 0; i < program.size(); ++i) write_word(i, program[i]);
    }
};

#endif
