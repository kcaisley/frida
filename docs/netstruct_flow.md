Right now, the final netstructs, when written to json look like this:

```python
{
  "cellname": "samp",
  "ports": {"in": "I", "out": "O", "clk": "I", "clk_b": "I", "vdd": "B", "vss": "B"},
  "devices": {
    "MN": {
      "pins": {"d": "out", "g": "clk", "s": "in", "b": "vss"},
      "params": {"dev": "nmos", "type": "lvt", "w": 10, "l": 2, "nf": 1},
      "model": "n18lvt",
      "w": 2.2e-06,
      "l": 3.6e-07,
      "nf": 1
    }
    "MP": {
      "pins": {"d": "out", "g": "clk_b", "s": "in", "b": "vdd"},
      "params": {"dev": "pmos", "type": "lvt", "w": 10, "l": 2, "nf": 1},
      "model": "p18lvt",
      "w": 2.2e-06,
      "l": 3.6e-07,
      "nf": 1
    }
  },
  "meta": {"switch_type": "tgate"}, # bad!
  "tech": "tower180",
  "subckt": "samp"  # bad!
}
```

But this is no what we want. There are several issues: the three *_params have been popped, when really we want them to exist, simply returns to dictionaries of scalars as we loop over and expand them. Also, we have a meta and subckt field, which we don't want. The values at each iteraction of topo_params appear to be being transfered to meta, but this shouldn't happen.

So instead, let's start from the initial samp subckt, and show what the subckt netstruct should look like at each step.

```python
# An initial good input
subckt = {
    "cellname": "samp",
    "ports": {},  # Empty - computed by generate_topology()
    "devices": {},  # Empty - computed by generate_topology()  
    "topo_params": {"switch_type": ["nmos", "pmos", "tgate"]},
    "dev_params": {
        "nmos": {"type": "lvt", "w": 1, "l": 1, "nf": 1},
        "pmos": {"type": "lvt", "w": 1, "l": 1, "nf": 1},
    },
    "inst_params": [{"devices": ["MN", "MP"], "w": [5, 10, 20, 40], "l": [1, 2]}],
    "tech": ["tsmc65", "tsmc28", "tower180"]
}
```

After being fed into expand_topo_params(subckt_template, generate_topology_fn), we get back a subckt netstruct list, with three elements, since topo params has been expanded, and there is only one field (switch type), with a inital list of three values.

The one element of the struct list, should now look like this. Note how ports an devices has been filled into, with devices only having pins and a non-tech specific dev param:

```python
{
    "cellname": "samp",
    "ports": {"in": "i", "out": "o", "clk": "i", "clk_b": "i", "vdd": "b", "vss": "b"},
    "devices": {
        "MN": {
            "pins": {"d": "out", "g": "clk", "s": "in", "b": "vss"},
            "params": {"dev": "nmos"}
        }
        "MP": {
            "pins": {"d": "out", "g": "clk_b", "s": "in", "b": "vdd"},
            "params": {"dev": "pmos"}
        }
    },
    "topo_params": {"switch_type": "tgate"},
    "dev_params": {
        "nmos": {"type": "lvt", "w": 1, "l": 1, "nf": 1},
        "pmos": {"type": "lvt", "w": 1, "l": 1, "nf": 1},
    },
    "inst_params": [{"devices": ["MN", "MP"], "w": [5, 10, 20, 40], "l": [1, 2]}],
    "tech": ["tsmc65", "tsmc28", "tower180"]
}
```

Next, we should have a function called expand_dev_params(), which sweeps across the dev_params field applying globally to all devices. In our example, the number of elements in our netstruct list doesn't multiply, because each sub field just has a scala value. If for example "w": [1, 2], was used for on of the device types though, then we would have 2x the entrys now in our list. Regardless, the other effect is that it will fill in default values for the devices. In this example, will fill our a type, w, l and nf value. In this concrete example, our list would still only have three elemenets, with this being the last:

