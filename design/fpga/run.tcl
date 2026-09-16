# -----------------------------------------------------------
# BDAQ Firmware - Vivado Build Script
# -----------------------------------------------------------
#
#   Start vivado in batch mode (supply arguments below):
#       vivado -mode batch -source run.tcl -notrace \
#           -log build/vivado.log -journal build/vivado.jou -tclargs PART SIZE OPTIONS
#
#   Or in tcl mode for interactive use:
#       vivado -mode tcl -source run.tcl \
#           -log build/vivado.log -journal build/vivado.jou -tclargs PART SIZE OPTIONS
#
#   Based on: tj-monopix2-daq/firmware/vivado/run.tcl

# All project inputs and output paths are supplied on the command line.
set include_dirs {}
set verilog_files {}
set xdc_files {}
set edif_files {}
set top ""
set output_name ""
set output_dir ""


proc run_bit {part size} {
    global include_dirs verilog_files xdc_files edif_files top output_name output_dir

    set identifier $output_name
    set bit_name $output_name
    foreach path [concat $verilog_files $edif_files $xdc_files] {
        if {![file isfile $path]} {error "Input file does not exist: $path"}
    }
    file mkdir $output_dir/build $output_dir/bit $output_dir/reports
    cd $output_dir

    create_project -force -part $part $identifier build

    foreach path $verilog_files {read_verilog $path}
    foreach path $edif_files {read_edif $path}
    foreach path $xdc_files {read_xdc $path}

    synth_design -top $top -include_dirs $include_dirs -verilog_define BDAQ53=1 -verilog_define "SYNTHESIS=1"
    write_checkpoint -force $output_dir/build/${identifier}_synth.dcp
    opt_design
    place_design
    phys_opt_design
    route_design
    write_checkpoint -force $output_dir/build/${identifier}_route.dcp
    report_utilization -file "reports/report_utilization_$identifier.log"
    report_timing -file "reports/report_timing_$identifier.log"

    set_property BITSTREAM.CONFIG.SPI_BUSWIDTH 4 [current_design]
    write_bitstream -force -bin_file -file $output_dir/bit/$bit_name
    write_cfgmem -format mcs -size $size -interface SPIx4 -loadbit [list up 0x0 $output_dir/bit/$bit_name.bit] -force -file $output_dir/bit/$bit_name
    close_project
}

if {"--help" in $argv || "-h" in $argv} {
    puts {Usage: vivado -mode batch -source run.tcl -tclargs PART SIZE OPTIONS
Required:
  PART                FPGA part (xc7k160tfbg676-1 or xc7k160tffg676-2)
  SIZE                Flash size in MB
  --verilog FILE      Verilog compilation unit (repeatable)
  --xdc FILE          Constraint file (repeatable)
  --top MODULE        Top module
  --name NAME         Project and image basename
  --out-dir DIR       Parent of build/, bit/, reports/
Optional:
  --edif FILE         EDIF netlist (repeatable)
  --include-dir DIR   Verilog include directory (repeatable)
All paths resolve from the invocation directory. No HDL, XDC, EDIF or include
paths are added implicitly. Existing matching outputs are overwritten.
BDAQ53 and SYNTHESIS macros and SPIx4 configuration are fixed for BDAQ hardware.}
    exit 0
}
if {[catch {
    if {$argc < 2} {error "Expected PART SIZE and required options (use --help)"}
    lassign [lrange $argv 0 1] part size
    if {$part ni {xc7k160tfbg676-1 xc7k160tffg676-2}} {error "Unsupported BDAQ FPGA part: $part"}
    if {![string is integer -strict $size] || $size <= 0} {error "SIZE must be a positive integer"}
    set remaining [lrange $argv 2 end]
    if {[llength $remaining] % 2} {error "Missing option value (use --help)"}
    foreach {option value} $remaining {
        if {$value eq "" || [string match --* $value]} {error "Missing value for $option"}
        switch -- $option {
            --verilog     {lappend verilog_files [file normalize $value]}
            --xdc         {lappend xdc_files [file normalize $value]}
            --edif        {lappend edif_files [file normalize $value]}
            --include-dir {lappend include_dirs [file normalize $value]}
            --top         {set top $value}
            --name        {
                if {![regexp {^[A-Za-z0-9_][A-Za-z0-9_.-]*$} $value]} {
                    error "--name must be a basename, not a path"
                }
                set output_name $value
            }
            --out-dir     {set output_dir [file normalize $value]}
            default       {error "Unknown option: $option"}
        }
    }
    foreach {option value} [list --verilog $verilog_files --xdc $xdc_files \
        --top $top --name $output_name --out-dir $output_dir] {
        if {$value eq ""} {error "Required option: $option"}
    }
    foreach path $include_dirs {
        if {![file isdirectory $path]} {error "Include directory does not exist: $path"}
    }
    run_bit $part $size
} message]} {
    puts stderr "ERROR: $message"
    exit 1
}

exit 0
