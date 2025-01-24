# from sar_adc_sim import *
import matplotlib.pyplot as plt
import pandas as pd
import os
import argparse
os.environ["XDG_SESSION_TYPE"] = "xcb" # this silences the display Wayland error

# Create the parser
parser = argparse.ArgumentParser(description='Analysis script for SAR ADC data')

parser.add_argument('rawfile', help='Filepath of .csv rawfile from T-spice output')
parser.add_argument('--radix', type=float, default=2.0, help='Radix for the calculation (default: 2.0)')
parser.add_argument('--convs', type=int, default=8, help='Number of conversion registers (default: 8)')
parser.add_argument('--time', type=int, default=2000, help='Duration in microseconds (default: 2000)')
parser.add_argument('--vdd', type=int, default=1.2, help='Supply voltages in volts (default: 1.2)')

# Parse arguments
args = parser.parse_args()

# Use the arguments
rawfile = args.rawfile
radix = args.radix
convs = args.convs
time = args.time
vdd = args.vdd

# Load the CSV data into a pandas DataFrame, skip first row as it just has text e.g. "Transient analysis: temperature=25.0"
df = pd.read_csv(rawfile, skiprows=1)
# df = pd.read_csv(f'{radix}radix_{convs}bit_{duration}u.csv', skiprows=1)
# df = pd.read_csv('sim/results/SB_saradc8_radix1p80/SB_saradc8_radix1p80.csv', skiprows=1)

# Remove unwanted text from column names: V(....)
df.columns = df.columns.str.replace(r'V\(|\)', '', regex=True)
# Delete the clock columns, as they aren't sampled at right point anyways, and aren't used
df = df.drop(columns='syncp')
df = df.drop(columns='clockp')
# Drop the sampled voltage columns, as they aren't sampled at right point anyways (would be +25ns, so offset 250), and aren't used
df = df.drop(columns='cnode3p')
df = df.drop(columns='cnode3n')

# Since sim time step 0.1ns, and ADC runs on 10 MHz clock (100ns), we have a valid code each 1000 rows
# The final comz_p and comz_n bits are valid 4.5-8.5 ns into the 100.0 ns period
# NOTE: This isn't the correct offset however, for plates
df = df[(df.index % 1000) == 70 ]
df = df.reset_index(drop=True)
sample_count = time * 10 # Work out the total of conversions representated in the data set

# Since measurement data out is derived to the voltage 100ns before, we can shift the voltages down by one to correlate the two
for col in ['Time','inn', 'inp']:
    df.loc[:, col] = df.loc[:, col].shift(1)

# Remove first two rows, as supply voltages aren't ramped up yet so measurements are meaningless
df = df.drop(index=[0, 1]).reset_index(drop=True)

# Remove every row past 580, as the ADC stops acting linear due to switch
# df = df.iloc[:7000].reset_index(drop=True)

# Find total input, drop unneeded values
df['Vin'] = df['inp'] - df['inn']
df['Vin_norm'] = df['Vin'] / vdd
# df = df.drop(columns='inp')
# df = df.drop(columns='inn')

# Digitize the data bit lines to that they are either 1 or 0
df['comz_p'] = df.loc[:,'comz_p'].apply(lambda x: 1 if x > (vdd/2) else (0 if x <= (vdd/2) else x))
df['comz_n'] = df.loc[:,'comz_n'].apply(lambda x: 1 if x > (vdd/2) else (0 if x <= (vdd/2) else x))
# df['comp'] = df['comz_p'] - df['comz_n'] # FIX ME: Why isn't this needed?

# Digitize the data bit lines to that they are either 1 or 0
for col in [f'data<{i}>' for i in range(convs)]:  # Create list ['data<0>',..., 'data<7>']
    df[col] = df.loc[:,col].apply(lambda x: 1 if x > (vdd/2) else (0 if x <= (vdd/2) else x))

# df = df.drop(columns='comz_p')
# df = df.drop(columns='comz_n')
# print(df)
#


# Define the binary weights for data<0> to data<7>, where data<0> is the 2nd lowest LSB, and data<7> is MSB
weights = [radix**i for i in range(convs)]
print(weights)
# Calculate the 'Dout' column
# The 'Dout' column contains the weighted sum of data<0> to data<7>
# enumerate returns the index, value of the sequence: [https://docs.python.org/3.9/library/functions.html#enumerate]
df['Dout'] = sum((2*df[f'data<{i}>']-1) * (weight) for i, weight in enumerate(weights))   # enumerate returns the
df['Dout'] += df['comz_n'] - 1 # FIX ME: Use this comz_p values was wrong... but why?
df['Dout_norm'] = df['Dout'] / (radix**convs)


# ax# instances are an xy pair of axes, here we have one per sub-plot
# fig, (ax0, ax1) = plt.subplots(nrows=2, ncols=1)
fig, (ax0) = plt.subplots(nrows=1, ncols=1)

# Plot the line for Vin vs Dout
ax0.plot(df['Vin_norm'], df['Dout_norm'], label='Dout vs Vin', color='b')
ax0.set_xlabel('Vin_norm')
ax0.set_ylabel('Dout_norm')
ax0.set_title(f'Dout_norm vs Vin_norm (radix = {radix}, conversions = {convs}, samples = {time*10})')
ax0.legend()
ax0.grid(True)

# plot histogram showing code density

# ax1.set_xlabel('Re-Analog')
# ax1.set_ylabel('Code Count')
# ax1.set_title(f'Re-Analog Code Density (radix = {radix}, conversions = {convs}, samples = {time*10})')
# ax1.grid(True)

plt.show()
