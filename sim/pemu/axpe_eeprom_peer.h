/* Independent digital AT24C256 byte-operation peer. The wire state machine
 * follows I2C edges and the device's two-byte address/write-cycle contract.
 * No ISA/model/firmware timing is consulted. Not electrical or physical evidence.
 */
#ifndef AXPE_EEPROM_PEER_H
#define AXPE_EEPROM_PEER_H
#include "axpe_peers.h"
#include <utility>

struct At24c256Peer : Peer {
    unsigned address;
    uint64_t write_cycles, cycle=0, busy_until=0;
    bool write_protected=false, nack_read_address=false;
    int nack_byte=-1; // Injection: zero=device address, one/two=word address, three=data.
    std::vector<uint8_t> memory=std::vector<uint8_t>(32768,0xff);
    std::vector<uint8_t> received;
    std::vector<unsigned> read_addresses;
    unsigned starts=0, repeated_starts=0, stops=0, nacks=0, busy_nacks=0;
    unsigned writes=0, master_nacks=0;
    std::string error;

    At24c256Peer(unsigned addr,uint64_t duration):address(addr),write_cycles(duration) {}
    uint8_t step(uint8_t out,uint8_t oe) override {
        ++cycle;
        if ((oe & out & 0x0cu) && error.empty()) error="I2C master drove a line high";
        const bool scl=wire(out,oe,3,false),sda=wire(out,oe,2,pulling);
        if (scl && prev_scl && sda!=prev_sda) {
            if (!sda) {
                if (active) ++repeated_starts;
                ++starts;active=true;selected=false;phase=ADDRESS;bit=0;byte_index=0;
                shift_in=0;pulling=false;sampled=false;releasing=false;
            } else {
                ++stops;active=false;pulling=false;sampled=false;
                if (!pending.empty()) {
                    if (!write_protected) {
                        busy_until=cycle+write_cycles;
                        // Digital write completion is deferred until the busy interval ends.
                        committing=pending;
                    }
                    pending.clear();
                }
            }
        } else if (active && !prev_scl && scl) {
            if (bit<8 && phase!=READ) shift_in=uint8_t((shift_in<<1)|(sda?1u:0u));
            if (bit==8 && phase==READ && selected && sda) {++master_nacks;releasing=true;}
            sampled=true;
        } else if (active && prev_scl && !scl) {
            if (sampled) {
                ++bit;sampled=false;
                if (bit==8) finish_byte();
                if (bit==9) {bit=0;after_ack();}
            }
            if (!selected || releasing) pulling=false;
            else if (phase==READ && bit<8) pulling=((shift_out>>(7-bit))&1u)==0;
            else pulling=phase!=READ && bit==8 && ack;
        }
        if (!committing.empty() && cycle>=busy_until) {
            for (const auto &entry:committing) memory[entry.first]=entry.second;
            ++writes;committing.clear();
        }
        prev_scl=scl;prev_sda=sda;
        return with_line(idle_lines(out,oe),2,sda);
    }

  private:
    enum Phase {ADDRESS,WORD_HIGH,WORD_LOW,DATA,READ} phase=ADDRESS;
    bool prev_scl=true,prev_sda=true,active=false,selected=false,pulling=false;
    bool sampled=false,releasing=false,ack=false,reading=false;
    unsigned bit=0,byte_index=0,pointer=0,word_high=0,page_base=0,page_offset=0;
    uint8_t shift_in=0,shift_out=0;
    std::vector<std::pair<unsigned,uint8_t>> pending,committing;
    void finish_byte() {
        if (phase==READ) return;
        received.push_back(shift_in);
        ack=byte_index!=unsigned(nack_byte);
        if (phase==ADDRESS) {
            ack=ack && (shift_in>>1)==address && cycle>=busy_until && !((shift_in&1u) && nack_read_address);
            if ((shift_in>>1)==address && cycle<busy_until) ++busy_nacks;
            selected=ack;reading=(shift_in&1u)!=0;
            if (selected && reading) {shift_out=memory[pointer];read_addresses.push_back(pointer);}
        } else if (selected) {
            if (ack && phase==WORD_HIGH) word_high=shift_in&0x7f;
            if (ack && phase==WORD_LOW) {pointer=(word_high<<8)|shift_in;page_base=pointer&~63u;page_offset=pointer&63u;}
            if (ack && phase==DATA) {pending.emplace_back(page_base|page_offset,shift_in);page_offset=(page_offset+1)&63u;}
            if (!ack) selected=false;
        }
        if (!ack) ++nacks;
        ++byte_index;
    }
    void after_ack() {
        if (selected) {
            if (phase==ADDRESS) phase=reading?READ:WORD_HIGH;
            else if (phase==WORD_HIGH) phase=WORD_LOW;
            else if (phase==WORD_LOW) phase=DATA;
            else if (phase==READ && !releasing) {pointer=(pointer+1)&0x7fff;shift_out=memory[pointer];read_addresses.push_back(pointer);}
        }
        shift_in=0;
    }
};
#endif
