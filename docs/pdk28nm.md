Looks like a 1.28 GHZ pll is already being built:
By Franco Brandi / Tobias Hofmann
https://indico.cern.ch/event/1127562/contributions/5026556/attachments/2512967/4320206/2022.09.14_ASIC-Support_news_and_EP-WP5_developments.pdf
https://asic-support-28.web.cern.ch/documents/macro_blocks/slvs_tx_rx/topical_doc_28nm_txrx_frbandi_v1.pdf
https://asic-support-28.web.cern.ch/ip-blocks/slvs_tx_rx/

There are more block heres:

[](https://asic-support-28.web.cern.ch/ip-blocks/page/2/)

Some earlier discussion of 28nm:

[](https://agenda.infn.it/event/12813/contributions/16317/attachments/11832/13318/PLL.pdf)

[](https://agenda.infn.it/event/12813/contributions/16303/attachments/11836/13322/FullCustom.pdf)

full custom layout, digital pll, 

>   The “very essential” rules for design in 28 nm are:
    Design Rule #1: Use only transistors for your design
    Design Rule #2: If you need passive components, then go back to Rule #1

- Now 28nm is available, but:
	- 2-4x transistors -> longer simulation, layout, verification
	- 3x PDK/DRC rules
	- 2x cost (8k EUR/mm^2)

# Review of PDK Docs:

All document are found in prefix: `/tools/kits/TSMC/CRN28HPC+/HEP_DesignKit_TSMC28_HPCplusRF_v1.0/pdk/1P9M_5X1Y1Z1U_UT_AlRDL/cdsPDK/PDK_doc/TSMC_DOC_WM/`

- `PDK/Application_note_for_customized_cells.pdf`: instructions on adding 3rd party IP into TSMC PDK, by streaming in layouts, assigning pins
- `PDK/N28_APP_of_MonteCarlo_statistical_simulation.pdf`: MonteCarlo is done by changing `top_tt` library for `top_globalmc_localmc` model cards of transistors. Is this do-able with Spectre natively, or do we need 'ADE XL' as a front end?
- `PDK/parasitic_rc_UserGuide.pdf`: Raphael 2D and 3D parasitic models for PEX. (Actually in pdk, under do-not-use) See: ![](https://cseweb.ucsd.edu/classes/fa12/cse291-c/slides/L5extract.pdf)
- `PDK/tsmcN28MSOAEnablement.pdf`: summarizes metal stack up, MSOA (mixed signal open access) explanation
- `PDK/tsmc_PDK_usage_guide.pdf`: I see that I need to copy `display.drf` and `ln -s` link in `models` and `steam` to my `tsmc28` init directory.
- `model/2d5 (or 1d8) /cln28ull_v1d0_2_usage_guide.pdf`: And finally, the master document for transitor models. Version 2d5 vs 1d8 folder doesn't matter
  - primitive MOSFET models have been replaced with macro model (compiled TMI shared library)
  - core transistor is BSIM6 version BSIMBULK binary model, surrounding layout effect are macro
  - diodes use standard spice model
  - resistors, mom varactors, and fmom use TSMC proprietary models
  - You should see a `** TMI Share Library Version XXXXXX` in the sim log, if not there may be problem
  - SPICE netlist difference
    ```
    For primitive model:
    M1 d g s b nch l=30n w=0.6u
    .print dc I1(M1)
    
    For macro model:
    X1 d g s b nch_mac l=30n w=0.6u
    .print dc I1(X1.main)
    ```
  - Layout effects are modeled in either SPICE model or macro surroundings
  - OD rouding, poly rounding, contact placement, and edge finger LOD are in macro
  - LOD, WPE, PSE (poly space effect), OSE (OD to OD space effect), MBE (metal boundary effect), RDR
  - In BSIM6 there are Instance Parameters which are set and passed in the netlist, and there are model parameters which are part of the compiled model binary, and don't change from device to device.
  - How are parameters passed to the macro model? Perhaps it relies on the same input instance parameters that the core BSIM model uses?
  - RDR = restrictive design rules. Should double check these devices, if the length is under 100nm.
  - There is a 0.9 shrinkage in the "model usage files", so don't add it in netlists. It comes from the 'geoshrink' or in Spectre called the `.param scalefactor`. Therefore don't 
  - There are four modes for variation simulation: trad. total corner, global corner, local monte carlo, global+local monte carlo
  - Variation models are selected with high-level `.lib` statements, check slides 36-40 for instructions
  - Full MC (Case 4) give most silicon accuracy, but is expensive. Instead use global corner (Case 2) for digital long path circuit, as global var dominates.
  - And for analog design, mismatch matters, so do Case 2+MC or just Case 3 which includes MC by default
  - you can run mismatch only for key devices, if designer
  - `soa_warn=yes` will give warnings for over voltage
  - `.lib 'usage.l' noise_mc` and related command will enable flicker noise models, which are independant of device corner
  
  
# Short conversation with Hans:

* For TSMC 65: 1.2V was core, IO voltages 1.8, 2.5, 3.3 V
* Core devices have a thinner oxide, which is good for TID hardness
    * we don't want to use IO devices, due to thicker oxide
    * oxide thickness is a property of geometry, and uses a seperate mask
* On the other hand, transistor thresholds flavors are not geometry determined but instead by doping profiles.
    * you are limited by 
* check CERN PDK, to understand which flavors of thresholda are compatible -> every additional threshold costs money
- Requesting runs for Cern needs to be done 4 months in advance. Today is ~Aug 1.
    - 4 months from Aug 1 is Nov 30 MPW
    - 4.5 months from Aug 1 is Dec 15 MPW
    - 6 months from Aug 1 is Feb 2 mini@sic
    - If I want any of these next two runs, I should send my email application to CERN tomorrow.
    

# Transistor sizing scheme

From my thesis:

> In particular, minimum size devices should be avoided; device widths should be kept larger than 200 nm and length to 40 nm or more. Particularly long devices lengths of 1 μm or more should also be avoided.

So it looks like for things like oscillators, I could get device widths up to 10-20 micrometers, and lengths from 40-200nm.

In finfets, increasing the number of fin is the same thing as making the device wider per finger. So fins and fingers determines total width.

In most designs, it seems they have fixed length, and finger width, and all they tune in the number of fingers, i.e. total width. 

I think I may be able to get away with a L=50n, but I'm not sure what I should choose for my unit finger width? I'm considering 100n, 200n, and 250n and my finger width.

Hakhamaneshi's thesis has some tidbits.


### from laygo2 notes

- All placement should rely on the PR boundary

- X axis: base on poly pitch

- Y axis: multiple of fin grid (in mine, this is finger width). This is equal to the height of the unit transistor.

![Alt text](img/layout_grid.png)

Quantized routing grid and unit transistor:

- M1/M2 are used to connect transistors (generally non-uniform)
- TR (transistor) sizing: quantized to unit transistor (4 fins suggested)

![Alt text](img/layout_cells.png)

Transistors are aranged in the following manner:

- Core cell: active device, taps above/below, dummy fill on ends
- Row boundary cell: poly pattern rules, isolating blocks
- Local boundary cell: between core devices
- Spacing cells, just for uniform placement and density rules

Ah! We see in the image below, the core NMOS cell is `nf=2`.

![Alt text](img/layout_rows.png)

Other devices
– Define pin(or port) to be compatible with routing grid
– Metal-Oxide-Metal (MOM) cap
– Thick gate (IO) TR and diode for BGR generator

![Alt text](img/layout_other.png)

# 28nm spice models heirarchy

In 28nm, toplevel.scs -> crn28ull_1d8_elk_v1d8_2p2_shrink0d9_embedded_usage.scs (.LIB TTMacro_MOS_MOSCAP) -> cln28ull_1d8_elk_v1d8_3.scs (TT_MOS_CAP)


# FD SOI, Finfet, and Bulk:

A better name for FD-SOI is 'Ultra Thin Body' or UTB-SOI

When you compare two basically different technologies like FinFET and FDSOI it’s not a case that one is intrinsically better than the other for all applications, they both have pros and cons which make them the best choice for different applications.

FinFETs have more drive current per unit cell area, higher capacitance, steeper subthreshold slope, no Vth tuning. FDSOI has lower drive current but also lower capacitance, lower power/current density, and the ability to tune Vth up or down using back biasing.

So in more heavily loaded circuits FinFETs clock faster, have lower leakage but also higher dynamic power and power/current density. In more lightly loaded circuits — especially if parallelisation can be used — FDSOI has lower dynamic (and total) power and can run at lower voltages with higher power efficiency than FinFETs.

For circuits with a lot of “dark silicon” or low average activity where gate density and maximum clock rate are important (e.g. mobile AP, PC CPU) FinFET is the winner. For power-critical parallel circuits with high activity running all the time at high temperature (e.g. 100G networking devices) FDSOI wins because power efficiency per gate transition is better and power/current density is lower, so fewer problems with electromigration and hotspots than FinFET. FDSOI chip size may be a bit larger but this is overridden by lower power consumption. FDSOI can also win where minimum power per operation is crucial and maximum clock rate is less important (e.g. IoT).

Both are a lot better than bulk CMOS, but in different ways. Each is better than the other in some applications and worse in others.

Fins a fabricated on a fixed grid, on the order of 30nm, while gates are at a 50nm pitch. A Gate crossing multipel fins creates a wider transistor. Multiple gates neighboring gates will create fingers, which also 

# Layout key insights


What I'm building: ADC, PLL, Memory, digital logic, Serdes, serial driver in 28nm

Key insights:

28nm really restricts your layout, so that devices fall on a regular grid

routing is best done in unit tracks

column parrallel ROICs are an ideal candidate for this type of layout generation

Pcells aren't DRC clean, and need lots of additions (end caps, cut?)

Static (handmade) templates can encapsulate most of the DRC rules and process specific stuff. These templates can be extremely quantized to a unit area, in small process nodes. And if they're made dynamic, you pay a bit more in the way of layout complexity/irregularity but recieve better layout density and application specific customizations.


# 28nm Forum (Nov 30th)

Marco Andorono, CERN:
- CERN IP blocks plus a distributed list of different institution shared IP designs
- analog IP, digital soft IP (software like, rtl code, verified), hard digital IP (output of flow: layouts, good for highly optimized floor plan)
- after 3-way NDA, and EDA tool sharing (one per IP) and CERN design sharing letter (one per institute)
- IP block datasheet template
- IP block design doesn't stop with layout, it need documentation and files for using in digital-on-top flow (LIB, abstract)
- Abstract generation for analog block will haver a user guide soon
- Lib file has timing arcs, power, etc. Liberate AMS generator can automate this.
- OD/PO dummy fill should be done at block level, there is a script for this
- Latch up violations should be avoided using guard rings
- Triple guard rings are recommended for blocks, and between power domains. Using LVS logical boundary

Frank Bandi, CERN:
- Analog blocks: Bandgap, 8bit ADC, SLVS TX/RX, TID monitoring, Radhard ESD and CMOS IO pads (from Sofics)
- Integrated DC-DC converters, LDOs, shunt LDOs
- 14b Sigma delta ADC, Fin 20kHz, for monitoring
- Fast and slow rail-to-rail

Adam Klekotko and Stefan Biereigel, KU Leuven/CERN:
- DART28 25.6 Gbps per lane, NRZ, four lanes.
- High Speed Transmitter macro block:
	- 12.8 Ghz all digital PLL w/ LC oscillator
	- TMR high-speed serializer (20:1): uses (True single phase clocking) TSPC logic dynamic circuits, storing data in node capacitance. Faster than static circuits.
	- pre-emphasis
	- Dual-use driver (DUDE) for silicon photonics ring modulator or 100ohm differential transmission line
- Clock coming from PLL needed duty-cycle correct, and balancing of even-odd jitter (EOJ)
- Single lane operation, 120mW per channel. Driver > Serializer > All other blocks
- HST block has RTL (divider and low speed serializer) and Full custom (high-speed serlizer and output) part
- Liberate AMS only captures interfaces timing, long run time,
- Mixed signal simulation takes a long time to run
- STA flow is best! Load OA schematic/layout into innovus, each block and heirachy is characterized with .lib, and then in innovus you can simulate
- 



Redistribution layers (RDLs) are the copper metal interconnects that electrically connect one part of the semiconductor package to another. RDLs are measured by line and space, which refer to the width and pitch of a metal trace. Higher-end RDLs may be at 2μm line/space and smaller.

The RDL is a layer of wiring metal interconnects that redistribute the I/O access to different parts of the chip and makes it easier to add microbumps to a die.
