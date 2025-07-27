import os
import subprocess

# This should be run from the directory above the psfbin and psfascii dirs

# Define the base directories
raw_dir = "SB_saradc8_radixN.raw"
psfascii_dir = "SB_saradc8_radixN.psfascii"

tnoise_range = range(0, 50)  # tnoise-000 to tnoise-099

# Loop through all combinations of vcm, vdiff, and tnoise
for tnoise in tnoise_range:
    # Construct the input and output filenames
    input_filename = f"afs_tn_sweep-{tnoise:03}_tran1.tran.tran"
    output_filename = f"tnoise-{tnoise:03}_tran1.tran.psfascii"

    # Construct the full paths
    input_path = os.path.join(raw_dir, input_filename)
    output_path = os.path.join(psfascii_dir, output_filename)

    # Print the file being accessed for debugging
    print(f"Processing: {input_path} -> {output_path}")

    # Check if the input file exists
    if os.path.exists(input_path):
        # Run the psf command
        command = ["psf", "-i", input_path, "-o", output_path]
        subprocess.run(command)
    else:
        print(f"File not found: {input_path}")

print("Processing complete.")
