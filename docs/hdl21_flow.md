# Block files

In the following desciption, references to `Block` corresponds actually to `Cdac`, `Samp`, `Comp`, etc in a corresponding block `.py` file.

## Generator Structure

The starting level is a `@h.generator` which takes a set of parameters with a type of, e.g. `BlockParams` (defined with `@h.paramclass`).

Inside this generator function are:
- Initial helper values, which are necessary to dynamically build the ports or the topology
- A `@h.module` Block class which defines port names (perhaps some of which are dynamic from helper values)
  - This decorator immediately makes an inline instance of this class which can be acted on
- Finally a list of procedural commands which can add to the instance of the `@h.module` created before

After generation, call `pdk.compile(module)` to convert `h.Mos` primitives to PDK-specific devices before netlisting.

## Variants

The next level of hierarchy are the `*_variants()` functions which generate a list of variants of the `*Params` instances:
- Have override arguments, but by default have lists of variables to sweep
- Create a list of the Cartesian product of all parameter value combinations (specified by the typed enums)
- *May* run a `is_valid_*_params()` function before appending a variant to the list, which drops the variant being considered if it's not a valid config 

## Testbenches

After this, we can create an associated:
- `@h.paramclass BlockTbParams` which can be used to create an (often static, single) instance of parameters for a testbench module
- `@h.generator BlockTb`, which given a valid params instance will return a tb netlist module
  - As we'll see later, this can be either wrapped by a `def sim_input()` to append the correct temp and simulator lang statements, or just be called directly if we just want to netlist but not sim
- Inside the `BlockTb` `@h.generator` function we can instantiate one or multiple DUTs using the generator functions of the Block itself (in hierarchical blocks, this is also used in the Block `@h.generator` itself)

## Simulation

In the case that our entry point under question will run a simulation, we have the aforementioned `def sim_input()` function which sets the specific temperatures, times, voltages, etc.

### Simulation Options

Use `hs.Options()` for simulator settings like temperature:

```python
@hs.sim
class MySim:
    tb = MyTestbench
    tr = hs.Tran(tstop=1*MICRO)
    temp = hs.Options(name="temp", value=27)  # Sets temperature
```

This generates clean Spectre output: `simOpts options temp=27`

### Transient Analysis with Noise

Enable noise in transient analysis using the `noise` parameter:

```python
tr = hs.Tran(tstop=1*MICRO, noise=True)  # Spectre: isnoisy=yes
```

### Netlist Generation

Use `write_sim_netlist()` to generate simulation netlists. This uses the same code path as actual simulation, ensuring NETLIST mode outputs match what would be fed to Spectre:

```python
from alt.flow import write_sim_netlist

sim = sim_input(params)
write_sim_netlist(sim, "output.scs", compact=True)
```

The `compact=True` option produces single-line instance formatting:
```spectre
mp_buf_0 ( inter_0 dac_0 vdd vdd ) pmos w=1u l=100n nf=1 m=1
```

Instead of verbose multi-line format:
```spectre
mp_buf_0
+ // Ports:
+ ( inter_0 dac_0 vdd vdd )
+  pmos
+  w=1u l=0.100u nf=1 m=1
```

## Testing

Finally, at the top level is the concept of `test_*` functions. These are executed by the pytest framework, in various modes controlled by the `--mode` CLI option:
- `netlist`: HDL21 netlist generation only (no simulator needed)
- `min`: One setting, one corner (quick sanity check)
- `typ`: One corner, many settings (typical parameter sweep)
- `max`: Full PVT sweep (comprehensive characterization)

Since some of the operations are rather complex, they are bundled in separate `run_*` functions to modularize the functionality.

## Measurement

The `measure.py` module provides post-processing functions that extract metrics from simulation results:
- `comp_delay_ns`, `comp_offset_mV`, `comp_noise_sigma_mV`, etc.
- `samp_settling_ns`, `samp_charge_injection_mV`
- `cdac_settling_ns`, `compute_inl_dnl`
