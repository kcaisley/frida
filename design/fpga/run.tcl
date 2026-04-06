# -----------------------------------------------------------
# FRIDA DAQ Firmware - Vivado Build Script
# -----------------------------------------------------------
#
#   Start vivado in batch mode (run from design/fpga/):
#       vivado -mode batch -source run.tcl -notrace
#
#   Or in tcl mode for interactive use:
#       vivado -mode tcl -source run.tcl
#
#   Based on: tj-monopix2-daq/firmware/vivado/run.tcl

# Use current environment python instead of vivado included python
if {[info exists ::env(PYTHONPATH)]} {
    unset ::env(PYTHONPATH)
}
if {[info exists ::env(PYTHONHOME)]} {
    unset ::env(PYTHONHOME)
}
# Get rid of Vivado python (since Vivado 2021) in PATH
set env(PATH) [join [lsearch -inline -all -not -regexp [split $::env(PATH) ":"] (.*)lnx64\/python(.*)] ":"]

set fpga_dir [exec pwd]
# Try to find basil via Python, fall back to known location in libs/
if {[catch {set basil_dir [exec python -c "import basil, os; print(str(os.path.dirname(os.path.dirname(basil.__file__))))"]}]} {
    set basil_dir [file normalize $::env(HOME)/libs/basil]
    puts "INFO: basil not installed as Python package, using $basil_dir"
}
set include_dirs [list $fpga_dir $fpga_dir/SiTCP $basil_dir/basil/firmware/modules $basil_dir/basil/firmware/modules/utils]

file mkdir bit reports


proc run_bit {part xdc_file size {suffix ""}} {
    global fpga_dir
    global include_dirs

    set board_name [lindex [split [lindex [split $xdc_file '.'] 0] '_'] 0]
    set fpga_name  [lindex [split [lindex [split $xdc_file '.'] 0] '_'] 1]
    if {$suffix != ""} {set suffix \_$suffix}
    set identifier $board_name\_$fpga_name$suffix

    create_project -force -part $part $identifier designs

    read_verilog $fpga_dir/daq_top.v
    read_verilog $fpga_dir/daq_core.v
    read_edif $fpga_dir/SiTCP/SiTCP_XC7K_32K_BBT_V110.edf
    read_xdc $fpga_dir/$xdc_file
    read_xdc $fpga_dir/SiTCP/EDF_SiTCP.xdc

    synth_design -top daq_top -include_dirs $include_dirs -verilog_define [string toupper $board_name]=1 -verilog_define "SYNTHESIS=1"
    opt_design
    place_design
    phys_opt_design
    route_design
    report_utilization -file "reports/report_utilization_$identifier.log"
    report_timing -file "reports/report_timing_$identifier.log"

    write_bitstream -force -bin_file -file $fpga_dir/bit/frida_$identifier
    write_cfgmem -format mcs -size $size -interface SPIx4 -loadbit "up 0x0 $fpga_dir/bit/frida_$identifier.bit" -force -file $fpga_dir/bit/frida_$identifier
    close_project
}


#
# Create projects and bitfiles
#

if {$argc == 0} {
    #          FPGA model              constraints file     flash size  suffix
    run_bit    xc7k160tfbg676-1        bdaq53_kx1.xdc       64          ""
    # run_bit  xc7k160tffg676-2        bdaq53_kx2.xdc       64          ""
} else {
    if {($argc == 3) || ($argc == 4)} {
        run_bit {*}$argv
    } else {
        puts "ERROR: Invalid args"
    }
}

exit
