# Read-only timing queries on an existing mapped DDC. No compile or SDC edits.
# Required env: MC_LAB_CONFIG, MC_MAPPED_DDC, MC_ANALYSIS_TOP, MC_ANALYSIS_OUT.
proc analyze_controller_paths {} {
    global env search_path target_library link_library
    foreach name {MC_LAB_CONFIG MC_MAPPED_DDC MC_ANALYSIS_TOP MC_ANALYSIS_OUT} {
        if {![info exists env($name)]} { error "Missing environment setting $name" }
    }
    source $env(MC_LAB_CONFIG)
    set search_path [concat $search_path $LIB_SEARCH_PATH]
    set target_library $TARGET_LIBRARIES
    set link_library [concat "*" $TARGET_LIBRARIES]
    foreach lib $TARGET_LIBRARIES {
        if {![file isfile $lib]} { error "Missing library $lib" }
    }
    if {![file isfile $env(MC_MAPPED_DDC)]} { error "Missing mapped DDC" }
    set out $env(MC_ANALYSIS_OUT)
    file mkdir $out
    read_ddc $env(MC_MAPPED_DDC)
    current_design $env(MC_ANALYSIS_TOP)
    if {![link]} { error "Mapped design link failed" }
    redirect [file join $out area.rpt] { report_area -hierarchy }
    redirect [file join $out check_timing.rpt] { check_timing }
    redirect [file join $out constraints.rpt] { report_constraint -all_violators -significant_digits 6 }
    redirect [file join $out clocks.rpt] { report_clock }
    redirect [file join $out timing.rpt] {
        report_timing -delay_type max -max_paths 100 -nworst 1 -nets -transition_time -capacitance -input_pins -significant_digits 6
    }
    set register_q [all_registers -output_pins]
    set register_d [all_registers -data_pins]
    set data_inputs [remove_from_collection [all_inputs] [get_ports clk]]
    redirect [file join $out register_to_register.rpt] {
        report_timing -delay_type max -from $register_q -to $register_d -max_paths 10 -nworst 1 -nets -transition_time -capacitance -input_pins -significant_digits 6
    }
    redirect [file join $out input_to_register.rpt] {
        report_timing -delay_type max -from $data_inputs -to $register_d -max_paths 10 -nworst 1 -nets -transition_time -capacitance -input_pins -significant_digits 6
    }
    redirect [file join $out register_to_output.rpt] {
        report_timing -delay_type max -from $register_q -to [all_outputs] -max_paths 100 -nworst 1 -nets -transition_time -capacitance -input_pins -significant_digits 6
    }
    redirect [file join $out input_to_output.rpt] {
        report_timing -delay_type max -from $data_inputs -to [all_outputs] -max_paths 10 -nworst 1 -nets -transition_time -capacitance -input_pins -significant_digits 6
    }
    foreach group {read_data done} {
        set endpoints [get_pins -hierarchical -filter "full_name =~ *${group}_reg*/D"]
        if {[sizeof_collection $endpoints] == 0} { error "Missing $group endpoints" }
        redirect [file join $out ${group}_setup.rpt] {
            report_timing -delay_type max -to $endpoints -max_paths 10 -nworst 1 -nets -transition_time -capacitance -input_pins -significant_digits 6
        }
    }
    redirect [file join $out hold.rpt] {
        report_timing -delay_type min -max_paths 40 -nworst 1 -nets -transition_time -capacitance -input_pins -significant_digits 6
    }
    set fp [open [file join $out SUCCESS] w]
    puts $fp "Existing mapped DDC queried; inspect constraints and path coverage separately."
    close $fp
}
if {[catch {analyze_controller_paths} message]} { puts stderr "ERROR: $message"; exit 1 }
exit 0
