import hdl21 as h
from pathlib import Path





# First, create external modules for 28nm NMOS and PMOS

@h.paramclass
class MosParams:    # External modules support parameters, unlike Hdl21 modules
    w = h.Param(dtype=float, desc="Channel Width")
    l = h.Param(dtype=float, desc="Channel Length")
    nf = h.Param(dtype=int, desc="Number of fingers")


nch = h.ExternalModule(
    name="sky130_fd_pr__nfet_01v8_lvt", desc="Tsmc28 NMOS", # Modules 'name' is used *verbatim when exporting*, so be sure to match
    port_list=[h.Inout(name="D"), h.Inout(name="G"), h.Inout(name="S"), h.Inout(name="B")], 
    paramtype=MosParams)

pch = h.ExternalModule(
    name="sky130_fd_pr__pfet_01v8_lvt", desc="Tsmc28 PMOS", 
    port_list=[h.Inout(name="D"), h.Inout(name="G"), h.Inout(name="S"), h.Inout(name="B")], 
    paramtype=MosParams)

# Then, create a inverter module, using these two

@h.paramclass
class InverterParams:
    nmos_params = h.Param(dtype=MosParams, desc="NMOS Parameters")
    pmos_params = h.Param(dtype=MosParams, desc="PMOS Parameters")
    # res_value = h.Param(dtype=float, desc="Drain resistor Value")



@h.generator
def common_source_amp_gen(params: InverterParams) -> h.Module:
    @h.module
    class Inverter:
        VSS = h.Inout() # Hdl21 provides four port constructors: Input, Output, Inout, and Port.
        VDD = h.Inout() # The last creates a directionless (or direction unspecified) port akin to those of common spice-level languages.
        vin = h.Input() 
        vout = h.Output()
        nmos = nch(params.nmos_params)(D=vout, G=vin, S=VSS, B=VSS)
        pmos = pch(params.pmos_params)(D=vout, G=vin, S=VSS, B=VSS)
        # res = h.Resistor(r=params.res_value)(p=VDD, n=vout)
    
    return Inverter


# Testbench setup

def run_characterization_sims(np_filename):
    
    # creating an array
    ids = np.zeros([np.size(mos_list),np.size(lch_list),np.size(vbs_list),np.size(vgs_list),np.size(vds_list)])


vds = vds_list[vds_index]


sim_options = SimOptions(
    rundir=Path("./scratch"),
    fmt=ResultFormat.SIM_DATA,
    simulator=SupportedSimulators.NGSPICE,
)


# For simulation and testbenching, notice how the testbench module is created seperately from the simulation class

tb = h.sim.tb("name of testbench")

#naming some signals from the testbench
tb.VDS = h.Signal()
tb.VGS = h.Signal()
tb.VBS = h.Signal()

# Testbenches must adhere to the testbench IO interface:
# A single, width-one port, nominally named "VSS", and expected to be connected from "simulator ground" to the DUT's groun
    tb.dut = nch(MosParams(w=w_unit, l=lch, nf=1))(D=tb.VDS, G=tb.VGS, S=tb.VSS, B=tb.VBS)
    tb.VDS_src = Vdc(Vdc.Params(dc=str(vds)))(p=tb.VDS, n=tb.VSS)
    tb.VGS_src = Vdc(Vdc.Params(dc=str(vgs)))(p=tb.VGS, n=tb.VSS)
    tb.VBS_src = Vdc(Vdc.Params(dc=str(vbs)))(p=tb.VBS, n=tb.VSS)

# There are three methods for creating a testbench:
#   1) Seperate tb (using procedural/class/generator, whatever) followed by sim object creation using s = h.sim.Sim().
# Everything, tb and attrs, etc are fed at once
#   2) Class-based defenition, using a @sim decorator. The tb module is/can be? defined inline.

sim = h.sim.Sim(tb=tb)
sim.lib(f"path/to/share/pdk/sky130A/libs.tech/ngspice/sky130.lib.spice", 'tt')
sim.op()    # I don't understand exactly how this works. I see an analysis type Enum, and a family of classes for each type. But this looks like a method?

# when sim.lib, or sim.op() are being run, where do these methods live? Are they implended by the Sim.Add() method?

sim.literal(".save @m.xtop.xdut.msky130_fd_pr__nfet_01v8_lvt[gm]")  # Will need to translate this to the equivalent in Spectre
sim.literal(".save all")

sim.noise() # This isn't implemented in Spectre yet. When it is though, is it large or small signal? (AC vs transient)
# I checked this. In both ngspice (and Spectre, IIRC) noise simulation is small signal AC based.
# To do transient noise simulation, 

sim_results = sim.run(sim_options)
ids[mos_type_index,lch_index,vbs_index,vgs_index,vds_index] = -sim_results[0].data['i(v.xtop.vvds_src)']


                        
print("a")
results = {
    "keys" : "[mos_list_index,lch_list_idnex,vbs_list_index,vgs_list_index,vds_list_index]",
    "mos_list" : mos_list,
    "lch_list" : lch_list,
    "vbs_list" : vbs_list,
    "vgs_list" : vgs_list,
    "vds_list" : vds_list,
    "ids" : ids,
    "gm" : gm,
    "gds" : gds,
    "cgg" : cgg,
    "cdd" : cdd,
    }
np.save(np_filename,results)
return results









# This allows the script to executable in standalone without causing
# problems if it is contents are called from another script.
# Should always appear at the bottom of the file.
# if __name__ == "__main__":
#     main()

# ^^ disable for now, as I'm just testing