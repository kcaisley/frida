import numpy as np
from spicelib import Trace, RawWrite
from spicelib import RawRead
import matplotlib
matplotlib.use('Qt5Agg')
import matplotlib.pyplot as plt
from sys import getsizeof


rawfile = RawWrite()



tx = Trace('time', np.arange(0.0, 3e-3, 997E-11))
vy = Trace('N001', np.sin(2 * np.pi * tx.data * 10000))
vz = Trace('N002', np.cos(2 * np.pi * tx.data * 9970))

rawfile.add_trace(tx)
rawfile.add_trace(vy)
rawfile.add_trace(vz)

print(getsizeof(tx.data))

rawfile.save("test_sincos.raw")

raw = RawRead("test_sincos.raw")        # Read the RAW file contents from disk

print(raw.get_trace_names())            # Get and print a list of all the traces
print(raw.get_raw_property())           # Print all the properties found in the Header section

vin = raw.get_trace('N001')            # Get the trace data
vout = raw.get_trace('N002')          # Get the second trace

steps = raw.get_steps()                 # Get list of step numbers ([0,1,2]) for sweeped simulations
                                        # Returns [0] if there is just 1 step

plt.figure()                            # Create the canvas for plotting


plt.grid(True)

# plt.xlim([0.9e-3, 1.2e-3])              # Limit the X axis to just a subrange

xdata = raw.get_axis()                  # Get the X-axis data (time)

ydata = vin.get_wave()                  # Get all the values for the 'vin' trace
plt.plot(xdata, ydata)                  # Do an X/Y plot on first subplot

ydata = vout.get_wave()                 # Get all the values for the 'vout' trace
plt.plot(xdata, ydata)                  # Do an X/Y plot on first subplot as well

for step in steps:                      # On the second plot, print all the STEPS of Vout
    ydata = vout.get_wave(step)         # Retrieve the values for this step
    xdata = raw.get_axis(step)          # Retrieve the time vector
    plt.plot(xdata, ydata)              # Do X/Y plot on second subplot

plt.show()           