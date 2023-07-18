import hdl21 as h

# Generator for basic CMOS inverters. Various sizes and scales are needed.




@h.paramclass
class InvParams:
    lengths = h. Param(dtype=int, desc="W")
    widths = h.Param(dtype=int, desc="")
    pnratio = h.Param(dtype=int, desc="Ratio of PMOS to NMOS widths. Required.") 

#Params
@h.generator
def InvGenerator(params: MyParams) -> h.Module:

@h.module
class Inv:
    in = h.Input()
    out = h.Output()
    vdd = h.Power()
    vss = h.Ground()
    p = h.primitives.Mos()

    