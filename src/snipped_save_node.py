# Create a test bench module
tb = h.sim.tb()

# Create signals in testbench module
tb.VDS = h.Signal()
tb.VGS = h.Signal()
tb.VBS = h.Signal()

# Create testbench devices in testbench module
tb.dut = nch(MosParams(w=0.5, l=0.15, nf=1))(D=tb.VDS, G=tb.VGS, S=tb.VSS, B=tb.VBS)
tb.VDS_src = Vdc(Vdc.Params(dc=str(vds)))(p=tb.VDS, n=tb.VSS)
tb.VGS_src = Vdc(Vdc.Params(dc=str(vgs)))(p=tb.VGS, n=tb.VSS)
tb.VBS_src = Vdc(Vdc.Params(dc=str(vbs)))(p=tb.VBS, n=tb.VSS)

# Create simulation object, wrapped around testbench module
sim = h.sim.Sim(tb=tb)
sim.lib(f"/tools/kits/SKY/sky130A/libs.tech/ngspice/sky130.lib.spice", 'tt')
sim.op()
sim.save(tb.VDS) # <--- How to probe the tb.VDS signal?
sim.save(SaveMode.SELECTED)

# Setup sim options
sim_options = SimOptions(
    rundir=Path("./scratch"),
    fmt=ResultFormat.SIM_DATA,
    simulator=SupportedSimulators.XYCE,
)

# Run simulation
sim_results = sim.run(sim_options)

"""
NotImplementedError: Unimplemented control card signal: "VDS" for <vlsirtools.netlist.spice.XyceNetlister object at 0x7fe4cd1ffb10>
"""