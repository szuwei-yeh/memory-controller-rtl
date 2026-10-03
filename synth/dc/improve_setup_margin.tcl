# Incremental setup-margin experiment on a hold-repaired mapped baseline.
# Final measurement uses the baseline constraints, never the temporary guard.
proc margin_reports {out prefix} {
    redirect [file join $out ${prefix}_design.rpt] { report_design }
    redirect [file join $out ${prefix}_area.rpt] { report_area -hierarchy }
    redirect [file join $out ${prefix}_clocks.rpt] { report_clock }
    redirect [file join $out ${prefix}_setup.rpt] {
        report_timing -delay_type max -max_paths 10 -nets -transition_time -capacitance -input_pins -significant_digits 6
    }
    redirect [file join $out ${prefix}_hold.rpt] {
        report_timing -delay_type min -max_paths 20 -nets -transition_time -capacitance -input_pins -significant_digits 6
    }
    redirect [file join $out ${prefix}_internal_setup.rpt] {
        report_timing -delay_type max -to [all_registers -data_pins] -max_paths 1 -significant_digits 6
    }
    redirect [file join $out ${prefix}_constraints.rpt] { report_constraint -all_violators -significant_digits 6 }
    redirect [file join $out ${prefix}_qor.rpt] { report_qor }
    redirect [file join $out ${prefix}_references.rpt] { report_reference -hierarchy }
    redirect [file join $out ${prefix}_check_design.rpt] { check_design }
    redirect [file join $out ${prefix}_check_timing.rpt] { check_timing }
    write_sdc [file join $out ${prefix}.sdc]
    write -format verilog -hierarchy -output [file join $out ${prefix}.v]
    write -format ddc -hierarchy -output [file join $out ${prefix}.ddc]
}

