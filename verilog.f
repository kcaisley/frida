-F libs/basil/verilog.f
// Select the ODDR model instead of the Spartan wrappers with the same name.
-v libs/basil/basil/firmware/modules/utils/ODDR.v
+define+BDAQ53=1
+incdir+design/hdl
+incdir+design/fpga
+incdir+design/fpga/SiTCP
-y design/fpga
