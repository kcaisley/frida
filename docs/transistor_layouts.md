In particular, minimum size devices should be avoided; device widths should be kept larger than 200 nm and length to 40 nm or more. Particularly long devices lengths of 1 μm or more should also be avoided.

So it looks like for things like oscillators, I could get device widths up to 10-20 micrometers, and lengths from 40-200nm.

In finfets, increasing the number of fin is the same thing as making the device wider per finger. So fins and fingers determines total width.

In most designs, it seems they have fixed length, and finger width, and all they tune in the number of fingers, i.e. total width. 

I think I may be able to get away with a L=50n, but I'm not sure what I should choose for my unit finger width? I'm considering 100n, 200n, and 250n and my finger width.

Hakhamaneshi's thesis has some tidbits.


### from laygo2 notes

- All placement should rely on the PR boundary

- X axis: base on poly pitch

- Y axis: multiple of fin grid (in mine, this is finger width). This is equal to the height of the unit transistor.

![Alt text](images/layout_grid.png)

Quantized routing grid and unit transistor:

- M1/M2 are used to connect transistors (generally non-uniform)
- TR (transistor) sizing: quantized to unit transistor (4 fins suggested)

![Alt text](images/layout_cells.png)

Transistors are aranged in the following manner:

- Core cell: active device, taps above/below, dummy fill on ends
- Row boundary cell: poly pattern rules, isolating blocks
- Local boundary cell: between core devices
- Spacing cells, just for uniform placement and density rules

Ah! We see in the image below, the core NMOS cell is `nf=2`.

![Alt text](images/layout_rows.png)

Other devices
– Define pin(or port) to be compatible with routing grid
– Metal-Oxide-Metal (MOM) cap
– Thick gate (IO) TR and diode for BGR generator

![Alt text](images/layout_other.png)


# FD SOI, Finfet, and Bulk:

A better name for FD-SOI is 'Ultra Thin Body' or UTB-SOI

When you compare two basically different technologies like FinFET and FDSOI it’s not a case that one is intrinsically better than the other for all applications, they both have pros and cons which make them the best choice for different applications.

FinFETs have more drive current per unit cell area, higher capacitance, steeper subthreshold slope, no Vth tuning. FDSOI has lower drive current but also lower capacitance, lower power/current density, and the ability to tune Vth up or down using back biasing.

So in more heavily loaded circuits FinFETs clock faster, have lower leakage but also higher dynamic power and power/current density. In more lightly loaded circuits — especially if parallelisation can be used — FDSOI has lower dynamic (and total) power and can run at lower voltages with higher power efficiency than FinFETs.

For circuits with a lot of “dark silicon” or low average activity where gate density and maximum clock rate are important (e.g. mobile AP, PC CPU) FinFET is the winner. For power-critical parallel circuits with high activity running all the time at high temperature (e.g. 100G networking devices) FDSOI wins because power efficiency per gate transition is better and power/current density is lower, so fewer problems with electromigration and hotspots than FinFET. FDSOI chip size may be a bit larger but this is overridden by lower power consumption. FDSOI can also win where minimum power per operation is crucial and maximum clock rate is less important (e.g. IoT).

Both are a lot better than bulk CMOS, but in different ways. Each is better than the other in some applications and worse in others.

Fins a fabricated on a fixed grid, on the order of 30nm, while gates are at a 50nm pitch. A Gate crossing multipel fins creates a wider transistor. Multiple gates neighboring gates will create fingers, which also 

## RDLs

Redistribution layers (RDLs) are the copper metal interconnects that electrically connect one part of the semiconductor package to another. RDLs are measured by line and space, which refer to the width and pitch of a metal trace. Higher-end RDLs may be at 2μm line/space and smaller.

The RDL is a layer of wiring metal interconnects that redistribute the I/O access to different parts of the chip and makes it easier to add microbumps to a die.