```python
{
    "cellname": "samp",
    "ports": {"in": "i", "out": "o", "clk": "i", "clk_b": "i", "vdd": "b", "vss": "b"},
    "devices": {
        "MN": {
            "pins": {"d": "out", "g": "clk", "s": "in", "b": "vss"},
            "params": {"dev": "pmos", "type": "lvt", "w": 1, "l": 1, "nf": 1},
        }
        "MP": {
            "pins": {"d": "out", "g": "clk_b", "s": "in", "b": "vdd"},
            "params": {"dev": "pmos", "type": "lvt", "w": 1, "l": 1, "nf": 1},
        }
    },
    "topo_params": {"switch_type": "tgate"},
    "dev_params": {
        "nmos": {"type": "lvt", "w": 1, "l": 1, "nf": 1},
        "pmos": {"type": "lvt", "w": 1, "l": 1, "nf": 1},
    },
    "inst_params": [{"devices": ["MN", "MP"], "w": [5, 10, 20, 40], "l": [1, 2]}],
    "tech": ["tsmc65", "tsmc28", "tower180"]
}
```

Next, we run a function called expand_inst_params(), which finds the cartesian product of the different combinations of values in the list, and apply these value at each entry. In this case since we have 4 w values, and 2 l values, our previous list of 3 subckt netstruct now grows to 3 x 4 x 2 = 24 entries. One of the elements would look like this below. Note how the w and l values of the selected instanced have be overwritten from the defaults applies in the last pages. Also keep in mind that the devices key: value pair in the inst_params shouldn't be expanded, as it's a list of which devices to select, rather than a description of values to sweep.

```python
{
    "cellname": "samp",
    "ports": {"in": "i", "out": "o", "clk": "i", "clk_b": "i", "vdd": "b", "vss": "b"},
    "devices": {
        "MN": {
            "pins": {"d": "out", "g": "clk", "s": "in", "b": "vss"},
            "params": {"dev": "pmos", "type": "lvt", "w": 10, "l": 2, "nf": 1},
        }
        "MP": {
            "pins": {"d": "out", "g": "clk_b", "s": "in", "b": "vdd"},
            "params": {"dev": "pmos", "type": "lvt", "w": 10, "l": 2, "nf": 1},
        }
    },
    "topo_params": {"switch_type": "tgate"},
    "dev_params": {
        "nmos": {"type": "lvt", "w": 1, "l": 1, "nf": 1},
        "pmos": {"type": "lvt", "w": 1, "l": 1, "nf": 1},
    },
    "inst_params": [{"devices": ["MN", "MP"], "w": 10, "l": 2}],
    "tech": ["tsmc65", "tsmc28", "tower180"]
}
```

And finally, we can have a simply function called expand_tech, which just brings our netlist to 24 * 3 entries, as the tech fiels is expanded. one of the 72 entries:

```python
{
    "cellname": "samp",
    "ports": {"in": "i", "out": "o", "clk": "i", "clk_b": "i", "vdd": "b", "vss": "b"},
    "devices": {
        "MN": {
            "pins": {"d": "out", "g": "clk", "s": "in", "b": "vss"},
            "params": {"dev": "pmos", "type": "lvt", "w": 10, "l": 2, "nf": 1},
        }
        "MP": {
            "pins": {"d": "out", "g": "clk_b", "s": "in", "b": "vdd"},
            "params": {"dev": "pmos", "type": "lvt", "w": 10, "l": 2, "nf": 1},
        }
    },
    "topo_params": {"switch_type": "tgate"},
    "dev_params": {
        "nmos": {"type": "lvt", "w": 1, "l": 1, "nf": 1},
        "pmos": {"type": "lvt", "w": 1, "l": 1, "nf": 1},
    },
    "inst_params": [{"devices": ["MN", "MP"], "w": 10, "l": 2}],
    "tech": "tower180"
}
```

After this step, the map technology function is run, which fills in the actual physical device params, based on the generic params and the techmap lookup. Note how in the final netstruct (ready for netlisting) there are no 'meta' fields or 'subckt' fiels, but we haven't 'popped' off the now scalar topo, dev, inst and tech params.

