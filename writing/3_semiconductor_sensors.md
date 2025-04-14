# Fabrication

## Wafers

The base wafers are the starting point of any fabrication process.

It seems the three choices for wafers are

Czochralski wafers (5 kΩ cm – 7 kΩ cm)
Float-zone wafers (8 kΩ cm – 9 kΩ cm)
Epitaxial high-Z


Wafer resistivity is important for allowing depletion, which in turn is important to allow a field improving fast collection and to prevent recombination which creates signal loss.




# Deposition
The start of a deposition process is nucleation, followed by growth. 

Deposition comes in two primary mode flavors, chemical or physical.

Chemical deposition is characterized by the phase (liquid/gas) of the precursor.
Plating and spin-coating use a liquid phase
Chemical vapor deposition (CVD) uses gas-phase precursor.
Atomic layer deposition (ALD) and it's sister molecular layer deposition (MLD) use a gaseos precursor (they are considered a subset of CVD)

W
Physical vapor deposition [(PVD)](https://en.wikipedia.org/wiki/Physical_vapor_deposition) uses mechanical, electromechanical or thermodynamic means to produce a thin film of soli
    [evaporative deposition](https://en.wikipedia.org/wiki/Evaporation_(deposition)), a type of PVD

Melecular beam epitaxy, atomic layer deposition, and molecular layer deposition allow for single layers of atoms at a time



ion implantation follows the same bethe bloch fomula, but because you want to particle to fulls stop, you get this concept of 'bragg peaks' where the particle deposits more energy as it decelerates. This means to get a constant doping over a wide depth, you need to overlap multiple bragg peaks.

molecular beam epitaxy



- Enclosed layout transistors (ELTs) used to be needed as in rectangular layout the parasitic FET on side of channel is significant, as LOCOS was poorly defined
- But now in more modern processes, the use of shallow trench isolation (STI) creates a more cleanly defined edge of the transistor which minimizes the existance of a parasitic FET.




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

This studied the electric, thermal, and quantum effects of carriers and electromagnetic fields in lattices of crystal solids. It extends beyond semiconductors, of course, as both insulators and conductors exist here too, so the label is a bit of a misnomer.

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

Devices list:
PN junction
PIN
JFEt
MESFET
DEPFET/DEPMOS

BJT: difference of input impdeance, carrier dominance, and thermal noise (gen/recomb)


Fab

Strategies to do lithography:
Traditional UV or EUV
Maskless? Electron beam?

Strategies to etch (subtract)
You can do wet (liquid) or dry (plasma) etching
Dry etching is better, as it won’t undercut a resist, i.e. it’s “anisotropic”

Strategies to make thin films/epitaxial layers (this can interact with a mask to control region)
Sputtering
CVD
Atomic layer depositor (previously atomic layer epitaxy)
Epitaxial growth

To implant:
Ion implantation

What is ?
Molecular beam epitaxy


Micro fabrication Processes techonologies (i.e. an entire fab line for something):
CMOS
Power FETs (GaN and SiC)
DRAM
CCD
Solar cells
Displays:
LCD
LCD+small LED backlight
LED display (uses PN junctions)
OLED (photo-luminescent molecules, not PN)

MEMS

Glass layer and filters
Optical waveguides on glass substrate








# Effect and properties

Hetero junctions
tunnel diode/back diodes
different bandgaps

PIN 

photodiodes (any pn juction is potentially a photodiode)

Zener breakdown vs avalance breakdown


### Surfaces and and interfaces
semiconductor-metal contacts
Interface states
Ultrahigh vacuum technology
Surface analysis: Electron, photon and ion spectroscopy overviewPhotoemission spectroscopy
Particle-solid scattering: electrons, Auger electron spectroscopy, & electron energy loss spectroscopy
Particle-solid scattering: ions, Rutherford backscattering spectrometry & secondary ion mass spectrometery
Electron diffraction
Scanned probe microscopy and spectroscopy
Optical spectroscopies: modulation, ellipsometry, Raman, surface photovoltage, cathodoluminescence
Electronic materials surfaces: growth, diffusion, etching, bonding, epitaxy
Adsorbates on semiconductors
Metals on semiconductors
Semiconductor heterojunctions

ohmic contacts

reduced/low dimensional structures (of particle momentum):
Three-dimensional (3D) structure or bulk structure: No quantization of the particle motion occurs, i.e., the particle is free.
Two-dimensional (2D) structure or quantum well: Quantization of the particle motion occurs in one direction, while the particle is free to move in the other two directions.
One-dimensional (1D) structure or quantum wire: Quantization occurs in two directions, leading to free movement along only one direction.
Zero-dimensional (0D) structure or quantum dot (sometimes called "quantum box"): Quantization occurs in all three directions.

### Lab fabrication:
epitaxial growth
XRD + PL characterization
reactive ion etching
metal contact deposition (evaporation and sputter deposition)
thermal annealing
dielectrics and passivation
ion implatation


### Fundamentals
bandgaps
tunneling, floating gates
hot carriers
heterojunctions

### adv devices
gated diode, high-k dieletrics
amphoteric traps
Generation-recombination theory, equilibrium, non-equilibrium, steady-state and non-steady-state, conductance, surface recombination boundary conditions
CMOS transistors (bulk, SOI, mobility, transconductance, subthreshold operation, SPICE modeling, short-channel and narrow-width effects, surface and buried channel devices, propagation delay, ion-sensitive FETs (ISFETs), hot carrier injection
charge pumping, interface, and dielectric traps




/eda/cadence
/eda/synopsys/installs/tools
/eda/synopsys/installs/2022-23/
/eda/synopsys/installs/2023-24/
    /mentor


ICVWB_2022.12   
PWA_2022.12
RAPHAEL_2022.12
RAPHAEL-FX_2022.12
SEN-PROC-EXP_2022.12
SENTAURUS_2022.12
SENTAURUS-PCM_2022.09
SILICON-WB_2022.12
SLITHO_2022.12
TAURUS-MD_2022.12
TAURUS-TS4_2022.12

GENSYS_2023.12
ICVWB_2023.09-SP1
RAPHAEL-FX_2023.12
SEN-PROC-EXP_2023.12
SENTAURUS_2023.12
SILICON-WB_2023.09-SP1
SLITHO_2023.12
S-METRO_2023.12


sentarus process userguide
icwb.create.mask

in-sprocess, you can:
define contact, which is a logical 


in sdevice, apply voltage to contact, with voltage, and source resistance

collection electrodes, set then to be 'ground' 

for floating nodes, you don't specify a contact, because you don't want to have to enforce a 

two steps for charge collection:
quasistationary, to reach starting condition from zero, w/ numerically stable solution

transient


/szhang/3dTCAD/TJ2023/
importing GDS, from next time, to produce .mac file.

What is the language which is used to control sprocess?


