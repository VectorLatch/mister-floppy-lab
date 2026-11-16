# On-build timing inspection only; does not alter generated FPGA configuration.
project_open Minimig
create_timing_netlist
read_sdc
update_timing_netlist
report_timing -setup -npaths 10 -detail full_path -file bart-critical-setup.txt
report_timing -hold -npaths 5 -detail full_path -file bart-critical-hold.txt
delete_timing_netlist
project_close
