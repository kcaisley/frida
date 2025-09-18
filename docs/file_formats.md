# List of formats used, with some some documentation

.raw
.sp
.cdl
.saif   https://antmicro.com/blog/2025/07/power-estimation-in-openroad-using-saif-in-verilator/
.fst    .fst is a more modern, open-source, compressed waveform format favored by tools like Verilator and GTKWave: https://blog.timhutt.co.uk/fst_spec/
.fsdb   .fsdb is a proprietary, compressed waveform format primarily used by the Synopsys simulator Verdi
.vcd    
.spef
.sdf    https://www.chipverify.com/verilog/verilog-sdf
.sdc
.itf    https://physicaldesign-asic.blogspot.com/2020/07/interconnect-technology-format-itf.html, https://vlsi-concept.blogspot.com/2009/01/interconnect-technology-file-itf.html
.def
.lef
.gds
.lib
.upf
.v (RTL)
.v (netlist)


Verilog files define nets, modules, and ports
instances are either modules, or primatives (celldefine)
nets connect between modules and primatives
nets have types `net_type ::= supply0 | supply1 | tri | triand | trior | tri0 | tri1 | uwire | wire | wand | wor` of which wire is the most common


Liberty files define cells (equal to master in ODB and macro in LEF), pins


LEF/DEF:
MACRO, PIN (defining name and direction), PORTS (defining physical geometry) and OBS (non-port geometry)


ODB    vs verilog
block (perspective from within a module definition)
bterm (inputs/outputs)
nets (wires)
iterms (inputs/outputs of )
master (module name)
instance (name of instance of module)


NOTE: cell is an ambiguous, as it could refere to either a master or a instances.