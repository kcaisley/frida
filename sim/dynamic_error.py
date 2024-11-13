# in a time step simulator, when an output is calculated from input, essentially every block needs to have a 'unit delay' associated with it
# the trick is to make sure that the step is so small, relative to the dynamics of the system, that the regadless of if the block has 'phase delay' or 'prop delay' or 'dynamics'
# we won't notice that fact that it actally always takes one time step to calculate the output from the input.
# This means that every block's output at time T is a function of all inputs at time 0:T, where we an impulse reponse to model the pulse, regardless of 

# This means we need to convert all signals to inpulse response, even gaussian noise.
# But we can start from the differential equation, state space, or frequency/laplace LTI model of the system.
# then we also need a graph of connections, and the order in which to 'update' each output as a funtion of it's inputs.
# 

import numpy as np
from scipy import signal, stats
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use("TkAgg")  # or "Qt5Agg"

# Define waveform parameters
frequency = 100e6  # 100 MHz
amplitude = 100e-3  # 100 mV peak
time_step = 1e-12  # 1 ps time step
duration = 50e-9  # 50 ns total duration

# Generate time array and triangle waveform
time_array = np.arange(0, duration, time_step)
triangle_waveform = amplitude * signal.sawtooth(2 * np.pi * frequency * time_array, 0.5)

# Define Gaussian noise with mean=0 and std deviation=1 mV
noise_std_dev = 1e-3  # 1 mV
noise = stats.norm.rvs(scale=noise_std_dev, size=time_array.size)

# Convolve triangle waveform with Gaussian noise (this simulates adding noise to the signal)
noisy_waveform = triangle_waveform + noise

# Plot the waveforms
plt.figure(figsize=(12, 6))

# Plot original triangle waveform
plt.subplot(2, 1, 1)
plt.plot(time_array * 1e9, triangle_waveform, label="Original Triangle Waveform", color='blue')
plt.xlabel("Time (ns)")
plt.ylabel("Voltage (V)")
plt.title("Triangle Waveform at 100 MHz, Amplitude ±100 mV")
plt.grid(True)

# Plot noisy waveform
plt.subplot(2, 1, 2)
plt.plot(time_array * 1e9, noisy_waveform, label="Noisy Waveform", color='orange')
plt.xlabel("Time (ns)")
plt.ylabel("Voltage (V)")
plt.title("Triangle Waveform with Gaussian Noise (10 mV std deviation)")
plt.grid(True)

# Show plot
plt.tight_layout()
plt.show()

