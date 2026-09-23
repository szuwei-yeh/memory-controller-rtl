# Read-only diagnostics for the completed baseline; no compile or netlist changes.
source synth/lab_config.tcl
set target_library $TARGET_LIBRARIES
set link_library [concat "*" $TARGET_LIBRARIES]
set search_path [concat $search_path $LIB_SEARCH_PATH]
set out build/synth/dc/frfcfs_aging_q16_5ns
read_ddc [file join $out mapped.ddc]
link
redirect [file join $out hold.rpt] { report_timing -delay_type min -max_paths 20 -input_pins -nets -transition_time -capacitance -significant_digits 6 }
redirect [file join $out constraints_precise.rpt] { report_constraint -all_violators -significant_digits 6 }
redirect [file join $out setup_precise.rpt] { report_timing -delay_type max -max_paths 1 -significant_digits 6 }
redirect [file join $out clocks.rpt] { report_clock }
redirect [file join $out library_attributes.rpt] {
    foreach attr {time_unit_name capacitive_load_units default_operating_conditions nom_process nom_voltage nom_temperature} {
        puts "$attr = [get_attribute [get_libs gscl45nm] $attr]"
    }
}
exit 0
