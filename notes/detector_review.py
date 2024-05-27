import numpy as np
import pandas as pd

# Create an empty DataFrame with predefined columns
# specs = pd.DataFrame(columns=['System', 'Org', 'W Count', 'H Count', 'Pixel Pitch', 'Frame Rate', 'Pixel Count', 'Pixel Rate'])



de20 = pd.DataFrame(
    [{
    'Org': 'Direct Electron',
    'System': 'DE-20',
    'W Count': 5120,
    'H Count': 3840,
    'Pixel Pitch': 6.4,
    'Frame Rate': 25
    }]
)

celeritas = pd.DataFrame(
    [{
    'System': 'Celeritas XS',
    'Org': 'Direct Electron',
    'W Count': 1024,
    'H Count': 1024,
    'Pixel Pitch': 15.0,
    'Pixel Rate': 2202009600
    }]
)

# df = df.concat(de20, ignore_index=True)

# Display the DataFrame
print(de20)
# print(de20.dtypes)
print(celeritas)
# print(celeritas.dtypes)


# date, technology node, 
