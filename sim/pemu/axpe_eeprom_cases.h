#ifndef AXPE_EEPROM_CASES_H
#define AXPE_EEPROM_CASES_H
#include "axpe_cases.h"
#include "axpe_eeprom_peer.h"

inline bool eeprom_execute(Chip &chip,At24c256Peer &peer,const std::string &path,
                           unsigned budget,uint8_t expected,const DemoRates &rates) {
    const auto program=load_hex(path);
    if (program.empty()) return false;
    I2cTimingPeer timing(peer,rates);
    chip.peer=&timing;
    chip.stop();
    if (!chip.load_verified(program)) {chip.peer=nullptr;return false;}
    chip.run();
    uint16_t status=0;
    for (unsigned spent=0;spent<budget;spent+=256) {
        chip.ticks(256);status=chip.status();
        if (status & (ST_HALTED|ST_FAULT)) break;
    }
    bool ok=(status&ST_HALTED) && !(status&(ST_FAULT|ST_REFUSED)) && uint8_t(status)==expected;
    ok=ok && !(chip.dev.uio_oe()&0x0cu) && peer.stops && peer.error.empty() && timing.error.empty() && timing.starts>=1;
    chip.peer=&peer;
    if (!ok) std::fprintf(stderr,"EEPROM %s: status=%04x expected=%02x oe=%02x stops=%u peer=%s\n",
        path.c_str(),status,expected,chip.dev.uio_oe(),peer.stops,peer.error.c_str());
    // Deliberately keep the peer attached between programs: host loading advances
    // EEPROM write time and must not become a reset of the external device.
    return ok;
}

inline bool run_eeprom_suite(Chip &chip,const std::string &directory) {
    std::ifstream plan(directory+"/cases.txt");
    unsigned period=0;DemoRates rates;plan>>period>>rates.clock_hz>>rates.i2c_hz>>rates.i2c_guard_ns;
    if (!plan || period<4) return false;
    const unsigned budget=period*128u+4096u;
    std::string name;unsigned address,word,data;uint64_t write_cycles;
    unsigned cases=0;
    while (plan>>name>>address>>word>>data>>write_cycles) {
        const std::string base=directory+"/"+name;
        chip.dev.reset(4);
        ++cases;
        At24c256Peer peer(address,write_cycles);
        const auto before=peer.memory;
        if (!eeprom_execute(chip,peer,base+"/write.hex",budget,0x80,rates)) return false;
        if (peer.memory!=before || peer.writes) {std::fputs("EEPROM: write committed before busy interval\n",stderr);return false;}
        if (!eeprom_execute(chip,peer,base+"/poll.hex",budget,0,rates)) return false;
        if (!peer.busy_nacks || peer.writes) return false;
        chip.ticks(static_cast<int>(peer.busy_until-peer.cycle+1));
        if (!eeprom_execute(chip,peer,base+"/poll.hex",budget,0x80,rates)) return false;
        if (peer.writes!=1 || peer.memory[word]!=data) {std::fputs("EEPROM oracle: write address/data mismatch\n",stderr);return false;}
        for (unsigned i=0;i<peer.memory.size();++i)
            if (i!=word && peer.memory[i]!=before[i]) return false;
        const unsigned restarts=peer.repeated_starts,nacks=peer.master_nacks;
        if (!eeprom_execute(chip,peer,base+"/read-low.hex",budget,uint8_t(0x80|(data&15)),rates)) return false;
        if (!eeprom_execute(chip,peer,base+"/read-high.hex",budget,uint8_t(0x80|(data>>4)),rates)) return false;
        if (peer.repeated_starts!=restarts+2 || peer.master_nacks!=nacks+2 || peer.read_addresses.size()!=2 || peer.read_addresses[0]!=word || peer.read_addresses[1]!=word) {std::fputs("EEPROM oracle: repeated START/master NACK/read pointer mismatch\n",stderr);return false;}
        chip.peer=nullptr;
        // An absent/wrong-address target and NACK at every write stage must STOP,
        // release both lines and neither commit nor report a successful write.
        for (int stage=-1;stage<4;++stage) {
            chip.dev.reset(4);
            At24c256Peer refusal(stage<0 ? address^1u : address,0);
            refusal.nack_byte=stage;
            if (!eeprom_execute(chip,refusal,base+"/write.hex",budget,0,rates)) return false;
            if (!refusal.nacks || refusal.writes) return false;
            chip.peer=nullptr;
        }
        for (int stage=0;stage<3;++stage) {
            chip.dev.reset(4);At24c256Peer refusal(address,0);refusal.nack_byte=stage;
            if (!eeprom_execute(chip,refusal,base+"/read-low.hex",budget,0,rates)) return false;
            if (refusal.writes) return false;
            chip.peer=nullptr;
        }
        chip.dev.reset(4);At24c256Peer read_nack(address,0);read_nack.nack_read_address=true;
        if (!eeprom_execute(chip,read_nack,base+"/read-low.hex",budget,0,rates) || read_nack.repeated_starts!=1) return false;
        chip.peer=nullptr;
        chip.dev.reset(4);At24c256Peer protection(address,0);protection.write_protected=true;
        if (!eeprom_execute(chip,protection,base+"/write.hex",budget,0x80,rates)) return false;
        if (protection.writes || protection.memory!=before) return false;
        chip.peer=nullptr;
        std::printf("EEPROM %s: two-byte address %04x, data %02x, deferred write/ACK polling, repeated START, NACK/STOP/release and WP pass\n",name.c_str(),word,data);
    }
    return plan.eof() && cases==4;
}
#endif
