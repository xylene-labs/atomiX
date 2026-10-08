# Exploratory PE-10 resizer probe on the completed CTS-size-8 route.
# Run from the repository root inside the pinned LibreLane/OpenROAD shell.
# This does not write a candidate database or establish post-route closure:
# estimate_parasitics -placement replaces the extracted route estimate.
read_liberty build/asic/pdk-cmos5l/ihp-sg13cmos5l/libs.ref/sg13cmos5l_stdcell/lib/sg13cmos5l_stdcell_slow_1p08V_125C.lib
read_db build/asic/tt-axpe-25ns-cts8/runs/pe10-25ns-cts8/final/odb/tt_um_shubhgau_atomix_axpe.odb
read_sdc build/asic/tt-axpe-25ns-cts8/runs/pe10-25ns-cts8/final/sdc/tt_um_shubhgau_atomix_axpe.sdc
read_spef build/asic/tt-axpe-25ns-cts8/runs/pe10-25ns-cts8/final/spef/nom/tt_um_shubhgau_atomix_axpe.nom.spef
puts "AXPE_ROUTED_BEFORE"
report_check_types -max_slew -max_capacitance -max_fanout -violators
set_wire_rc -layer Metal2
estimate_parasitics -placement
puts "AXPE_PLACEMENT_BEFORE"
report_check_types -max_slew -max_capacitance -max_fanout -violators
repair_design -slew_margin 20 -cap_margin 20 -verbose
puts "AXPE_PLACEMENT_AFTER"
report_check_types -max_slew -max_capacitance -max_fanout -violators
