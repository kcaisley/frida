import hdl21 as h

# Generator for basic CMOS inverters. Various sizes and scales are needed.

# 

@h.paramclass
class InvParams:
    lengths = h. Param(dtype=int, desc="W")
    widths = h.Param(dtype=int, desc="")
    pnratio = h.Param(dtype=int, desc="Ratio of PMOS to NMOS widths. Required.") 


# You have to define a class, but you don't have to create an param object from it before feeding it to a generator object.
# If, in the definition of the corresponding generator object, it knows to expect a input 

#Params
@h.generator
def InvGenerator(params: MyParams) -> h.Module:


class Inv:
    in = h.Input()
    out = h.Output()
    vdd = h.Power()
    vss = h.Ground()