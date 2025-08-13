# Synthesis

- Input Files: adc.v, salogic.v, clkgate.v, capdriver.v, comp.v, sampswitch.v, caparray.v, constraint.sdc, tcbn65lpwc.lib, tcbn65lp_9lmT2.lef
- Flow Config Files: designs/tsmc65/adc/config.mk, platforms/tsmc65/config.mk, platforms/tsmc65/setRC.tcl, platforms/tsmc65/tapcell.tcl, platforms/tsmc65/pdn.tcl  
- Output Files: results/tsmc65/adc/base/1_synth.v, results/tsmc65/adc/base/1_synth.sdc, results/tsmc65/adc/base/1_2_yosys.v, results/tsmc65/adc/base/1_1_yosys_canonicalize.rtlil, results/tsmc65/adc/base/clock_period.txt, results/tsmc65/adc/base/mem.json
- Report/Collateral Files: reports/tsmc65/adc/base/synth_stat.txt, reports/tsmc65/adc/base/synth_check.txt, logs/tsmc65/adc/base/1_1_yosys_canonicalize.log, logs/tsmc65/adc/base/1_2_yosys.log, objects/tsmc65/adc/base/lib/tcbn65lpwc.lib, objects/tsmc65/adc/base/abc.constr

# Floorplan

Mixed-signal layout with digital logic constrained to 40x40µm using M1-M3 layers:

```
┌─────────┐ ┌────────────┐ ┌─────────┐                      
│         │ │            │ │         │                      
│         │ │ Comparator │ │         │                      
│Switch P │ │  (20x20µm) │ │Switch N │                      
│(10x20µm)│ │            │ │(10x20µm)│                      
└─────────┘ └────────────┘ └─────────┘                      
┌────────────────────────────────────┐                      
│  (sampswitches and comp connect)   │                      
│                                    │                      
│                                    │                      
│                                    │                      
│                                    │                      
│                                    │                      
│                                    │                      
│          Digital Logic             │                     
│         (40x40µm max)              │                      
│        (M1-M3 layers)              │                      
│                                    │                      
│(cap array              (cap array  │                      
│ P connect)              N connect) │                      
│                                    │                      
│                                    │                      
│                                    │                      
│                                    │                      
│                                    │                      
│                                    │                      
│                                    │                      
│                                    │                      
│                                    │                      
│                                    │                      
│                                    │                      
│                                    │                      
│             (SPI and config bits)  │                      
└────────────────────────────────────┘                      
```

Note: Capacitor arrays are placed physically above in M5-M8 metal layers.