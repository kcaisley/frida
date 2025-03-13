import sys
import re
import os
import shutil


def escape_angle_brackets(line):
    # Escape < and > with a backslash
    updated_line = re.sub(r"([<>])", r"\\\1", line)
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


def modify_transistor_port_order(line):
    # Find the start and end of the port list
    start = line.find("(")
    end = line.find(")")
    # Extract the port list and split it into individual ports
    ports = line[start + 1 : end].split()
    # Rotate the ports: move the first port to the end
    ports = ports[1:] + [ports[0]]
    # Reconstruct the line with the modified port order
    updated_line = line[: start + 1] + " ".join(ports) + line[end:]
    print(f"{line}  =>  {updated_line}")
    return updated_line


def process_file(filename):
    try:
        # Extract the prefix directory from the filename
        ahdl_dir = (
            os.path.splitext(filename)[0] + ".HDL"
        )  # FIX ME: This produces an error when there are no ahdl models!

        # Break the file into a list of strings
        with open(filename, "r") as file:
            lines = file.readlines()

        with open(filename, "w") as file:
            # Notice to prevent re-running on same file.
            file.write(
                "// ---- Post-processed by `prep_netlist.py` for compatibility ----\n"
            )
            for line in lines:
                if line.startswith("save"):
                    line = escape_angle_brackets(line)
                if line.startswith("ahdl_include"):
                    line = modify_ahdl_include_line(line)
                if line.startswith(("Mp", "Mn")):
                    line = modify_transistor_port_order(line)
                if not line.startswith(
                    "PAGEFRAME_1"
                ):  # This removes the PAGEFRAME_1 instances (but leaves the `subckt` def)
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

    except Exception as e:
        print(f"An error occurred: {e}")


def cleanup_dir():
    # Iterate over all items in the current directory
    for item in os.listdir():
        # Check if the item is a file and ends with .va or .log
        if os.path.isfile(item) and item.endswith((".va", ".log")):
            print(f"Deleting file: {item}")
            os.remove(item)  # Delete the file
        # Check if the item is a directory and ends with .ahdlSimDB or .raw
        elif os.path.isdir(item) and item.endswith((".ahdlSimDB", ".raw", ".cadence")):
            print(f"Deleting directory: {item}")
            shutil.rmtree(item)  # Recursively delete the directory


if __name__ == "__main__":
    # Get the current working directory and the script's directory
    current_directory = os.getcwd()
    script_directory = os.path.dirname(os.path.abspath(__file__))

    # Check if the script is being run from the same directory
    if current_directory == script_directory:
        print(
            "Error: This script should not be run from the same directory as the script."
        )
        print("Please run it from a lower-level directory.")
        print("Usage: python ../prep_netlist.py <netlist_name.scs>")

    # Check for the correct number of command-line arguments
    elif len(sys.argv) != 2:
        print("Error: This script needs a netlist as an argument.")
        print("Usage: python ../prep_netlist.py <netlist_name.scs>")

    # Check if the file has already been processed
    else:
        try:
            with open(sys.argv[1], "r") as file:
                first_line = file.readline()
                if (
                    first_line.strip()
                    == "// ---- Post processed by prep_netlist.py for compatibility ----"
                ):
                    print(
                        f"Error: The netlist {sys.argv[1]} has already been processed by prep_netlist.py."
                    )
                else:
                    cleanup_dir()
                    process_file(sys.argv[1])
        except FileNotFoundError:
            print(f"Error: The netlist {sys.argv[1]} was not found.")
