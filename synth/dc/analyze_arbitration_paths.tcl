# Read-only margin checks on an existing mapped DDC; no compile or SDC reload.
# Required env: MC_LAB_CONFIG, MC_MAPPED_DDC, MC_ANALYSIS_TOP, MC_ANALYSIS_OUT.
proc analyze_arbitration_paths {} {
    global env search_path target_library link_library
    foreach name {MC_LAB_CONFIG MC_MAPPED_DDC MC_ANALYSIS_TOP MC_ANALYSIS_OUT} {
        if {![info exists env($name)]} { error "Missing environment setting $name" }
    }
    source $env(MC_LAB_CONFIG)
    set search_path [concat $search_path $LIB_SEARCH_PATH]
    set target_library $TARGET_LIBRARIES
    set link_library [concat "*" $TARGET_LIBRARIES]
    read_ddc $env(MC_MAPPED_DDC)
    current_design $env(MC_ANALYSIS_TOP)
    if {![link]} { error "Mapped design link failed" }
    set out $env(MC_ANALYSIS_OUT)
    file mkdir $out
    redirect [file join $out area.rpt] { report_area }
    redirect [file join $out clocks.rpt] { report_clock }
    redirect [file join $out constraints.rpt] { report_constraint -all_violators -significant_digits 6 }
    set register_q [all_registers -output_pins]
    set register_d [all_registers -data_pins]
    redirect [file join $out register_to_register.rpt] {
        report_timing -delay_type max -from $register_q -to $register_d -max_paths 5 -nworst 1 -nets -transition_time -capacitance -input_pins -significant_digits 6
    }
    redirect [file join $out register_to_output.rpt] {
        report_timing -delay_type max -from $register_q -to [all_outputs] -max_paths 5 -nworst 1 -nets -transition_time -capacitance -input_pins -significant_digits 6
    }
    set fp [open [file join $out SUCCESS] w]
    puts $fp "Read-only margin queries completed."
    close $fp
}
if {[catch {analyze_arbitration_paths} message]} { puts stderr "ERROR: $message"; exit 1 }
exit 0
