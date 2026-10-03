# Read-only electrical queries on a retained mapped DDC. No compile, load edits,
# library-attribute edits or SDC relaxation are performed.
proc diagnose_capacitance {} {
    global env search_path target_library link_library
    foreach name {MC_LAB_CONFIG MC_MAPPED_DDC MC_ANALYSIS_TOP MC_ANALYSIS_OUT} {
        if {![info exists env($name)]} { error "Missing environment setting $name" }
    }
    set out $env(MC_ANALYSIS_OUT)
    if {[file exists $out]} { error "Use a new diagnosis output directory" }
    source $env(MC_LAB_CONFIG)
    foreach name {TARGET_LIBRARIES LIB_SEARCH_PATH LIB_TIME_NS LIB_CAP_FF} {
        if {![info exists $name]} { error "Missing lab setting $name" }
    }
    foreach lib $TARGET_LIBRARIES { if {![file isfile $lib]} { error "Missing library $lib" } }
    if {![file isfile $env(MC_MAPPED_DDC)]} { error "Missing mapped DDC" }
    set search_path [concat $search_path $LIB_SEARCH_PATH]
    set target_library $TARGET_LIBRARIES
    set link_library [concat "*" $TARGET_LIBRARIES]
    read_ddc $env(MC_MAPPED_DDC)
    current_design $env(MC_ANALYSIS_TOP)
    if {![link]} { error "Mapped design link failed" }
    file mkdir $out
    redirect [file join $out audit_area.rpt] { report_area -hierarchy }
    redirect [file join $out audit_setup.rpt] {
        report_timing -delay_type max -max_paths 10 -significant_digits 6
    }
    redirect [file join $out audit_hold.rpt] {
        report_timing -delay_type min -max_paths 20 -significant_digits 6
    }
    redirect [file join $out audit_constraints.rpt] { report_constraint -all_violators -significant_digits 6 }
    redirect [file join $out audit_qor.rpt] { report_qor }
    redirect [file join $out audit_references.rpt] { report_reference -hierarchy }
    redirect [file join $out audit_check_timing.rpt] { check_timing }
    redirect [file join $out audit_check_design.rpt] { check_design }
    redirect [file join $out audit_design.rpt] { report_design }
    write_sdc [file join $out query.sdc]
    set library [get_libs gscl45nm]
    if {[sizeof_collection $library] != 1} { error "Expected matching gscl45nm library" }
    redirect [file join $out environment.rpt] {
        puts "library=gscl45nm"
        puts "time_unit_name=[get_attribute $library time_unit_name]"
        puts "capacitive_load_units_fF=[get_attribute $library capacitive_load_units]"
        puts "config_time_unit_ns=$LIB_TIME_NS"
        puts "config_capacitance_unit_fF=$LIB_CAP_FF"
    }
    set zero_refs {}
    set fp [open [file join $out db_limits.tsv] w]
    puts $fp "library_pin\tdirection\tmax_capacitance_library_units"
    foreach_in_collection pin [get_lib_pins gscl45nm/*/*] {
        set direction [get_attribute $pin direction]
        if {$direction ne "out" && $direction ne "inout"} { continue }
        set cap [get_attribute -quiet $pin max_capacitance]
        set name [get_object_name $pin]
        if {$cap eq ""} {
            puts $fp "$name\t$direction\tABSENT"
        } else {
            puts $fp "$name\t$direction\t$cap"
            if {$cap == 0} { lappend zero_refs [lindex [split $name /] 1] }
        }
    }
    close $fp
    set zero_refs [lsort -unique $zero_refs]
    if {[llength $zero_refs] == 0} { error "No zero-limit references found" }
    set filter_parts {}
    foreach ref $zero_refs { lappend filter_parts "ref_name == $ref" }
    set cells [get_cells -hierarchical -filter [join $filter_parts " || "] *]
    set nets ""
    set fp [open [file join $out zero_drivers.tsv] w]
    puts $fp "net\tdriver_pin\treference\tmax_capacitance_library_units\tactual_capacitance_library_units"
    foreach_in_collection cell $cells {
        set ref [get_attribute $cell ref_name]
        foreach_in_collection pin [get_pins -of_objects $cell -filter {pin_direction == out}] {
            set libpin [get_lib_pins gscl45nm/${ref}/[file tail [get_object_name $pin]]]
            set cap [get_attribute -quiet $libpin max_capacitance]
            if {$cap eq "" || $cap != 0} { continue }
            # Use the top segment of a physical net: hierarchical port aliases
            # otherwise differ from the names in report_constraint.
            set net [get_nets -segments -top_net_of_hierarchical_group -of_objects $pin]
            if {[sizeof_collection $net] != 1} { error "Expected one net per zero-limit output" }
            set nets [add_to_collection -unique $nets $net]
            puts $fp "[get_object_name $net]\t[get_object_name $pin]\t$ref\t$cap\t[get_attribute $net total_capacitance_max]"
        }
    }
    close $fp
    redirect [file join $out zero_nets.rpt] {
        # DC ignores significant_digits for connection reports; the collector
        # checks their native precision against Liberty with explicit tolerances.
        report_net -connections -verbose -nosplit $nets
    }
    set fp [open [file join $out SUCCESS] w]
    puts $fp "Retained mapping queried without compile or constraint/library edits; verify source, units and load accounting."
    close $fp
}
if {[catch {diagnose_capacitance} message]} { puts stderr "ERROR: $message"; exit 1 }
exit 0
