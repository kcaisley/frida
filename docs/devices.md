bjt  bipolar because there are teo currenet.  Want to make tge base as thin as possible, as if it’s not fully depleted, we want to avoid recombination so that IC ~ IE


fet. Mosfet or jfet. Unipolar.


all equations from circuits classes

bjt vs mosfet

majority carriers, wi thermall my insensitive (thermal generation and recombination are not so perfect, less noise)

high input impedance, low power

Smaller, simpler fabrication


Fet
JFET and MSFET, enhancement and depletion mode


Devices
BJT, FETS, photodiodes, caps, resistors, inductors

# Radiation

TID
Short Channel Effects  (RISCE)
Narrow Channel Effect  (RINCE)

SEE - Single Event Upsets


# List of junctions

This studied the electric, thermal, and quantum effects of carriers and electromagnetic fields in lattices of crystall solids. It extends beyond semiconductors, of course, as both insulators and conductors exist here too, so the label is a bit of a misnomer.

The scope is wave functions to junctions. At the top end, this is:

* mos  metal isn’t usually used thoPolysilicon gates can bear high temperatures while metal gates can melt over that same temperature, so we can use the polysilicon gates as a self-alignment gate process during the fabrication of CMOS. There’s no current flow, but the electric field can still modulate the bend across the oxide. Flat band, accumulation (e in n type), depletion (space charge), inversion (holes in N) states 

* pn

* ms junction. schottky barrier vs ohmic state. called a ohmic contact if metal work function is less than SC work function
* pin (or ptype-oxide-ntype)

One important link, after studying devices in a vacuum, is to study them under radiation from incident particles, i.e. 

$$
-\frac{d^2\phi}{dx^2}=\frac{dE}{dx}=\frac{\rho}{\epsilon}
$$

### Device fabrication possible steps:

Dy processing/microstructuring, ceramic layer deposition, reactive ion etching, metrology, wet processing (organic-organic etc, maskless lithography, dicing (by wafer size), GEM foil production, backside processing, wafer-wafer bonding, through silicon vias, bump-bonding


## FD SOI, Finfet, and Bulk:

A better name for FD-SOI is 'Ultra Thin Body' or UTB-SOI

When you compare two basically different technologies like FinFET and FDSOI it’s not a case that one is intrinsically better than the other for all applications, they both have pros and cons which make them the best choice for different applications.

FinFETs have more drive current per unit cell area, higher capacitance, steeper subthreshold slope, no Vth tuning. FDSOI has lower drive current but also lower capacitance, lower power/current density, and the ability to tune Vth up or down using back biasing.

So in more heavily loaded circuits FinFETs clock faster, have lower leakage but also higher dynamic power and power/current density. In more lightly loaded circuits — especially if parallelisation can be used — FDSOI has lower dynamic (and total) power and can run at lower voltages with higher power efficiency than FinFETs.

For circuits with a lot of “dark silicon” or low average activity where gate density and maximum clock rate are important (e.g. mobile AP, PC CPU) FinFET is the winner. For power-critical parallel circuits with high activity running all the time at high temperature (e.g. 100G networking devices) FDSOI wins because power efficiency per gate transition is better and power/current density is lower, so fewer problems with electromigration and hotspots than FinFET. FDSOI chip size may be a bit larger but this is overridden by lower power consumption. FDSOI can also win where minimum power per operation is crucial and maximum clock rate is less important (e.g. IoT).

Both are a lot better than bulk CMOS, but in different ways. Each is better than the other in some applications and worse in others.