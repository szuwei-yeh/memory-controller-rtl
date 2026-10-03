# Isolated hold-only experiment on an existing mapped DDC.
# Required env: MC_LAB_CONFIG, MC_MAPPED_DDC, MC_ANALYSIS_TOP, MC_ANALYSIS_OUT.
# The saved DDC supplies its existing timing constraints; do not reload the SDC.
proc hold_reports {out prefix} {
    redirect [file join $out ${prefix}_design.rpt] { report_design }
    redirect [file join $out ${prefix}_area.rpt] { report_area -hierarchy }
    redirect [file join $out ${prefix}_clocks.rpt] { report_clock }
    redirect [file join $out ${prefix}_setup.rpt] {
        report_timing -delay_type max -max_paths 10 -nets -transition_time -capacitance -input_pins -significant_digits 6
    }
    redirect [file join $out ${prefix}_hold.rpt] {
        report_timing -delay_type min -max_paths 20 -nets -transition_time -capacitance -input_pins -significant_digits 6
    }
    redirect [file join $out ${prefix}_constraints.rpt] {
        report_constraint -all_violators -significant_digits 6
    }
    redirect [file join $out ${prefix}_qor.rpt] { report_qor }
    redirect [file join $out ${prefix}_references.rpt] { report_reference -hierarchy }
    redirect [file join $out ${prefix}_check_design.rpt] { check_design }
    redirect [file join $out ${prefix}_check_timing.rpt] { check_timing }
    write_sdc [file join $out ${prefix}.sdc]
    write -format verilog -hierarchy -output [file join $out ${prefix}.v]
    write -format ddc -hierarchy -output [file join $out ${prefix}.ddc]
}

proc repair_hold {} {
    global env search_path target_library link_library
    foreach name {MC_LAB_CONFIG MC_MAPPED_DDC MC_ANALYSIS_TOP MC_ANALYSIS_OUT} {
        if {![info exists env($name)]} { error "Missing environment setting $name" }
    }
    if {![file isfile $env(MC_MAPPED_DDC)]} { error "Mapped baseline DDC is missing" }
    set out $env(MC_ANALYSIS_OUT)
    # Require a new destination so an experiment cannot overwrite earlier runs.
    if {[file exists $out]} { error "Use a new experiment output directory" }
    source $env(MC_LAB_CONFIG)
    foreach name {TARGET_LIBRARIES LIB_SEARCH_PATH LIB_CORNER LIB_TIME_NS LIB_CAP_FF} {
        if {![info exists $name]} { error "Missing lab setting $name" }
    }
    foreach lib $TARGET_LIBRARIES {
        if {![file isfile $lib]} { error "Missing library $lib" }
    }
    set search_path [concat $search_path $LIB_SEARCH_PATH]
    set target_library $TARGET_LIBRARIES
    set link_library [concat "*" $TARGET_LIBRARIES]
    read_ddc $env(MC_MAPPED_DDC)
    current_design $env(MC_ANALYSIS_TOP)
    if {![link]} { error "Mapped design link failed" }
    set clock [get_clocks core_clk]
    if {[sizeof_collection $clock] != 1} { error "Expected the existing core_clk clock" }
    file mkdir $out
    redirect [file join $out environment.rpt] {
        puts "Library/corner: $LIB_CORNER"
        puts "Target libraries: $TARGET_LIBRARIES"
        puts "Time unit ns: $LIB_TIME_NS; capacitance unit fF: $LIB_CAP_FF"
        puts "Baseline DDC: $env(MC_MAPPED_DDC)"
    }
    redirect [file join $out buffer_model.rpt] {
        puts "BUFX2 output function: [get_attribute [get_lib_pins */BUFX2/Y] function]"
        puts "BUFX2 area: [get_attribute [get_lib_cells */BUFX2] area]"
    }
    redirect [file join $out compile_help.rpt] { man compile }
    redirect [file join $out set_fix_hold_help.rpt] { man set_fix_hold }
    hold_reports $out before
    # Hold fixing changes the mapped implementation. All existing clocks,
    # uncertainties, I/O delays, path coverage and library limits are retained.
    set_fix_hold $clock
    if {![compile -only_hold_time]} { error "Hold-only compile failed" }
    hold_reports $out after
    set fp [open [file join $out SUCCESS] w]
    puts $fp "Hold-only tool flow completed; adoption requires timing, constraints and mapped-equivalence review."
    close $fp
}
if {[catch {repair_hold} message]} { puts stderr "ERROR: $message"; exit 1 }
exit 0
