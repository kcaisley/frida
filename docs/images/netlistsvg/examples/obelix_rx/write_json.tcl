# Regenerate from /local/frida:
# yosys -Q -c docs/images/netlistsvg/examples/obelix_rx/write_json.tcl
# This source sits beside its generated JSON.
yosys -import
set obelix /users/kcaisley/libs/obelix1-daq
set basil /local/frida/libs/basil/basil/firmware/modules/utils
read_verilog -sv -lib \
  $basil/bus_to_ip.v \
  $basil/cdc_reset_sync.v \
  $basil/cdc_syncfifo.v \
  $basil/generic_fifo.v \
  $basil/flag_domain_crossing.v \
  $basil/IDDR.v
read_verilog -sv -DCOCOTB_SIM \
  -I$obelix/firmware/src/obelix1_rx \
  $obelix/firmware/src/obelix1_rx/obelix1_rx.v \
  $obelix/firmware/src/utils/rec_sync.v \
  $obelix/firmware/src/utils/decode_8b10b.v
prep -top obelix1_rx
write_json docs/images/netlistsvg/examples/obelix_rx/netlist.json
