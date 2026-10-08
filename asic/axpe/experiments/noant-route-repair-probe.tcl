# Exploratory repair on the completed no-antenna-repair route.
# This changes only OpenROAD's in-memory database; no routed result is written.
read_liberty build/asic/pdk-cmos5l/ihp-sg13cmos5l/libs.ref/sg13cmos5l_stdcell/lib/sg13cmos5l_stdcell_slow_1p08V_125C.lib
read_db build/asic/tt-axpe-25ns-postgrt-noant/runs/pe10-25ns-postgrt-noant-route/final/odb/tt_um_shubhgau_atomix_axpe.odb
read_sdc build/asic/tt-axpe-25ns-postgrt-noant/runs/pe10-25ns-postgrt-noant-route/final/sdc/tt_um_shubhgau_atomix_axpe.sdc
read_spef build/asic/tt-axpe-25ns-postgrt-noant/runs/pe10-25ns-postgrt-noant-route/final/spef/nom/tt_um_shubhgau_atomix_axpe.nom.spef
puts "AXPE_ROUTED_BEFORE"
report_check_types -max_slew -max_capacitance -max_fanout -violators
set_wire_rc -layer Metal2
repair_design -slew_margin 20 -cap_margin 20 -verbose
puts "AXPE_REPAIR_UNROUTED_AFTER"
report_check_types -max_slew -max_capacitance -max_fanout -violators
