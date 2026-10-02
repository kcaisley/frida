yosys -import
read_verilog -sv -DCOCOTB_SIM \
  -I/users/kcaisley/libs/obelix1-daq/firmware/src/obelix1_rx \
  /users/kcaisley/libs/obelix1-daq/firmware/src/obelix1_rx/obelix1_rx.v \
  /users/kcaisley/libs/obelix1-daq/firmware/src/utils/rec_sync.v \
  /users/kcaisley/libs/obelix1-daq/firmware/src/utils/decode_8b10b.v \
  /local/frida/libs/basil/basil/firmware/modules/utils/bus_to_ip.v \
  /local/frida/libs/basil/basil/firmware/modules/utils/cdc_reset_sync.v \
  /local/frida/libs/basil/basil/firmware/modules/utils/cdc_syncfifo.v \
  /local/frida/libs/basil/basil/firmware/modules/utils/generic_fifo.v \
  /local/frida/libs/basil/basil/firmware/modules/utils/flag_domain_crossing.v \
  /local/frida/libs/basil/basil/firmware/modules/utils/IDDR.v
