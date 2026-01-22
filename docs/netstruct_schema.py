# Imaging a subcircuit with several device instances, including:
# several nmos and pmos devices named MNA, MNB, MNC etc.... MPA, MPB, MPC, etc....
# several capacitors, CA, CB, CC, etc....
# and several instances of a subckt 'depedant_cellB', each named XdependentcellB_1, XdependentcellB_2, etc..
# which iteself internally contains several mosfets, e.g. MN1, MN2, MP2, MP2, MP3

subckts = {
    "name": "higher_cellA",
    "ports": {},  # in all the most simple cases, will be computed from params
    "devices": [],  # in all the most simple cases, will be computed from params
    "tech": ["tsmc65", "tsmc28", "tower180"],  # top level must list technologies
    
    # always a dict of lists, parameters used by generate_topology()
    "topo_params": {  
        "A": [7, 9, 11, 13],
        "B": [0, 2, 4, 6],
        "C": ["sdf", "ddd", "dsa", "ags", "adc"],
        "D": ["abd", "adc", "sdgs"]
    },
    
    # Used by expand_sweeps(), always a dict of dicts (of lists/scalar depending on if there are just defaults or some combinations)
    # default params, generate_topology() or not specifically in inst_params for all devices matching these types. 
    # At least one default for all devices param field is required
    "dev_params": {  # considered last, after inst_params, by expand_sweeps
        "nmos": {"type": ["lvt", "svt"], "w": 1, "l": 1, "nf": 1},
        "pmos": {"type": "lvt", "w": 1, "l": 1, "nf": 1},
        "cap": {"type": ["momcap_1m", "momcap_2m", "momcap_3m"], "c": 1, "m": 1},
        "dependant_cellB": {
            # In this example, only made of transistors, so not too hard to write out
            # note how reference to dependant cells need to specify parameters for lookup
            # but technology, name, ports, devices, etc are left out, as these were calculated in an earlier step
            # critically: topo_, dev_, and inst_param values can mirror those in the dependant cells script e.g. dependant_cellB.py, 
            # or can be a subset, if you don't want to consider all combinations
            # but can't be a superset, as any extra combinations wouldn't have files
            # These will be used by a merged version of the expand_sweeps() function when run on higher_cellA
            "topo_params": {"A": ["topo1", "topo2"]},
            "inst_params": [  # applies to specific instances
                {"devices": ["MN1", "MP1"], "w": [20, 40], "l": [1, 2]}
            ],
            "dev_params": {  # applies as defaults/sweeps to all devices of one class
                "nmos": {"type": "lvt", "w": 1, "l": 1, "nf": 1},
                "pmos": {"type": "lvt", "w": 1, "l": 1, "nf": 1}
            }
        }
    },
    
    # Used by expand_sweeps(), considered actually before dev_params(), 
    # but after generate_topology() and doesn't overwrite dev params manually specified in the generate_topology() function.
    "inst_params": [
        {"devices": ["MNA", "MNB", "MNB"], "w": [20, 40], "l": [1, 2]},
        
        # apply a specific set of parameters to on instance of dependant_cellB, preempting the values set for all the other instances 
        { 
            "inst": ["XdependentcellB_1"],
            "topo_params": {"A": ["topo3"]},
            "inst_params": [],
            "dev_params": {
                "nmos": {"type": "lvt", "w": [10, 20], "l": 1, "nf": 1},
                "pmos": {"type": "lvt", "w": 10, "l": 1, "nf": 1}
            }
        }
    ]
}

# After generate_topology() loops across the cartesian product of topo_params, we have a list of subckt struct objects, 
# and after expand_sweeps() acts on inst_params, dev_params, and tech, we have a much longer list of subckt structs. 
# This is because every one of the lists in these structs is expanded as a cartesian product. 
# At the end, the devices and ports list of every subckt struct in a big list should be fully filled out, 
# with every single device with its inline params specified



def generate_topology(subckts):
    #.... some calculations, depending on subckts.topo_params

    # returns with devices and ports started to be filled in!
    return list_of_subckts