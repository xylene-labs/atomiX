/* Independent peers for the three mandatory protocols.
 *
 * These are written from each protocol's own rules -- start bits and bit
 * centres, SPI mode 0 edges, I2C start/stop conditions and acknowledgement
 * cells -- and not from axpe's ISA, its golden model, or the firmware under
 * test. That is the point: an oracle derived from the thing it checks agrees
 * with it by construction.
 *
 * They are peers in simulation. A peer on a bench cannot find what a real
 * device's rise times, pull-up values and clock tolerance find, so this is
 * not the hardware-peer evidence PE-09 exists to produce, and the board keeps
 * the two at different evidence levels on purpose.
 *
 * Every peer sees the bus the way a wire does: a line the chip drives takes the
 * chip's level, a released line is pulled up, and anything pulling down wins.
 * That is what makes I2C's open-drain path real here rather than assumed -- a
 * firmware that drove SDA high instead of releasing it would still look
 * correct against a peer that only watched levels. */
#ifndef AXPE_PEERS_H
#define AXPE_PEERS_H

#include <cstdint>
#include <string>
#include <vector>

struct Peer {
    virtual ~Peer() = default;
    /* Called once per chip cycle with what the chip is driving. Returns the
     * level of all eight bidirectional lines as the wire resolves them. */
    virtual uint8_t step(uint8_t chip_out, uint8_t chip_oe) = 0;
};

/* One line, with the chip on one side and a pull-up on the other. */
inline bool wire(uint8_t chip_out, uint8_t chip_oe, unsigned pin, bool peer_low)
{
    const bool chip_drives = (chip_oe >> pin) & 1u;
    const bool chip_low = chip_drives && !((chip_out >> pin) & 1u);
    return !(chip_low || peer_low);
}

/* Everything the peer does not touch, as a pulled-up bus would read. */
inline uint8_t idle_lines(uint8_t chip_out, uint8_t chip_oe)
{
    uint8_t level = 0;
    for (unsigned pin = 0; pin < 8; ++pin)
        if (wire(chip_out, chip_oe, pin, false)) level |= static_cast<uint8_t>(1u << pin);
    return level;
}

inline uint8_t with_line(uint8_t level, unsigned pin, bool high)
{
    const uint8_t mask = static_cast<uint8_t>(1u << pin);
    return high ? static_cast<uint8_t>(level | mask)
                : static_cast<uint8_t>(level & ~mask);
}

/* --- UART 8N1 receiver ---------------------------------------------------
 *
 * A conventional receiver: wait for the falling edge that starts a frame,
 * check the start bit is still low half a bit later, then sample at each bit
 * centre. It knows the bit period and nothing else about the transmitter. */
struct UartReceiver : Peer {
    unsigned tx_pin, baud_cycles;
    std::vector<uint8_t> bytes;
    std::string error;

    UartReceiver(unsigned pin, unsigned baud) : tx_pin(pin), baud_cycles(baud) {}

    uint8_t step(uint8_t chip_out, uint8_t chip_oe) override
    {
        const bool tx = wire(chip_out, chip_oe, tx_pin, false);
        if (!framing) {
            if (previous && !tx) { framing = true; elapsed = 0; bit = 0; value = 0; }
        } else {
            ++elapsed;
            const unsigned centre = baud_cycles / 2 + bit * baud_cycles;
            if (elapsed == centre) {
                if (bit == 0) {
                    if (tx) error = "start bit was not low at its centre";
                } else if (bit <= 8) {
                    if (tx) value |= static_cast<uint8_t>(1u << (bit - 1));
                } else {
                    if (!tx) error = "stop bit was not high at its centre";
                    else bytes.push_back(value);
                    framing = false;
                }
                ++bit;
            }
        }
        previous = tx;
        return idle_lines(chip_out, chip_oe);
    }

  private:
    bool previous = true, framing = false;
    unsigned elapsed = 0, bit = 0;
    uint8_t value = 0;
};

