************************************************************************
* Library Name: tcbn65lplvt
* Cell Name:    CKXOR2D2LVT
* View Name:    schematic
************************************************************************

.SUBCKT CKXOR2D2LVT_dnw A1 A2 Z VDD VSS
*.PININFO A1:I A2:I Z:O VDD:B VSS:B
MM_u6-M_u2 net25 A1 net11 VDD pch_lvt l=60n w=290.0n m=1
MM_u5-M_u3 net5 net25 VDD VDD pch_lvt l=60n w=290.0n m=1
MM_u4_1-M_u3 Z net11 VDD VDD pch_lvt l=60n w=520.0n m=1
MM_u8-M_u3 net13 A1 VDD VDD pch_lvt l=60n w=520.0n m=1
MM_u4_0-M_u3 Z net11 VDD VDD pch_lvt l=60n w=520.0n m=1
MMI0-M_u2 net5 net13 net11 VDD pch_lvt l=60n w=290.0n m=1
MM_u2-M_u3 net25 A2 VDD VDD pch_lvt l=60n w=520.0n m=1
MM_u6-M_u3 net25 net13 net11 VSS nch_lvt l=60n w=195.00n m=1
MMI0-M_u3 net5 A1 net11 VSS nch_lvt l=60n w=195.00n m=1
MM_u8-M_u2 net13 A1 VSS VSS nch_lvt l=60n w=195.00n m=1
MM_u4_1-M_u2 Z net11 VSS VSS nch_lvt l=60n w=390.0n m=1
MM_u2-M_u2 net25 A2 VSS VSS nch_lvt l=60n w=390.0n m=1
MM_u5-M_u2 net5 net25 VSS VSS nch_lvt l=60n w=195.00n m=1
MM_u4_0-M_u2 Z net11 VSS VSS nch_lvt l=60n w=390.0n m=1
.ENDS


************************************************************************
* Library Name: tcbn65lplvt
* Cell Name:    CKXOR2D4LVT
* View Name:    schematic
************************************************************************

.SUBCKT CKXOR2D4LVT_dnw A1 A2 Z VDD VSS
*.PININFO A1:I A2:I Z:O VDD:B VSS:B
MM_u4_3-M_u3 Z net20 VDD VDD pch_lvt l=60n w=520.0n m=1
MM_u2_1-M_u3 net97 A2 VDD VDD pch_lvt l=60n w=520.0n m=1
MM_u2_0-M_u3 net97 A2 VDD VDD pch_lvt l=60n w=520.0n m=1
MM_u2_2-M_u3 net97 A2 VDD VDD pch_lvt l=60n w=520.0n m=1
MM_u5-M_u3 net61 net97 VDD VDD pch_lvt l=60n w=520.0n m=1
MM_u6_0-M_u2 net97 A1 net20 VDD pch_lvt l=60n w=440.0n m=1
MM_u4_1-M_u3 Z net20 VDD VDD pch_lvt l=60n w=520.0n m=1
MM_u6_1-M_u2 net97 A1 net20 VDD pch_lvt l=60n w=440.0n m=1
MM_u8-M_u3 net63 A1 VDD VDD pch_lvt l=60n w=520.0n m=1
MM_u4_0-M_u3 Z net20 VDD VDD pch_lvt l=60n w=520.0n m=1
MMI0_1-M_u2 net61 net63 net20 VDD pch_lvt l=60n w=395.00n m=1
MMI0_0-M_u2 net61 net63 net20 VDD pch_lvt l=60n w=395.00n m=1
MM_u4_2-M_u3 Z net20 VDD VDD pch_lvt l=60n w=520.0n m=1
MM_u6_0-M_u3 net97 net63 net20 VSS nch_lvt l=60n w=275.00n m=1
MMI0_0-M_u3 net61 A1 net20 VSS nch_lvt l=60n w=275.00n m=1
MM_u8-M_u2 net63 A1 VSS VSS nch_lvt l=60n w=390.0n m=1
MM_u2_1-M_u2 net97 A2 VSS VSS nch_lvt l=60n w=390.0n m=1
MM_u4_1-M_u2 Z net20 VSS VSS nch_lvt l=60n w=390.0n m=1
MM_u4_2-M_u2 Z net20 VSS VSS nch_lvt l=60n w=390.0n m=1
MM_u6_1-M_u3 net97 net63 net20 VSS nch_lvt l=60n w=275.00n m=1
MM_u5-M_u2 net61 net97 VSS VSS nch_lvt l=60n w=390.0n m=1
MMI0_1-M_u3 net61 A1 net20 VSS nch_lvt l=60n w=275.00n m=1
MM_u2_2-M_u2 net97 A2 VSS VSS nch_lvt l=60n w=390.0n m=1
MM_u4_3-M_u2 Z net20 VSS VSS nch_lvt l=60n w=390.0n m=1
MM_u4_0-M_u2 Z net20 VSS VSS nch_lvt l=60n w=390.0n m=1
MM_u2_0-M_u2 net97 A2 VSS VSS nch_lvt l=60n w=390.0n m=1
.ENDS
