import matplotlib.pyplot as plt
import pandas as pd
from scipy import stats
import os
import argparse
os.environ["XDG_SESSION_TYPE"] = "xcb" # For silencing "Warning: Ignoring XDG_SESSION_TYPE=wayland on Gnome"

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

if os.path.exists(f'./spice_{radix}radix_{convs}bit_{time}u.pkl'):
    print("Pickled precleaned cache file found, loading it...")
    df = pd.read_pickle(f'./spice_{radix}radix_{convs}bit_{time}u.pkl')
else:
    print("Loading raw CSV...")
    # Load the CSV data into a pandas DataFrame, skip first row as it just has text e.g. "Transient analysis: temperature=25.0"
    df = pd.read_csv(rawfile, skiprows=1)
    # df = pd.read_csv(f'{radix}radix_{convs}bit_{duration}u.csv', skiprows=1)
    # df = pd.read_csv('sim/results/SB_saradc8_radix1p80/SB_saradc8_radix1p80.csv', skiprows=1)

    print("Cleaning dataframe...")
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

    print("Writing dataframe to `spice_####radix_####bit_###u.pkl` pickle cache file...")
    df.to_pickle(f'./spice_{radix}radix_{convs}bit_{time}u.pkl')

print("Computing new columns...")
# Find total input, drop unneeded values
df['Vin'] = df['inp'] - df['inn']
df['Vin_norm'] = df['Vin'] / vdd

# Drop unused columns
df = df.drop(columns='inp')
df = df.drop(columns='inn')

# Digitize the data bit lines to that they are either 1 or 0
df['comz_p'] = df.loc[:,'comz_p'].apply(lambda x: 1 if x > (vdd/2) else (0 if x <= (vdd/2) else x))
df['comz_n'] = df.loc[:,'comz_n'].apply(lambda x: 1 if x > (vdd/2) else (0 if x <= (vdd/2) else x))
# df['comp'] = df['comz_p'] - df['comz_n'] # FIX ME: Why isn't this needed?

# Digitize the data bit lines to that they are either 1 or 0
for col in [f'data<{i}>' for i in range(convs)]:  # Create list ['data<0>',..., 'data<7>']
    df[col] = df.loc[:,col].apply(lambda x: 1 if x > (vdd/2) else (0 if x <= (vdd/2) else x))

# Define the binary weights for data<0> to data<7>, where data<0> is the 2nd lowest LSB, and data<7> is MSB
weights = [radix**i for i in range(convs)]
print(f'weights = {weights}')
print(f'sum of weights = {sum(weights)}')
# Calculate the 'Dout' column
# The 'Dout' column contains the weighted sum of data<0> to data<7>
# enumerate returns the index, value of the sequence: [https://docs.python.org/3.9/library/functions.html#enumerate]
df['Dout'] = sum((2*df[f'data<{i}>']-1) * (weight) for i, weight in enumerate(weights))   # enumerate returns the
df['Dout'] += df['comz_n'] - 1 # we use negative comp output, because data outputs are tapped from N side

# Compute linear fit
dout_regression = stats.linregress(df['Vin'], df['Dout'])
df['Dout_linear'] = dout_regression.slope * df['Vin'] + dout_regression.intercept

# Compute error
df['Dout_error'] = df['Dout'] - df['Dout_linear']



# STRATEGY 1: Rounding to nearest integer
# Compute an inter rounded version of dout
df['Dout_rounded'] = df['Dout'].round()

# Compute code frequency of the rounded values
dout_rounded_histo = df['Dout_rounded'].value_counts(sort = False)

# dout_rounded_histo contains the count of values in each bin
total_values = dout_rounded_histo.sum()  # Total number of values across all bins
num_bins = len(dout_rounded_histo)  # Number of bins
average_per_bin = total_values / num_bins  # Average number of values per bin

dout_averaged = (dout_rounded_histo.values) / average_per_bin - 1

rms_dnl = dout_averaged.std()

print(f'RMS DNL: {rms_dnl}')

# Compute a linear fit of dout
dout_rounded_regression = stats.linregress(df['Vin'], df['Dout_rounded'])
df['Dout_rounded_linear'] = dout_rounded_regression.slope * df['Vin'] + dout_rounded_regression.intercept