```python
# A final, good output, ready for netlisting, and with param data left over, for lookup
{
  "cellname": "samp",
  "ports": {"in": "I", "out": "O", "clk": "I", "clk_b": "I", "vdd": "B", "vss": "B"},
  "devices": {
    "MN": {
      "pins": {"d": "out", "g": "clk", "s": "in", "b": "vss"},
      "params": {"dev": "nmos", "type": "lvt", "w": 10, "l": 2, "nf": 1},
      "model": "n18lvt",
      "w": 2.2e-06,
      "l": 3.6e-07,
      "nf": 1
    }
    "MP": {
      "pins": {"d": "out", "g": "clk_b", "s": "in", "b": "vdd"},
      "params": {"dev": "pmos", "type": "lvt", "w": 10, "l": 2, "nf": 1},
      "model": "p18lvt",
      "w": 2.2e-06,
      "l": 3.6e-07,
      "nf": 1
    }
  },
    "topo_params": {"switch_type": "tgate"},
    "dev_params": {
        "nmos": {"type": "lvt", "w": 1, "l": 1, "nf": 1},
        "pmos": {"type": "lvt", "w": 1, "l": 1, "nf": 1},
    },
    "inst_params": [{"devices": ["MN", "MP"], "w": 10, "l": 2}],
    "tech": "tower180"
}
```


We need to make sure that when child subckt devices exist in the subckt netstruct, that they are considered as additional axes upon which the expand_topo_params(), expand_dev_params(), and expand_inst_params() act on:

Here is a more complex example, with a nested child subckt:
``` python
subckt = {
    "cellname": "cellA",
    "ports": {},
    "devices": [],
    "topo_params": {
        "A": [7, 9, 11, 13],
        "B": [0, 2, 4, 6],
        "C": ["sdf", "ddd", "dsa", "ags", "adc"],
        "D": ["abd", "adc", "sdgs"],
    },
    "dev_params": {
        "nmos": {"type": ["lvt", "svt"], "w": 1, "l": 1, "nf": 1},
        "pmos": {"type": "lvt", "w": 1, "l": 1, "nf": 1},
        "cap": {"type": ["momcap_1m", "momcap_2m", "momcap_3m"], "c": 1, "m": 1},
        "cellB": {
            "topo_params": {"A": ["topo1", "topo2"]},
            "dev_params": {
                "nmos": {"type": "lvt", "w": 1, "l": 1, "nf": 1},
                "pmos": {"type": "lvt", "w": 1, "l": 1, "nf": 1},
            },
            "inst_params": [
                {"instname": ["MN1", "MP1"], "w": [20, 40], "l": [1, 2]}
            ],
        },
    },
    "inst_params": [
        {"devices": ["MNA", "MNB", "MNB"], "w": [20, 40], "l": [1, 2]},
        {
            "devices": ["XdependentcellB_1"],
            "cellname" 
            "topo_params": {"A": ["topo3"]},
            "dev_params": {
                "nmos": {"type": "lvt", "w": [10, 20], "l": 1, "nf": 1},
                "pmos": {"type": "lvt", "w": 10, "l": 1, "nf": 1},
            },
            "inst_params": [],
        },
    ],
    "tech": ["tsmc65", "tsmc28", "tower180"],
}
```

I think to make this easier to track, we should add the ability to descend into the child istances to the expand_*() functions, which directly affect the *_params fields. But then their effect on the actual "ports and devices" fields should be broken out into a seperate function. And since the expansion is similar across all cases, in that it's just creating a cartians produce of the params being selected, I think we can do it with a single function:

```python
subckts = circuit_module.subckt

subckts = expand_params(subckts, mode = "topo_params")
subckts = generate_topology(subckts)

subckts = expand_params(subckts, mode = "inst_params")
subckts = apply_inst_params(subckts)

subckts = expand_params(subckts, mode = "tech_params")
subckts = apply_tech_params(subckts)

# by analogy, the case of a tesbench
tbs = expand_params(tbs, mode = "temp_params")
tbs = apply_temp_params(tb)

tbs = expand_params(tbs, mode = "corner_params")
tbs = apply_corner_params(tbs)
```

