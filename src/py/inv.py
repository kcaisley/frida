import hdl21 as h
from hdl21.prefix import µ, n, f
import sys

from ...Tsmc28.tsmc28_hdl21.pdk import MosParams

# First, create external modules for 28nm NMOS and PMOS

nch = h.ExternalModule(
    name="nch_lvt_mac", desc="Tsmc28 NMOS", # Modules 'name' is used *verbatim when exporting*, so be sure to match
    port_list=[h.Inout(name="D"), h.Inout(name="G"), h.Inout(name="S"), h.Inout(name="B")], 
    paramtype=MosParams)

pch = h.ExternalModule(
    name="pch_lvt_mac", desc="Tsmc28 PMOS", 
    port_list=[h.Inout(name="D"), h.Inout(name="G"), h.Inout(name="S"), h.Inout(name="B")], 
    paramtype=MosParams)

# Then, create a inverter module, using these two

@h.paramclass
class InverterParams:
    nmos_params = h.Param(dtype=MosParams, desc="NMOS Parameters")
    pmos_params = h.Param(dtype=MosParams, desc="PMOS Parameters")
    # res_value = h.Param(dtype=float, desc="Drain resistor Value")

@h.generator
def inverter_gen(params: InverterParams) -> h.Module:
    @h.module
    class Inverter:
        vss = h.Inout() # Hdl21 provides four port constructors: Input, Output, Inout, and Port.
        vdd = h.Inout() # The last creates a directionless (or direction unspecified) port akin to those of common spice-level languages.
        vin = h.Input() 
        vout = h.Output()
        pmos = pch(params.pmos_params)(D=vout, G=vin, S=vdd, B=vdd)
        nmos = nch(params.nmos_params)(D=vout, G=vin, S=vss, B=vss)
        # res = h.Resistor(r=params.res_value)(p=VDD, n=vout)
    
    return Inverter

#What is the name of the thing returned from the generator though?


# Create an object of InverterParams with NMOS and PMOS parameters in one line
inverter_params_obj = InverterParams(nmos_params=MosParams(w=300*n, l=100*n, multi=1, nf=1), pmos_params=MosParams(w=300*n, l=100*n, multi=1, nf=1))
inverter_params_obj2 = InverterParams(nmos_params=MosParams(w=200*n, l=100*n, multi=1, nf=1), pmos_params=MosParams(w=300*n, l=100*n, multi=1, nf=1))



# inverter_gen(inverter_params_obj)

x1 = inverter_gen(inverter_params_obj)
x2 = inverter_gen(inverter_params_obj2)

# h.netlist(Inverter, sys.stdout, fmt='spectre')

print("hello")

h.Instance