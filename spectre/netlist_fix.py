import sys
import re
import os

def escape_angle_brackets(line):
    # Escape < and > with a backslash
    updated_line = re.sub(r'([<>])', r'\\\1', line)
    print(f"{line}  =>  {updated_line}")
    return updated_line


def modify_ahdl_include_line(line, prefix):
    # Modify the ahdl_include line to prepend the prefix directory
    updated_line = re.sub(r'^(ahdl_include\s+)(.+)$', r'\1' + prefix + r'/\2', line)
    print(f"{line}  =>  {updated_line}")
    return updated_line

def process_file(filename):
    try:
        # Extract the prefix directory from the filename
        prefix = os.path.splitext(filename)[0] + ".HDL"

        with open(filename, 'r') as file:
            lines = file.readlines()

        with open(filename, 'w') as file:
            for line in lines:
                if line.startswith('save'):
                    line = escape_angle_brackets(line)
                elif line.startswith('ahdl_include'):
                    line = modify_ahdl_include_line(line, prefix)
                file.write(line)

        print(f"Processed {filename} successfully.")

    except FileNotFoundError:
        print(f"Error: The file {filename} was not found.")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python script.py <filename>")
    else:
        process_file(sys.argv[1])