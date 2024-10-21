import pandas as pd

# Define the dictionaries
dict1 = {
    'Org': 'Direct Electron',
    'System': 'DE-20',
    'W Count': 5120,
    'H Count': 3840,
    'Pixel Pitch': 6.4,
    'Frame Rate': 25
}

dict2 = {
    'System': 'Celeritas XS',
    'Org': 'Direct Electron',
    'W Count': 1024,
    'H Count': 1024,
    'Pixel Pitch': 15.0,
    'Pixel Rate': 2202009600
}

# Create a list of dictionaries
data = [dict1, dict2]

# Create the DataFrame
df = pd.DataFrame(data)

# Display the DataFrame
print(df)