# Run from the project root through scripts/synth.py dc --lab.
proc run_controller {} {
    global env search_path target_library link_library
    source $env(MC_LAB_CONFIG)
    foreach name {TARGET_LIBRARIES LIB_SEARCH_PATH LIB_CORNER LIB_TIME_NS LIB_CAP_FF} {
        if {![info exists $name]} { error "Missing lab setting $name" }
    }
    foreach lib $TARGET_LIBRARIES { if {![file isfile $lib]} { error "Missing library $lib" } }
    if {$LIB_TIME_NS<=0 || $LIB_CAP_FF<=0} { error "Invalid library units" }
    set out $env(MC_OUT)
    file delete -force [file join $out SUCCESS]
    set search_path [concat $search_path $LIB_SEARCH_PATH]
    set target_library $TARGET_LIBRARIES
    set link_library [concat "*" $TARGET_LIBRARIES]
    define_design_lib WORK -path [file join $out work]
    set fp [open synth/rtl_files.f r]
    set rtl_files [split [string trim [read $fp]] "\n"]
    close $fp
    foreach path $rtl_files {
        if {![regexp {^rtl/[A-Za-z0-9_]+\.sv$} $path]} { error "Unsafe RTL manifest entry: $path" }
    }
    if {![analyze -format sverilog -define SYNTHESIS $rtl_files]} { error "RTL analysis failed" }
    if {![elaborate mc_top -parameters "Q_DEPTH=$env(MC_Q),SCHED_POLICY=$env(MC_POLICY),AGING_ENABLE=$env(MC_AGING)"]} {
        error "RTL elaboration failed"
    }
    # DC retains the parameter-specialized top as current_design.
    puts "Elaborated controller top: [get_object_name [current_design]]"
    if {![link]} { error "Design link failed" }
    if {![check_design]} { error "Design checks failed" }
    if {[info exists OPERATING_CONDITION]} { set_operating_conditions $OPERATING_CONDITION }
    set CLOCK_NS $env(MC_CLOCK_NS)
    source synth/constraints/controller.sdc
    redirect [file join $out environment.rpt] {
        puts "Library/corner: $LIB_CORNER"
        puts "Target libraries: $TARGET_LIBRARIES"
        puts "Link libraries: $link_library"
        puts "Time unit ns: $LIB_TIME_NS; capacitance unit fF: $LIB_CAP_FF"
        puts "Clock target ns: $CLOCK_NS; Q: $env(MC_Q); policy: $env(MC_POLICY); aging: $env(MC_AGING)"
        puts "Tool version: see dc_shell startup banner in tool.log"
        report_design
        if {[info exists TARGET_LIBRARY_NAMES]} { foreach_in_collection lib [get_libs $TARGET_LIBRARY_NAMES] {
            puts "Loaded library: [get_object_name $lib]"
            foreach attr {time_unit_name capacitive_load_units default_operating_conditions nom_process nom_voltage nom_temperature} {
                puts "$attr: [get_attribute $lib $attr]"
            }
        } }
    }
    # Fixed effort for every point; no automatic retiming or extra pipeline stages.
    compile -map_effort medium
    # Preserve the mapped design even if a later diagnostic command fails.
    write -format ddc -hierarchy -output [file join $out mapped.ddc]
    redirect [file join $out check_design.rpt] { check_design }
    redirect [file join $out check_timing.rpt] { check_timing }
    redirect [file join $out design.rpt] { report_design }
    redirect [file join $out area.rpt] { report_area -hierarchy }
    redirect [file join $out timing.rpt] { report_timing -delay_type max -max_paths 10 -nets -transition_time -capacitance -input_pins -significant_digits 6 }
    redirect [file join $out hold.rpt] { report_timing -delay_type min -max_paths 20 -nets -transition_time -capacitance -input_pins -significant_digits 6 }
    redirect [file join $out constraints.rpt] { report_constraint -all_violators -significant_digits 6 }
    redirect [file join $out qor.rpt] { report_qor }
    redirect [file join $out references.rpt] { report_reference -hierarchy }
    change_names -rules verilog -hierarchy
    write -format verilog -hierarchy -output [file join $out mapped.v]
    write -format ddc -hierarchy -output [file join $out mapped.ddc]
    write_sdc [file join $out mapped.sdc]
    set fp [open [file join $out SUCCESS] w]; puts $fp "Tool flow completed; inspect timing violations separately."; close $fp
}
if {[catch {run_controller} message]} { puts stderr "ERROR: $message"; exit 1 }
exit 0
