# from sar_adc_sim import *
import matplotlib.pyplot as plt
import pandas as pd
import os
os.environ["XDG_SESSION_TYPE"] = "xcb" # this silences the display Wayland error

radix = 1.8     #
convs = 8       # how many conversion registers are set each
duration = 1100  # in microseconds
vhigh = 1.2  # voltages for low and high logic levels

# Load the CSV data into a pandas DataFrame, skip first row as it just has text e.g. "Transient analysis: temperature=25.0"
df = pd.read_csv(f'{radix}radix_{convs}bit_{duration}u.csv', skiprows=1)

# Remove unwanted parts from column names: V(....)
df.columns = df.columns.str.replace(r'V\(|\)', '', regex=True)

# We have since sim time step is 0.1ns, and ADC runs on 10 MHz clock (100ns), we have a valid code each 1000 rows (with some offset, 250)
df = df[(df.index % 1000) == 250 ]
df = df.reset_index(drop=True)
sample_count = duration * 10 # this should equand we have a ADC conversion

# The voltages aren't available until the second
for col in ['Time','reference', 'signal', 'cnode3p', 'cnode3n']:
    df.loc[:, col] = df.loc[:, col].shift(1)

# Remove first two rows, as it is from the power on cycle
df = df.drop(index=[0, 1]).reset_index(drop=True)

# Remove every row past 580, as the ADC stops acting linear due to switch
# df = df.iloc[:7000].reset_index(drop=True)

# Delete the clock columns, as we don't need them
df = df.drop(columns='syncp')
df = df.drop(columns='clockp')

# Find total input, drop unneeded values
df['Vin'] = df['reference'] - df['signal']
df = df.drop(columns='signal')
df = df.drop(columns='reference')

# Find real input, drop unneeded values
df['Vsamp'] = df['cnode3n'] - df['cnode3p']
# df = df.drop(columns='cnode3p')
# df = df.drop(columns='cnode3n')

# Digitize the data bit lines to that they are either 1 or 0
for col in [f'data<{i}>' for i in range(convs)]:  # Create list ['data<0>',..., 'data<7>']
    df[col] = df.loc[:,col].apply(lambda x: 1 if x > 1.1 else (0 if x < 0.1 else x))

# Define the binary weights for data<0> to data<7>, where data<0> is the LSB, and data<7> is MSB
weights = [radix**i for i in reversed(range(convs))]
print(weights)

# Calculate the 'Dout' column
# The 'Dout' column contains the weighted sum of data<0> to data<7>
df['Dout'] = sum(df[f'data<{7-i}>'] * weight for i, weight in enumerate(weights))

# Plot the line for Vin vs Dout
plt.plot(df['Vin'], df['Dout'], label='Dout vs Vin', color='b')

# Adding labels and title
plt.xlabel('Vin')
plt.ylabel('Dout')
plt.title(f'Dout vs Vin (radix = {radix}, conversions = {convs}, samples = {duration*10})')

# Show the plot
plt.legend()
plt.grid(True)
plt.show()

# Slice the DataFrame to exclude the first and last 100 rows

# Plot the histogram
plt.figure(figsize=(10, 6))

histbins = list(range(0, 256))
plt.hist(df['Dout'], bins=histbins, color='g', edgecolor='black')

# Adding labels and title
plt.xlabel('Re-Analog')
plt.ylabel('Code Count')
plt.title(f'Re-Analog Code Density (radix = {radix}, conversions = {convs}, samples = {duration*10})')

# Show the plot
plt.grid(True)
plt.show()