proc improve_margin {} {
    global env search_path target_library link_library
    foreach name {MC_LAB_CONFIG MC_MAPPED_DDC MC_ANALYSIS_TOP MC_ANALYSIS_OUT MC_SETUP_GUARD_NS} {
        if {![info exists env($name)]} { error "Missing environment setting $name" }
    }
    if {![file isfile $env(MC_MAPPED_DDC)]} { error "Mapped baseline DDC is missing" }
    set out $env(MC_ANALYSIS_OUT)
    if {[file exists $out]} { error "Use a new experiment output directory" }
    source $env(MC_LAB_CONFIG)
    foreach name {TARGET_LIBRARIES LIB_SEARCH_PATH LIB_CORNER LIB_TIME_NS LIB_CAP_FF} {
        if {![info exists $name]} { error "Missing lab setting $name" }
    }
    foreach lib $TARGET_LIBRARIES { if {![file isfile $lib]} { error "Missing library $lib" } }
    if {$LIB_TIME_NS <= 0 || $LIB_CAP_FF <= 0 || $env(MC_SETUP_GUARD_NS) <= 0} {
        error "Invalid units or optimization guard"
    }
    set search_path [concat $search_path $LIB_SEARCH_PATH]
    set target_library $TARGET_LIBRARIES
    set link_library [concat "*" $TARGET_LIBRARIES]
    read_ddc $env(MC_MAPPED_DDC)
    current_design $env(MC_ANALYSIS_TOP)
    if {![link]} { error "Mapped design link failed" }
    set clock [get_clocks core_clk]
    if {[sizeof_collection $clock] != 1} { error "Expected existing core_clk" }
    file mkdir $out
    redirect [file join $out compile_help.rpt] { man compile }
    redirect [file join $out uncertainty_help.rpt] { man set_clock_uncertainty }
    margin_reports $out before
    # This experiment supports the published common 0.1 ns setup/hold uncertainty.
    # Check the saved constraint before making any temporary optimization change.
    set fp [open [file join $out before.sdc] r]
    set saved_sdc [read $fp]
    close $fp
    if {$LIB_TIME_NS != 1.0 || ![regexp {(?m)^set_clock_uncertainty 0\.1\s+\[get_clocks core_clk\]} $saved_sdc]} {
        error "Baseline does not have the expected common 0.1 ns uncertainty"
    }
    set guard [expr {$env(MC_SETUP_GUARD_NS)/$LIB_TIME_NS}]
    set mode incremental
    if {[info exists env(MC_SETUP_MODE)]} { set mode $env(MC_SETUP_MODE) }
    if {$mode ni {incremental size_only valid_caps preserve_nand2 preserve_zero_caps}} { error "Unknown setup optimization mode" }
    puts "Setup optimization mode: $mode; additional setup guard ns: $env(MC_SETUP_GUARD_NS)"
    if {$mode eq "size_only"} {
        redirect [file join $out size_only_help.rpt] { man set_size_only }
        set leaf_cells [get_cells -hierarchical -filter {is_hierarchical == false} *]
        set originally_size_only [filter_collection $leaf_cells {size_only == true}]
        set_size_only -all_instances $leaf_cells true
    }
    if {$mode in {valid_caps preserve_nand2 preserve_zero_caps}} {
        # Exclude the zero-cap NAND2 cell from this optimization. DC also remaps
        # existing instances of an excluded reference; numerical library limits
        # are never edited. Restore the original
        # dont_use settings after optimization and before final assessment.
        set refs {gscl45nm/NAND2X1}
        set filter {ref_name == NAND2X1}
        if {$mode eq "preserve_zero_caps"} {
            set refs {gscl45nm/AOI21X1 gscl45nm/AOI22X1 gscl45nm/NAND2X1 gscl45nm/NAND3X1 gscl45nm/NOR2X1}
            set filter {ref_name == AOI21X1 || ref_name == AOI22X1 || ref_name == NAND2X1 || ref_name == NAND3X1 || ref_name == NOR2X1}
        }
        set restricted [get_lib_cells $refs]
        if {[sizeof_collection $restricted] != [llength $refs]} { error "Missing restricted cell types" }
        set originally_dont_use [filter_collection $restricted {dont_use == true}]
        redirect [file join $out restricted_cells.rpt] {
            foreach_in_collection cell $restricted {
                set name [get_object_name $cell]
                set cap [get_attribute [get_lib_pins ${name}/Y] max_capacitance]
                if {$cap != 0} { error "Expected zero max_capacitance on $name/Y" }
                puts "$name/Y max_capacitance=$cap; original dont_use=[get_attribute $cell dont_use]"
            }
        }
        set_dont_use $restricted
        if {$mode in {preserve_nand2 preserve_zero_caps}} {
            set preserved_cells [get_cells -hierarchical -filter $filter *]
            set originally_dont_touch [filter_collection $preserved_cells {dont_touch == true}]
            puts "Preserving [sizeof_collection $preserved_cells] existing restricted-cell instances during optimization"
            set_dont_touch $preserved_cells
        }
    }
    set_clock_uncertainty -setup [expr {0.1+$guard}] $clock
    write_sdc [file join $out optimization_target.sdc]
    # Skip DRC fixing during the timing experiment; all DRC limits remain
    # constrained and must be reviewed in the final complete violation report.
    if {![compile -incremental_mapping -map_effort high -no_design_rule]} {
        error "Incremental setup optimization failed"
    }
    redirect [file join $out guarded_setup.rpt] {
        report_timing -delay_type max -max_paths 10 -significant_digits 6
    }
    if {$mode eq "size_only"} {
        set_size_only -all_instances $leaf_cells false
        if {[sizeof_collection $originally_size_only] > 0} {
            set_size_only -all_instances $originally_size_only true
        }
    }
    if {$mode in {valid_caps preserve_nand2 preserve_zero_caps}} {
        remove_attribute $restricted dont_use
        if {[sizeof_collection $originally_dont_use] > 0} { set_dont_use $originally_dont_use }
        if {$mode in {preserve_nand2 preserve_zero_caps}} {
            remove_attribute $preserved_cells dont_touch
            if {[sizeof_collection $originally_dont_touch] > 0} { set_dont_touch $originally_dont_touch }
        }
    }
    # Restore the original common uncertainty before hold repair and assessment.
    set_clock_uncertainty 0.1 $clock
    set_fix_hold $clock
    if {![compile -only_hold_time]} { error "Final hold repair failed" }
    margin_reports $out after
    set fp [open [file join $out SUCCESS] w]
    puts $fp "Tool flow completed; adoption requires original-constraint timing, DRC, area and mapped equivalence."
    close $fp
}
if {[catch {improve_margin} message]} { puts stderr "ERROR: $message"; exit 1 }
exit 0