/* --- UART peer that never says what rate it is using ----------------------
 *
 * Transmits a fixed pattern at its own bit period and decodes whatever comes
 * back at that same period. The chip is told neither number. That is the whole
 * test for PE-15: a receiver here that decodes a clean frame is one whose bit
 * centres line up with edges the chip placed from a period it measured off
 * this peer's own transmission, so getting the rate wrong by even a cycle per
 * bit accumulates into a framing or data error over ten cells.
 *
 * 0x55 is sent because it alternates: every low run in the frame is exactly one
 * bit long, so a receiver-side minimum is the bit period rather than some
 * multiple of it. Several frames go out because the chip starts whenever its
 * RUN frame lets it and may miss the first edges; it takes a minimum over
 * complete low runs, so a late start costs samples, never accuracy. */
struct UartAutobaudPeer : Peer {
    UartReceiver rx;
    unsigned tx_pin, baud_cycles, quiet, frames;
    uint8_t pattern;

    UartAutobaudPeer(unsigned chip_tx, unsigned peer_tx, unsigned baud,
                     unsigned lead_in, unsigned count, uint8_t sent)
        : rx(chip_tx, baud), tx_pin(peer_tx), baud_cycles(baud), quiet(lead_in),
          frames(count), pattern(sent) {}

    uint8_t step(uint8_t chip_out, uint8_t chip_oe) override
    {
        const uint8_t level = rx.step(chip_out, chip_oe);
        /* Resolved through the wire rather than forced, so a firmware that
         * drove this line instead of listening on it would show up as
         * contention here rather than being hidden by the peer. */
        const bool line = wire(chip_out, chip_oe, tx_pin, !sending());
        ++cycle;
        return with_line(level, tx_pin, line);
    }

    const std::string &error() const { return rx.error; }
    const std::vector<uint8_t> &decoded() const { return rx.bytes; }

  private:
    unsigned cycle = 0;

    /* The level this peer holds on its own transmit line, idle-high 8N1. */
    bool sending() const
    {
        if (cycle < quiet) return true;
        const unsigned t = cycle - quiet;
        if (t >= frames * 10u * baud_cycles) return true;
        const unsigned bit = (t / baud_cycles) % 10u;
        if (bit == 0) return false;                       // start
        if (bit <= 8) return ((pattern >> (bit - 1)) & 1u) != 0;
        return true;                                      // stop
    }
};

/* --- SPI mode 0 target ---------------------------------------------------
 *
 * Samples MOSI on the rising edge and moves MISO on the falling one, which is
 * what mode 0 means. It presents its first bit when CS asserts, because the
 * master's first rising edge comes before any falling one. */
struct SpiTarget : Peer {
    unsigned sck_pin, mosi_pin, miso_pin, cs_pin;
    uint8_t response;
    uint8_t received = 0;
    unsigned frames = 0;
    std::string error;

    SpiTarget(unsigned sck, unsigned mosi, unsigned miso, unsigned cs, uint8_t answer)
        : sck_pin(sck), mosi_pin(mosi), miso_pin(miso), cs_pin(cs), response(answer) {}

    uint8_t step(uint8_t chip_out, uint8_t chip_oe) override
    {
        const bool cs = wire(chip_out, chip_oe, cs_pin, false);
        const bool sck = wire(chip_out, chip_oe, sck_pin, false);
        const bool mosi = wire(chip_out, chip_oe, mosi_pin, false);

        if (prev_cs && !cs) {            // selected
            shift_out = response;
            shift_in = 0;
            bits = 0;
        } else if (!prev_cs && cs) {     // released
            if (bits == 8) { received = shift_in; ++frames; }
            else if (bits == 0) error = "CS was asserted without a single clock";
            else error = "CS rose after " + std::to_string(bits) + " bits";
        }

        if (!cs) {
            if (!prev_sck && sck) {      // rising: the master's bit is stable
                shift_in = static_cast<uint8_t>((shift_in << 1) | (mosi ? 1u : 0u));
                ++bits;
            } else if (prev_sck && !sck) {  // falling: present the next bit
                shift_out = static_cast<uint8_t>(shift_out << 1);
            }
        }

        prev_cs = cs;
        prev_sck = sck;

        uint8_t level = idle_lines(chip_out, chip_oe);
        // MISO is driven only while selected; otherwise the target lets go.
        const bool miso = cs ? true : ((shift_out >> 7) & 1u) != 0;
        return with_line(level, miso_pin, miso);
    }

  private:
    bool prev_cs = true, prev_sck = false;
    uint8_t shift_in = 0, shift_out = 0;
    unsigned bits = 0;
};