# Compute error
df['Dout_rounded_error'] = df['Dout_rounded'] - df['Dout_rounded_linear']



# Strategy 2: Mapping to lower resolution set of bins (in this case 8)
# Compute a 'binned' version, which maps the 9 nonbinary bin across 8 uniform binary bin
# In a 9bit config, with 1.8 radix, the range is -136.4995072 to +136.4995072 (+ 1) = 274
# To map this onto a 8-bit range we can find the radio of the two ranges, where 8bit range = 256
# ratio of 274 / 256 is ~ 1.75
df['Dout_mapped'] = (df['Dout'] / 1.075).round() * 1.075

# Compute code frequency of the mapped values
dout_mapped_histo = df['Dout_mapped'].value_counts(sort = False)

# Compute linear fit
dout_mapped_regression = stats.linregress(df['Vin'], df['Dout_mapped'])
df['Dout_mapped_linear'] = dout_mapped_regression.slope * df['Vin'] + dout_mapped_regression.intercept

# Compute error
df['Dout_mapped_error'] = df['Dout_mapped'] - df['Dout_mapped_linear']



# Strategy 3: what about some normalization?
# df['Dout_norm'] = df['Dout'] / (radix**convs)

print("Plotting...")
# plt.style.use('dark_background')

# ax# instances are an xy pair of axes, here we have one per sub-plot
fig, ax = plt.subplots(ncols = 2, nrows = 2, gridspec_kw={'width_ratios': [1, 2]})

ax = ax.flatten()

# Plot histogram showing code density
ax[0].barh(dout_rounded_histo.index, dout_averaged, label='Dout rounded DNL (stdev = %d)' % rms_dnl)
# ax[0].barh(dout_mapped_histo.index, dout_mapped_histo.values, label='Dout mapped')
ax[0].set_ylabel('Dout')
ax[0].set_xlabel('Code Count')
ax[0].set_title(f'Dout Code Density (radix = {radix}, conversions = {convs}, samples = {time*10})')
ax[0].legend()
ax[0].grid(True)

# Plot the line for Dout vs Vin
ax[1].plot(df['Vin'], df['Dout_rounded'], label='Dout rounded')
ax[1].plot(df['Vin'], df['Dout_mapped'], label='Dout mapped')
ax[1].plot(df['Vin'], df['Dout'], label='Dout')
ax[1].sharey(ax[0])
# ax[1].plot(df['Vin'], df['Dout_linear'], label='Dout_rounded linear fit')
# ax[1].plot(df['Vin'], df['Dout_mapped_linear'], label='Dout_mapped linear fit')
ax[1].set_xlabel('Vin')
ax[1].set_ylabel('Dout')
ax[1].set_title(f'Dout vs Vin (radix = {radix}, conversions = {convs}, samples = {time*10})')
ax[1].legend()
ax[1].grid(True)

ax[2].axis('off')

# Plot the line for Dout error vs Vin
ax[3].plot(df['Vin'], df['Dout_rounded_error'], label='Dout rounded error')
ax[3].plot(df['Vin'], df['Dout_mapped_error'], label='Dout mapped error')
ax[3].plot(df['Vin'], df['Dout_error'], label='Dout error')
ax[3].sharex(ax[1])
ax[3].set_xlabel('Vin')
ax[3].set_ylabel('Error')
ax[3].set_title(f'Dout Error vs Vin (radix = {radix}, conversions = {convs}, samples = {time*10})')
ax[3].legend()
ax[3].grid(True)

plt.show()

# codes which show non-monotonic behavior
# [1.0, 1.8, 3.24, 5.832000000000001, 10.4976, 18.895680000000002, 34.012224, 61.22200320000001]
# comp_n  data<0>  data<1>  data<2>  data<3>  data<4>  data<5>  data<6>  data<7>       -Vin       Dout
#      0        1        1        0        0        1        0        1        1    0.48723  79.564147
#      1        1        1        0        0        1        0        1        1    0.48990  80.564147
#      0        0        0        1        0        1        0        1        1    0.48993  80.444147
#      1        0        0        1        0        1        0        1        1    0.49257  81.444147
#
#


# Debug prints
# print(df.to_string())
# print(f'histo data = {histo_dnl.to_string()}')
