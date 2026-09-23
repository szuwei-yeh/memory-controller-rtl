# Copy to an untracked lab_config.tcl ON THE LAB SERVER and fill from the lab setup.
# Do not commit licensed library files or private installation details.
set TARGET_LIBRARIES [list /absolute/path/to/lab/standard_cells.db]
set LIB_SEARCH_PATH [list /absolute/path/to/lab]
set LIB_CORNER "replace_with_library_and_process_voltage_temperature_corner"
# Number of ns and fF in one library time/capacitance unit. Verify report_lib.
set LIB_TIME_NS 1.0
set LIB_CAP_FF 1000.0