Not that the apply, and generate functions don't act on the child subcircuit! Just the devices list in the parent top level. The dev_params, topo_params, and inst params inside the childeren will simply be used to lookup the correct file, do be added in the subckt_childeren entry in the files_cts -> files.json


```
# note, we've renamed

dev_params merged into inst_params
devices -> instances
devices -> instances // in the inst_params blocks
```

# Simple inverter
subckt = {
    "cellname": "inverter",
    "tech": ["tsmc65", "tsmc28"],

    # Port directions: I = input, O = output, B = bidirectional (power)
    "ports": {"in": "I", "out": "O", "vdd": "B", "vss": "B"},

    "instances": {
        # NMOS pull-down (conducts when in is high)
        "MN": {"dev": "nmos", "pins": {"d": "out", "g": "in", "s": "vss", "b": "vss"}},
        # PMOS pull-up (conducts when in is low)
        "MP": {"dev": "pmos", "pins": {"d": "out", "g": "in", "s": "vdd", "b": "vdd"}},
    },

    "inst_params": [
        # Sweep w and l for both transistors in unison
        {"instances": {"nmos": "all", "pmos": "all"}, "w": [1, 2, 4], "l": [1, 2], "type": "lvt", "nf": 1},
    ],
}


# Clocked inverter (transmission-gate style with clock high-side PMOS and low-side NMOS)
subckt = {
    "cellname": "clocked_inverter",
    "tech": ["tsmc65", "tsmc28"],

    # Port directions: I = input, O = output, B = bidirectional (power)
    "ports": {"in": "I", "out": "O", "clk": "I", "clkb": "I", "vdd": "B", "vss": "B"},

    "instances": {
        # Core inverter PMOS (pull-up)
        "MP_inv": {"dev": "pmos", "pins": {"d": "out_int", "g": "in", "s": "vdd_sw", "b": "vdd"}},
        # Core inverter NMOS (pull-down)
        "MN_inv": {"dev": "nmos", "pins": {"d": "out_int", "g": "in", "s": "vss_sw", "b": "vss"}},
        # Clock high-side PMOS (connects vdd to inverter when clkb is low)
        "MP_clk": {"dev": "pmos", "pins": {"d": "vdd_sw", "g": "clkb", "s": "vdd", "b": "vdd"}},
        # Clock low-side NMOS (connects vss to inverter when clk is high)
        "MN_clk": {"dev": "nmos", "pins": {"d": "vss_sw", "g": "clk", "s": "vss", "b": "vss"}},
        # Output buffer NMOS
        "MN_out": {"dev": "nmos", "pins": {"d": "out", "g": "out_int", "s": "vss", "b": "vss"}},
        # Output buffer PMOS
        "MP_out": {"dev": "pmos", "pins": {"d": "out", "g": "out_int", "s": "vdd", "b": "vdd"}},
    },

    "inst_params": [
        # Clock transistors: larger for lower on-resistance
        {"instances": {"nmos": ["MN_clk"], "pmos": ["MP_clk"]}, "w": [4, 8], "l": [1], "type": "svt", "nf": 2},
        # Core inverter transistors: sweep sizing
        {"instances": {"nmos": ["MN_inv"], "pmos": ["MP_inv"]}, "w": [1, 2], "l": [1, 2], "type": "lvt", "nf": 1},
        # Output buffer: fixed sizing
        {"instances": {"nmos": ["MN_out"], "pmos": ["MP_out"]}, "w": [2], "l": [1], "type": "lvt", "nf": 1},
    ],
}


