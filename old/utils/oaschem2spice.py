#!/usr/bin/env python3

"""
Handles the complete workflow from Cadence library to final SPICE netlist with proper formatting and unit handling.

Process:
1. Creates si.env configuration file
2. Runs 'si -batch -command netlist' to generate CDL
3. Converts CDL to cleaned SPICE format

Usage:
    python3 oaschem2spice.py <LibName> <CellName> [OutputName]

Example:
    python3 oaschem2spice.py OBELIX_BCID_DRIVER BCID_DRIVER_DC_ORG driver_output

Output Files:
    - si.env (temporary configuration)
    - <OutputName>.cdl (intermediate CDL)
    - <OutputName>.sp (final SPICE output)
"""

import re
import sys
import subprocess


def create_si_env(simLibName, simCellName):
    """Create the si.env file for Cadence netlisting"""
    content = f"""simLibName = "{simLibName}"
simCellName = "{simCellName}"
simViewName = "schematic"
simSimulator = "auCdl"
simNotIncremental = 't
simReNetlistAll = nil
simViewList = '("auCdl" "schematic")
simStopList = '("auCdl")
simNetlistHier = 't
nlFormatterClass = 'spectreFormatter
nlCreateAmap = 't
nlDesignVarNameList = nil
simViewList = '("auCdl" "schematic")
simStopList = '("auCdl")
simNetlistHier = t
hnlNetlistFileName = "{simCellName}.cdl"
resistorModel = ""
shortRES = 0.0
preserveRES = 't
checkRESVAL = 'nil
checkRESSIZE = 't
preserveCAP = 't
checkCAPVAL = 't
checkCAPAREA = 't
preserveDIO = 't
checkDIOAREA = 't
checkDIOPERI = 't
checkCAPPERI = 't
simPrintInhConnAttributes = 'nil
checkScale = "meter"
checkLDD = 'nil
pinMAP = 'nil
preserveBangInNetlist = 'nil
shrinkFACTOR = 0.0
globalPowerSig = ""
globalGndSig = ""
displayPININFO = 'f
preserveALL = 't
setEQUIV = ""
auCdlDefNetlistProc = "ansCdlSubcktCall"
allowNetNamesBeginningWithDigits = 'nil
"""
    with open("si.env", "w") as f:
        f.write(content)


def run_si_netlist():
    """Run the Cadence netlister to generate CDL"""
    print("Running si -batch -command netlist... (this may take a couple seconds)")
    try:
        result = subprocess.run(
            ["si", "-batch", "-command", "netlist"], capture_output=True, text=True
        )
        if result.returncode != 0:
            print("Error running si command:")
            print(result.stderr)
            print(result.stdout)
            return False
        return True
    except FileNotFoundError:
        print(
            "Error: 'si' command not found. Please ensure Cadence tools are in your PATH"
        )
        return False


