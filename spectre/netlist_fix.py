import sys
import re
import os
import shutil

def escape_angle_brackets(line):
    # Escape < and > with a backslash
    updated_line = re.sub(r'([<>])', r'\\\1', line)
    print(f"{line}  =>  {updated_line}")
    return updated_line

def modify_ahdl_include_line(line):
    # Find the position of "ahdl_include"
    start_index = line.find("ahdl_include") + len("ahdl_include")
    
    # Extract the part after "ahdl_include"
    after_ahdl = line[start_index:].strip()
    
    # Add double quotes around the string after "ahdl_include"
    updated_line = line[:start_index] + ' "' + after_ahdl + '"'
    print(f"{line}  =>  {updated_line}")
    return updated_line

def process_file(filename):
    try:
        # Extract the prefix directory from the filename
        ahdl_dir = os.path.splitext(filename)[0] + ".HDL"

        # Break the file into a list of strings
        with open(filename, 'r') as file:
            lines = file.readlines()

        with open(filename, 'w') as file:
            for line in lines:
                if line.startswith('save'):
                    line = escape_angle_brackets(line)
                if line.startswith('ahdl_include'):
                    line = modify_ahdl_include_line(line)
                if not line.startswith('PAGEFRAME_1'):	# This removes the PAGEFRAME_1 instances (but leaves the `subckt` definition, which is fine)
                    file.write(line)
        print("Removing `PAGEFRAME_1` instances.")
        print(f"Processed {filename} successfully.")
        print(f"AHDL direct is: {ahdl_dir}")
        # Iterate over all files and subdirectories in the source directory
        for f in os.listdir(ahdl_dir):
            source_f = os.path.join(ahdl_dir, f)
            dest_f = os.path.join(os.path.dirname(ahdl_dir), f)
            shutil.move(source_f, dest_f)
        os.rmdir(ahdl_dir)
        print("Move adhl files up and deleting dir...")
            
    except FileNotFoundError:
        print(f"Error: The file {filename} was not found.")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python script.py <filename>")
    else:
        process_file(sys.argv[1])
