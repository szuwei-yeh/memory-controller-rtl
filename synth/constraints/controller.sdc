# This file is sourced with CLOCK_NS, LIB_TIME_NS and LIB_CAP_FF defined.
# All functional paths, including synchronous reset, remain constrained.
create_clock -name core_clk -period [expr {$CLOCK_NS/$LIB_TIME_NS}] [get_ports clk]
set_clock_uncertainty [expr {0.1/$LIB_TIME_NS}] [get_clocks core_clk]
set inputs [remove_from_collection [all_inputs] [get_ports clk]]
set_input_delay -max [expr {1.0/$LIB_TIME_NS}] -clock core_clk $inputs
set_input_delay -min 0 -clock core_clk $inputs
set_output_delay -max [expr {1.0/$LIB_TIME_NS}] -clock core_clk [all_outputs]
set_output_delay -min 0 -clock core_clk [all_outputs]
set_input_transition [expr {0.1/$LIB_TIME_NS}] $inputs
set_load [expr {10.0/$LIB_CAP_FF}] [all_outputs]