def convert_cdl_to_spice(cdl_file, spice_file):
    """Main conversion function"""
    with open(cdl_file, "r") as f:
        lines = f.readlines()

    with open(spice_file, "w") as f_out:
        cleaned_lines = []

        # Group lines and remove unnecessary lines
        for line in lines:
            line = line.strip()

            # if not line:
            #     continue
            # Handle subckt declarations specially
            # if line.startswith('.SUBCKT'):
            #     processed = process_subckt_declaration(line, lines_iter)
            #     f_out.write(processed)
            if line.startswith("*"):
                # Keep PININFO but remove type indicators if present
                continue
                # line = re.sub(r':[IOB]', '', line)
                # f_out.write(line + '\n')

            elif line.startswith(".PARAM"):
                continue
            elif line.startswith("+"):
                cleaned_lines[-1] = cleaned_lines[-1] + line[1:]
            else:
                # Process all other lines
                cleaned_lines.append(line)
                # cleaned = clean_cdl_line(line)
                # f_out.write(cleaned + '\n')
        for line in cleaned_lines:
            # Lowercase whole string:
            line = line.lower()
            # Remove group_* parameters
            line = re.sub(r'\sgroup_[a-z]+="[^"]*"', "", line)
            # Remove rf_flag
            line = re.sub(r"\srf_flag=\d+", "", line)
            # Remove slashes between instance and cell name
            line = line.replace(" / ", " ")

            # Remove duplicate prefix on device instance name (e.g. MM1 -> M1 orand DD3 -> D3)
            if len(line) >= 2 and line[0] == line[1]:
                line = (
                    line[0] + line[2:]
                )  # Keep first char + everything after the second char

            # MOSFET fixes
            line = line.replace(" n ", " nmos_svt ")
            line = line.replace(" p ", " pmos_svt ")
            line = line.replace(" n18lvt ", " nmos_lvt ")
            line = line.replace(" p18lvt ", " pmos_lvt ")
            line = line.replace(" n_iso ", " nmos_svt ")
            line = line.replace(" p_iso ", " pmos_svt ")
            line = line.replace(" p_iso ", " pmos_svt ")
            line = line.replace("(", "")
            line = line.replace(")", "")
            line = line.replace("$w=", "w=")
            line = line.replace("$l=", "l=")

            # Diode fixes
            line = line.replace("ddwnps18", "diode_dnwell")

            # Resistor fixes
            if line.startswith("r"):  # Check if line starts with 'r'
                parts = line.split()  # Split into components
                parts.pop(3)  # Remove the 4th element (floating-point number)
                line = str.join(" ", parts)  # Reconstruct the line
            line = line.replace("$sub=", "")
            # Handle $[r#] → res_metal (using regex to catch any number)
            line = re.sub(r"\$\[r\d+\]", "res_metal", line)
            line = line.replace("$[rh]", "res_poly_2t")
            line = line.replace("$[rh3]", "res_poly_3t")
            line = line.replace("$[rb]", "res_bulk_2t")
            line = line.replace("$[rb3]", "res_bulk_3t")

            # Capacitor fixes
            # Handle using regex capacitance values appearing
            if line.startswith("c"):
                parts = line.split()
                if re.match(r"^\d+\.?\d*[fpnum]?$", parts[3]):
                    parts.pop(3)
                    line = str.join(" ", parts)
            line = re.sub(r"\$\[cmim_\w+\]", "cap_mim", line)
            line = re.sub(r"\$\[cm(33t|43t|53t|33|43|53)\]", "cap_mom_3t", line)
            line = re.sub(r"\$\[cm(32t|42t|52t|3|4|5)\]", "cap_mom_2t", line)
            line = line.replace("$[ch]", "cap_mos_2t")
            line = line.replace("$[ch3]", "cap_mos_3t")

            # Convert w=xxx to decimal
            line = re.sub(
                r"w=(\d+)e-(\d+)",
                lambda m: f"w={float(m.group(1)) * 10 ** -int(m.group(2)):.3f}",
                line,
            )
            # Convert l=xxx to decimal
            line = re.sub(
                r"l=(\d+)e-(\d+)",
                lambda m: f"l={float(m.group(1)) * 10 ** -int(m.group(2)):.3f}",
                line,
            )

            # Add 'u' to w= values (handles both decimal and scientific notation)
            line = re.sub(
                r"(w=)([\d\.]+)(e[+-]?\d+)?\b",
                lambda m: f"{m.group(1)}{m.group(2)}{m.group(3) or ''}u",
                line,
            )
            # Add 'u' to l= values (handles both decimal and scientific notation)
            line = re.sub(
                r"(l=)([\d\.]+)(e[+-]?\d+)?\b",
                lambda m: f"{m.group(1)}{m.group(2)}{m.group(3) or ''}u",
                line,
            )
            parts = line.split()

            # Remove double spaces
            line = line.replace("  ", " ")

            f_out.write(line + "\n")


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <mode> [args...]")
        print("Modes:")
        print("  oa <LibName> <CellName> [OutputName]  - Convert from OA library")
        print("  file <input_file>        - Convert from CDL/SPICE file")
        print()
        print("Examples:")
        print(
            "  python oaschem2spice.py oa OBELIX_BCID_DRIVER BCID_DRIVER_DC_ORG driver_output"
        )
        print("  python oaschem2spice.py file strongarm_bag.sp")
        sys.exit(1)

    mode = sys.argv[1]

    if mode == "oa":
        # Original OA library mode
        if len(sys.argv) < 4 or len(sys.argv) > 5:
            print(
                "Usage for OA mode: python oaschem2spice.py oa <LibName> <CellName> [OutputName]"
            )
            sys.exit(1)

        simLibName = sys.argv[2]
        simCellName = sys.argv[3]
        outputName = sys.argv[4] if len(sys.argv) == 5 else simCellName
        intermediate_cdl_file = f"{simCellName}.cdl"  # si generates this filename
        cdl_file = f"{outputName}.cdl"  # final output filename
        spice_file = f"{outputName}.sp"

        # Step 1: Create si.env
        print(f"Creating si.env for {simLibName}/{simCellName}...")
        create_si_env(simLibName, simCellName)
        print(f"Finished si.env for {simLibName}/{simCellName}...")

        # Step 2: Run si netlist command
        if not run_si_netlist():
            sys.exit(1)
        print(
            f"Converted OA schematic to .cdl netlist for {simLibName}/{simCellName}..."
        )

        # Step 3: Convert CDL to SPICE
        print(f"Converting {intermediate_cdl_file} to {spice_file}...")
        convert_cdl_to_spice(intermediate_cdl_file, spice_file)

        # Step 4: Rename intermediate CDL to final name if different
        if intermediate_cdl_file != cdl_file:
            import os

            os.rename(intermediate_cdl_file, cdl_file)
            print(f"Renamed {intermediate_cdl_file} to {cdl_file}")

        print("\nConversion complete!")
        print(f"SPICE netlist saved to {spice_file}")

    elif mode == "file":
        # Direct file conversion mode
        if len(sys.argv) != 3:
            print("Usage for file mode: python oaschem2spice.py file <input_file>")
            sys.exit(1)

        input_file = sys.argv[2]

        # Generate output filename by replacing extension with .sp
        if "." in input_file:
            base_name = input_file.rsplit(".", 1)[0]
        else:
            base_name = input_file
        spice_file = f"{base_name}_normalized.sp"

        print(f"Converting {input_file} to {spice_file}...")
        convert_cdl_to_spice(input_file, spice_file)

        print("\nConversion complete!")
        print(f"Normalized SPICE netlist saved to {spice_file}")

    else:
        print(f"Unknown mode: {mode}")
        print("Valid modes are: oa, file")
        sys.exit(1)


if __name__ == "__main__":
    main()