# Hierarchical cell containing subcells
subckt = {
    "cellname": "cellA",
    "tech": ["tsmc65", "tsmc28", "tower180"],

    "ports": {"in": "I", "out": "O", "vdd": "B", "vss": "B"},

    "instances": {
        # Primitive devices use "dev"
        "MNA": {"dev": "nmos", "pins": {"d": "net1", "g": "in", "s": "vss", "b": "vss"}},
        "MNB": {"dev": "nmos", "pins": {"d": "net2", "g": "net1", "s": "vss", "b": "vss"}},
        # Subcells use "cell" instead of "dev"
        "XcellB_0": {"cell": "cellB", "pins": {"in": "net2", "out": "net3", "vdd": "vdd", "vss": "vss"}},
        "XcellB_1": {"cell": "cellB", "pins": {"in": "net3", "out": "out", "vdd": "vdd", "vss": "vss"}},
    },

    # Parameters used by generate_topology()
    "topo_params": {
        "A": [7, 9, 11, 13],
        "B": [0, 2, 4, 6],
        "C": ["sdf", "ddd", "dsa", "ags", "adc"],
        "D": ["abd", "adc", "sdgs"],
    },

    "inst_params": [
        # Sweep w and l for specific primitive instances
        {"instances": {"nmos": ["MNA", "MNB"]}, "w": [20, 40], "l": [1, 2]},
        # Defaults for all nmos instances
        {"instances": {"nmos": "all"}, "type": ["lvt", "svt"], "w": 1, "l": 1, "nf": 1},
        # Defaults for all pmos instances
        {"instances": {"pmos": "all"}, "type": "lvt", "w": 1, "l": 1, "nf": 1},
        # Defaults for all cap instances
        {"instances": {"cap": "all"}, "type": ["momcap_1m", "momcap_2m", "momcap_3m"], "c": 1, "m": 1},
        # Override params for a specific cellB instance
        {"instances": {"cellB": ["XcellB_1"]}, "topo_params": {"A": ["topo3"]}, "inst_params": [
            {"instances": {"nmos": "all"}, "type": "lvt", "w": [10, 20], "l": 1, "nf": 1},
            {"instances": {"pmos": "all"}, "type": "lvt", "w": 10, "l": 1, "nf": 1},
        ]},
        # Defaults for all cellB instances
        {"instances": {"cellB": "all"}, "topo_params": {"A": ["topo1", "topo2"]}, "inst_params": [
            {"instances": {"nmos": ["MN1"], "pmos": ["MP1"]}, "w": [20, 40], "l": [1, 2]},
            {"instances": {"nmos": "all"}, "type": "lvt", "w": 1, "l": 1, "nf": 1},
            {"instances": {"pmos": "all"}, "type": "lvt", "w": 1, "l": 1, "nf": 1},
        ]},
    ],
}


# Purely hierarchical cell - ports and instances computed by generate_topology()
subckt = {
    "cellname": "top_level",
    "tech": ["tsmc65", "tsmc28"],

    # Computed by generate_topology()
    "ports": {},
    "instances": {},

    # Parameters used by generate_topology() to build the hierarchy
    "topo_params": {
        "num_stages": [2, 4, 8],
        "buffer_style": ["single", "differential"],
        "output_drive": ["1x", "2x", "4x"],
    },

    "inst_params": [
        # Specific instance overrides for the input stage
        {"instances": {"inverter": ["Xinv_in"]}, "inst_params": [
            {"instances": {"nmos": "all", "pmos": "all"}, "w": [1], "l": [2], "type": "lvt", "nf": 1},
        ]},
        # Output driver sizing
        {"instances": {"inverter": ["Xinv_out"]}, "inst_params": [
            {"instances": {"nmos": "all", "pmos": "all"}, "w": [8, 16], "l": [1], "type": "lvt", "nf": [2, 4]},
        ]},
        # Defaults for all inverter instances
        {"instances": {"inverter": "all"}, "inst_params": [
            {"instances": {"nmos": "all", "pmos": "all"}, "w": [1, 2, 4], "l": [1, 2], "type": "lvt", "nf": 1},
        ]},
        # Defaults for all clocked_inverter instances
        {"instances": {"clocked_inverter": "all"}, "inst_params": [
            {"instances": {"nmos": ["MN_clk"], "pmos": ["MP_clk"]}, "w": [4, 8], "l": [1], "type": "svt", "nf": 2},
            {"instances": {"nmos": "all", "pmos": "all"}, "w": [2], "l": [1], "type": "lvt", "nf": 1},
        ]},
    ],
}
