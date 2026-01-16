# Subcircuit

- Each block script needs a `subcircuit()` function, ensure it is at the top of the file, which takes no arguments are returns a list/scalar of `topology`s and `sweep` tuples.
- Several helper functions can be used for example generate_topology() or generate_sweeps() but they must be after `subcircuit()` and before `testbench`.
- This function should have no print statements.
- Devices additions should always appear on one line, e.g. `devices[f"MPdrv{idx}"] = {"dev": "pmos", "pins": {"d": f"bot[{idx}]", "g": f"inter[{idx}]", "s": "vdd", "b": "vdd"}, "w": driver_w}`
- The sweeps variable contains a set of `globals` which can be set one to be a static default each device's parameters, or they can appear as a list to increment and produce netlists with a changing base value of every element of the same type. The `selections` field is used to specifically then set a couple devices to (typically larger) values, for example using larger widths for a pair of differential input transistors.
- `selections` isn't required if different devices sizes needn't be tried, and in purely heirarchial netlists `selections` would never appear and neither would `globals`, as heirachial blocks don't change with process node. (For testbenches they do though!)
- The `sweeps` and `topology` list of structs should be a assembled inside of `subcircuit()` but can be computed used values calculated from the help functions.
- When naming ports or nets, don't use `p` or `n` to delinate differential pairs; instead use `+` and `-` with no seperator.

# Testbench
- Each block script needs a `testbench()` function, similar to the subcircuit in terms of IO.
- Sweeps likely aren't needed, other than the `tech` field in the `sweeps` struct.
- A succint comment at the top of the circuit should describe the purpose and sequence of test stimuli applied to the circuit.
- Note that voltages, current, and times are input using generic steps, which are then converter to physical quantities by the flow/netlist.py. This allow one syntax to generate testbenchs with different technology voltage supplies, and work in generic time steps rather than having to specify nanoseconds, etc.

# Measure
- Measurement entails reading in the .raw files created by simulation, and performing a series of post-processing and calculations to find the performance of the circuit block under test.
- All measurements are done using calc_*() functions from flow/measure.
- No plotting is done, and no in-line print statements should be include in this function, as this is done at at a higher level by flow/measure.
- measure() starts by reading from the column-based data of the spice simulation .raw files, which is loaded into a wave struct which is dictionary of numpy arrays, in which individual waveforms can then be accessed as w.name
- the various calc_*() functions always take w.name traces as inputs, and write back a new w.name trace in a new numpy array 'column', or by adding a new metric under a 'm' struct. These metrics are anything of a different dimension (normally reduced, i.e. something like gain or rise time) which wouldn't make sense to write back in a table format.
- At the end of analysis, all the columns in the `w` object are written to a csv file, and all the other `m` values are written to a json file.
- No print outs are done in this function, instead the higher level flow/measure.py by default reports all the calculated metrics. This includes a `tqdm` progress bar, which iterates as each subcircuit raw analysis is completed.
