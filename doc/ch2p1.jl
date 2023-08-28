using Plots
W = 50e-6
L = 0.5e-6
Vds = 3
Vgs = range(start=0, stop=3, length=100)

Vth = 0.7
μnCox = 50e-6 # amps per volts squared


# helpful to remember that for tox ≈ 20 A, Cox ≈ 17.25 fF/μm^2
# 20 Angstrom is 2nm
# our device is Tox=9nm, and so we get something 2/9 times smaller
# so Cox = (2/9) *17.25 = 3.8 fF/um^2
# 
#
# Cox is fF/um^2 and unCox is uA/V^2. this works as Farads are (A*s)/V.

# This equation is only valid for saturation region, which is okay as Vgs-Vth stays
# below Vds = 3V in this case. Also it's not valid for Vgs < Vth, as the transistor is off.
Ids = (μnCox*(W/L)) .* (Vgs .- Vth).^2

println(Vgs)
println(Ids)

plot(Vgs,Ids)
savefig("output.png")
