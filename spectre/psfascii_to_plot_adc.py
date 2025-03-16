from psf_utils import PSF
from inform import Error, display
import matplotlib.pyplot as plt


import subprocess

# Base path and file pattern
base_path = "sim_saradc/SB_saradc8_radixN.psfascii"
file_pattern = "tnoise-{:03d}_tran1.tran.psfascii"

# Loop through the files from 000 to 049
for i in range(50):
    # Format the file name with the current index
    file_name = file_pattern.format(i)
    # Construct the full command
    command = ["list-psf", "-f", f"{base_path}/{file_name}"]

    # Run the command
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # Print the output and error (if any)
    print(f"Cached {file_name}!")
    # print(result.stdout.decode())
    if result.stderr:
        print(f"Error for {file_name}:")
        print(result.stderr.decode())

# try:
#     psf = PSF('sim_saradc/SB_saradc8_radixN.psfascii/tnoise-000_tran1.tran.psfascii')
#     inp
#     inn

#     cdac_p = psf.get_signal('cdac_p')
#     cdac_n = psf.get_signal('cdac_n')
# except Error as e:
#     e.terminate()
