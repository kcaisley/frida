#!/usr/bin/python3

# Imports
import hashlib


# DOESN'T WORK YET, NEEDS FIXES!

"""
SPICE netlist comparison tool.
Code based on `netcomp`: copyright 2004 Sam Hocevar <sam@hocevar.net>

Usage: netcmp.py netlist_a netlist_b [-o output_file]
"""

class Node:
    def __init__(self, component: str, pin: str, net: str):
        """ Simple class to represent a Node"""
        self.component = component
        self.pin = pin
        self.net = net


class Net:
    def __init__(self, name: str, full_signal_name: str):
        """ Simple class to represent a Net """
        self.name = name
        self.full_signal_name = full_signal_name


class NetCmp:
    def hash(self):
        return self._hash
    def __init__(self, netlistpath):
        """ Main class for netlist comparison """
        # Init class vars
        self.nets = {}
        self.components = {}
        self.netlistpath = netlistpath
        self._hash = None

        # Parse the netlist file
        self.parse(netlistpath)

    def parse(self, filepath: str) -> None:
        """ Parse the netlist file """
        # Open netlist file
        with open(filepath) as fp:
            current_subckt = None
            
            for line in fp:
                line = line.strip()
                
                # Skip empty lines and comments
                if not line or line.startswith('*'):
                    continue
                    
                # Handle SUBCKT definition
                if line.startswith('.SUBCKT'):
                    tokens = line.split()
                    current_subckt = tokens[1]
                    continue
                    
                # Handle END of subcircuit
                if line.startswith('.ENDS'):
                    current_subckt = None
                    continue
                    
                # Parse device instances (M, R, C, X, etc.)
                if current_subckt and line and line[0] in 'MRCQX':
                    tokens = line.split()
                    if len(tokens) >= 4:
                        device_name = tokens[0]
                        
                        # For MOSFET (M devices), typically: Mname drain gate source bulk model
                        if tokens[0][0] == 'M' and len(tokens) >= 5:
                            pins = ['drain', 'gate', 'source', 'bulk']
                            nets = tokens[1:5]
                        # For other devices, assume first few tokens are nets
                        else:
                            pins = [f'pin{i}' for i in range(len(tokens)-2)]
                            nets = tokens[1:-1]  # Everything except device name and model
                        
                        # Create nodes for each pin
                        for i, (pin, net) in enumerate(zip(pins, nets)):
                            node = Node(component=device_name, pin=pin, net=net)
                            
                            # Store in components dict
                            if device_name not in self.components:
                                self.components[device_name] = {}
                            self.components[device_name][pin] = node
                            
                            # Store nets
                            if net not in self.nets:
                                self.nets[net] = Net(name=net, full_signal_name=net)

            # Regenerate hash
            self._hash = self._generate_hash()

    def _generate_hash(self) -> str:
        """ Create an md5 hash of the design based on nodes and nets, irrespective of netlist ordering """
        # Initialise empty dict for flatten nodes
        node_flat = {}

        # Iterate through all components
        for comp_name, comp_dict in self.components.items():

            # Iterate through all pins of the component
            for pin_name, node in comp_dict.items():

                # Store the node for each pin in the flat dict
                node_flat[comp_name+"."+pin_name] = node

        # Initialise hasher instance
        hasher = hashlib.md5()

        # Create a list of all node names from the node_flat dict
        node_list = list(node_flat.keys())

        # !IMPORTANT! Sort the node_list alphabetically, so that we always have the same order
        # (regardless of netlist order)
        node_list.sort()

        # Iterate through every node name in the list
        for node_name in node_list:

            # Update the hasher with the node name and the node net
            hasher.update(node_name.encode())
            hasher.update(node_flat[node_name].net.encode())

        # Return a hex digest string of the hasher
        return hasher.hexdigest()

    def compare(self, b: "NetCmp", report_path: str = None) -> int:
        """ Compare this design with b. Writes report to report_path if provided, or prints to stdout. Returns number of differences found """
        
        # Collect all differences first
        differences = []
        
        # Iterate through each component
        for comp_name, comp_dict in self.components.items():
            # Check this component is in design b
            if comp_name in b.components:
                # Iterate through every pin of this component
                for pin, node in comp_dict.items():
                    # Check this pin is in design B's component
                    if pin in b.components[comp_name]:
                        # If the net attached to this pin is different from the one on design B, report the diff
                        if node.net != b.components[comp_name][pin].net:
                            differences.append(f"NET DIFF: {comp_name}.{pin} connected to '{node.net}' vs '{b.components[comp_name][pin].net}'")
                    # The pin is missing from design B's component, report it
                    else:
                        differences.append(f"PIN MISSING: {comp_name}.{pin} exists in netlist A but not B")
            # The component is missing from design B, report it
            else:
                differences.append(f"MISSING: Component {comp_name} exists in netlist A but not B")

        # Iterate through all components in design B
        for comp_name in b.components.keys():
            # If the component is not in our design, report it
            if comp_name not in self.components:
                differences.append(f"EXTRA: Component {comp_name} exists in netlist B but not A")

        # Output results
        if report_path:
            # Write to CSV file
            with open(report_path, "w+") as fp:
                fp.write("A: {}, ({})\n".format(self.hash(), self.netlistpath))
                fp.write("B: {}, ({})\n".format(b.hash(), b.netlistpath))
                fp.write("--------------------------------\n")
                fp.write("INDEX, REF, DIFF, A, B\n")
                
                for i, diff in enumerate(differences):
                    fp.write("{:03}, {}\n".format(i, diff))
                
                fp.write("--------------------------------\n")
                fp.write("{} differences found".format(len(differences)))
        else:
            # Print to stdout
            if differences:
                print(f"Comparing {self.netlistpath} vs {b.netlistpath}:")
                for diff in differences:
                    print(f"  {diff}")
                print(f"\n{len(differences)} differences found")
            else:
                print(f"Netlists are identical: {len(differences)} differences found")

        return len(differences)

    def __hash__(self):
        return self._hash

    def __eq__(self, other):
        if not isinstance(other, NetCmp):
            return False
        else:
            return hash(self) == hash(other)


# Execute if run directly (and not imported)
if __name__ == "__main__":

    import argparse

    # Initialise argument parser, with netlist a & b and optional report file arguments
    # Usage: netcmp.py [netlist_a] [netlist_b] [-o report_file]
    parser = argparse.ArgumentParser(
        description="SPICE netlist comparison tool.",
        epilog="Example: netcmp.py design1.sp design2.sp -o differences.csv"
    )
    parser.add_argument("netlist_a", help="Path to netlist A")
    parser.add_argument("netlist_b", help="Path to netlist B")
    parser.add_argument("-o", "--output", help="Path to store CSV report (optional)")
    args = parser.parse_args()

    # Create NetCmp instances for each netlist
    a = NetCmp(args.netlist_a)
    b = NetCmp(args.netlist_b)

    # Compare designs
    diff = a.compare(b, args.output)

    # Print comparison done if using CSV output
    if args.output:
        print("Comparison complete, {} differences found. Report saved to {}".format(diff, args.output))
    
    