/* --- I2C target ----------------------------------------------------------
 *
 * A 7-bit addressed device. START and STOP are SDA transitions while SCL is
 * high; every other SDA move belongs to a bit cell. The target acknowledges by
 * pulling SDA down for the ninth cell of a byte addressed to it, and lets go
 * afterwards, so a firmware that never released the line would deadlock here
 * exactly as it would on a real bus. */
struct I2cTarget : Peer {
    unsigned sda_pin, scl_pin, address;
    uint8_t to_send;

    std::vector<uint8_t> writes;      // bytes written to this device
    unsigned address_bytes = 0;       // address phases this device answered
    bool saw_start = false, saw_repeated_start = false, saw_stop = false;
    bool saw_master_nack = false, read_requested = false;
    std::string error;

    I2cTarget(unsigned sda, unsigned scl, unsigned addr, uint8_t answer)
        : sda_pin(sda), scl_pin(scl), address(addr), to_send(answer) {}

    uint8_t step(uint8_t chip_out, uint8_t chip_oe) override
    {
        const bool scl = wire(chip_out, chip_oe, scl_pin, false);
        const bool sda = wire(chip_out, chip_oe, sda_pin, pulling);

        if (scl && prev_scl && sda != prev_sda) {
            if (!sda) {                            // SDA fell while SCL high
                if (active) saw_repeated_start = true; else saw_start = true;
                active = true; matched = false; reading = false;
                phase = ADDRESS; bit = 0; shift_in = 0; pulling = false;
                sampled = false; releasing = false;
            } else {                               // SDA rose while SCL high
                saw_stop = true;
                active = false;
                pulling = false;
                sampled = false;
                releasing = false;
            }
        } else if (active && !prev_scl && scl) {   // rising: sample
            if (bit < 8) {
                if (phase != READ) shift_in = static_cast<uint8_t>((shift_in << 1) | (sda ? 1u : 0u));
            } else if (phase == READ) {
                if (sda) {
                    // A master that does not acknowledge is telling the target
                    // it wants no more bytes. The target lets go of SDA so the
                    // master can put a STOP on the bus; one that kept driving
                    // would hold the line down through the STOP it is waiting
                    // for, which is a hung bus, not a finished transfer.
                    saw_master_nack = true;
                    releasing = true;
                }
            }
            sampled = true;
        } else if (active && prev_scl && !scl) {   // falling: set up the next cell
            // Only a cell that was actually clocked advances the count. The
            // falling edge that ends a START condition is not a bit boundary,
            // and counting it would shift every byte by one.
            if (sampled) {
                ++bit;
                sampled = false;
                // The eight data bits are complete here and the ninth cell is
                // the acknowledgement, so whether to acknowledge is decided
                // now rather than after the cell it belongs to has gone by.
                if (bit == 8) finish_byte();
                if (bit == 9) { bit = 0; after_ack(); }
            }
            drive_for_cell();
        }

        prev_scl = scl;
        prev_sda = sda;
        return with_line(idle_lines(chip_out, chip_oe), sda_pin, sda);
    }

  private:
    enum Phase { ADDRESS, WRITE, READ } phase = ADDRESS;
    bool prev_scl = true, prev_sda = true;
    bool active = false, matched = false, reading = false, pulling = false;
    bool sampled = false, releasing = false;
    unsigned bit = 0;
    uint8_t shift_in = 0, shift_out = 0;

    void finish_byte()
    {
        if (phase == ADDRESS) {
            matched = (shift_in >> 1) == address;
            reading = (shift_in & 1u) != 0;
            if (matched) {
                ++address_bytes;
                if (reading) { shift_out = to_send; read_requested = true; }
            } else {
                active = false;        // not for us: stop answering
            }
        } else if (phase == WRITE) {
            writes.push_back(shift_in);
        }
    }

    /* The acknowledgement cell is over: a matched address turns into whichever
     * direction it asked for, and the next byte starts clean. */
    void after_ack()
    {
        if (phase == ADDRESS && matched) phase = reading ? READ : WRITE;
        shift_in = 0;
    }

    void drive_for_cell()
    {
        if (!active || releasing) { pulling = false; return; }
        if (phase == READ && bit < 8)
            pulling = ((shift_out >> (7 - bit)) & 1u) == 0;   // 0 is a pull-down
        else if (phase != READ && bit == 8)
            pulling = matched;                                 // the acknowledgement
        else
            pulling = false;
    }
};

#endif
