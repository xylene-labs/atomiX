# A bounded ECO on the pinned 200 um pre-route checkpoint. The Python driver
# checks source identities and verifies the complete cell/connectivity delta.
# No parasitics or timing from the parent remain valid after this change.
read_liberty $::env(AXPE_ECO_LIBERTY)
read_db $::env(AXPE_ECO_ODB)
read_sdc $::env(AXPE_ECO_SDC)

proc pin_names {net} {
    set names {}
    foreach pin [get_pins -of_objects [get_nets $net]] {
        lappend names [get_full_name $pin]
    }
    return [lsort $names]
}

set expected [lsort {input4/X max_length7624/A _17135_/D _09704_/A1 _09988_/A1}]
if {[pin_names net4] ne $expected} {
    error "net4 connectivity differs from the pinned checkpoint"
}

# The two muxes are adjacent (159.84/653.94 and 165.12/661.50 um).
# Move only these two loads, reserving two input4 fanout slots for diodes.
insert_buffer -net net4 -load_pins [get_pins {_09704_/A1 _09988_/A1}] \
    -buffer_cell sg13cmos5l_buf_1 -buffer_name eco_net4_mux \
    -net_name eco_net4_mux_net -location {164 658}
detailed_placement
check_placement -verbose
set added [get_cells eco_net4_mux*]
if {[llength $added] != 1} { error "expected exactly one ECO buffer" }
set name [get_full_name $added]
set child [get_full_name [get_nets -of_objects [get_pins ${name}/X]]]
puts "AXPE_ECO_PARENT: [pin_names net4]"
puts "AXPE_ECO_CHILD: [pin_names $child]"

if {[pin_names net4] ne [lsort [list input4/X max_length7624/A _17135_/D ${name}/A]]} {
    error "unexpected parent-net connectivity after ECO"
}
if {[pin_names $child] ne [lsort [list ${name}/X _09704_/A1 _09988_/A1]]} {
    error "unexpected child-net connectivity after ECO"
}
puts "AXPE_ECO_CONNECTIVITY_PASS: parent fanout 3, child fanout 2 before routing"
set prefix $::env(AXPE_ECO_OUTPUT_PREFIX)
write_db ${prefix}.odb
write_def ${prefix}.def
write_verilog ${prefix}.nl.v
