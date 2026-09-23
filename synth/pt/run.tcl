proc run_sta {} {
    global env search_path link_path
    source $env(MC_LAB_CONFIG)
    set search_path [concat $search_path $LIB_SEARCH_PATH]
    set link_path [concat "*" $TARGET_LIBRARIES]
    set out $env(MC_OUT)
    file delete -force [file join $out SUCCESS]
    read_verilog [file join $env(MC_DC_RUN) mapped.v]
    current_design mc_top
    link_design mc_top
    read_sdc [file join $env(MC_DC_RUN) mapped.sdc]
    update_timing
    redirect [file join $out version.rpt] { version }
    redirect [file join $out check_timing.rpt] { check_timing -verbose }
    redirect [file join $out coverage.rpt] { report_analysis_coverage }
    redirect [file join $out setup.rpt] { report_timing -delay_type max -max_paths 10 }
    redirect [file join $out hold.rpt] { report_timing -delay_type min -max_paths 10 }
    redirect [file join $out constraints.rpt] { report_constraint -all_violators }
    set fp [open [file join $out SUCCESS] w]; puts $fp "Pre-layout STA complete; no extracted parasitics."; close $fp
}
if {[catch {run_sta} message]} { puts stderr "ERROR: $message"; exit 1 }
exit 0
