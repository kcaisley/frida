OpenSTA

**Table of Contents**

[Command Line Arguments 1](#command-line-arguments)

[Example Command Scripts 1](#example-command-scripts)

[Timing Analysis using SDF 2](#timing-analysis-using-sdf)

[Timing Analysis with Multiple Process Corners
2](#timing-analysis-with-multiple-process-corners)

[Power Analysis 2](#power-analysis)

[TCL Interpreter 3](#tcl-interpreter)

[Debugging Timing 4](#__RefHeading___Toc42587_2528141652_Copy_1)

[No paths found 4](#no-paths-found)

[No path reported an endpoint 5](#no-path-reported-an-endpoint)

[Commands 6](#commands)

[Filter Expressions 80](#filter-expressions)

[Variables 80](#variables)

# **Command Line Arguments**

The command line arguments for sta are shown below.

sta  
-help show help and exit  
-version show version and exit  
-no_init do not read ~/.sta  
-no_splash do not print the splash message  
-threads count|max use count threads  
-exit exit after reading *cmd_file*  
*cmd_file* source *cmd_file*

When OpenSTA starts up, commands are first read from the user
initialization file ~/.sta if it exists. If a TCL command file
*cmd_file* is specified on the command line, commands are read from the
file and executed before entering an interactive TCL command
interpreter. If -exit is specified the application exits after reading
*cmd_file*. Use the TCL exit command to exit the application. The
–threads option specifies how many parallel threads to use. Use
–threads max to use one thread per processor.

# Example Command Scripts

To read a design into OpenSTA use the read_liberty command to read
Liberty library files. Next, read hierarchical structural Verilog files
with the read_verilog command. The link_design command links the
Verilog to the Liberty timing cells. Any number of Liberty and Verilog
files can be read before linking the design.

Delays used for timing analysis are calculated using the Liberty timing
models. If no parasitics are read only the pin capacitances of the
timing models are used in delay calculation. Use the read_spef command
to read parasitics from an extractor, or read_sdf to use delays
calculated by an external delay calculator.

Timing constraints can be entered as TCL commands or read using the
read_sdc command.

The units used by OpenSTA for all command arguments and reports are
taken from the first Liberty file that is read. Use the set_cmd_units
command to override the default units.

## Timing Analysis using SDF

A sample command file that reads a library and a Verilog netlist and
reports timing checks is shown below.

read_liberty example1_slow.lib  
read_verilog example1.v  
link_design top  
read_sdf example1.sdf  
create_clock -name clk -period 10 {clk1 clk2 clk3}  
set_input_delay -clock clk 0 {in1 in2}  
report_checks

This example can be found in examples/sdf_delays.tcl.

## Timing Analysis with Multiple Process Corners

An example command script using three process corners and +/-10% min/max
derating is shown below.

define_corners wc typ bc  
read_liberty -corner wc example1_slow.lib  
read_liberty -corner typ example1_typ.lib  
read_liberty -corner bc example1_fast.lib  
read_verilog example1.v  
link_design top  
set_timing_derate -early 0.9  
set_timing_derate -late 1.1  
create_clock -name clk -period 10 {clk1 clk2 clk3}  
set_input_delay -clock clk 0 {in1 in2}  
report_checks -path_delay min_max  
report_checks -corner typ

This example can be found in examples/spef_parasitics.tcl. Other
examples can be found in the examples directory.

## Power Analysis

OpenSTA also supports static power analysis with the report_power
command. Probabalistic switching activities are propagated from the
input ports to determine switching activities for internal pins.

read_liberty sky130hd_tt.lib  
read_verilog gcd_sky130hd.v  
link_design gcd  
read_sdc gcd_sky130hd.sdc  
read_spef gcd_sky130hd.spef  
set_power_activity -input -activity 0.1  
set_power_activity -input_port reset -activity 0  
report_power

In this example the activity for all inputs is set to 0.1, and then the
activity for the reset signal is set to zero because it does not switch
during steady state operation.

Group Internal Switching Leakage Total  
Power Power Power Power (Watts)  
----------------------------------------------------------------  
Sequential 3.27e-04 7.87e-05 2.96e-10 4.06e-04 36.4%  
Combinational 2.34e-04 3.10e-04 6.95e-10 5.43e-04 48.7%  
Clock 4.68e-05 1.20e-04 2.30e-11 1.67e-04 15.0%  
Macro 0.00e+00 0.00e+00 0.00e+00 0.00e+00 0.0%  
Pad 0.00e+00 0.00e+00 0.00e+00 0.00e+00 0.0%  
----------------------------------------------------------------  
Total 6.07e-04 5.09e-04 1.01e-09 1.12e-03 100.0%  
  
54.4% 45.6% 0.0%

This example can be found in examples/power.tcl.

Gate level simulation results can be used to get a more accurate power
estimate. For example, the Icarus verilog simulator can be used to run
the the test bench examples/gcd_tb.v for the gcd design in the previous
example.

iverilog -o gcd_tb gcd_tb.v  
vvp gcd_tb

The test bench writes the VCD (Value Change Data) file gcd_sky130hd.vcd
which can then be read with the read_vcd command.

read_liberty sky130hd_tt.lib  
read_verilog gcd_sky130hd.v  
link_design gcd  
read_sdc gcd_sky130hd.sdc  
read_spef gcd_sky130hd.spef  
read_vcd -scope gcd_tb/gcd1 gcd_sky130hd.vcd.gz  
report_power

This example can be found in examples/power_vcd.tcl.

Note that in this simple example design simulation based activities does
not significantly change the results.

# TCL Interpreter

Keyword arguments to commands may be abbreviated. For example,

report_checks -unique

is equivalent to the following command.

report_checks -unique_paths_to_endpoint

The help command lists matching commands and their arguments.

> help report*  
report_annotated_check [-setup] [-hold] [-recovery] [-removal]
[-nochange]  
[-width] [-period] [-max_skew] [-max_lines liness]
[-list_annotated]group_path_count  
[-list_not_annotated] [-constant_arcs]  
report_annotated_delay [-cell] [-net] [-from_in_ports]
[-to_out_ports]  
[-max_lines liness] [-list_annotated] [-list_not_annotated]
[-constant_arcs]  
report_arrival pin  
report_check_types [-violators] [-verbose] [-corner corner]  
[-format slack_only|end] [-max_delay] [-min_delay]
[-recovery] [-removal]  
[-clock_gating_setup] [-clock_gating_hold] [-max_slew]
[-min_slew]  
[-max_fanout] [-min_fanout] [-max_capacitance]
[-min_capacitance  
[-min_pulse_width] [-min_period] [-max_skew] [-net net]
[-digits digits  
[-no_line_splits] [> filename] [>> filename]  
report_checks [-from from_list|-rise_from from_list|-fall_from
from_list]  
[-through through_list|-rise_through through_list|-fall_through
through_list]  
[-to to_list|-rise_to to_list|-fall_to to_list]
[-unconstrained]  
[-path_delay
min|min_rise|min_fall|max|max_rise|max_fall|min_max]  
[-corner corner] [-group_path_count path_count]  
[-endpoint_path_count path_count]  
[-unique_paths_to_endpoint] [-slack_max slack_max]
[-slack_min slack_min]  
[-sort_by_slack] [-path_group group_name]  
[-format full|full_clock|full_clock_expanded|short|end|summary]  
...

Many reporting commands support redirection of the output to a file much
like a Unix shell.

report_checks -to out1 > path.log  
report_checks -to out2 >> path.log

# Debugging Timing

Here are some guidelines for debugging your design if static timing does
not report any paths, or does not report the expected paths.

Debugging timing problems generally involves using the following
commands to follow the propagation of arrival times from a known arrival
downstream to understand why the arrival times are not propagating:

report_edges  
report_arrivals  
report_net

report_edges -from can be used to walk forward and report_edges -to to
walk backward in the netlist/timing graph. report_arrivals shows the
min/max rise/fall arrival times with respect to each clock that has a
path to the pin. report_net shows connections to a net across hierarchy
levels.

## No paths found

The report_checks command only reports paths that are constrained by
timing checks or SDC commands such as set_output_delay. If the design
has only combinational logic (no registers or latches), there are no
timing checks, so no paths are reported. Use the -unconstrained option
to report_checks to see unconstrained paths.

% report_checks -unconstrained

If the design is sequential (has registers or latches) and no paths are
reported, it is likely that there is a problem with the clock
propagation. Check the timing at an register in the design with the
report_arrivals command.

% report_arrivals r1/CP  
(clk ^) r 0.00:0.00 f INF:-INF  
(clk v) r INF:-INF f 5.00:5.00

In this example the rising edge of the clock "clk" causes the rising
arrival min:max time at 0.00, and the falling edge arrives at 5.00.
Since the rising edge of the clock causes the rising edge of the
register clock pin, the clock path is positive unate.

The clock path should be positive or negative unate. Something is
probably wrong with the clock network if it is non-unate. A non-unate
clock path will report arrivals similar to the foillowing:

% report_arrivals r1/CP  
(clk ^) r 0.00:0.00 f 0.00:0.00  
(clk v) r 5.00:5.00 f 5.00:5.00

Notice that each clock edge causes both rise and fall arrivals at the
register clock pin.

If there are no paths to the register clock pin, nothing is printed. Use
the report_edges -to command to find the gate driving the clock pin.

% report_edges -to r1/CP  
i1/ZN -> CP wire  
^ -> ^ 0.00:0.00  
v -> v 0.00:0.00

This shows that the gate/pin i1/ZN is driving the clock pin. The
report_edges -to commond can be used to walk backward or forward
through the netlist one gate/net at a time. By checking the arrivals
with the report_arrival command you can determine where the path is
broken.

## No path reported an endpoint

In order for a timing check to be reported, there must be an arrival
time at the data pin (the constrained pin) as well as the timing check
clock pin. If report_checks -to a register input does not report any
paths, check that the input is constrained by a timing check with
report_edges -to.

% report_edges -to r1/D  
CP -> D hold  
^ -> ^ -0.04:-0.04  
^ -> v -0.03:-0.03  
CP -> D setup  
^ -> ^ 0.09:0.0  
^ -> v 0.08:0.08  
in1 -> D wire  
^ -> ^ 0.00:0.00  
v -> v 0.00:0.00

This reports the setup and hold checks for the D pin of r1.

Next, check the arrival times at the D and CP pins of the register with
report_arrivals.

% report_arrivals r1/D  
(clk1 ^) r 1.00:1.00 f 1.00:1.00  
% report_arrivals r1/CP  
(clk1 ^) r 0.00:0.00 f INF:-INF  
(clk1 v) r INF:-INF f 5.00:5.00

If there are no arrivals on an input port of the design, use the
set_input_delay command to specify the arrival times on the port.

# Commands

|                 |  |
| --------------- |  |
| **all_clocks** |  |

The all_clocks command returns a list of all clocks that have been
defined.

|                 |                                          |
| --------------- | ---------------------------------------- |
| **all_inputs** | [-no_clocks]                          |
| -no_clocks    | Exclude inputs defined as clock sources. |

The all_inputs command returns a list of all input and bidirect ports
of the current design.

|                  |  |
| ---------------- |  |
| **all_outputs** |  |

The all_outputs command returns a list of all output and bidirect ports
of the design.

<table>
<tbody>
<tr class="odd">
<td><strong>all_registers</strong></td>
<td>[-clock <em>clock_names</em>]<br />
[-cells | -data_pins | -clock_pins | -async_pins<br />
| ‑output_pins]<br />
[-level_sensitive]<br />
[-edge_triggered]</td>
</tr>
<tr class="even">
<td>-clock <em>clock_names</em></td>
<td>A list of clock names. Only registers clocked by these clocks are returned.</td>
</tr>
<tr class="odd">
<td>-cells</td>
<td>Return a list of register instances.</td>
</tr>
<tr class="even">
<td>-data_pins</td>
<td>Return the register data pins.</td>
</tr>
<tr class="odd">
<td>-clock_pins</td>
<td>Return the register clock pins.</td>
</tr>
<tr class="even">
<td>-async_pins</td>
<td>Return the register set/clear pins.</td>
</tr>
<tr class="odd">
<td>-output_pins</td>
<td>Return the register output pins.</td>
</tr>
<tr class="even">
<td>-level_sensitive</td>
<td>Return level-sensitive latches.</td>
</tr>
<tr class="odd">
<td>-edge_triggered</td>
<td>Return edge-triggered registers.</td>
</tr>
</tbody>
</table>

The all_registers command returns a list of register instances or
register pins in the design. Options allow the list of registers to be
restricted in various ways. The -clock keyword restrcts the registers to
those that are clocked by a set of clocks. The -cells option returns the
list of registers or latches (the default). The -‑data_pins,
-clock_pins, -async_pins and -output_pins options cause
all_registers to return a list of register pins rather than instances.

<table>
<tbody>
<tr class="odd">
<td><strong>check_setup</strong></td>
<td>[-verbose]<br />
[-unconstrained_endpoints]<br />
[-multiple_clock]<br />
[-no_clock]<br />
[-no_input_delay]<br />
[-loops]<br />
[-generated_clocks]<br />
[&gt; <em>filename</em>]<br />
[&gt;&gt; <em>filename</em>]</td>
</tr>
<tr class="even">
<td>-verbose</td>
<td>Show offending objects rather than just error counts.</td>
</tr>
<tr class="odd">
<td>-unconstrained_endpoints</td>
<td>Check path endpoints for timing constraints (timing check or set_output_delay).</td>
</tr>
<tr class="even">
<td>-multiple_clock</td>
<td>Check register/latch clock pins for multiple clocks.</td>
</tr>
<tr class="odd">
<td>-no_clock</td>
<td>Check register/latch clock pins for a clock.</td>
</tr>
<tr class="even">
<td>-no_input_delay</td>
<td>Check for inputs that do not have a set_input_delay command.</td>
</tr>
<tr class="odd">
<td>-loops</td>
<td>Check for combinational logic loops.</td>
</tr>
<tr class="even">
<td>-generated_clocks</td>
<td>Check that generated clock source pins have been defined as clocks.</td>
</tr>
</tbody>
</table>

The check_setup command performs sanity checks on the design.
Individual checks can be performed with the keywords. If no check
keywords are specified all checks are performed. Checks that fail are
reported as warnings. If no checks fail nothing is reported. The command
returns 1 if there are no warnings for use in scripts.

<table>
<tbody>
<tr class="odd">
<td><strong>connect_pin</strong></td>
<td><em>net<br />
port</em>|<em>pin</em></td>
</tr>
<tr class="even">
<td><em>net</em></td>
<td>A net to add connections to.</td>
</tr>
<tr class="odd">
<td><em>port</em></td>
<td>A port to connect to <em>net</em>.</td>
</tr>
<tr class="even">
<td><em>Pin</em></td>
<td>A pin to connect to <em>net</em>.</td>
</tr>
</tbody>
</table>

The connect_pin command connects a port or instance pin to a net.

<table>
<tbody>
<tr class="odd">
<td><strong>create_clock</strong></td>
<td>-period <em>period</em><br />
[-name <em>clock_name</em>]<br />
[-waveform <em>edge_list</em>]<br />
[-add]<br />
[<em>pin_list</em>]</td>
</tr>
<tr class="even">
<td>-period <em>period</em></td>
<td>The clock period.</td>
</tr>
<tr class="odd">
<td>-name <em>clock_name</em></td>
<td>The name of the clock.</td>
</tr>
<tr class="even">
<td>-waveform <em>edge_list</em></td>
<td>A list of edge rise and fall time.</td>
</tr>
<tr class="odd">
<td>-add</td>
<td>Add this clock to the clocks on <em>pin_list</em>.</td>
</tr>
<tr class="even">
<td><em>pin_list</em></td>
<td>A list of pins driven by the clock.</td>
</tr>
</tbody>
</table>

The create_clock command defines the waveform of a clock used by the
design.

If no *pin_list* is specified the clock is *virtual*. A virtual clock
can be refered to by name in input arrival and departure time commands
but is not attached to any pins in the design.

If no clock name is specified the name of the first pin is used as the
clock name.

If a wavform is not specified the clock rises at zero and falls at half
the clock period. The waveform is a list with time the clock rises as
the first element and the time it falls as the second element.

If a clock is already defined on a pin the clock is redefined using the
new clock parameters. If multiple clocks drive the same pin, use the
-add option to prevent the existing definition from being overwritten.

The following command creates a clock with a period of 10 time units
that rises at time 0 and falls at 5 time units on the pin named clk1.

create_clock -period 10 clk1

The following command creates a clock with a period of 10 time units
that is high at time zero, falls at time 2 and rises at time 8. The
clock drives three pins named clk1, clk2, and clk3.

create_clock -period 10 -waveform {8 2} -name clk {clk1 clk2 clk3}

<table>
<tbody>
<tr class="odd">
<td><strong>create_generated_clock</strong></td>
<td>[-name <em>clock_name</em>]<br />
-source <em>master_pin<br />
</em>[-master_clock <em>master_clock</em>]<br />
[-divide_by <em>divisor</em>]<br />
[-multiply_by <em>multiplier</em>]<br />
[-duty_cycle duty_cycle]<br />
[-invert]<br />
[-edges <em>edge_list</em>]<br />
[-edge_shift <em>shift_list</em>]<br />
[-add]<br />
<em>pin_list</em></td>
</tr>
<tr class="even">
<td>-name <em>clock_name</em></td>
<td>The name of the generated clock.</td>
</tr>
<tr class="odd">
<td>-source <em>master_pin</em></td>
<td>A pin or port in the fanout of the master clock that is the source of the generated clock.</td>
</tr>
<tr class="even">
<td>-master_clock <em>master_clock</em></td>
<td>Use -master_clock to specify which source clock to use when multiple clocks are present on <em>master_pin</em>.</td>
</tr>
<tr class="odd">
<td>-divide_by <em>divisor</em></td>
<td>Divide the master clock period by <em>divisor</em>.</td>
</tr>
<tr class="even">
<td>-multiply_by <em>multiplier</em></td>
<td>Multiply the master clock period by <em>multiplier</em>.</td>
</tr>
<tr class="odd">
<td>-duty_cycle <em>duty_cycle</em></td>
<td>The percent of the period that the generated clock is high (between 0 and 100).</td>
</tr>
<tr class="even">
<td>-invert</td>
<td>Invert the master clock.</td>
</tr>
<tr class="odd">
<td>-edges <em>edge_list</em></td>
<td>List of master clock edges to use in the generated clock. Edges are numbered from 1. edge_list must be 3 edges long.</td>
</tr>
<tr class="even">
<td>-edge_shift <em>shift_list</em></td>
<td>Not supported.</td>
</tr>
<tr class="odd">
<td>-add</td>
<td>Add this clock to the existing clocks on <em>pin_list</em>.</td>
</tr>
<tr class="even">
<td><em>pin_list</em></td>
<td>A list of pins driven by the generated clock.</td>
</tr>
</tbody>
</table>

The create_generated_clock command is used to generate a clock from an
existing clock definition. It is used to model clock generation circuits
such as clock dividers and phase locked loops.

The -divide_by, -multiply_by and -edges arguments are mutually
exclusive.

The -multiply_by option is used to generate a higher frequency clock
from the source clock. The period of the generated clock is divided by
*multiplier*. The clock *multiplier* must be a positive integer. If a
duty cycle is specified the generated clock rises at zero and falls at
period * duty_cycle / 100. If no duty cycle is specified the source
clock edge times are divided by *multiplier*.

The -divide_by option is used to generate a lower frequency clock from
the source clock. The clock *divisor* must be a positive integer. If the
clock divisor is a power of two the source clock period is multiplied by
*divisor*, the clock rise time is the same as the source clock, and the
clock fall edge is one half period later. If the clock divisor is not a
power of two the source clock waveform edge times are multiplied by
*divisor*.

The -edges option forms the generated clock waveform by selecting edges
from the source clock waveform.

If the -invert option is specified the waveform derived above is
inverted.

If a clock is already defined on a pin the clock is redefined using the
new clock parameters. If multiple clocks drive the same pin, use the
-add option to prevent the existing definition from being overwritten.

In the example show below generates a clock named gclk1 on register
output pin r1/Q by dividing it by four.

create_clock -period 10 -waveform {1 8} clk1  
create_generated_clock -name gclk1 -source clk1 -divide_by 4 r1/Q

The generated clock has a period of 40, rises at time 1 and falls at
time 21.

In the example shown below the duty cycle is used to define the derived
clock waveform.

create_generated_clock -name gclk1 -source clk1 -duty_cycle 50 \\  
-multiply_by 2 r1/Q

The generated clock has a period of 5, rises at time .5 and falls at
time 3.

In the example shown below the first, third and fifth source clock edges
are used to define the derived clock waveform.

create_generated_clock -name gclk1 -source clk1 -edges {1 3 5} r1/Q

The generated clock has a period of 20, rises at time 1 and falls at
time 11.

<table>
<tbody>
<tr class="odd">
<td><strong>create_voltage_area</strong></td>
<td><em>[-name name]<br />
[-coordinate coordinates]<br />
[-guard_band_x guard_x]<br />
[-guard_band_y guard_y]<br />
cells</em></td>
</tr>
</tbody>
</table>

This command is parsed and ignored by timing analysis.

|                     |              |
| ------------------- | ------------ |
| **current_design** | [*design*] |

|                       |                |
| --------------------- | -------------- |
| **current_instance** | [*instance*] |
| *instance*            | Not supported. |

|                     |                                         |
| ------------------- | --------------------------------------- |
| **define_corners** | *corner1* *[corner2]...*              |
| *corner*            | The name of a delay calculation corner. |

Use the define_corners command to define the names of multiple
process/temperature/voltage corners. The define_corners command must
follow set_operating_conditions -analysis_type and precede any
reference to the corner names and can only appear once in a command
file. There is no support for re-defining corners.

For analysis type single, each corner has one delay calculation result
and early/late path arrivals. For analysis type best_case/worst_case
and on_chip_variation, each corner has min/max delay calculation
results and early/late path arrivals.

|                   |                             |
| ----------------- | --------------------------- |
| **delete_clock** | [-all] *clocks*           |
| *clocks*          | A list of clocks to remove. |

|                        |                                          |
| ---------------------- | ---------------------------------------- |
| **delete_from_list** | *list objects*                           |
| *list*                 | *A list of objects.*                     |
| *objects*              | *A list of objects to delete from list.* |

|                              |                                       |
| ---------------------------- | ------------------------------------- |
| **delete_generated_clock** | [-all] *clocks*                     |
| *clocks*                     | A list of generated clocks to remove. |

|                      |                     |
| -------------------- | ------------------- |
| **delete_instance** | *instance*          |
| *instance*           | Instance to delete. |

The network editing command delete_instance removes an instance from
the design.

|                 |                |
| --------------- | -------------- |
| **delete_net** | *net*          |
| *net*           | Net to delete. |

The network editing command delete_net removes a net from the design.

<table>
<tbody>
<tr class="odd">
<td><strong>disconnect_pin</strong></td>
<td><em>net<br />
port</em> | <em>pin</em> | -all</td>
</tr>
<tr class="even">
<td><em>net</em></td>
<td>The net to disconnect pins from.</td>
</tr>
<tr class="odd">
<td><em>port</em></td>
<td>A port to connect to <em>net</em>.</td>
</tr>
<tr class="even">
<td><em>pin</em></td>
<td>A pin to connect to <em>net</em>.</td>
</tr>
<tr class="odd">
<td>-all</td>
<td>Disconnect all pins from the net.</td>
</tr>
</tbody>
</table>

Disconnects a port or pin from a net. Parasitics connected to the pin
are deleted.

|                        |  |
| ---------------------- |  |
| **elapsed_run_time** |  |

Returns the total clock run time in seconds as a float.

<table>
<tbody>
<tr class="odd">
<td><strong>find_timing_paths</strong></td>
<td>[-from <em>from_list</em><br />
|-rise_from <em>from_list</em><br />
|-fall_from <em>from_list</em>]<br />
[-through <em>through_list</em><br />
|-rise_through <em>through_list</em><br />
|-fall_through <em>through_list</em>]<br />
[-to <em>to_list</em><br />
|-rise_to <em>to_list</em><br />
|-fall_to <em>to_list</em>]<br />
[-unconstrained]<br />
[-path_delay min|min_rise|min_fall<br />
|max|max_rise|max_fall<br />
|min_max]<br />
[-group_path_count <em>path_count</em>]<br />
[-endpoint_path_count <em>endpoint_path_count</em>]<br />
[-unique_paths_to_endpoint]<br />
[-corner <em>corner</em>]<br />
[-slack_max <em>max_slack</em>]<br />
[-slack_min <em>min_slack</em>]<br />
[-sort_by_slack]<br />
[-path_group <em>groups</em>]</td>
</tr>
<tr class="even">
<td>-from <em>from_list</em></td>
<td>Return paths from a list of clocks, instances, ports, register clock pins, or latch data pins.</td>
</tr>
<tr class="odd">
<td>-rise_from <em>from_list</em></td>
<td>Return paths from the rising edge of clocks, instances, ports, register clock pins, or latch data pins.</td>
</tr>
<tr class="even">
<td>-fall_from <em>from_list</em></td>
<td>Return paths from the falling edge of clocks, instances, ports, register clock pins, or latch data pins.</td>
</tr>
<tr class="odd">
<td>-through <em>through_list</em></td>
<td>Return paths through a list of instances, pins or nets.</td>
</tr>
<tr class="even">
<td>-rise_through <em>through_list</em></td>
<td>Return rising paths through a list of instances, pins or nets.</td>
</tr>
<tr class="odd">
<td>-fall_through <em>through_list</em></td>
<td>Return falling paths through a list of instances, pins or nets.</td>
</tr>
<tr class="even">
<td>-to <em>to_list</em></td>
<td>Return paths to a list of clocks, instances, ports or pins.</td>
</tr>
<tr class="odd">
<td>-rise_to <em>to_list</em></td>
<td>Return rising paths to a list of clocks, instances, ports or pins.</td>
</tr>
<tr class="even">
<td>-fall_to <em>to_list</em></td>
<td>Return falling paths to a list of clocks, instances, ports or pins.</td>
</tr>
<tr class="odd">
<td>-unconstrained</td>
<td>Report unconstrained paths also.</td>
</tr>
<tr class="even">
<td>-path_delay min</td>
<td>Return min path (hold) checks.</td>
</tr>
<tr class="odd">
<td>-path_delay min_rise</td>
<td>Return min path (hold) checks for rising endpoints.</td>
</tr>
<tr class="even">
<td>-path_delay min_fall</td>
<td>Return min path (hold) checks for falling endpoints.</td>
</tr>
<tr class="odd">
<td>-path_delay max</td>
<td>Return max path (setup) checks.</td>
</tr>
<tr class="even">
<td>-path_delay max_rise</td>
<td>Return max path (setup) checks for rising endpoints.</td>
</tr>
<tr class="odd">
<td>-path_delay max_fall</td>
<td>Return max path (setup) checks for falling endpoints.</td>
</tr>
<tr class="even">
<td>-path_delay min_max</td>
<td>Return max and max path (setup and hold) checks.</td>
</tr>
<tr class="odd">
<td>-group_path_count <em>path_count</em></td>
<td>The number of paths to return in each path group.</td>
</tr>
<tr class="even">
<td>-endpoint_path_count <em>endpoint_path_count</em></td>
<td>The number of paths to return for each endpoint.</td>
</tr>
<tr class="odd">
<td>‑unique_paths_to_endpoint</td>
<td>Return multiple paths to an endpoint that traverse different pins without showing multiple paths with different rise/fall transitions.</td>
</tr>
<tr class="even">
<td>-corner <em>corner</em></td>
<td>Return paths for one process corner.</td>
</tr>
<tr class="odd">
<td>-slack_max <em>max_slack</em></td>
<td>Return paths with slack less than <em>max_slack</em>.</td>
</tr>
<tr class="even">
<td>-slack_min <em>min_slack</em></td>
<td>Return paths with slack greater than <em>min_slack</em>.</td>
</tr>
<tr class="odd">
<td>-sort_by_slack</td>
<td>Sort paths by slack rather than slack within path groups.</td>
</tr>
<tr class="even">
<td>-path_group <em>groups</em></td>
<td>Return paths in path groups. Paths in all groups are returned if this option is not specified.</td>
</tr>
</tbody>
</table>

The find_timing_paths command returns a list of path objects for
scripting. Use the get_property function to access properties of the
paths.

<table>
<tbody>
<tr class="odd">
<td><strong>get_cells</strong></td>
<td>[-hierarchical]<br />
[-hsc <em>separator</em>]<br />
[-filter <em>expr</em>]<br />
[-regexp]<br />
[-nocase]<em><br />
</em>[-quiet]<br />
[-of_objects <em>objects</em>]<br />
[<em>patterns</em>]</td>
</tr>
<tr class="even">
<td>-hierarchical</td>
<td>Searches hierarchy levels below the current instance for matches.</td>
</tr>
<tr class="odd">
<td>-hsc <em>separator</em></td>
<td>Character to use to separate hierarchical instance names in <em>patterns.</em></td>
</tr>
<tr class="even">
<td>-filter <em>expr</em></td>
<td>A filter expression of the form<br />
“<em>property==value”<br />
</em>where <em>property</em> is a property supported by the get_property command. See the section “Filter Expressions” for additional forms.</td>
</tr>
<tr class="odd">
<td>-regexp</td>
<td>Use regular expression matching instead of glob pattern matching.</td>
</tr>
<tr class="even">
<td>-nocase</td>
<td>Ignore case when matching. Only valid with –regexp.</td>
</tr>
<tr class="odd">
<td>-quiet</td>
<td>Do not warn if no matches are found.</td>
</tr>
<tr class="even">
<td>-of_objects <em>objects</em></td>
<td>The name of a pin or net, a list of pins returned by get_pins, or a list of nets returned by get_nets. The –hierarchical option cannot be used with ‑of_objects.</td>
</tr>
<tr class="odd">
<td><em>patterns</em></td>
<td>A list of instance name patterns.</td>
</tr>
</tbody>
</table>

The get_cells command returns a list of all cell instances that match
*patterns*.

<table>
<tbody>
<tr class="odd">
<td><strong>get_clocks</strong></td>
<td>[-regexp]<br />
[-nocase]<br />
[-filter <em>expr</em>]<br />
[-quiet]<em><br />
patterns</em></td>
</tr>
<tr class="even">
<td>-regexp</td>
<td>Use regular expression matching instead of glob pattern matching.</td>
</tr>
<tr class="odd">
<td>-nocase</td>
<td>Ignore case when matching. Only valid with –regexp.</td>
</tr>
<tr class="even">
<td>-filter <em>expr</em></td>
<td>A filter expression of the form<br />
“<em>property==value”<br />
</em>where <em>property</em> is a property supported by the get_property command. See the section “Filter Expressions” for additional forms.</td>
</tr>
<tr class="odd">
<td>-quiet</td>
<td>Do not warn if no matches are found.</td>
</tr>
<tr class="even">
<td><em>patterns</em></td>
<td>A list of clock name patterns.</td>
</tr>
</tbody>
</table>

The get_clocks command returns a list of all clocks that have been
defined.

<table>
<tbody>
<tr class="odd">
<td><strong>get_fanin</strong></td>
<td>-to <em>sink_list</em><br />
[-flat]<br />
[-only_cells]<br />
[-startpoints_only]<br />
[-levels <em>level_count</em>]<br />
[-pin_levels <em>pin_count</em>]<br />
[-trace_arcs timing|enabled|all]</td>
</tr>
<tr class="even">
<td>-to <em>sink_list</em></td>
<td>List of pins, ports, or nets to find the fanin of. For nets, the fanin of driver pins on the nets are returned.</td>
</tr>
<tr class="odd">
<td>-flat</td>
<td>With –flat pins in the fanin at any hierarchy level are returned. Without ‑flat only pins at the same hierarchy level as the sinks are returned.</td>
</tr>
<tr class="even">
<td>-only_cells</td>
<td>Return the instances connected to the pins in the fanin.</td>
</tr>
<tr class="odd">
<td>-startpoints_only</td>
<td>Only return pins that are startpoints.</td>
</tr>
<tr class="even">
<td>-level <em>level_count</em></td>
<td>Only return pins within <em>level_count</em> instance traversals.</td>
</tr>
<tr class="odd">
<td>-pin_levels <em>pin_count</em></td>
<td>Only return pins within <em>pin_count</em> pin traversals.</td>
</tr>
<tr class="even">
<td>-trace_arcs timing</td>
<td>Only trace through timing arcs that are not disabled.</td>
</tr>
<tr class="odd">
<td>-trace_arcs enabled</td>
<td>Only trace through timing arcs that are not disabled.</td>
</tr>
<tr class="even">
<td>-trace_arcs all</td>
<td>Trace through all arcs, including disabled ones.</td>
</tr>
</tbody>
</table>

The get_fanin command returns traverses the design from *sink_list*
pins, ports or nets backwards and return the fanin pins or instances.

<table>
<tbody>
<tr class="odd">
<td><strong>get_fanout</strong></td>
<td>-from <em>source_list</em><br />
[-flat]<br />
[-only_cells]<br />
[-endpoints_only]<br />
[-levels <em>level_count</em>]<br />
[-pin_levels <em>pin_count</em>]<br />
[-trace_arcs timing|enabled|all]</td>
</tr>
<tr class="even">
<td>-from <em>source_list</em></td>
<td>List of pins, ports, or nets to find the fanout of. For nets, the fanout of load pins on the nets are returned.</td>
</tr>
<tr class="odd">
<td>-flat</td>
<td>With –flat pins in the fanin at any hierarchy level are returned. Without ‑flat only pins at the same hierarchy level as the sinks are returned.</td>
</tr>
<tr class="even">
<td>-only_cells</td>
<td>Return the instances connected to the pins in the fanout.</td>
</tr>
<tr class="odd">
<td>-endpoints_only</td>
<td>Only return pins that are endpoints.</td>
</tr>
<tr class="even">
<td>-level <em>level_count</em></td>
<td>Only return pins within <em>level_count</em> instance traversals.</td>
</tr>
<tr class="odd">
<td>-pin_levels <em>pin_count</em></td>
<td>Only return pins within <em>pin_count</em> pin traversals.</td>
</tr>
<tr class="even">
<td>-trace_arcs timing</td>
<td>Only trace through timing arcs that are not disabled.</td>
</tr>
<tr class="odd">
<td>-trace_arcs enabled</td>
<td>Only trace through timing arcs that are not disabled.</td>
</tr>
<tr class="even">
<td>-trace_arcs all</td>
<td>Trace through all arcs, including disabled ones.</td>
</tr>
</tbody>
</table>

The get_fanout command returns traverses the design from *source_list*
pins, ports or nets backwards and return the fanout pins or instances.

|                     |                                                            |
| ------------------- | ---------------------------------------------------------- |
| **get_full_name** | *object*                                                   |
| *object*            | A library, cell, port, instance, pin or timing arc object. |

Return the name of *object*. Equivalent to [get_property *object*
full_name].

<table>
<tbody>
<tr class="odd">
<td><strong>get_lib_cells</strong></td>
<td>[-of_objects <em>objects</em>]<br />
[-hsc <em>separator</em>]<br />
[-filter <em>expr</em>]<br />
[-regexp]<br />
[-nocase]<br />
[-quiet]<em><br />
patterns</em></td>
</tr>
<tr class="even">
<td><em>-of_objects objects</em></td>
<td>A list of instance objects.</td>
</tr>
<tr class="odd">
<td>-hsc <em>separator</em></td>
<td>Character that separates the library name and cell name in <em>patterns</em>. Defaults to ‘/’.</td>
</tr>
<tr class="even">
<td>-filter <em>expr</em></td>
<td>A filter expression of the form<br />
“<em>property==value”<br />
</em>where <em>property</em> is a property supported by the get_property command. See the section “Filter Expressions” for additional forms.</td>
</tr>
<tr class="odd">
<td>-regexp</td>
<td>Use regular expression matching instead of glob pattern matching.</td>
</tr>
<tr class="even">
<td>-nocase</td>
<td>Ignore case when matching. Only valid with –regexp.</td>
</tr>
<tr class="odd">
<td>-quiet</td>
<td>Do not warn if no matches are found.</td>
</tr>
<tr class="even">
<td><em>patterns</em></td>
<td>A list of library cell name patterns of the form library_name/cell_name.</td>
</tr>
</tbody>
</table>

The get_lib_cells command returns a list of library cells that match
*pattern*. The library name can be prepended to the cell name pattern
with the *separator* character, which defaults to hierarchy_separator.

<table>
<tbody>
<tr class="odd">
<td><strong>get_lib_pins</strong></td>
<td>[-of_objects <em>objects</em>]<br />
[-hsc <em>separator</em>]<br />
[-filter <em>expr</em>]<br />
[-regexp]<br />
[-nocase]<br />
[-quiet]<em><br />
patterns</em></td>
</tr>
<tr class="even">
<td><em>-of_objects objects</em></td>
<td>A list of library cell objects.</td>
</tr>
<tr class="odd">
<td>-hsc <em>separator</em></td>
<td>Character that separates the library name, cell name and port name in <em>pattern</em>. Defaults to ‘/’.</td>
</tr>
<tr class="even">
<td>-filter <em>expr</em></td>
<td>A filter expression of the form<br />
“<em>property==value”<br />
</em>where <em>property</em> is a property supported by the get_property command. See the section “Filter Expressions” for additional forms.</td>
</tr>
<tr class="odd">
<td>-regexp</td>
<td>Use regular expression matching instead of glob pattern matching.</td>
</tr>
<tr class="even">
<td>-nocase</td>
<td>Ignore case when matching. Only valid with –regexp.</td>
</tr>
<tr class="odd">
<td>-quiet</td>
<td>Do not warn if no matches are found.</td>
</tr>
<tr class="even">
<td><em>patterns</em></td>
<td>A list of library port name patterns of the form library_name/cell_name/port_name.</td>
</tr>
</tbody>
</table>

The get_lib_pins command returns a list of library ports that match
*pattern*. Use *separator* to separate the library and cell name
patterns from the port name in *pattern*.

<table>
<tbody>
<tr class="odd">
<td><strong>get_libs</strong></td>
<td>[-filter <em>expr</em>]<br />
[-regexp]<br />
[-nocase]<br />
[-quiet]<em><br />
patterns</em></td>
</tr>
<tr class="even">
<td>-filter <em>expr</em></td>
<td>A filter expression of the form<br />
“<em>property==value”<br />
</em>where <em>property</em> is a property supported by the get_property command. See the section “Filter Expressions” for additional forms.</td>
</tr>
<tr class="odd">
<td>-regexp</td>
<td>Use regular expression matching instead of glob pattern matching.</td>
</tr>
<tr class="even">
<td>-nocase</td>
<td>Ignore case when matching. Only valid with –regexp.</td>
</tr>
<tr class="odd">
<td>-quiet</td>
<td>Do not warn if no matches are found.</td>
</tr>
<tr class="even">
<td><em>patterns</em></td>
<td>A list of library name patterns.</td>
</tr>
</tbody>
</table>

The get_libs command returns a list of clocks that match *patterns*.

<table>
<tbody>
<tr class="odd">
<td><strong>get_nets</strong></td>
<td>[-hierarchical]<br />
[-hsc <em>separator</em>]<br />
[-filter <em>expr</em>]<br />
[-regexp]<br />
[-nocase]<br />
[-quiet]<em><br />
</em>[-of_objects <em>objects</em>]<br />
[<em>patterns</em>]</td>
</tr>
<tr class="even">
<td>-hierarchical</td>
<td>Searches hierarchy levels below the current instance for matches.</td>
</tr>
<tr class="odd">
<td>-hsc <em>separator</em></td>
<td>Character that separates the library name, cell name and port name in <em>pattern</em>. Defaults to ‘/’.</td>
</tr>
<tr class="even">
<td>-filter <em>expr</em></td>
<td>A filter expression of the form<br />
“<em>property==value”<br />
</em>where <em>property</em> is a property supported by the get_property command. See the section “Filter Expressions” for additional forms.</td>
</tr>
<tr class="odd">
<td>-regexp</td>
<td>Use regular expression matching instead of glob pattern matching.</td>
</tr>
<tr class="even">
<td>-nocase</td>
<td>Ignore case when matching. Only valid with –regexp.</td>
</tr>
<tr class="odd">
<td>-quiet</td>
<td>Do not warn if no matches are found.</td>
</tr>
<tr class="even">
<td>-of_objects <em>objects</em></td>
<td>The name of a pin or instance, a list of pins returned by get_pins, or a list of instances returned by get_cells. The –hierarchical option cannot be used with –of_objects.</td>
</tr>
<tr class="odd">
<td><em>patterns</em></td>
<td>A list of net name patterns.</td>
</tr>
</tbody>
</table>

The get_nets command returns a list of all nets that match *patterns*.

|               |                                                            |
| ------------- | ---------------------------------------------------------- |
| **get_name** | *object*                                                   |
| *object*      | A library, cell, port, instance, pin or timing arc object. |

Return the name of *object*. Equivalent to [get_property *object*
name].

<table>
<tbody>
<tr class="odd">
<td><strong>get_pins</strong></td>
<td>[-hierarchical]<br />
[-hsc <em>separator</em>]<br />
[-filter <em>expr</em>]<br />
[-regexp]<br />
[-nocase]<br />
[-quiet]<br />
[-of_objects <em>objects</em>]<br />
[<em>patterns</em>]</td>
</tr>
<tr class="even">
<td>-hierarchical</td>
<td>Searches hierarchy levels below the current instance for matches.</td>
</tr>
<tr class="odd">
<td>-hsc <em>separator</em></td>
<td>Character that separates the library name, cell name and port name in <em>pattern</em>. Defaults to ‘/’.</td>
</tr>
<tr class="even">
<td>-filter <em>expr</em></td>
<td>A filter expression of the form<br />
“<em>property==value”<br />
</em>where <em>property</em> is a property supported by the get_property command. See the section “Filter Expressions” for additional forms.</td>
</tr>
<tr class="odd">
<td>-nocase</td>
<td>Ignore case when matching. Only valid with –regexp.</td>
</tr>
<tr class="even">
<td>-quiet</td>
<td>Do not warn if no matches are found.</td>
</tr>
<tr class="odd">
<td>-of_objects <em>objects</em></td>
<td>The name of a net or instance, a list of nets returned by get_nets, or a list of instances returned by get_cells. The –hierarchical option cannot be used with –of_objects.</td>
</tr>
<tr class="even">
<td><em>patterns</em></td>
<td>A list of pin name patterns.</td>
</tr>
</tbody>
</table>

The get_pins command returns a list of all instance pins that match
*patterns*.

A useful idiom to find the driver pin for a net is the following.

get_pins -of_objects [get_net *net_name*] -filter
“direction==output”

<table>
<tbody>
<tr class="odd">
<td><strong>get_ports</strong></td>
<td>[-filter <em>expr</em>]<br />
[-regexp]<br />
[-nocase]<br />
[-quiet]<br />
[-of_objects <em>objects</em>]<br />
[<em>patterns</em>]</td>
</tr>
<tr class="even">
<td>-filter <em>expr</em></td>
<td>A filter expression of the form<br />
“<em>property==value”<br />
</em>where <em>property</em> is a property supported by the get_property command. See the section “Filter Expressions” for additional forms.</td>
</tr>
<tr class="odd">
<td>-regexp</td>
<td>Use regular expression matching instead of glob pattern matching.</td>
</tr>
<tr class="even">
<td>-nocase</td>
<td>Ignore case when matching. Only valid with –regexp.</td>
</tr>
<tr class="odd">
<td>-quiet</td>
<td>Do not warn if no matches are found.</td>
</tr>
<tr class="even">
<td>-of_objects <em>objects</em></td>
<td>The name of net or a list of nets returned by get_nets.</td>
</tr>
<tr class="odd">
<td><em>patterns</em></td>
<td>A list of port name patterns.</td>
</tr>
</tbody>
</table>

The get_ports command returns a list of all top level ports that match
*patterns*.

<table>
<tbody>
<tr class="odd">
<td><strong>get_property</strong></td>
<td>[-object_type <em>object_type</em>]<br />
<em>object</em><br />
<em>property</em></td>
</tr>
<tr class="even">
<td><em>-object_type object_type</em></td>
<td>The type of <em>object</em> when it is specified as a name.<br />
cell|pin|net|port|clock|library|library_cell|library_pin|timing_arc</td>
</tr>
<tr class="odd">
<td><em>object</em></td>
<td>An object returned by get_cells, get_pins, get_nets, get_ports, get_clocks, get_libs, get_lib_cells, get_lib_pins, or get_timing_arcs, or object name. ‑object_type is required if <em>object</em> is a name.</td>
</tr>
<tr class="even">
<td><em>property</em></td>
<td>A property name.</td>
</tr>
</tbody>
</table>

The properties for different objects types are shown below.

cell (SDC lib_cell)

base_name  
filename  
full_name  
library  
name

clock

full_name  
is_generated  
is_propagated  
is_virtual  
name  
period  
sources

edge

delay_max_fall  
delay_min_fall  
delay_max_rise  
delay_min_rise  
full_name  
from_pin  
sense  
to_pin

instance (SDC cell)

cell  
full_name  
is_buffer  
is_clock_gate  
is_hierarchical  
is_inverter  
is_macro  
is_memory  
liberty_cell  
name  
ref_name

liberty_cell (SDC lib_cell)

area  
base_name  
dont_use  
filename  
full_name  
is_buffer  
is_inverter  
is_memory  
library  
name

liberty_port (SDC lib_pin)

capacitance  
direction  
drive_resistance  
drive_resistance_max_fall  
drive_resistance_max_rise  
drive_resistance_min_fall  
drive_resistance_min_rise  
full_name  
intrinsic_delay  
intrinsic_delay_max_fall  
intrinsic_delay_max_rise  
intrinsic_delay_min_fall  
intrinsic_delay_min_rise  
is_register_clock  
lib_cell  
name

library

filename (Liberty library only)  
name  
full_name

net

full_name  
name

path (PathEnd)

endpoint  
endpoint_clock  
endpoint_clock_pin  
slack  
startpoint  
startpoint_clock  
points

pin

activity (activity in transitions per second, duty cycle, origin)  
slew_max_fall  
slew_max_rise  
slew_min_fall  
slew_min_rise  
clocks  
clock_domains  
direction  
full_name  
is_hierarchical  
is_port  
is_register_clock  
lib_pin_name  
name  
slack_max  
slack_max_fall  
slack_max_rise  
slack_min  
slack_min_fall  
slack_min_rise

port

activity  
slew_max_fall  
slew_max_rise  
slew_min_fall  
slew_min_rise  
direction  
full_name  
liberty_port  
name  
slack_max  
slack_max_fall  
slack_max_rise  
slack_min  
slack_min_fall  
slack_min_rise

point (PathRef)

arrival  
pin  
required  
slack

<table>
<tbody>
<tr class="odd">
<td><strong>get_timing_edges</strong></td>
<td>[-from <em>from_pins</em>]<br />
[-to <em>to_pins</em>]<br />
[-of_objects <em>objects</em>]<br />
[-filter <em>expr</em>]<br />
[<em>patterns</em>]</td>
</tr>
<tr class="even">
<td>-f<em>ro</em>m <em>from_pin</em></td>
<td>A list of pins.</td>
</tr>
<tr class="odd">
<td>-to <em>to_pin</em></td>
<td>A list of pins.</td>
</tr>
<tr class="even">
<td>-of_objects <em>objects</em></td>
<td>A list of instances or library cells. The –from and -to options cannot be used with –of_objects.</td>
</tr>
<tr class="odd">
<td><em>-filte</em>r <em>expr</em></td>
<td>A filter expression of the form<br />
“<em>property==value”<br />
</em>where <em>property</em> is a property supported by the get_property command. See the section “Filter Expressions” for additional forms.</td>
</tr>
</tbody>
</table>

The get_timing_edges command returns a list of timing edges (arcs) to,
from or between pins. The result can be passed to get_property or
set_disable_timing.

<table>
<tbody>
<tr class="odd">
<td><strong>group_path</strong></td>
<td>-name <em>group_name<br />
</em>[-weight <em>weight</em>]<br />
[-critical_range <em>range</em>]<br />
[-from <em>from_list</em><br />
|-rise_from <em>from_list</em><br />
|-fall_from <em>from_list</em>]<br />
[-through <em>through_list</em>]<br />
[-rise_through <em>through_list</em>]<br />
[-fall_through <em>through_list</em>]<br />
[-to <em>to_list</em><br />
|-rise_to <em>to_list</em><br />
|-fall_to <em>to_list</em>]</td>
</tr>
<tr class="even">
<td>-name <em>group_name</em></td>
<td>The name of the path group.</td>
</tr>
<tr class="odd">
<td>-weight <em>weight</em></td>
<td>Not supported.</td>
</tr>
<tr class="even">
<td>-critical_range <em>range</em></td>
<td>Not supported.</td>
</tr>
<tr class="odd">
<td>-from <em>from_list</em></td>
<td>Group paths from a list of clocks, instances, ports, register clock pins, or latch data pins.</td>
</tr>
<tr class="even">
<td>-rise_from <em>from_list</em></td>
<td>Group paths from the rising edge of clocks, instances, ports, register clock pins, or latch data pins.</td>
</tr>
<tr class="odd">
<td>-fall_from <em>from_list</em></td>
<td>Group paths from the falling edge of clocks, instances, ports, register clock pins, or latch data pins.</td>
</tr>
<tr class="even">
<td>-through <em>through_list</em></td>
<td>Group paths through a list of instances, pins or nets.</td>
</tr>
<tr class="odd">
<td>-rise_through <em>through_list</em></td>
<td>Group rising paths through a list of instances, pins or nets.</td>
</tr>
<tr class="even">
<td>-fall_through <em>through_list</em></td>
<td>Group falling paths through a list of instances, pins or nets.</td>
</tr>
<tr class="odd">
<td>-to <em>to_list</em></td>
<td>Group paths to a list of clocks, instances, ports or pins.</td>
</tr>
<tr class="even">
<td>-rise_to <em>to_list</em></td>
<td>Group rising paths to a list of clocks, instances, ports or pins.</td>
</tr>
<tr class="odd">
<td>-fall_to <em>to_list</em></td>
<td>Group falling paths to a list of clocks, instances, ports or pins.</td>
</tr>
</tbody>
</table>

The group_path command is used to group paths reported by the
report_checks command. See set_false_path for a description of
allowed *from_list*, *through_list* and *to_list* objects.

<table>
<tbody>
<tr class="odd">
<td><strong>include</strong></td>
<td>[-echo|-e]<br />
[-verbose|-v]<em><br />
filename</em><br />
[&gt; <em>log_filename</em>]<br />
[&gt;&gt; log_<em>filename</em>]</td>
</tr>
<tr class="even">
<td>-echo|-e</td>
<td>Print each command before evaluating it.</td>
</tr>
<tr class="odd">
<td>-verbose|-v</td>
<td>Print each command before evaluating it as well as the result it returns.</td>
</tr>
<tr class="even">
<td><em>filename</em></td>
<td>The name of the file containing commands to read.</td>
</tr>
<tr class="odd">
<td>&gt; <em>log_filename</em></td>
<td>Redirect command output to log_filename.</td>
</tr>
<tr class="even">
<td>&gt;&gt; <em>log_filename</em></td>
<td>Redirect command output and append log_filename.</td>
</tr>
</tbody>
</table>

Read STA/SDC/Tcl commands from *filename*.

The include command stops and reports any errors encountered while
reading a file unless sta_continue_on_error is 1.

<table>
<tbody>
<tr class="odd">
<td><strong>link_design</strong></td>
<td>[-no_black_boxes]<br />
[<em>cell_name</em>]</td>
</tr>
<tr class="even">
<td>-no_black_boxes</td>
<td>Do not make empty “black box” cells for instances that reference undefined cells.</td>
</tr>
<tr class="odd">
<td><em>cell_name</em></td>
<td>The top level module/cell name of the design hierarchy to link.</td>
</tr>
</tbody>
</table>

Link (elaborate, flatten) the the top level cell *cell_name*. The
design must be linked after reading netlist and library files. The
default value of *cell_name* is the current design.

The linker creates empty "block box" cells for instances the reference
undefined cells when the variable link_create_black_boxes is true.
When link_create_black_boxes is false an error is reported and the
link fails.

The link_design command returns 1 if the link succeeds and 0 if it
fails.

<table>
<tbody>
<tr class="odd">
<td><strong>make_instance</strong></td>
<td><em>inst_path<br />
lib_cell</em></td>
</tr>
<tr class="even">
<td><em>inst_path</em></td>
<td>A hierarchical instance name.</td>
</tr>
<tr class="odd">
<td><em>lib_cell</em></td>
<td>The library cell of the new instance.</td>
</tr>
</tbody>
</table>

The make_instance command makes an instance of library cell
*lib_cell*.

|                   |                      |
| ----------------- | -------------------- |
| **make_net**     | *net_name_list*    |
| *net_name_list* | A list of net names. |

Creates a net for each hierarchical net name.

<table>
<tbody>
<tr class="odd">
<td><strong>read_liberty</strong></td>
<td>[-corner <em>corner</em>]<br />
[-min]<br />
[-max]<br />
[-infer_latches]<br />
<em>filename</em></td>
</tr>
<tr class="even">
<td>-corner <em>corner</em></td>
<td>Use the library for process corner <em>corner</em> delay calculation.</td>
</tr>
<tr class="odd">
<td>-min</td>
<td>Use library for min delay calculation.</td>
</tr>
<tr class="even">
<td>-max</td>
<td>Use library for max delay calculation.</td>
</tr>
<tr class="odd">
<td><em>filename</em></td>
<td>The liberty file name to read.</td>
</tr>
</tbody>
</table>

The read_liberty command reads a Liberty format library file. The first
library that is read sets the units used by SDC/TCL commands and
reporting. The include_file attribute is supported.

Some Liberty libraries do not include latch groups for cells that are
describe transparent latches. In that situation the -infer_latches
command flag can be used to infer the latches. The timing arcs required
for a latch to be inferred should look like the following:

cell (infered_latch) {  
pin(D) {  
direction : input ;  
timing () {  
related_pin : "E" ;  
timing_type : setup_falling ;  
}  
timing () {  
related_pin : "E" ;  
timing_type : hold_falling ;  
}  
}  
pin(E) {  
direction : input;  
}  
pin(Q) {  
direction : output ;  
timing () {  
related_pin : "D" ;  
}  
timing () {  
related_pin : "E" ;  
timing_type : rising_edge ;  
}  
}  
}

In this example a positive level-sensitive latch is inferred.

Files compressed with gzip are automatically uncompressed.

<table>
<tbody>
<tr class="odd">
<td><strong>read_saif</strong></td>
<td>[-scope <em>scope</em>]<br />
<em>filename</em></td>
</tr>
<tr class="even">
<td><em>scope</em></td>
<td>The SAIF scope of the current design to extract simulation data. Typically the test bench name and design under test instance name. Scope levels are separated with ‘/’.</td>
</tr>
<tr class="odd">
<td><em>filename</em></td>
<td>The name of the SAIF file to read.</td>
</tr>
</tbody>
</table>

The read_saif command reads a SAIF (Switching Activity Interchange
Format) file from a Verilog simulation and extracts pin activities and
duty cycles for use in power estimation. Files compressed with gzip are
supported. Annotated activities are propagated to the fanout of the
annotated pins.

<table>
<tbody>
<tr class="odd">
<td><strong>read_sdc</strong></td>
<td>[-echo]<br />
<em>filename</em></td>
</tr>
<tr class="even">
<td>-echo</td>
<td>Print each command before evaluating it.</td>
</tr>
<tr class="odd">
<td><em>filename</em></td>
<td>SDC command file.</td>
</tr>
</tbody>
</table>

Read SDC commands from *filename*.

The read_sdc command stops and reports any errors encountered while
reading a file unless sta_continue_on_error is 1.

Files compressed with gzip are automatically uncompressed.

<table>
<tbody>
<tr class="odd">
<td><strong>read_sdf</strong></td>
<td>[-corner <em>corner</em>]<br />
[-unescaped_dividers]<br />
<em>filename</em></td>
</tr>
<tr class="even">
<td>-corner <em>corner</em></td>
<td>Process corner delays to annotate.</td>
</tr>
<tr class="odd">
<td>-unescaped_dividers</td>
<td>With this option path names in the SDF do not have to escape hierarchy dividers when the path name is escaped. For example, the escaped Verilog name "\inst1/inst2 " can be referenced as "inst1/inst2". The correct SDF name is "inst1\/inst2", since the divider does not represent a change in hierarchy in this case.</td>
</tr>
<tr class="even">
<td><em>filename</em></td>
<td>The name of the SDF file to read.</td>
</tr>
</tbody>
</table>

Read SDF delays from a file. The min and max values in the SDF tuples
are used to annotate the delays for *corner*. The typical values in the
SDF tuples are ignored. If multiple corners are defined -corner must be
specified.

Files compressed with gzip are automatically uncompressed.

INCREMENT is supported as an alias for INCREMENTAL.

The following SDF statements are not supported.

PORT  
INSTANCE wildcards

<table>
<tbody>
<tr class="odd">
<td><strong>read_spef</strong></td>
<td>[-min]<br />
[-max]<br />
[-path path]<br />
[-corner <em>corner</em>]<br />
[-keep_capacitive_coupling]<br />
[-coupling_reduction_factor <em>factor</em>]<br />
[-reduce]<br />
<em>filename</em></td>
</tr>
<tr class="even">
<td>-min</td>
<td>Annotate parasitics for min delays.</td>
</tr>
<tr class="odd">
<td>-max</td>
<td>Annotate parasitics for max delays.</td>
</tr>
<tr class="even">
<td><em>path</em></td>
<td>Hierarchical block instance path to annotate with parasitics.</td>
</tr>
<tr class="odd">
<td>-corner <em>corner</em></td>
<td>Annotate parasitics for one process corner.</td>
</tr>
<tr class="even">
<td>‑keep_capacitive_coupling</td>
<td>Keep coupling capacitors in parasitic networks rather than converting them to grounded capacitors.</td>
</tr>
<tr class="odd">
<td><em>‑coupling_reduction_factor<br />
factor</em></td>
<td>Factor to multiply coupling capacitance by when reducing parasitic networks. The default value is 1.0.</td>
</tr>
<tr class="even">
<td>-reduce</td>
<td>Reduce detailed parasitics and do not save the detailed parastic network.</td>
</tr>
<tr class="odd">
<td><em>filename</em></td>
<td>The name of the parasitics file to read.</td>
</tr>
</tbody>
</table>

The read_spef command reads a file of net parasitics in SPEF format.
Use the ‑report_parasitic_annotation command to check for nets that
are not annotated.

Files compressed with gzip are automatically uncompressed.

Separate parasitics can be annotated for corners and min and max paths
using the -corner, –min and -max arguments. To use the same parastiics
for every corner and for min/max delay calculation read the SPEF without
-corner, -min, and -max options.

read_spef *spef1*

To use separate parastics for min/max delay, use the -min, and -max
options for each SPEF file.

read_spef -min *spef1  
*read_spef -max *spef2*

To use separate parastics for each corner, use the -corner option for
each SPEF file.

read_spef -corner ss *spef1  
*read_spef -corner tt spef2*  
*read_spef -corner ff *spef3*

To use separate parastics for each corner and separate min/max delay
calculation, use the -corner option along with the -min, and -max
options.

read_spef -corner ss -min *spef1  
*read_spef -corner ss -max spef2*  
*read_spef -corner ff -min spef*3  
*read_spef -corner ff -max spef*4*

With the -reduce option, the current delay calculator reduces the
parastic network to the appropriate type and deletes the parasitic
network. This substantially reduces the memory required to store the
parasitics.

Coupling capacitors are multiplied by the –coupling_reduction_factor
when a parasitic network is reduced.

The following SPEF constructs are ignored.

*DESIGN_FLOW (all values are ignored)  
*S slews  
*D driving cell  
*I pin capacitances (library cell capacitances are used instead)  
*Q r_net load poles  
*K r_net load residues

If the SPEF file contains triplet values the first value is used.

Parasitic networks (DSPEF) can be annotated on hierarchical blocks using
the -path argument to specify the instance path to the block. Parasitic
networks in the higher level netlist are stitched together at the
hierarchcal pins of the blocks.

<table>
<tbody>
<tr class="odd">
<td><strong>read_vcd</strong></td>
<td>[-scope <em>scope</em>]<br />
<em>filename</em></td>
</tr>
<tr class="even">
<td><em>scope</em></td>
<td>The VCD scope of the current design to extract simulation data. Typically the test bench name and design under test instance name. Scope levels are separated with ‘/’.</td>
</tr>
<tr class="odd">
<td><em>filename</em></td>
<td>The name of the VCD file to read.</td>
</tr>
</tbody>
</table>

The read_vcd command reads a VCD (Value Change Dump) file from a
Verilog simulation and extracts pin activities and duty cycles for use
in power estimation. Files compressed with gzip are supported. Annotated
activities are propagated to the fanout of the annotated pins.

|                   |                                       |
| ----------------- | ------------------------------------- |
| **read_verilog** | *filename*                            |
| *filename*        | The name of the verilog file to read. |

The read_verilog command reads a gate level verilog netlist. After all
verilog netlist and Liberty libraries are read the design must be linked
with the link_design command.

Verilog 2001 module port declaratations are supported. An example is
shown below.

module top (input in1, in2, clk1, clk2, clk3,  
output out);

Files compressed with gzip are automatically uncompressed.

<table>
<tbody>
<tr class="odd">
<td><strong>replace_cell</strong></td>
<td><em>instance_list<br />
replacement_cell</em></td>
</tr>
<tr class="even">
<td><em>instance_list</em></td>
<td>A list of instances to swap the cell.</td>
</tr>
<tr class="odd">
<td><em>replacement_cell</em></td>
<td>The replacement lib cell.</td>
</tr>
</tbody>
</table>

The replace_cell command changes the cell of an instance. The
replacement cell must have the same port list (number, name, and order)
as the instance's existing cell for the replacement to be successful.

<table>
<tbody>
<tr class="odd">
<td><strong>replace_activity_annotation</strong></td>
<td>[-report_unannotated]<br />
[-report_annotated]</td>
</tr>
<tr class="even">
<td>-report_unannotated</td>
<td>Report unannotated pins.</td>
</tr>
<tr class="odd">
<td>-report_unannotated</td>
<td>Report annotated pins.</td>
</tr>
</tbody>
</table>

Report a summary of pins that are annotated by read_vcd, read_saif or
set_power_activity. Sequential internal pins and hierarchical pins are
ignored.

<table>
<tbody>
<tr class="odd">
<td><strong>report_annotated_check</strong></td>
<td>[-setup]<br />
[-hold]<br />
[-recovery]<br />
[-removal]<br />
[-nochange]<br />
[-width]<br />
[-period]<br />
[-max_skew]<br />
[-max_line <em>lines</em>]<br />
[-report_annotated]<br />
[-report_unannotated]<br />
[-constant_arcs]</td>
</tr>
<tr class="even">
<td><em>-setup</em></td>
<td>Report annotated setup checks.</td>
</tr>
<tr class="odd">
<td><em>-hold</em></td>
<td>Report annotated hold checks.</td>
</tr>
<tr class="even">
<td><em>-recovery</em></td>
<td>Report annotated recovery checks.</td>
</tr>
<tr class="odd">
<td><em>-removal</em></td>
<td>Report annotated removal checks.</td>
</tr>
<tr class="even">
<td><em>-nochange</em></td>
<td>Report annotated nochange checks.</td>
</tr>
<tr class="odd">
<td><em>-width</em></td>
<td>Report annotated width checks.</td>
</tr>
<tr class="even">
<td><em>-period</em></td>
<td>Report annotated period checks.</td>
</tr>
<tr class="odd">
<td><em>-max_skew</em></td>
<td>Report annotated max skew checks.</td>
</tr>
<tr class="even">
<td><em><strong>-max_line lines</strong></em></td>
<td>Maximum number of lines listed by the –report_annotated and ‑report_unannotated options.</td>
</tr>
<tr class="odd">
<td>-report_annotated</td>
<td>Report annotated timing arcs.</td>
</tr>
<tr class="even">
<td>-report_unannotated</td>
<td>Report unannotated timing arcs.</td>
</tr>
<tr class="odd">
<td>-constant_arcs</td>
<td>Report separate annotation counts for arcs disabled by logic constants (set_logic_one, set_logic_zero).</td>
</tr>
</tbody>
</table>

The report_annotated_check command reports a summary of SDF timing
check annotation. The -report_annotated and –report_annotated options
can be used to list arcs that are annotated or not annotated.

<table>
<tbody>
<tr class="odd">
<td><strong>report_annotated_delay</strong></td>
<td>[-cell]<br />
[-net]<br />
[-from_in_ports]<br />
[-to_out_ports]<br />
[-max_lines <em>lines</em>]<br />
[-report_annotated]<br />
[-report_unannotated]<br />
[-constant_arcs]</td>
</tr>
<tr class="even">
<td><em>-cell</em></td>
<td>Report annotated cell delays.</td>
</tr>
<tr class="odd">
<td><em>-net</em></td>
<td>Report annotated internal net delays.</td>
</tr>
<tr class="even">
<td><em>-</em>from_in_ports</td>
<td>Report annotated delays from input ports.</td>
</tr>
<tr class="odd">
<td><em>-</em>to_out_ports</td>
<td>Report annotated delays to output ports.</td>
</tr>
<tr class="even">
<td>-max_lines <em>lines</em></td>
<td>Maximum number of lines listed by the –report_annotated and ‑report_unannotated options.</td>
</tr>
<tr class="odd">
<td>-report_annotated</td>
<td>Report annotated timing arcs.</td>
</tr>
<tr class="even">
<td>-report_unannotated</td>
<td>Report unannotated timing arcs.</td>
</tr>
<tr class="odd">
<td>-constant_arcs</td>
<td>Report separate annotation counts for arcs disabled by logic constants (set_logic_one, set_logic_zero).</td>
</tr>
</tbody>
</table>

The report_annotated_delay command reports a summary of SDF delay
annotation. Without the ‑from_in_ports and –to_out_ports options
arcs to and from top level ports are not reported. The
‑report_annotated and –report_unannotated options can be used to
list arcs that are annotated or not annotated.

<table>
<tbody>
<tr class="odd">
<td><strong>report_checks</strong></td>
<td>[-from <em>from_list</em><br />
|-rise_from <em>from_list</em><br />
|-fall_from <em>from_list</em>]<br />
[-through <em>through_list</em><br />
|-rise_through <em>through_list</em><br />
|-fall_through <em>through_list</em>]<br />
[-to <em>to_list</em><br />
|-rise_to <em>to_list</em><br />
|-fall_to <em>to_list</em>]<br />
[-unconstrained]<br />
[-path_delay min|min_rise|min_fall<br />
|max|max_rise|max_fall<br />
|min_max]<br />
[-group_path_count <em>path_count</em>]<br />
[-endpoint_path_count <em>endpoint_path_count</em>]<br />
[-unique_paths_to_endpoint]<br />
[-corner <em>corner</em>]<br />
[-slack_max <em>max_slack</em>]<br />
[-slack_min <em>min_slack</em>]<br />
[-sort_by_slack]<br />
[-path_group <em>groups</em>]<br />
[-format end|full|short|summary<br />
|full_clock|full_clock_expanded<br />
|json]<br />
[-fields <em>fields</em>]<br />
[-digits <em>digits</em>]<br />
[-no_line_split]<br />
[&gt; <em>filename</em>]<br />
[&gt;&gt; <em>filename</em>]</td>
</tr>
<tr class="even">
<td>-from <em>from_list</em></td>
<td>Report paths from a list of clocks, instances, ports, register clock pins, or latch data pins.</td>
</tr>
<tr class="odd">
<td>-rise_from <em>from_list</em></td>
<td>Report paths from the rising edge of clocks, instances, ports, register clock pins, or latch data pins.</td>
</tr>
<tr class="even">
<td>-fall_from <em>from_list</em></td>
<td>Report paths from the falling edge of clocks, instances, ports, register clock pins, or latch data pins.</td>
</tr>
<tr class="odd">
<td>-through <em>through_list</em></td>
<td>Report paths through a list of instances, pins or nets.</td>
</tr>
<tr class="even">
<td>-rise_through <em>through_list</em></td>
<td>Report rising paths through a list of instances, pins or nets.</td>
</tr>
<tr class="odd">
<td>-fall_through <em>through_list</em></td>
<td>Report falling paths through a list of instances, pins or nets.</td>
</tr>
<tr class="even">
<td>-to <em>to_list</em></td>
<td>Report paths to a list of clocks, instances, ports or pins.</td>
</tr>
<tr class="odd">
<td>-rise_to <em>to_list</em></td>
<td>Report rising paths to a list of clocks, instances, ports or pins.</td>
</tr>
<tr class="even">
<td>-fall_to <em>to_list</em></td>
<td>Report falling paths to a list of clocks, instances, ports or pins.</td>
</tr>
<tr class="odd">
<td>-unconstrained</td>
<td>Report unconstrained paths also. The unconstrained path group is not reported without this option.</td>
</tr>
<tr class="even">
<td>-path_delay min</td>
<td>Report min path (hold) checks.</td>
</tr>
<tr class="odd">
<td>-path_delay min_rise</td>
<td>Report min path (hold) checks for rising endpoints.</td>
</tr>
<tr class="even">
<td>-path_delay min_fall</td>
<td>Report min path (hold) checks for falling endpoints.</td>
</tr>
<tr class="odd">
<td>-path_delay max</td>
<td>Report max path (setup) checks.</td>
</tr>
<tr class="even">
<td>-path_delay max_rise</td>
<td>Report max path (setup) checks for rising endpoints.</td>
</tr>
<tr class="odd">
<td>-path_delay max_fall</td>
<td>Report max path (setup) checks for falling endpoints.</td>
</tr>
<tr class="even">
<td>-path_delay min_max</td>
<td>Report max and max path (setup and hold) checks.</td>
</tr>
<tr class="odd">
<td>-group_path_count <em>path_count</em></td>
<td>The number of paths to report in each path group. The default is 1.</td>
</tr>
<tr class="even">
<td>-endpoint_path_count <em>endpoint_path_count</em></td>
<td>The number of paths to report for each endpoint. The default is 1.</td>
</tr>
<tr class="odd">
<td>‑unique_paths_to_endpoint</td>
<td>When multiple paths to an endpoint are specified with ‑endpoint_path_count many of the paths may differ only in the rise/fall edges of the pins in the paths. With this option only the worst path through the set of pis is reported.</td>
</tr>
<tr class="even">
<td>-corner <em>corner</em></td>
<td>Report paths for one process corner. The default is to report paths for all process corners.</td>
</tr>
<tr class="odd">
<td>-slack_max <em>max_slack</em></td>
<td>Only report paths with less slack than <em>max_slack</em>.</td>
</tr>
<tr class="even">
<td>-slack_min <em>min_slack</em></td>
<td>Only report paths with more slack than <em>min_slack</em>.</td>
</tr>
<tr class="odd">
<td>-sort_by_slack</td>
<td>Sort paths by slack rather than slack grouped by path group.</td>
</tr>
<tr class="even">
<td>-path_group <em>groups</em></td>
<td>List of path groups to report. The default is to report all path groups.</td>
</tr>
<tr class="odd">
<td>-format end</td>
<td>Report path ends in one line with delay, required time and slack.</td>
</tr>
<tr class="even">
<td>-format full</td>
<td>Report path start and end points and the path. This is the default path type.</td>
</tr>
<tr class="odd">
<td>-format full_clock</td>
<td>Report path start and end points, the path, and the source and and target clock paths.</td>
</tr>
<tr class="even">
<td>-format full_clock_expanded</td>
<td>Report path start and end points, the path, and the source and and target clock paths. If the clock is generated and propagated, the path from the clock source pin is also reported.</td>
</tr>
<tr class="odd">
<td>-format short</td>
<td>Report only path start and end points.</td>
</tr>
<tr class="even">
<td>-format summary</td>
<td>Report only path ends with delay.</td>
</tr>
<tr class="odd">
<td>-format json</td>
<td>Report in json format. -fields is ignored.</td>
</tr>
<tr class="even">
<td>-fields <em>fields</em></td>
<td>List of capacitance|slew|input_pins|hierarcial_pins|nets|fanout|src_attr</td>
</tr>
<tr class="odd">
<td>-digits <em>digits</em></td>
<td>The number of digits after the decimal point to report. The default value is the variable sta_report_default_digits.</td>
</tr>
<tr class="even">
<td>-no_line_splits</td>
<td>Do not split long lines into multiple lines.</td>
</tr>
</tbody>
</table>

The report_checks command reports paths in the design. Paths are
reported in groups by capture clock, unclocked path delays, gated clocks
and unconstrained.

See set_false_path for a description of allowed *from_list*,
*through_list* and *to_list* objects.

<table>
<tbody>
<tr class="odd">
<td><strong>report_check_types</strong></td>
<td>[-violators]<br />
[-verbose]<br />
[-format slack_only|end]<br />
[-max_delay]<br />
[-min_delay]<br />
[-recovery]<br />
[-removal]<br />
[-clock_gating_setup]<br />
[-clock_gating_hold]<br />
[-max_slew]<br />
[-min_slew]<br />
[-min_pulse_width]<br />
[-min_period]<br />
[-digits <em>digits</em>]<br />
[-no_split_lines]<br />
[&gt; <em>filename</em>]<br />
[&gt;&gt; <em>filename</em>]</td>
</tr>
<tr class="even">
<td>-violators</td>
<td>Report all violated timing and design rule constraints.</td>
</tr>
<tr class="odd">
<td><em>-verbose</em></td>
<td>Use a verbose output format.</td>
</tr>
<tr class="even">
<td>-format slack_only</td>
<td>Report the minumum slack for each timing check.</td>
</tr>
<tr class="odd">
<td>-format end</td>
<td>Report the endpoint for each check.</td>
</tr>
<tr class="even">
<td>-max_delay</td>
<td>Report setup and max delay path delay constraints.</td>
</tr>
<tr class="odd">
<td>-min_delay</td>
<td>Report hold and min delay path delay constraints.</td>
</tr>
<tr class="even">
<td>-recovery</td>
<td>Report asynchronous recovery checks.</td>
</tr>
<tr class="odd">
<td>-removal</td>
<td>Report asynchronous removal checks.</td>
</tr>
<tr class="even">
<td>-clock_gating_setup</td>
<td>Report gated clock enable setup checks.</td>
</tr>
<tr class="odd">
<td>-clock_gating_hold</td>
<td>Report gated clock hold setup checks.</td>
</tr>
<tr class="even">
<td>-max_slew</td>
<td>Report max transition design rule checks.</td>
</tr>
<tr class="odd">
<td>-max_skew</td>
<td>Report max skew design rule checks.</td>
</tr>
<tr class="even">
<td>-min_pulse_width</td>
<td>Report min pulse width design rule checks.</td>
</tr>
<tr class="odd">
<td>-min_period</td>
<td>Report min period design rule checks.</td>
</tr>
<tr class="even">
<td>-min_slew</td>
<td>Report min slew design rule checks.</td>
</tr>
<tr class="odd">
<td>-digits <em>digits</em></td>
<td>The number of digits after the decimal point to report. The default value is the variable sta_report_default_digits.</td>
</tr>
<tr class="even">
<td>-no_split_lines</td>
<td>Do not split long lines into multiple lines.</td>
</tr>
</tbody>
</table>

The report_check_types command reports the slack for each type of
timing and design rule constraint. The keyword options allow a subset of
the constraint types to be reported.

<table>
<tbody>
<tr class="odd">
<td><strong>report_clock_latency</strong></td>
<td>[-clock <em>clocks</em>]<br />
[-include_internal_latency]<em><br />
</em>[-digits <em>digits</em>]</td>
</tr>
<tr class="even">
<td>-clock <em>clocks</em></td>
<td>The clocks to report.</td>
</tr>
<tr class="odd">
<td>-include_internal_latency</td>
<td>Include internal clock latency from liberty min/max_clock_tree_path timing groups.</td>
</tr>
<tr class="even">
<td>-digits <em>digits</em></td>
<td>The number of digits to report for delays.</td>
</tr>
</tbody>
</table>

Report the clock network latency.

<table>
<tbody>
<tr class="odd">
<td><strong>report_clock_min_period</strong></td>
<td>[-clocks <em>clocks</em>]<br />
[-include_port_paths]</td>
</tr>
<tr class="even">
<td>-clocks <em>clocks</em></td>
<td>The clocks to report.</td>
</tr>
<tr class="odd">
<td>-include_port_paths</td>
<td>Include paths from input port and to output ports.</td>
</tr>
</tbody>
</table>

Report the minimum period and maximum frequency for *clocks*. If the
-clocks argument is not specified all clocks are reported. The minimum
period is determined by examining the smallest slack paths between
registers the rising edges of the clock or between falling edges of the
clock. Paths between different clocks, different clock edges of the same
clock, level sensitive latches, or paths constrained by
set_multicycle_path, set_max_path are not considered.

|                               |                                |
| ----------------------------- | ------------------------------ |
| **report_clock_properties** | [*clock_names*]             |
| *clock_names*                | List of clock names to report. |

The report_clock_properties command reports the period and rise/fall
edge times for each clock that has been defined.

<table>
<tbody>
<tr class="odd">
<td><strong>report_clock_skew</strong></td>
<td>[-setup|-hold]<br />
[-clock <em>clocks</em>]<em><br />
</em>[-include_internal_latency]<em><br />
</em>[-digits <em>digits</em>]</td>
</tr>
<tr class="even">
<td>-setup</td>
<td>Report skew for setup checks.</td>
</tr>
<tr class="odd">
<td>-hold</td>
<td>Report skew for hold checks.</td>
</tr>
<tr class="even">
<td>-clock <em>clocks</em></td>
<td>The clocks to report.</td>
</tr>
<tr class="odd">
<td>-include_internal_latency</td>
<td>Include internal clock latency from liberty min/max_clock_tree_path timing groups.</td>
</tr>
<tr class="even">
<td>-digits <em>digits</em></td>
<td>The number of digits to report for delays.</td>
</tr>
</tbody>
</table>

Report the maximum difference in clock arrival between every source and
target register that has a path between the source and target registers.

<table>
<tbody>
<tr class="odd">
<td><strong>report_dcalc</strong></td>
<td>[-from <em>from_pin</em>]<br />
[-to <em>to_pin</em>]<br />
[-corner <em>corner</em>]<br />
[-min]<br />
[-max]<br />
[-digits <em>digits</em>]<br />
[&gt; <em>filename</em>]<br />
[&gt;&gt; <em>filename</em>]</td>
</tr>
<tr class="even">
<td>-from <em>from_pin</em></td>
<td>Report delay calculations for timing arcs from instance input pin <em>from_pin</em>.</td>
</tr>
<tr class="odd">
<td>-to <em>to_pin</em></td>
<td>Report delay calculations for timing arcs to instance output pin to<em>_pin</em>.</td>
</tr>
<tr class="even">
<td>-corner <em>corner</em></td>
<td>Report paths for process <em>corner</em>. The -corner keyword is required if more than one process corner is defined.</td>
</tr>
<tr class="odd">
<td>-min</td>
<td>Report delay calculation for min delays.</td>
</tr>
<tr class="even">
<td>-max</td>
<td>Report delay calculation for max delays.</td>
</tr>
<tr class="odd">
<td>-digits <em>digits</em></td>
<td>The number of digits after the decimal point to report. The default is sta_report_default_digits.</td>
</tr>
</tbody>
</table>

The report_dcalc command shows how the delays between instance pins are
calculated. It is useful for debugging problems with delay calculation.

|                             |  |
| --------------------------- |  |
| **report_disabled_edges** |  |

The report_disabled_edges command reports disabled timing arcs along
with the reason they are disabled. Each disabled timing arc is reported
as the instance name along with the from and to ports of the arc. The
disable reason is shown next. Arcs that are disabled with
set_disable_timing are reported with constraint as the reason. Arcs
that are disabled by constants are reported with constant as the reason
along with the constant instance pin and value. Arcs that are disabled
to break combinational feedback loops are reported with loop as the
reason.

> report_disabled_edges  
u1 A B constant B=0

<table>
<tbody>
<tr class="odd">
<td><strong>report_edges</strong></td>
<td>[-from <em>from_pin</em>]<br />
[-to <em>to_pin</em>]</td>
</tr>
<tr class="even">
<td>-from <em>from_pin</em></td>
<td>Report edges/timing arcs from pin <em>from_pin</em>.</td>
</tr>
<tr class="odd">
<td>-to <em>to_pin</em></td>
<td>Report edges/timing arcs to pin to<em>_pin</em>.</td>
</tr>
</tbody>
</table>

Report the edges/timing arcs and their delays in the timing graph
from/to/between pins.

<table>
<tbody>
<tr class="odd">
<td><strong>report_instance</strong></td>
<td><em>instance_path<br />
</em>[&gt; <em>filename</em>]<br />
[&gt;&gt; <em>filename</em>]</td>
</tr>
<tr class="even">
<td><em>instance_path</em></td>
<td>Hierarchical path to a instance.</td>
</tr>
</tbody>
</table>

<table>
<tbody>
<tr class="odd">
<td><strong>report_lib_cell</strong></td>
<td><em>cell_name<br />
</em>[&gt; <em>filename</em>]<br />
[&gt;&gt; <em>filename</em>]</td>
</tr>
<tr class="even">
<td><em>cell_name</em></td>
<td>The name of a library cell.</td>
</tr>
</tbody>
</table>

Describe the liberty library cell *cell_name.*

<table>
<tbody>
<tr class="odd">
<td><strong>report_net</strong></td>
<td>[-digits <em>digits</em>]<br />
<em>net_path<br />
</em>[&gt; <em>filename</em>]<br />
[&gt;&gt; <em>filename</em>]</td>
</tr>
<tr class="even">
<td>-digits <em>digits</em></td>
<td>The number of digits after the decimal point to report. The default value is the variable sta_report_default_digits.</td>
</tr>
<tr class="odd">
<td><em>net_path</em></td>
<td>Hierarchical path to a net.</td>
</tr>
</tbody>
</table>

Report the connections and capacitance of a net.

<table>
<tbody>
<tr class="odd">
<td><strong>report_parasitic_annotation</strong></td>
<td>[-report_unannotated]<em><br />
</em>[&gt; <em>filename</em>]<br />
[&gt;&gt; <em>filename</em>]</td>
</tr>
<tr class="even">
<td>-report_unannotated</td>
<td>Report unannotated and partially annotated nets.</td>
</tr>
</tbody>
</table>

Report SPEF parasitic annotation completeness.

<table>
<tbody>
<tr class="odd">
<td><strong>report_power</strong></td>
<td>[-instances <em>instances</em>]<br />
[-highest_power_instances <em>count</em>]<em><br />
</em>[-digits <em>digits</em>]<br />
[&gt; <em>filename</em>]<br />
[&gt;&gt; <em>filename</em>]</td>
</tr>
<tr class="even">
<td>-instances <em>instances</em></td>
<td>Report the power for each instance of <em>instances</em>. If the instance is hierarchical the total power for the instances inside the hierarchical instance is reported.</td>
</tr>
<tr class="odd">
<td>-highest_power_instances <em>count</em></td>
<td>Report the power for the <em>count</em> highest power instances.</td>
</tr>
<tr class="even">
<td>-digits <em>digits</em></td>
<td>The number of digits after the decimal point to report. The default value is the variable sta_report_default_digits.</td>
</tr>
</tbody>
</table>

The report_power command uses static power analysis based on propagated
or annotated pin activities in the circuit using Liberty power models.
The internal, switching, leakage and total power are reported. Design
power is reported separately for combinational, sequential, macro and
pad groups. Power values are reported in watts.

The read_vcd or read_saif commands can be used to read activities from
a file based on simulation. If no simulation activities are available,
the set_power_activity command should be used to set the activity of
input ports or pins in the design. The default input activity and duty
for inputs are 0.1 and 0.5 respectively. The activities are propagated
from annotated input ports or pins through gates and used in the power
calculations.

Group Internal Switching Leakage Total  
Power Power Power Power  
----------------------------------------------------------------  
Sequential 3.29e-06 3.41e-08 2.37e-07 3.56e-06 92.4%  
Combinational 1.86e-07 3.31e-08 7.51e-08 2.94e-07 7.6%  
Macro 0.00e+00 0.00e+00 0.00e+00 0.00e+00 0.0%  
Pad 0.00e+00 0.00e+00 0.00e+00 0.00e+00 0.0%  
---------------------------------------------------------------  
Total 3.48e-06 6.72e-08 3.12e-07 3.86e-06 100.0%  
90.2% 1.7% 8.1%

<table>
<tbody>
<tr class="odd">
<td><strong>report_pulse_width_checks</strong></td>
<td>[-verbose]<br />
[-digits <em>digits</em>]<br />
[-no_line_splits]<br />
[<em>pins</em>]<br />
[&gt; <em>filename</em>]<br />
[&gt;&gt; <em>filename</em>]</td>
</tr>
<tr class="even">
<td><em>-verbose</em></td>
<td>Use a verbose output format.</td>
</tr>
<tr class="odd">
<td>-digits <em>digits</em></td>
<td>The number of digits after the decimal point to report. The default value is the variable sta_report_default_digits.</td>
</tr>
<tr class="even">
<td>-no_line_splits</td>
<td></td>
</tr>
<tr class="odd">
<td><em>pins</em></td>
<td>List of pins or ports to report.</td>
</tr>
</tbody>
</table>

The report_pulse_width_checks command reports min pulse width checks
for pins in the clock network. If *pins* is not specified all clock
network pins are reported.

<table>
<tbody>
<tr class="odd">
<td><strong>report_slews</strong></td>
<td>[-corner <em>corner</em>]<br />
<em>pin</em></td>
</tr>
<tr class="even">
<td>-corner <em>corner</em></td>
<td>Report paths for process <em>corner</em>. The -corner keyword is required if more than one process corner is defined.</td>
</tr>
<tr class="odd">
<td><em>pin</em></td>
<td></td>
</tr>
</tbody>
</table>

Report the slews at *pin*

<table>
<tbody>
<tr class="odd">
<td><strong>report_tns</strong></td>
<td>[-min]<br />
[-max]<em><br />
</em>[-digits <em>digits</em>]</td>
</tr>
<tr class="even">
<td>-max</td>
<td>Report the total max/setup slack.</td>
</tr>
<tr class="odd">
<td>-min</td>
<td>Report the total min/hold slack.</td>
</tr>
<tr class="even">
<td>-digits <em>digits</em></td>
<td>The number of digits after the decimal point to report. The default value is the variable sta_report_default_digits.</td>
</tr>
</tbody>
</table>

Report the total negative slack.

|                   |  |
| ----------------- |  |
| **report_units** |  |

Report the units used for command arguments and reporting.

report_units  
time 1ns  
capacitance 1pF  
resistance 1kohm  
voltage 1v  
current 1A  
power 1pW  
distance 1um

<table>
<tbody>
<tr class="odd">
<td><strong>report_wns</strong></td>
<td>[-min]<br />
[-max]<em><br />
</em>[-digits <em>digits</em>]</td>
</tr>
<tr class="even">
<td>-max</td>
<td>Report the worst max/setup slack.</td>
</tr>
<tr class="odd">
<td>-min</td>
<td>Report the worst min/hold slack.</td>
</tr>
<tr class="even">
<td>-digits <em>digits</em></td>
<td>The number of digits after the decimal point to report. The default value is the variable sta_report_default_digits.</td>
</tr>
</tbody>
</table>

Report the worst negative slack. If the worst slack is posiive, zero is
reported.

<table>
<tbody>
<tr class="odd">
<td><strong>report_worst_slack</strong></td>
<td>[-min]<br />
[-max]<em><br />
</em>[-digits <em>digits</em>]</td>
</tr>
<tr class="even">
<td>-max</td>
<td>Report the worst max/setup slack.</td>
</tr>
<tr class="odd">
<td>-min</td>
<td>Report the worst min/hold slack.</td>
</tr>
<tr class="even">
<td>-digits <em>digits</em></td>
<td>The number of digits after the decimal point to report. The default value is the variable sta_report_default_digits.</td>
</tr>
</tbody>
</table>

<table>
<tbody>
<tr class="odd">
<td><strong>set_assigned_check</strong></td>
<td>-setup|-hold|-recovery|-removal<br />
[-rise]<br />
[-fall]<br />
[-corner <em>corner</em>]<br />
[-min]<br />
[-max]<br />
[-from <em>from_pins</em>]<br />
[-to <em>to_pins</em>]<br />
[-clock rise|fall]<br />
[-cond sdf_cond]<br />
[-worst]<em><br />
margin</em></td>
</tr>
<tr class="even">
<td>-setup</td>
<td>Annotate setup timing checks.</td>
</tr>
<tr class="odd">
<td>-hold</td>
<td>Annotate hold timing checks.</td>
</tr>
<tr class="even">
<td>-recovery</td>
<td>Annotate recovery timing checks.</td>
</tr>
<tr class="odd">
<td>-removal</td>
<td>Annotate removal timing checks.</td>
</tr>
<tr class="even">
<td>-rise</td>
<td>Annotate rising delays.</td>
</tr>
<tr class="odd">
<td>-fall</td>
<td>Annotate falling delays.</td>
</tr>
<tr class="even">
<td>-corner <em>corner</em></td>
<td>The name of a process corner. The -corner keyword is required if more than one process corner is defined.</td>
</tr>
<tr class="odd">
<td>-min</td>
<td>Annotate the minimum value of the process corner.</td>
</tr>
<tr class="even">
<td>-max</td>
<td>Annotate the maximum value of the process corner.</td>
</tr>
<tr class="odd">
<td>-from <em>from_pins</em></td>
<td>A list of pins for the clock.</td>
</tr>
<tr class="even">
<td>-to <em>to_pins</em></td>
<td>A list of pins for the data.</td>
</tr>
<tr class="odd">
<td>-clock rise|fall</td>
<td>The timing check clock pin transition.</td>
</tr>
<tr class="even">
<td><em>margin</em></td>
<td>The timing check margin.</td>
</tr>
</tbody>
</table>

The set_assigned_check command is used to annotate the timing checks
between two pins on an instance. The annotated delay overrides the
calculated delay. This command is a interactive way to back-annotate
delays like an SDF file.

<table>
<tbody>
<tr class="odd">
<td><strong>set_assigned_delay</strong></td>
<td>-cell|-net<br />
[-rise]<br />
[-fall]<br />
[-corner <em>corner</em>]<br />
[-min]<br />
[-max]<br />
[-from <em>from_pins</em>]<br />
[-to <em>to_pins</em>]<em><br />
delay</em></td>
</tr>
<tr class="even">
<td>-cell</td>
<td>Annotate the delays between two pins on an instance.</td>
</tr>
<tr class="odd">
<td>-net</td>
<td>Annotate the delays between two pins on a net.</td>
</tr>
<tr class="even">
<td>-rise</td>
<td>Annotate the rising delays.</td>
</tr>
<tr class="odd">
<td>-fall</td>
<td>Annotate the falling delays.</td>
</tr>
<tr class="even">
<td>-corner <em>corner</em></td>
<td>The name of a process corner. The -corner keyword is required if more than one process corner is defined.</td>
</tr>
<tr class="odd">
<td>-min</td>
<td>Annotate the minimum delays.</td>
</tr>
<tr class="even">
<td>-max</td>
<td>Annotate the maximum delays.</td>
</tr>
<tr class="odd">
<td>-from <em>from_pins</em></td>
<td>A list of pins.</td>
</tr>
<tr class="even">
<td>-to <em>to_pins</em></td>
<td>A list of pins.</td>
</tr>
<tr class="odd">
<td><em>delay</em></td>
<td>The delay between <em>from_pins</em> and <em>to_pins</em>.</td>
</tr>
</tbody>
</table>

The set_assigned_delay command is used to annotate the delays between
two pins on an instance or net. The annotated delay overrides the
calculated delay. This command is a interactive way to back-annotate
delays like an SDF file.

Use the -corner keyword to specify a process corner. The -corner keyword
is required if more than one process corner is defined.

<table>
<tbody>
<tr class="odd">
<td><strong>set_assigned_transition</strong></td>
<td>[-rise]<br />
[-fall]<br />
[-corner <em>corner</em>]<br />
[-min]<br />
[-max]<br />
<em>slew<br />
pin_list</em></td>
</tr>
<tr class="even">
<td>-rise</td>
<td>Annotate the rising transition.</td>
</tr>
<tr class="odd">
<td>-fall</td>
<td>Annotate the falling transition.</td>
</tr>
<tr class="even">
<td>-corner <em>corner</em></td>
<td>Annotate delays for process <em>corner</em>.</td>
</tr>
<tr class="odd">
<td>-min</td>
<td>Annotate the minimum transition time.</td>
</tr>
<tr class="even">
<td>-max</td>
<td>Annotate the maximum transition time.</td>
</tr>
<tr class="odd">
<td><em>slew</em></td>
<td>The pin transition time.</td>
</tr>
<tr class="even">
<td><em>pin_list</em></td>
<td>A list of pins.</td>
</tr>
</tbody>
</table>

The set_assigned_transition command is used to annotate the transition
time (slew) of a pin. The annotated transition time overrides the
calculated transition time.

<table>
<tbody>
<tr class="odd">
<td><strong>set_case_analysis</strong></td>
<td>0|1|zero|one|rise|rising|fall|falling<br />
<em>port_or_pin_list</em></td>
</tr>
<tr class="even">
<td><em>port_or_pin_list</em></td>
<td>A list of ports or pins.</td>
</tr>
</tbody>
</table>

The set_case_analysis command sets the signal on a port or pin to a
constant logic value. No paths are propagated from constant pins.
Constant values set with the set_case_analysis command are propagated
through downstream gates.

Conditional timing arcs with mode groups are controlled by logic values
on the instance pins.

<table>
<tbody>
<tr class="odd">
<td><strong>set_clock_gating_check</strong></td>
<td>[-setup <em>setup_time</em>]<br />
[-hold <em>hold_time</em>]<br />
[-rise]<br />
[-fall]<br />
[-high]<br />
[-low]<br />
[<em>objects</em>]</td>
</tr>
<tr class="even">
<td>-setup <em>setup_time</em></td>
<td>Clock enable setup margin.</td>
</tr>
<tr class="odd">
<td>-hold <em>hold_time</em></td>
<td>Clock enable hold margin.</td>
</tr>
<tr class="even">
<td>-rise</td>
<td>The setup/hold margin is for the rising edge of the clock enable.</td>
</tr>
<tr class="odd">
<td>-fall</td>
<td>The setup/hold margin is for the falling edge of the clock enable.</td>
</tr>
<tr class="even">
<td>-high</td>
<td>The gating clock is active high (pin and instance objects only).</td>
</tr>
<tr class="odd">
<td>-low</td>
<td>The gating clock is active low (pin and instance objects only).</td>
</tr>
<tr class="even">
<td><em>objects</em></td>
<td>A list of clocks, instances, pins or ports.</td>
</tr>
</tbody>
</table>

The set_clock_gating_check command is used to add setup or hold
timing checks for data signals used to gate clocks.

If no objects are specified the setup/hold margin is global and applies
to all clock gating circuits in the design. If neither of the -rise and
-fall options are used the setup/hold margin applies to the rising and
falling edges of the clock gating signal.

Normally the library cell function is used to determine the active state
of the clock. The clock is active high for AND/NAND functions and active
low for OR/NOR functions. The -high and -low options are used to specify
the active state of the clock for other cells, such as a MUX.

If multiple set_clock_gating_check commands apply to a clock gating
instance he priority of the commands is shown below (highest to lowest
priority).

clock enable pin  
instance  
clock pin  
clock  
global

<table>
<tbody>
<tr class="odd">
<td><strong>set_clock_groups</strong></td>
<td>[-name <em>name</em>]<br />
[-logically_exclusive]<br />
[-physically_exclusive]<br />
[-asynchronous]<br />
[-allow_paths]<br />
-group <em>clocks</em></td>
</tr>
<tr class="even">
<td>-name <em>name</em></td>
<td>The clock group name.</td>
</tr>
<tr class="odd">
<td>-logically_exclusive</td>
<td>The clocks in different groups do not interact logically but can be physically present on the same chip. Paths between clock groups are considered for noise analysis.</td>
</tr>
<tr class="even">
<td>-physically_exclusive</td>
<td>The clocks in different groups cannot be present at the same time on a chip. Paths between clock groups are not considered for noise analysis.</td>
</tr>
<tr class="odd">
<td>-asynchronous</td>
<td>The clock groups are asynchronous. Paths between clock groups are considered for noise analysis.</td>
</tr>
<tr class="even">
<td>-allow_paths</td>
<td></td>
</tr>
<tr class="odd">
<td><em>clocks</em></td>
<td>A list of clocks in the group.</td>
</tr>
</tbody>
</table>

The set_clock_groups command is used to deifine groups of clocks that
interact with each other. Clocks in different groups do not interact and
paths between them are not reported. Use a –group argument for each
clock group.

<table>
<tbody>
<tr class="odd">
<td><strong>set_clock_latency</strong></td>
<td>[-source]<em><br />
</em>[-clock <em>clock</em>]<br />
[-rise]<em><br />
</em>[-fall]<br />
[-min]<br />
[-max]<br />
<em>delay<br />
objects</em></td>
</tr>
<tr class="even">
<td>-source</td>
<td>The latency is at the clock source.</td>
</tr>
<tr class="odd">
<td><em>-</em>clo<em>ck clock</em></td>
<td>If multiple clocks are defined at a pin this use this option to specify the latency for a specific clock.</td>
</tr>
<tr class="even">
<td>-rise</td>
<td>The latency is for the rising edge of the clock.</td>
</tr>
<tr class="odd">
<td>-fall</td>
<td>The latency is for the falling edge of the clock.</td>
</tr>
<tr class="even">
<td>-min</td>
<td><em>delay</em> is the minimum latency.</td>
</tr>
<tr class="odd">
<td>-max</td>
<td><em>delay</em> is the maximum latency.</td>
</tr>
<tr class="even">
<td><em>delay</em></td>
<td>Clock source or insertion delay.</td>
</tr>
<tr class="odd">
<td><em>objects</em></td>
<td>A list of clocks, pins or ports.</td>
</tr>
</tbody>
</table>

The set_clock_latency command describes expected delays of the clock
tree when analyzing a design using ideal clocks. Use the -source option
to specify latency at the clock source, also known as insertion delay.
Source latency is delay in the clock tree that is external to the design
or a clock tree internal to an instance that implements a complex logic
function.

<table>
<tbody>
<tr class="odd">
<td><strong>set_clock_transition</strong></td>
<td>[-rise]<br />
[-fall]<br />
[-min]<br />
[-max]<em><br />
transition<br />
clocks</em></td>
</tr>
<tr class="even">
<td>-rise</td>
<td>Set the transition time for the rising edge of the clock.</td>
</tr>
<tr class="odd">
<td>-fall</td>
<td>Set the transition time for the falling edge of the clock.</td>
</tr>
<tr class="even">
<td>-min</td>
<td>Set the min transition time.</td>
</tr>
<tr class="odd">
<td>-max</td>
<td>Set the min transition time.</td>
</tr>
<tr class="even">
<td><em>transition</em></td>
<td>Clock transition time (slew).</td>
</tr>
<tr class="odd">
<td><em>clocks</em></td>
<td>A list of clocks.</td>
</tr>
</tbody>
</table>

The set_clock_transition command describes expected transition times
of the clock tree when analzying a design using ideal clocks.

<table>
<tbody>
<tr class="odd">
<td><strong>set_clock_uncertainty</strong></td>
<td>[-from|-rise_from|-fall_from <em>from_clock</em>]<em><br />
</em>[<em>-</em>to|-rise_to|-fall_to <em>to_clock</em>]<br />
[-rise]<br />
[-fall]<br />
[-setup]<br />
[-hold]<em><br />
uncertainty<br />
</em>[<em>objects</em>]</td>
</tr>
<tr class="even">
<td>-from <em>from_clock</em></td>
<td>Inter-clock uncertainty source clock.</td>
</tr>
<tr class="odd">
<td>-to <em>to_clock</em></td>
<td>Inter-clock uncertainty target clock.</td>
</tr>
<tr class="even">
<td>-rise</td>
<td>Inter-clock target clock rise edge, alternative to ‑rise_to.Inter-clock target clock rise edge, alternative to ‑rise_to.</td>
</tr>
<tr class="odd">
<td>-fall</td>
<td>Inter-clock target clock rise edge, alternative to ‑fall_to.</td>
</tr>
<tr class="even">
<td>-setup</td>
<td><em>uncertainty</em> is for setup checks.</td>
</tr>
<tr class="odd">
<td>-hold</td>
<td><em>uncertainty</em> is for hold checks.</td>
</tr>
<tr class="even">
<td><em>uncertainty</em></td>
<td>Clock uncertainty.</td>
</tr>
<tr class="odd">
<td><em>objects</em></td>
<td>A list of clocks, ports or pins.</td>
</tr>
</tbody>
</table>

The set_clock_uncertainty command specifies the uncertainty or jitter
in a clock. The uncertainty for a clock can be specified on its source
pin or port, or the clock itself.

set_clock_uncertainty .1 [get_clock clk1]

Inter-clock uncertainty between the source and target clocks of timing
checks is specified with the ‑from|‑rise_from|-fall_from and
‑to|‑rise_to|-fall_to arguments .

set_clock_uncertainty -from [get_clock clk1] -to [get_clocks
clk2] .1

The following commands are equivalent.

set_clock_uncertainty -from [get_clock clk1] -rise_to
[get_clocks clk2] .1  
set_clock_uncertainty -from [get_clock clk1] -to [get_clocks
clk2] -rise .1

<table>
<tbody>
<tr class="odd">
<td><strong>set_cmd_units</strong></td>
<td>[-capacitance <em>cap_unit</em>]<br />
[-resistance <em>res_unit</em>]<br />
[-time <em>time_unit</em>]<br />
[-voltage <em>voltage_unit</em>]<br />
[-current <em>current_unit</em>]<br />
[-power <em>power_unit</em>]<br />
[-distance <em>distance_unit</em>]</td>
</tr>
<tr class="even">
<td>-capacitance <em>cap_unit</em></td>
<td>The capacitance scale factor followed by 'f'.</td>
</tr>
<tr class="odd">
<td>-resistance <em>res_unit</em></td>
<td>The resistance scale factor followed by 'ohm'.</td>
</tr>
<tr class="even">
<td>-time <em>time_unit</em></td>
<td>The time scale factor followed by 's'.</td>
</tr>
<tr class="odd">
<td>-voltage <em>voltage_unit</em></td>
<td>The voltage scale factor followed by 'v<strong>'</strong>.</td>
</tr>
<tr class="even">
<td>-current <em>current_unit</em></td>
<td>The current scale factor followed by 'A'.</td>
</tr>
<tr class="odd">
<td>-power <em>power_unit</em></td>
<td>The power scale factor followed by 'w'.</td>
</tr>
<tr class="even">
<td>-distance <em>distance_unit</em></td>
<td>The distance scale factor followed by 'm'.</td>
</tr>
</tbody>
</table>

The set_cmd_units command is used to change the units used by the STA
command interpreter when parsing commands and reporting results. The
default units are the units specified in the first Liberty library file
that is read.

Units are specified as a scale factor followed by a unit name. The scale
factors are as follows.

M 1E+6  
k 1E+3  
m 1E-3  
u 1E-6  
n 1E-9  
p 1E-12  
f 1E-15

An example of the set_units command is shown below.

set_cmd_units -time ns -capacitance pF -current mA -voltage V  
-resistance kOhm -distance um

<table>
<tbody>
<tr class="odd">
<td><strong>set_data_check</strong></td>
<td>[-from|-rise_from|-fall_from <em>from_pin</em>]<br />
[-to|-rise_to|-fall_to <em>to_pin</em>]<br />
[-setup]<br />
[-hold]<br />
[-clock <em>clock</em>]<br />
<em>margin</em></td>
</tr>
<tr class="even">
<td>-from <em>from_pin</em></td>
<td>A pin used as the timing check reference.</td>
</tr>
<tr class="odd">
<td>-to <em>to_pin</em></td>
<td>A pin that the setup/hold check is applied to.</td>
</tr>
<tr class="even">
<td>-setup</td>
<td>Add a setup timing check.</td>
</tr>
<tr class="odd">
<td>-hold</td>
<td>Add a hold timing check.</td>
</tr>
<tr class="even">
<td>-clock <em>clock</em></td>
<td>The setup/hold check clock.</td>
</tr>
<tr class="odd">
<td><em>margin</em></td>
<td>The setup or hold time margin.</td>
</tr>
</tbody>
</table>

The set_data_check command is used to add a setup or hold timing check
between two pins.

|                                           |                                                                            |
| ----------------------------------------- | -------------------------------------------------------------------------- |
| **set_disable_inferred_clock_gating** | *objects*                                                                  |
| *objects*                                 | A list of clock gating instances, clock gating pins, or clock enable pins. |

The set_disable_inferred_clock_gating command disables clock gating
checks on a clock gating instance, clock gating pin, or clock gating
enable pin.

<table>
<tbody>
<tr class="odd">
<td><strong>set_disable_timing</strong></td>
<td>[-from <em>from_port</em>]<br />
[-to <em>to_port</em>]<br />
<em>objects</em></td>
</tr>
<tr class="even">
<td>-from <em>from_port</em></td>
<td></td>
</tr>
<tr class="odd">
<td>-to <em>to_port</em></td>
<td></td>
</tr>
<tr class="even">
<td><em>objects</em></td>
<td>A list of instances, ports, pins, cells, cell/port, or library/cell/port.</td>
</tr>
</tbody>
</table>

The set_disable_timing command is used to disable paths though pins in
the design. There are many different forms of the command depending on
the objects specified in *objects*.

All timing paths though an instance are disabled when *objects* contains
an instance. Timing checks in the instance are *not* disabled.

set_disable_timing u2

The -from and -to options can be used to restrict the disabled path to
those from, to or between specific pins on the instance.

set_disable_timing -from A u2  
set_disable_timing -to Z u2  
set_disable_timing -from A -to Z u2

A list of top level ports or instance pins can also be disabled.

set_disable_timing u2/Z  
set_disable_timing in1

Timing paths though all instances of a library cell in the design can be
disabled by naming the cell using a hierarchy separator between the
library and cell name. Paths from or to a cell port can be disabled with
the -from and -to options or a port name after library and cell names.

set_disable_timing liberty1/snl_bufx2  
set_disable_timing -from A liberty1/snl_bufx  
set_disable_timing -to Z liberty1/snl_bufx  
set_disable_timing liberty1/snl_bufx2/A

<table>
<tbody>
<tr class="odd">
<td><strong>set_drive</strong></td>
<td>[-rise]<br />
[-fall]<br />
[-max]<br />
[-min]<em><br />
resistance<br />
ports</em></td>
</tr>
<tr class="even">
<td>-rise</td>
<td>Set the drive rise resistance.</td>
</tr>
<tr class="odd">
<td>-fall</td>
<td>Set the drive fall resistance.</td>
</tr>
<tr class="even">
<td>-max</td>
<td>Set the maximum resistance.</td>
</tr>
<tr class="odd">
<td>-min</td>
<td>Set the minimum resistance.</td>
</tr>
<tr class="even">
<td><em>resistance</em></td>
<td>The external drive resistance.</td>
</tr>
<tr class="odd">
<td><em>ports</em></td>
<td>A list of ports.</td>
</tr>
</tbody>
</table>

The set_drive command describes the resistance of an input port
external driver.

<table>
<tbody>
<tr class="odd">
<td><strong>set_driving_cell</strong></td>
<td>[-lib_cell <em>cell_name</em>]<br />
[-library <em>library</em>]<br />
[-rise]<br />
[-fall]<br />
[-min]<br />
[-max]<br />
[-pin <em>pin</em>]<br />
[-from_pin <em>from_pin</em>]<br />
[-input_transition_rise <em>trans_rise</em>]<br />
[-input_transition_fall <em>trans_fall</em>]<em><br />
ports</em></td>
</tr>
<tr class="even">
<td>-lib_cell <em>cell_name</em></td>
<td>The driving cell.</td>
</tr>
<tr class="odd">
<td>-library <em>library</em></td>
<td>The driving cell library.</td>
</tr>
<tr class="even">
<td>-rise</td>
<td>Set the driving cell for a risingn edge.</td>
</tr>
<tr class="odd">
<td>-fall</td>
<td>Set the driving cell for a falling edge.</td>
</tr>
<tr class="even">
<td>-max</td>
<td>Set the driving cell for max delays.</td>
</tr>
<tr class="odd">
<td>-min</td>
<td>Set the driving cell for min delays.</td>
</tr>
<tr class="even">
<td>-pin <em>pin</em></td>
<td>The output port of the driving cell.</td>
</tr>
<tr class="odd">
<td>-from_pin <em>from_pin</em></td>
<td>Use timng arcs from <em>from_pin</em> to the output pin.</td>
</tr>
<tr class="even">
<td>-input_transition_rise <em>trans_rise</em></td>
<td>The transition time for a rising input at <em>from_pin</em>.</td>
</tr>
<tr class="odd">
<td>-input_transition_fall <em>trans_fall</em></td>
<td>The transition time for a falling input at <em>from_pin</em>.</td>
</tr>
<tr class="even">
<td><em>ports</em></td>
<td>A list of ports.</td>
</tr>
</tbody>
</table>

The set_driving_cell command describes an input port external driver.

<table>
<tbody>
<tr class="odd">
<td><strong>set_false_path</strong></td>
<td>[-setup]<br />
[-hold]<br />
[-rise]<br />
[-fall]<br />
[-from <em>from_list</em>]<br />
[-rise_from <em>from_list</em>]<br />
[-fall_from <em>from_list</em>]<br />
[-through <em>through_list</em>]<br />
[-rise_through <em>through_list</em>]<br />
[-fall_through <em>through_list</em>]<br />
[-to <em>to_list</em>]<br />
[-rise_to <em>to_list</em>]<br />
[-fall_to <em>to_list</em>]<br />
[-reset_path]</td>
</tr>
<tr class="even">
<td>-setup</td>
<td>Apply to setup checks.</td>
</tr>
<tr class="odd">
<td>-hold</td>
<td>Apply to hold checks.</td>
</tr>
<tr class="even">
<td>-rise</td>
<td>Apply to rising path edges.</td>
</tr>
<tr class="odd">
<td>-fall</td>
<td>Apply to falling path edges.</td>
</tr>
<tr class="even">
<td>-reset_path</td>
<td>Remove any matching set_false_path, set_multicycle_path, set_max_delay, set_min_delay exceptions first.</td>
</tr>
<tr class="odd">
<td>-from <em>from_list</em></td>
<td>A list of clocks, instances, ports or pins.</td>
</tr>
<tr class="even">
<td>-through <em>through_list</em></td>
<td>A list of instances, pins or nets.</td>
</tr>
<tr class="odd">
<td>-to <em>to_list</em></td>
<td>A list of clocks, instances, ports or pins.</td>
</tr>
</tbody>
</table>

The set_false_path command disables timing along a path from, through
and to a group of design objects.

Objects in *from_list* can be clocks, register/latch instances, or
register/latch clock pins. The -rise_from and -fall_from keywords
restrict the false paths to a specific clock edge.

Objects in *through_list* can be nets, instances, instance pins, or
hierarchical pins,. The -rise_through and -fall_through keywords
restrict the false paths to a specific path edge that traverses through
the object.

Objects in *to_list* can be clocks, register/latch instances, or
register/latch clock pins. The -rise_to and -fall_to keywords restrict
the false paths to a specific transition at the path end.

<table>
<tbody>
<tr class="odd">
<td><strong>set_fanout_load</strong></td>
<td><em>fanout<br />
port_list</em></td>
</tr>
</tbody>
</table>

This command is ignored.

|                               |                                                |
| ----------------------------- | ---------------------------------------------- |
| **set_hierarchy_separator** | *separator*                                    |
| *separator*                   | Character used to separate hierarchical names. |

Set the character used to separate names in a hierarchical instance, net
or pin name. This separator is used by the command interpreter to read
arguments and print results. The default separator is '/'.

|                         |                                                       |
| ----------------------- | ----------------------------------------------------- |
| **set_ideal_latency** | [-rise] [-fall] [-min] [-max] *delay objects* |

The set_ideal_latency command is parsed but ignored.

|                         |                                |
| ----------------------- | ------------------------------ |
| **set_ideal_network** | [-no_propagation] *objects* |

The set_ideal_network command is parsed but ignored.

|                            |                                                                  |
| -------------------------- | ---------------------------------------------------------------- |
| **set_ideal_transition** | [-rise] [-fall] [-min] [-max] *transition_time objects* |

The set_ideal_transition command is parsed but ignored.

<table>
<tbody>
<tr class="odd">
<td><strong>set_input_delay</strong></td>
<td>[-rise]<br />
[-fall]<br />
[-max]<br />
[-min]<br />
[-clock <em>clock</em>]<br />
[-clock_fall]<br />
[-reference_pin <em>ref_pin</em>]<br />
[-source_latency_included]<br />
[-network_latency_included]<br />
[-add_delay]<br />
<em>delay<br />
port_pin_list</em></td>
</tr>
<tr class="even">
<td>-rise</td>
<td>Set the arrival time for the rising edge of the input.</td>
</tr>
<tr class="odd">
<td>-fall</td>
<td>Set the arrival time for the falling edge of the input.</td>
</tr>
<tr class="even">
<td>-max</td>
<td>Set the maximum arrival time.</td>
</tr>
<tr class="odd">
<td>-min</td>
<td>Set the minimum arrival time.</td>
</tr>
<tr class="even">
<td>-clock <em>clock</em></td>
<td>The arrival time is from <em>clock</em>.</td>
</tr>
<tr class="odd">
<td>-clock_fall</td>
<td>The arrival time is from the falling edge of <em>clock.</em></td>
</tr>
<tr class="even">
<td>-reference_pin <em>ref_pin</em></td>
<td>The arrival time is with respect to the clock that arrives at <em>ref_pin</em>.</td>
</tr>
<tr class="odd">
<td>-source_latency_included</td>
<td>D no add the clock source latency (insertion delay) to the delay value.</td>
</tr>
<tr class="even">
<td>-network_latency_included</td>
<td>Do not add the clock latency to the delay value when the clock is ideal.</td>
</tr>
<tr class="odd">
<td>-add_delay</td>
<td>Add this arrival to any existing arrivals.</td>
</tr>
<tr class="even">
<td><em>delay</em></td>
<td>The arrival time after <em>clock</em>.</td>
</tr>
<tr class="odd">
<td><em>pin_port_list</em></td>
<td>A list of pins or ports.</td>
</tr>
</tbody>
</table>

The set_input_delay command is used to specify the arrival time of an
input signal.

The following command sets the min, max, rise and fall times on the in1
input port 1.0 time units after the rising edge of clk1.

set_input_delay -clock clk1 1.0 [get_ports in1]

Use multiple commands with the -add_delay option to specifiy separate
arrival times for min, max, rise and fall times or multiple clocks. For
example, the following specifies separate arrival times with respect to
clocks clk1 and clk2.

set_input_delay -clock clk1 1.0 [get_ports in1]  
set_input_delay -add_delay -clock clk2 2.0 [get_ports in1]

The –reference_pin option is used to specify an arrival time with
respect to the arrival on a pin in the clock network. For propagated
clocks, the input arrival time is relative to the clock arrival time at
the reference pin (the clock source latency and network latency from the
clock source to the reference pin). For ideal clocks, input arrival time
is relative to the reference pin clock source latency. With the
-clock_fall flag the arrival time is relative to the falling transition
at the reference pin. If no clocks arrive at the reference pin the
set_input_delay command is ignored. If no -clock is specified the
arrival time is with respect to all clocks that arrive at the reference
pin. The -source_latency_included and -network_latency_included
options cannot be used with -reference_pin.

Paths from inputs that do not have an arrival time defined by
set_input_delay are not reported. Set the
sta_input_port_default_clock variable to 1 to report paths from
inputs without a set_input_delay.

<table>
<tbody>
<tr class="odd">
<td><strong>set_input_transition</strong></td>
<td>[-rise]<br />
[-fall]<br />
[-max]<br />
[-min]<br />
<em>transition<br />
port_list</em></td>
</tr>
<tr class="even">
<td>-rise</td>
<td>Set the rising edge transition.</td>
</tr>
<tr class="odd">
<td>-fall</td>
<td>Set the falling edge transition.</td>
</tr>
<tr class="even">
<td>-max</td>
<td>Set the minimum transition time.</td>
</tr>
<tr class="odd">
<td>-min</td>
<td>Set the maximum transition time.</td>
</tr>
<tr class="even">
<td><em>transition</em></td>
<td>The transition time (slew).</td>
</tr>
<tr class="odd">
<td><em>port_list</em></td>
<td>A list of ports.</td>
</tr>
</tbody>
</table>

The set_input_transition command is used to specify the transition
time (slew) of an input signal.

|                                   |                        |
| --------------------------------- | ---------------------- |
| **set_level_shifter_strategy** | *[-rule rule_type]* |

This command is parsed and ignored by timing analysis.

|                                    |                        |
| ---------------------------------- | ---------------------- |
| **set_level_shifter_threshold** | *[-voltage voltage]* |

This command is parsed and ignored by timing analysis.

<table>
<tbody>
<tr class="odd">
<td><strong>set_load</strong></td>
<td>[-rise]<br />
[-fall]<br />
[-max]<br />
[-min]<br />
[-subtract_pin_load]<br />
[-pin_load]<br />
[-wire_load]<br />
<em>capacitance<br />
objects</em></td>
</tr>
<tr class="even">
<td>-rise</td>
<td>Set the external port rising capacitance (ports only).</td>
</tr>
<tr class="odd">
<td>-fall</td>
<td>Set the external port falling capacitance (ports only).</td>
</tr>
<tr class="even">
<td>-max</td>
<td>Set the max capacitance.</td>
</tr>
<tr class="odd">
<td>-min</td>
<td>Set the min capacitance.</td>
</tr>
<tr class="even">
<td>-subtract_pin_load</td>
<td>Subtract the capacitance of all instance pins connected to the net from <em>capacitance</em> (nets only). If the resulting capacitance is negative, zero is used. Pin capacitances are ignored by delay calculatioin when this option is used.</td>
</tr>
<tr class="odd">
<td>-pin_load</td>
<td><em>capcitance</em> is external instance pin capacitance (ports only).</td>
</tr>
<tr class="even">
<td>-wire_load</td>
<td><em>capcitance</em> is external wire capacitance (ports only).</td>
</tr>
<tr class="odd">
<td><em>capacitance</em></td>
<td>The capacitance, in library capacitance units.</td>
</tr>
<tr class="even">
<td><em>objects</em></td>
<td>A list of nets or ports.</td>
</tr>
</tbody>
</table>

The set_load command annotates wire capacitance on a net or external
capacitance on a port. There are four different uses for the set_load
commanc:

set_load -wire_load *port* external port wire capacitance  
set_load -pin_load *port* external port pin capacitance  
set_load *port* same as -pin_load  
set_load *net* net wire capacitance

External port capacitance can be annotated separately with the
-pin_load and ‑wire_load options. Without the -pin_load and
-wire_load options pin capacitance is annotated.

When annnotating net wire capacitance with the -subtract_pin_load
option the capacitance of all instance pins connected to the net is
subtracted from *capacitance*. Setting the capacitance on a net
overrides SPEF parasitics for delay calculation.

|                    |                        |
| ------------------ | ---------------------- |
| **set_logic_dc** | *port_list*           |
| *port_pin_list*  | List of ports or pins. |

Set a port or pin to a constant unknown logic value. No paths are
propagated from constant pins.

|                     |                        |
| ------------------- | ---------------------- |
| **set_logic_one** | *port_list*           |
| *port_pin_list*   | List of ports or pins. |

Set a port or pin to a constant logic one value. No paths are propagated
from constant pins. Constant values set with the set_logic_one command
are **not** propagated through downstream gates.

|                      |                        |
| -------------------- | ---------------------- |
| **set_logic_zero** | *port_list*           |
| *port_pin_list*    | List of ports or pins. |

Set a port or pin to a constant logic zero value. No paths are
propagated from constant pins. Constant values set with the
set_logic_zero command are **not** propagated through downstream
gates.

|                    |        |
| ------------------ | ------ |
| **set_max_area** | *area* |
| *area*             |        |

The set_max_area command is ignored during timing but is included in
SDC files that are written.

<table>
<tbody>
<tr class="odd">
<td><strong>set_max_capacitance</strong></td>
<td><em>capacitance<br />
objects</em></td>
</tr>
<tr class="even">
<td><em>capacitance</em></td>
<td></td>
</tr>
<tr class="odd">
<td><em>objects</em></td>
<td>List of ports or cells.</td>
</tr>
</tbody>
</table>

The set_max_capacitance command is ignored during timing but is
included in SDC files that are written.

<table>
<tbody>
<tr class="odd">
<td><strong>set_max_delay</strong></td>
<td>[-rise]<br />
[-fall]<br />
[-from <em>from_list</em>]<br />
[-rise_from <em>from_list</em>]<br />
[-fall_from <em>from_list</em>]<br />
[-through <em>through_list</em>]<br />
[-rise_through <em>through_list</em>]<br />
[-fall_through <em>through_list</em>]<br />
[-to <em>to_list</em>]<br />
[-rise_to <em>to_list</em>]<br />
[-fall_to <em>to_list</em>]<br />
[-ignore_clock_latency]<br />
[-probe]<br />
[-reset_path]<br />
<em>delay</em></td>
</tr>
<tr class="even">
<td>-rise</td>
<td>Set max delay for rising paths.</td>
</tr>
<tr class="odd">
<td>-fall</td>
<td>Set max delay for falling paths.</td>
</tr>
<tr class="even">
<td>-from <em>from_list</em></td>
<td>A list of clocks, instances, ports or pins.</td>
</tr>
<tr class="odd">
<td>-through <em>through_list</em></td>
<td>A list of instances, pins or nets.</td>
</tr>
<tr class="even">
<td>-to <em>to_list</em></td>
<td>A list of clocks, instances, ports or pins.</td>
</tr>
<tr class="odd">
<td>-ignore_clock_latency</td>
<td>Ignore clock latency at the source and target registers.</td>
</tr>
<tr class="even">
<td>-probe</td>
<td>Do not break paths at internal pins (non startpoints).</td>
</tr>
<tr class="odd">
<td>-reset_path</td>
<td>Remove any matching set_false_path, set_multicycle_path, set_max_delay, set_min_delay exceptions first.</td>
</tr>
<tr class="even">
<td><em>delay</em></td>
<td>The maximum delay.</td>
</tr>
</tbody>
</table>

The set_max_delay command constrains the maximum delay through
combinational logic paths. See set_false_path for a description of
allowed *from_list*, *through_list* and *to_list* objects. If the
*to_list* ends at a timing check the setup/hold time is included in the
path delay.

When the -ignore_clock_latency option is used clock latency at the
source and destination of the path delay is ignored. The constraint is
reported in the default path group (**default**) rather than the
clock path group when the path ends at a timing check.

|                              |                    |
| ---------------------------- | ------------------ |
| **set_max_dynamic_power** | *power* [*unit*] |

The set_max_dynamic_power command is ignored.

<table>
<tbody>
<tr class="odd">
<td><strong>set_max_fanout</strong></td>
<td><em>fanout<br />
objects</em></td>
</tr>
<tr class="even">
<td><em>fanout</em></td>
<td></td>
</tr>
<tr class="odd">
<td><em>objects</em></td>
<td>List of ports or cells.</td>
</tr>
</tbody>
</table>

The set_max_fanout command is ignored during timing but is included in
SDC files that are written.

|                              |                    |
| ---------------------------- | ------------------ |
| **set_max_leakage_power** | *power* [*unit*] |

The set_max_leakage_power command is ignored.

<table>
<tbody>
<tr class="odd">
<td><strong>set_max_time_borrow</strong></td>
<td><em>delay<br />
objects</em></td>
</tr>
<tr class="even">
<td><em>delay</em></td>
<td>The maximum time the latches can borrow.</td>
</tr>
<tr class="odd">
<td><em>objects</em></td>
<td>List of clocks, instances or pins.</td>
</tr>
</tbody>
</table>

The set_max_time_borrow command specifies the maximum amount of time
that latches can borrow. Time borrowing is the time that a data input to
a transparent latch arrives after the latch opens.

<table>
<tbody>
<tr class="odd">
<td><strong>set_max_transition</strong></td>
<td>[-data_path]<br />
[-clock_path]<br />
[-rise]<br />
[-fall]<br />
<em>transition<br />
objects</em></td>
</tr>
<tr class="even">
<td>-data_path</td>
<td>Set the max slew for data paths.</td>
</tr>
<tr class="odd">
<td>-clock_path</td>
<td>Set the max slew for clock paths.</td>
</tr>
<tr class="even">
<td>-rise</td>
<td>Set the max slew for rising paths.</td>
</tr>
<tr class="odd">
<td>-fall</td>
<td>Set the max slew for falling paths.</td>
</tr>
<tr class="even">
<td><em>transition</em></td>
<td>The maximum slew/transition time.</td>
</tr>
<tr class="odd">
<td><em>objects</em></td>
<td>List of clocks, ports or designs.</td>
</tr>
</tbody>
</table>

The set_max_transition command is specifies the maximum transition
time (slew) design rule checked by the report_check_types
–max_transition command.

If specified for a design, the default maximum transition is set for the
design.

If specified for a clock, the maximum transition is applied to all pins
in the clock domain. The –clock_path option restricts the maximum
transition to clocks in clock paths. The -data_path option restricts
the maximum transition to clocks data paths. The –clock_path,
-data_path, -rise and –fall options only apply to clock objects.

<table>
<tbody>
<tr class="odd">
<td><strong>set_min_capacitance</strong></td>
<td><em>capacitance<br />
objects</em></td>
</tr>
<tr class="even">
<td><em>capacitance</em></td>
<td>Minimum capacitance.</td>
</tr>
<tr class="odd">
<td><em>objects</em></td>
<td>List of ports or cells.</td>
</tr>
</tbody>
</table>

The set_min_capacitance command is ignored during timing but is
included in SDC files that are written.

<table>
<tbody>
<tr class="odd">
<td><strong>set_min_delay</strong></td>
<td>[-rise]<br />
[-fall]<br />
[-from <em>from_list</em>]<br />
[-rise_from <em>from_list</em>]<br />
[-fall_from <em>from_list</em>]<br />
[-through <em>through_list</em>]<br />
[-rise_through <em>through_list</em>]<br />
[-fall_through <em>through_list</em>]<br />
[-to <em>to_list</em>]<br />
[-rise_to <em>to_list</em>]<br />
[-fall_to <em>to_list</em>]<br />
[-ignore_clock_latency]<br />
[-probe]<br />
[-reset_path]<br />
<em>delay</em></td>
</tr>
<tr class="even">
<td>-rise</td>
<td>Set min delay for rising paths.</td>
</tr>
<tr class="odd">
<td>-fall</td>
<td>Set min delay for falling paths.</td>
</tr>
<tr class="even">
<td>-from <em>from_list</em></td>
<td>A list of clocks, instances, ports or pins.</td>
</tr>
<tr class="odd">
<td>-through <em>through_list</em></td>
<td>A list of instances, pins or nets.</td>
</tr>
<tr class="even">
<td>-to <em>to_list</em></td>
<td>A list of clocks, instances, ports or pins.</td>
</tr>
<tr class="odd">
<td>-ignore_clock_latency</td>
<td>Ignore clock latency at the source and target registers.</td>
</tr>
<tr class="even">
<td>-probe</td>
<td>Do not break paths at internal pins (non startpoints).</td>
</tr>
<tr class="odd">
<td>-reset_path</td>
<td>Remove any matching set_false_path, set_multicycle_path, set_max_delay, set_min_delay exceptions first.</td>
</tr>
<tr class="even">
<td><em>delay</em></td>
<td>The minimum delay.</td>
</tr>
</tbody>
</table>

The set_min_delay command constrains the minimum delay through
combinational logic. See set_false_path for a description of allowed
*from_list*, *through_list* and *to_list* objects. If the *to_list*
ends at a timing check the setup/hold time is included in the path
delay.

When the -ignore_clock_latency option is used clock latency at the
source and destination of the path delay is ignored. The constraint is
reported in the default path group (**default**) rather than the
clock path group when the path ends at a timing check.

<table>
<tbody>
<tr class="odd">
<td><strong>set_min_pulse_width</strong></td>
<td>[-high]<br />
[-low]<em><br />
min_width<br />
objects</em></td>
</tr>
<tr class="even">
<td>-high</td>
<td>Set the minimum high pulse width.</td>
</tr>
<tr class="odd">
<td>-low</td>
<td>Set the minimum low pulse width.</td>
</tr>
<tr class="even">
<td><em>min_width</em></td>
<td></td>
</tr>
<tr class="odd">
<td><em>objects</em></td>
<td>List of pins, instances or clocks.</td>
</tr>
</tbody>
</table>

If -low and -high are not specified the minimum width applies to both
high and low pulses.

<table>
<tbody>
<tr class="odd">
<td><strong>set_multicycle_path</strong></td>
<td>[-setup]<br />
[-hold]<br />
[-rise]<br />
[-fall]<br />
[-start]<br />
[-end]<br />
[-from <em>from_list</em>]<br />
[-rise_from <em>from_list</em>]<br />
[-fall_from <em>from_list</em>]<br />
[-through <em>through_list</em>]<br />
[-rise_through <em>through_list</em>]<br />
[-fall_through <em>through_list</em>]<br />
[-to <em>to_list</em>]<br />
[-rise_to <em>to_list</em>]<br />
[-fall_to <em>to_list</em>]<br />
[-reset_path]<br />
<em>path_multiplier</em></td>
</tr>
<tr class="even">
<td>-setup</td>
<td>Set cycle count for setup checks.</td>
</tr>
<tr class="odd">
<td>-hold</td>
<td>Set cycle count for hold checks.</td>
</tr>
<tr class="even">
<td>-rise</td>
<td>Set cycle count for rising path edges.</td>
</tr>
<tr class="odd">
<td>-fall</td>
<td>Set cycle count for falling path edges.</td>
</tr>
<tr class="even">
<td>-start</td>
<td>Multiply the source clock period by <em>period_multiplier</em>.</td>
</tr>
<tr class="odd">
<td>-end</td>
<td>Multiply the target clock period by <em>period_multiplier</em>.</td>
</tr>
<tr class="even">
<td>-from <em>from_list</em></td>
<td>A list of clocks, instances, ports or pins.</td>
</tr>
<tr class="odd">
<td>-through <em>through_list</em></td>
<td>A list of instances, pins or nets.</td>
</tr>
<tr class="even">
<td>-to <em>to_list</em></td>
<td>A list of clocks, instances, ports or pins.</td>
</tr>
<tr class="odd">
<td>-reset_path</td>
<td>Remove any matching set_false_path, set_multicycle_path, set_max_delay, set_min_delay exceptions first.</td>
</tr>
<tr class="even">
<td><em>path_multiplier</em></td>
<td>The number of clock periods to add to the path required time.</td>
</tr>
</tbody>
</table>

Normally the path between two registers or latches is assumed to take
one clock cycle. The set_multicycle_path command overrides this
assumption and allows multiple clock cycles for a timing check. See
set_false_path for a description of allowed *from_list*,
*through_list* and *to_list* objects.

<table>
<tbody>
<tr class="odd">
<td><strong>set_operating_conditions</strong></td>
<td>[-analysis_type single|bc_wc|on_chip_variation]<br />
[-library <em>lib</em>]<br />
[<em>condition</em>]<br />
[-min <em>min_condition</em>]<br />
[-max <em>max_condition</em>]<br />
[-min_library <em>min_lib</em>]<br />
[-max_library <em>max_lib</em>]</td>
</tr>
<tr class="even">
<td>-analysis_type single</td>
<td>Use one operating condition for min and max paths.</td>
</tr>
<tr class="odd">
<td>-analysis_type bc_wc</td>
<td>Best case, worst case analysis. Setup checks use <em>max_condition</em> for clock and data paths. Hold checks use the <em>min_condition</em> for clock and data paths.</td>
</tr>
<tr class="even">
<td>‑analysis_type on_chip_variation</td>
<td>The min and max operating conditions represent variations on the chip that can occur simultaineously. Setup checks use <em>max_condition</em> for data paths and <em>min_condition</em> for clock paths. Hold checks use <em>min_condition</em> for data paths and <em>max_condition</em> for clock paths. This is the default analysis type.</td>
</tr>
<tr class="odd">
<td>-library <em>lib</em></td>
<td>The name of the library that contains <em>condition</em>.</td>
</tr>
<tr class="even">
<td><em>condition</em></td>
<td>The operating condition for analysis type single.</td>
</tr>
<tr class="odd">
<td>-min <em>min_condition</em></td>
<td>The operating condition to use for min paths and hold checks.</td>
</tr>
<tr class="even">
<td>-max <em>max_condition</em></td>
<td>The operating condition to use for max paths and setup checks.</td>
</tr>
<tr class="odd">
<td>-min_library <em>min_lib</em></td>
<td>The name of the library that contains <em>min_condition</em>.</td>
</tr>
<tr class="even">
<td>-max_library <em>max_lib</em></td>
<td>The name of the library that contains <em>max_condition</em>.</td>
</tr>
</tbody>
</table>

The set_operating_conditions command is used to specify the type of
analysis performed and the operating conditions used to derate library
data.

<table>
<tbody>
<tr class="odd">
<td><strong>set_output_delay</strong></td>
<td>[-rise]<br />
[-fall]<br />
[-max]<br />
[-min]<br />
[-clock <em>clock</em>]<br />
[-clock_fall]<br />
[-reference_pin <em>ref_pin</em>]<br />
[-source_latency_included]<br />
[-network_latency_included]<br />
[-add_delay]<br />
<em>delay<br />
port_pin_list</em></td>
</tr>
<tr class="even">
<td>-rise</td>
<td>Set the output delay for the rising edge of the input.</td>
</tr>
<tr class="odd">
<td>-fall</td>
<td>Set the output delay for the falling edge of the input.</td>
</tr>
<tr class="even">
<td>-max</td>
<td>Set the maximum output delay.</td>
</tr>
<tr class="odd">
<td>-min</td>
<td>Set the minimum output delay.</td>
</tr>
<tr class="even">
<td>-clock <em>clock</em></td>
<td>The external check is to clock. The default clock edge is rising.</td>
</tr>
<tr class="odd">
<td>-clock_fall</td>
<td>The external check is to the falling edge of <em>clock</em>.</td>
</tr>
<tr class="even">
<td>-reference_pin <em>ref_pin</em></td>
<td>The external check is clocked by the clock that arrives at <em>ref_pin</em>.</td>
</tr>
<tr class="odd">
<td>-add_delay</td>
<td>Add this output delay to any existing output delays.</td>
</tr>
<tr class="even">
<td><em>delay</em></td>
<td>The external delay to the check clocked by <em>clock</em>.</td>
</tr>
<tr class="odd">
<td><em>pin_port_list</em></td>
<td>A list of pins or ports.</td>
</tr>
</tbody>
</table>

The set_output_delay command is used to specify the external delay to
a setup/hold check on an output port or internal pin that is clocked by
*clock*. Unless the -add_delay option is specified any existing output
delays are replaced.

The –reference_pin option is used to specify a timing check with
respect to the arrival on a pin in the clock network. For propagated
clocks, the timing check is relative to the clock arrival time at the
reference pin (the clock source latency and network latency from the
clock source to the reference pin). For ideal clocks, the timing check
is relative to the reference pin clock source latency. With the
-clock_fall flag the timing check is relative to the falling edge of
the reference pin. If no clocks arrive at the reference pin the
set_output_delay command is ignored. If no -clock is specified the
timing check is with respect to all clocks that arrive at the reference
pin. The -source_latency_included and -network_latency_included
options cannot be used with -reference_pin.

<table>
<tbody>
<tr class="odd">
<td><strong>set_port_fanout_number</strong></td>
<td>[-min]<br />
[-max]<br />
<em>fanout<br />
ports</em></td>
</tr>
<tr class="even">
<td>-min</td>
<td>Set the min fanout.</td>
</tr>
<tr class="odd">
<td>-max</td>
<td>Set the max fanout.</td>
</tr>
<tr class="even">
<td><em>fanout</em></td>
<td>The external fanout of the ports.</td>
</tr>
<tr class="odd">
<td><em>port_list</em></td>
<td>A list of ports.</td>
</tr>
</tbody>
</table>

Set the external fanout for *ports*.

<table>
<tbody>
<tr class="odd">
<td><strong>set_power_activity</strong></td>
<td>[-global]<br />
[-input]<br />
[-input_ports <em>ports</em>]<br />
[-pins <em>pins</em>]<br />
[-activity <em>activity |</em> -density density]<br />
[-duty <em>duty</em>]<br />
[-clock <em>clock</em>]</td>
</tr>
<tr class="even">
<td><em>-</em>global</td>
<td>Set the activity/duty for all non-clock pins.</td>
</tr>
<tr class="odd">
<td>-input</td>
<td>Set the default input port activity/duty.</td>
</tr>
<tr class="even">
<td>-input_ports <em>input_ports</em></td>
<td>Set the input port activity/duty.</td>
</tr>
<tr class="odd">
<td>-pins <em>pins</em></td>
<td>Set the pin activity/duty.</td>
</tr>
<tr class="even">
<td>-activity <em>activity</em></td>
<td>The activity, or number of transitions per clock cycle. If <em>clock</em> is not specified the clock with the minimum period is used. If no clocks are defined an error is reported.</td>
</tr>
<tr class="odd">
<td>-density <em>density</em></td>
<td>Transitioins per library time unit.</td>
</tr>
<tr class="even">
<td>-d<em>ut</em>y <em>duty</em></td>
<td>The duty, or probability the signal is high (0 &lt;= duty &lt;= 1.0). Defaults to 0.5.</td>
</tr>
<tr class="odd">
<td>-clock <em>clock</em></td>
<td>The clock to use for the period with -activity. This option is ignored if -density is used.</td>
</tr>
</tbody>
</table>

The set_power_activity command is used to set the activity and duty
used for power analysis globally or for input ports or pins in the
design.

The default input activity for inputs is 0.1 transitions per minimum
clock period if a clock is defined or 0.0 if there are no clocks
defined. The default input duty is 0.5. This is equivalent to the
following command:

set_power_activity -input -activity 0.1 -duty 0.5

|                            |                                  |
| -------------------------- | -------------------------------- |
| **set_propagated_clock** | *objects*                        |
| *objects*                  | A list of clocks, ports or pins. |

The set_propagated_clock command changes a clock tree from an ideal
network that has no delay one that uses calculated or back-annotated
gate and interconnect delays. When *objects* is a port or pin, clock
delays downstream of the object are used.

<table>
<tbody>
<tr class="odd">
<td><strong>set_pvt</strong></td>
<td><p>[-min]<br />
[-max]<br />
[-process <em>process</em>]<br />
[-voltage <em>voltage</em>]</p>
<p>[-temperature <em>temperature</em>]<br />
<em>instances</em></p></td>
</tr>
<tr class="even">
<td>-min</td>
<td>Set the PVT values for max delays.</td>
</tr>
<tr class="odd">
<td>-max</td>
<td>Set the PVT values for min delays.</td>
</tr>
<tr class="even">
<td>-process <em>process</em></td>
<td>A process value (float).</td>
</tr>
<tr class="odd">
<td>-voltage <em>voltage</em></td>
<td>A voltage value (float).</td>
</tr>
<tr class="even">
<td>-temperature <em>temperature</em></td>
<td>A temperature value (float).</td>
</tr>
<tr class="odd">
<td><em>instances</em></td>
<td>A list instances.</td>
</tr>
</tbody>
</table>

The set_pvt command sets the process, voltage and temperature values
used during delay calculation for a specific instance in the design.

<table>
<tbody>
<tr class="odd">
<td><strong>set_sense</strong></td>
<td>[-type clock|data]<br />
[-positive]<br />
[-negative]<br />
[-pulse <em>pulse_type</em>]<br />
[-stop_propagation]<br />
[-clock <em>clocks</em>]<br />
<em>pins</em></td>
</tr>
<tr class="even">
<td>-type clock</td>
<td>Set the sense for clock paths.</td>
</tr>
<tr class="odd">
<td>-type data</td>
<td>Set the sense for data paths (not supported).</td>
</tr>
<tr class="even">
<td>-positive</td>
<td>The clock sense is positive unate.</td>
</tr>
<tr class="odd">
<td>-negative</td>
<td>The clock sense is negative unate.</td>
</tr>
<tr class="even">
<td>-pulse <em>pulse_type</em></td>
<td>rise_triggered_high_pulse<br />
rise_triggered_low_pulse<br />
fall_triggered_high_pulse<br />
fall_triggered_low_pulse<br />
Not supported.</td>
</tr>
<tr class="odd">
<td>-stop_propagation</td>
<td>Stop propagating <em>clocks</em> at <em>pins</em>.</td>
</tr>
<tr class="even">
<td><em>clocks</em></td>
<td>A list of clocks to apply the sense.</td>
</tr>
<tr class="odd">
<td><em>pins</em></td>
<td>A list of pins.</td>
</tr>
</tbody>
</table>

The set_sense command is used to modify the propagation of a clock
signal. The clock sense is set with the ‑positive and –negative flags.
Use the –stop_propagation flag to stop the clock from propagating
beyond a pin. The –positive, -negative, -stop_propagation, and –pulse
options are mutually exclusive. If the –clock option is not used the
command applies to all clocks that traverse *pins*. The –pulse option is
currently not supported.

<table>
<tbody>
<tr class="odd">
<td><strong>set_timing_derate</strong></td>
<td>[-rise]<br />
[-fall]<br />
[-early]<br />
[-late]<br />
[-clock]<br />
[-data]<br />
[-net_delay]<br />
[-cell_delay]<br />
[-cell_check]<br />
<em>derate<br />
</em>[<em>objects</em>]</td>
</tr>
<tr class="even">
<td>-rise</td>
<td>Set the derating for rising delays.</td>
</tr>
<tr class="odd">
<td>-fall</td>
<td>Set the derating for falling delays.</td>
</tr>
<tr class="even">
<td>-early</td>
<td>Derate early (min) paths.</td>
</tr>
<tr class="odd">
<td>-late</td>
<td>Derate late (max) paths.</td>
</tr>
<tr class="even">
<td>-clock</td>
<td>Derate paths in the clock network.</td>
</tr>
<tr class="odd">
<td>-data</td>
<td>Derate data paths.</td>
</tr>
<tr class="even">
<td>-net_delay</td>
<td>Derate net (interconnect) delays.</td>
</tr>
<tr class="odd">
<td>-cell_delay</td>
<td>Derate cell delays.</td>
</tr>
<tr class="even">
<td>-cell_check</td>
<td>Derate cell timing check margins.</td>
</tr>
<tr class="odd">
<td><em>derate</em></td>
<td>The derating factor to apply to delays.</td>
</tr>
<tr class="even">
<td><em>objects</em></td>
<td>A list of instances, library cells, or nets.</td>
</tr>
</tbody>
</table>

The set_timing_derate command is used to derate delay calculation
results used by the STA. If the –early and –late flags are omitted the
both min and max paths are derated. If the –clock and –data flags are
not used the derating both clock and data paths are derated.

Use the unset_timing_derate command to remove all derating factors.

<table>
<tbody>
<tr class="odd">
<td><strong>set_resistance</strong></td>
<td>[-max]<br />
[-min]<br />
<em>resistance<br />
nets</em></td>
</tr>
<tr class="even">
<td>-min</td>
<td>The resistance for minimum path delay calculation.</td>
</tr>
<tr class="odd">
<td>-max</td>
<td>The resistance for maximum path delay calculation.</td>
</tr>
<tr class="even">
<td><em>resistance</em></td>
<td>The net resistance.</td>
</tr>
<tr class="odd">
<td><em>nets</em></td>
<td>A list of nets.</td>
</tr>
</tbody>
</table>

<table>
<tbody>
<tr class="odd">
<td><strong>set_units</strong></td>
<td>[-capacitance <em>cap_unit</em>]<br />
[-resistance <em>res_unit</em>]<br />
[-time <em>time_unit</em>]<br />
[-voltage <em>voltage_unit</em>]<br />
[-current <em>current_unit</em>]<br />
[-power <em>power_unit</em>]<br />
[-distance <em>distance_unit</em>]</td>
</tr>
<tr class="even">
<td><em>-capacitance cap_unit</em></td>
<td>The capacitance scale factor followed by 'f'.</td>
</tr>
<tr class="odd">
<td><em>-resistance res_unit</em></td>
<td>The resistance scale factor followed by 'ohm'.</td>
</tr>
<tr class="even">
<td><em>-time time_unit</em></td>
<td>The time scale factor followed by 's'.</td>
</tr>
<tr class="odd">
<td><em>-voltage voltage_unit</em></td>
<td>The voltage scale factor followed by 'v'.</td>
</tr>
<tr class="even">
<td><em>-current current_unit</em></td>
<td>The current scale factor followed by 'A'.</td>
</tr>
<tr class="odd">
<td><em>-power power_unit</em></td>
<td>The power scale factor followed by 'w'.</td>
</tr>
</tbody>
</table>

The set_units command is used to **check** the units used by the STA
command interpreter when parsing commands and reporting results. If the
current units differ from the set_unit value a warning is printed. Use
the set_cmd_units command to change the command units.

Units are specified as a scale factor followed by a unit name. The scale
factors are as follows.

M 1E+6  
k 1E+3  
m 1E-3  
u 1E-6  
n 1E-9  
p 1E-12  
f 1E-15

An example of the set_units command is shown below.

set_units -time ns -capacitance pF -current mA -voltage V -resistance
kOhm

|                                       |        |
| ------------------------------------- | ------ |
| **set_wire_load_min_block_size** | *size* |

The set_wire_load_min_block_size command is not supported.

|                           |                        |
| ------------------------- | ---------------------- |
| **set_wire_load_mode** | top|enclosed|segmented |
| top                       |                        |
| enclosed                  |                        |
| segmented                 |                        |

The set_wire_load_mode command is ignored during timing but is
included in SDC files that are written.

<table>
<tbody>
<tr class="odd">
<td><strong>set_wire_load_model</strong></td>
<td>-name <em>model_name<br />
</em>[-library <em>library</em>]<em><br />
</em>[-max]<br />
[-min]<em><br />
</em>[<em>objects</em>]</td>
</tr>
<tr class="even">
<td>-name <em>model_name</em></td>
<td>The name of a wire load model.</td>
</tr>
<tr class="odd">
<td>-library <em>library</em></td>
<td>Library to look for <em>model_name</em>.</td>
</tr>
<tr class="even">
<td>-max</td>
<td>The wire load model is for maximum path delays.</td>
</tr>
<tr class="odd">
<td>-min</td>
<td>The wire load model is for minimum path delays.</td>
</tr>
<tr class="even">
<td><em>objects</em></td>
<td>Not supported.</td>
</tr>
</tbody>
</table>

<table>
<tbody>
<tr class="odd">
<td><strong>set_wire_load_selection_group</strong></td>
<td>[-library <em>library</em>]<em><br />
</em>[-max]<br />
[-min]<br />
<em>group_name<br />
</em>[<em>objects</em>]</td>
</tr>
<tr class="even">
<td><em>library</em></td>
<td>Library to look for <em>group_name</em>.</td>
</tr>
<tr class="odd">
<td>-max</td>
<td>The wire load selection is for maximum path delays.</td>
</tr>
<tr class="even">
<td>-min</td>
<td>The wire load selection is for minimum path delays.</td>
</tr>
<tr class="odd">
<td><em>group_name</em></td>
<td>A wire load selection group name.</td>
</tr>
<tr class="even">
<td><em>objects</em></td>
<td>Not supported.</td>
</tr>
</tbody>
</table>

The set_wire_load_selection_group command is parsed but not
supported.

|                   |                                                  |
| ----------------- | ------------------------------------------------ |
| **suppress_msg** | *msg_ids*                                       |
| *msg_ids*        | A list of error/warning message IDs to suppress. |

The suppress_msg command suppresses specified error/warning messages by
ID. The list of message IDs can be found in *doc/messages.txt.*

|                           |                          |
| ------------------------- | ------------------------ |
| **unset_case_analysis** | *port_or_pin_list*    |
| *port_or_pin_list*     | A list of ports or pins. |

The unset_case_analysis command removes the constant values defined by
the set_case_analysis command.

<table>
<tbody>
<tr class="odd">
<td><strong>unset_clock_latency</strong></td>
<td><em>[-source]<br />
objects</em></td>
</tr>
<tr class="even">
<td><em>-source</em></td>
<td><em>Specifies source clock latency (clock insertion delay).</em></td>
</tr>
<tr class="odd">
<td><em>objects</em></td>
<td>A list of clocks, pins or ports.</td>
</tr>
</tbody>
</table>

The unset_clock_latency command removes the clock latency set with the
set_clock_latency command.

|                              |                   |
| ---------------------------- | ----------------- |
| **unset_clock_transition** | *clocks*          |
| *clocks*                     | A list of clocks. |

The unset_clock_transition command removes the clock transition set
with the set_clock_transition command.

<table>
<tbody>
<tr class="odd">
<td><strong>unset_clock_uncertainty</strong></td>
<td>[-from|-rise_from|-fall_from <em>from_clock</em>]<em><br />
</em>[<em>-</em>to|-rise_to|-fall_to <em>to_clock</em>]<br />
[-rise]<br />
[-fall]<br />
[-setup]<br />
[-hold]<em><br />
</em>[<em>objects</em>]</td>
</tr>
<tr class="even">
<td>-from <em>from_clock</em></td>
<td></td>
</tr>
<tr class="odd">
<td>-to <em>to_clock</em></td>
<td></td>
</tr>
<tr class="even">
<td>-rise</td>
<td>The uncertainty is for the rising edge of the clock.</td>
</tr>
<tr class="odd">
<td>-fall</td>
<td>The uncertainty is for the falling edge of the clock.</td>
</tr>
<tr class="even">
<td>-setup</td>
<td><em>uncertainty</em> is the setup check uncertainty.</td>
</tr>
<tr class="odd">
<td>-hold</td>
<td><em>uncertainty</em> is the hold uncertainty.</td>
</tr>
<tr class="even">
<td><em>uncertainty</em></td>
<td>Clock uncertainty.</td>
</tr>
<tr class="odd">
<td><em>objects</em></td>
<td>A list of clocks, ports or pins.</td>
</tr>
</tbody>
</table>

The unset_clock_uncertainty command removes clock uncertainty defined
with the set_clock_uncertainty command.

<table>
<tbody>
<tr class="odd">
<td><strong>unset_data_check</strong></td>
<td>[-from|-rise_from|-fall_from <em>from_object</em>]<br />
[-to|-rise_to|-fall_to <em>to_object</em>]<br />
[-setup]<br />
[-hold]<br />
[-clock <em>clock</em>]</td>
</tr>
<tr class="even">
<td>-from <em>from_object</em></td>
<td>A pin used as the timing check reference.</td>
</tr>
<tr class="odd">
<td><em>-to to_object</em></td>
<td>A pin that the setup/hold check is applied to.</td>
</tr>
<tr class="even">
<td>-setup</td>
<td>Add a setup timing check.</td>
</tr>
<tr class="odd">
<td>-hold</td>
<td>Add a hold timing check.</td>
</tr>
<tr class="even">
<td><em>clock</em></td>
<td>The setup/hold check clock.</td>
</tr>
</tbody>
</table>

The unset_clock_transition command removes a setup or hold check
defined by the set_data_check command.

|                                             |                                                                            |
| ------------------------------------------- | -------------------------------------------------------------------------- |
| **unset_disable_inferred_clock_gating** | *objects*                                                                  |
| *objects*                                   | A list of clock gating instances, clock gating pins, or clock enable pins. |

The unset_disable_inferred_clock_gating command removes a previous
set_disable_inferred_clock_gating command.

<table>
<tbody>
<tr class="odd">
<td><strong>unset_disable_timing</strong></td>
<td>[-from <em>from_port</em>]<br />
[-to <em>to_port</em>]<br />
<em>objects</em></td>
</tr>
<tr class="even">
<td><em>from_port</em></td>
<td></td>
</tr>
<tr class="odd">
<td><em>to_port</em></td>
<td></td>
</tr>
<tr class="even">
<td><em>objects</em></td>
<td>A list of instances, ports, pins, cells or [library/]cell/port.</td>
</tr>
</tbody>
</table>

The unset_disable_timing command is used to remove the effect of
previous set_disable_timing commands.

<table>
<tbody>
<tr class="odd">
<td><strong>unset_input_delay</strong></td>
<td>[-rise]<br />
[-fall]<br />
[-max]<br />
[-min]<br />
[-clock <em>clock</em>]<br />
[-clock_fall]<br />
<em>port_pin_list</em></td>
</tr>
<tr class="even">
<td>-rise</td>
<td>Unset the arrival time for the rising edge of the input.</td>
</tr>
<tr class="odd">
<td>-fall</td>
<td>Unset the arrival time for the falling edge of the input.</td>
</tr>
<tr class="even">
<td>-max</td>
<td>Unset the minimum arrival time.</td>
</tr>
<tr class="odd">
<td>-min</td>
<td>Unset the maximum arrival time.</td>
</tr>
<tr class="even">
<td><em>clock</em></td>
<td>Unset the arrival time from <em>clock</em>.</td>
</tr>
<tr class="odd">
<td>-clock_fall</td>
<td>Unset the arrival time from the falling edge of <em>clock</em></td>
</tr>
<tr class="even">
<td><em>pin_port_list</em></td>
<td>A list of pins or ports.</td>
</tr>
</tbody>
</table>

The unset_input_delay command removes a previously defined
set_input_delay.

<table>
<tbody>
<tr class="odd">
<td><strong>unset_output_delay</strong></td>
<td>[-rise]<br />
[-fall]<br />
[-max]<br />
[-min]<br />
[-clock <em>clock</em>]<br />
[-clock_fall]<br />
<em>port_pin_list</em></td>
</tr>
<tr class="even">
<td>-rise</td>
<td>This is the arrival time for the rising edge of the input.</td>
</tr>
<tr class="odd">
<td>-fall</td>
<td>This is the arrival time for the falling edge of the input.</td>
</tr>
<tr class="even">
<td>-max</td>
<td>This is the minimum arrival time.</td>
</tr>
<tr class="odd">
<td>-min</td>
<td>This is the maximum arrival time.</td>
</tr>
<tr class="even">
<td><em>clock</em></td>
<td>The arrival time is from this clock.</td>
</tr>
<tr class="odd">
<td>-clock_fall</td>
<td>The arrival time is from the falling edge of <em>clock</em></td>
</tr>
<tr class="even">
<td><em>pin_port_list</em></td>
<td>A list of pins or ports.</td>
</tr>
</tbody>
</table>

The unset_output_delay command a previously defined
set_output_delay.

<table>
<tbody>
<tr class="odd">
<td><strong>unset_path_exceptions</strong></td>
<td>[-setup]<br />
[-hold]<br />
[-rise]<br />
[-fall]<br />
[-from|-rise_from|-fall_from <em>from</em>]<br />
[-through|-rise_through|-fall_through <em>through</em>]<br />
[-to|-rise_to|-fall_to <em>to</em>]</td>
</tr>
<tr class="even">
<td>-setup</td>
<td>Unset path exceptions for setup checks.</td>
</tr>
<tr class="odd">
<td>-hold</td>
<td>Unset path exceptions for hold checks.</td>
</tr>
<tr class="even">
<td>-rise</td>
<td>Unset path exceptions for rising path edges.</td>
</tr>
<tr class="odd">
<td>-fall</td>
<td>Unset path exceptions for falling path edges.</td>
</tr>
<tr class="even">
<td>-from <em>from</em></td>
<td>A list of clocks, instances, ports or pins.</td>
</tr>
<tr class="odd">
<td>-through <em>through</em></td>
<td>A list of instances, pins or nets.</td>
</tr>
<tr class="even">
<td>-to <em>to</em></td>
<td>A list of clocks, instances, ports or pins.</td>
</tr>
</tbody>
</table>

The unset_path_exceptions command removes any matching
set_false_path, set_multicycle_path, set_max_delay, and
set_min_delay exceptions.

<table>
<tbody>
<tr class="odd">
<td><strong>unset_power_activity</strong></td>
<td>[-global]<br />
[-input]<br />
[-input_ports <em>ports</em>]<br />
[-pins <em>pins</em>]</td>
</tr>
<tr class="even">
<td><em>-</em>global</td>
<td>Set the activity/duty for all non-clock pins.</td>
</tr>
<tr class="odd">
<td>-input</td>
<td>Set the default input port activity/duty.</td>
</tr>
<tr class="even">
<td>-input_ports <em>input_ports</em></td>
<td>Set the input port activity/duty.</td>
</tr>
<tr class="odd">
<td>-pins <em>pins</em></td>
<td>Set the pin activity/duty.</td>
</tr>
<tr class="even">
<td>-activity <em>activity</em></td>
<td>The activity, or number of transitions per clock cycle. If <em>clock</em> is not specified the clock with the minimum period is used. If no clocks are defined an error is reported.</td>
</tr>
</tbody>
</table>

The unset_power_activity_command is used to undo the efffects of the
set_power_activity command.

|                              |                                  |
| ---------------------------- | -------------------------------- |
| **unset_propagated_clock** | *objects*                        |
| *objects*                    | A list of clocks, ports or pins. |

Remove a previous set_propagated_clock command.

|                           |  |
| ------------------------- |  |
| **unset_timing_derate** |  |

Remove all derating factors set with the set_timing_derate command.

|                     |                                                    |
| ------------------- | -------------------------------------------------- |
| **unsuppress_msg** | *msg_ids*                                         |
| *msg_ids*          | A list of error/warning message IDs to unsuppress. |

The unsuppress_msg command removes suppressions for the specified
error/warning messages by ID. The list of message IDs can be found in
*doc/messages.txt.*

|                     |  |
| ------------------- |  |
| **user_run_time** |  |

Returns the total user cpu run time in seconds as a float.

|                                |                                                             |
| ------------------------------ | ----------------------------------------------------------- |
| **with_output_to_variable** | *var* { *commands* }                                        |
| *var*                          | The name of a variable to save the output of *commands* to. |
| *commands*                     | TCL commands that the output will be redirected from.       |

The with_output_to_variable command redirects the output of TCL
commands to a variable.

<table>
<tbody>
<tr class="odd">
<td><strong>write_path_spice</strong></td>
<td>-path_args <em>path_args</em><br />
-spice_directory <em>spice_directory</em><br />
-lib_subckt_file <em>lib_subckts_file</em><br />
-model_file <em>model_file</em><br />
-power <em>power</em><br />
-ground <em>ground<br />
</em>[-simulator hspice|ngspice|xyce]</td>
</tr>
<tr class="even">
<td><em>path_args</em></td>
<td>-from|-through|-to arguments as in report_checks.</td>
</tr>
<tr class="odd">
<td><em>spice_directory</em></td>
<td>Directory for spice to write output files.</td>
</tr>
<tr class="even">
<td><em>lib_subckts_file</em></td>
<td>Cell transistor level subckts.</td>
</tr>
<tr class="odd">
<td><em>model_file</em></td>
<td>Transistor model definitions .included by <em>spice_file</em>.</td>
</tr>
<tr class="even">
<td><em>power</em></td>
<td>Voltage supply name in voltage_map of the default liberty library.</td>
</tr>
<tr class="odd">
<td><em>ground</em></td>
<td>Ground supply name in <em>voltage_map</em> of the default liberty library.</td>
</tr>
<tr class="even">
<td>-simulator</td>
<td>Simulator that will read the spice netlist.</td>
</tr>
</tbody>
</table>

The write_path_spice command writes a spice netlist for timing paths.
Use *path_args* to specify -from/-through/-to as arguments to the
find_timing_paths command. For each path, a spice netlist and the
subckts referenced by the path are written in *spice_directory*. The
spice netlist is written in path_\<id>.sp and subckt file is
path_\<id>.subckt.

The spice netlists used by the path are written to *subckt_file*, which
spice_file .includes. The device models used by the spice subckt
netlists in *model_file* are also .included in spice_file. Power and
ground names are specified with the -power and -ground arguments. The
spice netlist includes a piecewise linear voltage source at the input
and .measure statement for each gate delay and pin slew.

Example command:

write_path_spice -path_args {-from "in0" -to "out1" -unconstrained}
\\  
-spice_directory $result_dir \\  
-lib_subckt_file "write_spice1.subckt" \\  
-model_file "write_spice1.models" \\  
-power VDD -ground VSS

When the simulator is hspice, .measure statements will be added to the
spice netlist.

When the simulator is Xyce, the .print statement selects the CSV format
and writes the waveform data to a file name path_\<id>.csv so the
results can be used by gnuplot.

<table>
<tbody>
<tr class="odd">
<td><strong>write_sdc</strong></td>
<td>[-digits <em>digits</em>]<br />
[-gzip]<br />
[-no_timestamp]<br />
<em>filename</em></td>
</tr>
<tr class="even">
<td><em>digits</em></td>
<td>The number of digits after the decimal point to report. The default is 4.</td>
</tr>
<tr class="odd">
<td>-gzip</td>
<td>Compress the SDC with gzip.</td>
</tr>
<tr class="even">
<td><em>-no_timestamp</em></td>
<td>Do not include a time and date in the SDC file.</td>
</tr>
<tr class="odd">
<td><em>filename</em></td>
<td>The name of the file to write the constraints to.</td>
</tr>
</tbody>
</table>

Write the constraints for the design in SDC format to *filename*.

<table>
<tbody>
<tr class="odd">
<td><strong>write_sdf</strong></td>
<td>[-corner <em>corner</em>]<br />
[-divider /|.]<br />
[-include_typ]<br />
[-digits <em>digits</em>]<br />
[-gzip]<br />
[-no_timestamp]<br />
[-no_version]<br />
<em>filename</em></td>
</tr>
<tr class="even">
<td><em>corner</em></td>
<td>Write delays for <em>corner</em>.</td>
</tr>
<tr class="odd">
<td>-divider</td>
<td>Divider to use between hierarchy levels in pin and instance names.</td>
</tr>
<tr class="even">
<td>-include_typ</td>
<td>Include a 'typ' value in the SDF triple that is the average of min and max delays to satisfy some Verilog simulators that require three values in the delay triples.</td>
</tr>
<tr class="odd">
<td>-digits <em>digits</em></td>
<td>The number of digits after the decimal point to report. The default is 4.</td>
</tr>
<tr class="even">
<td>-gzip</td>
<td>Compress the SDF using gzip.</td>
</tr>
<tr class="odd">
<td>-no_timestamp</td>
<td>Do not write a DATE statement.</td>
</tr>
<tr class="even">
<td>-no_version</td>
<td>Do not write a VERSION statement.</td>
</tr>
<tr class="odd">
<td><em>filename</em></td>
<td>The SDF filename to write.</td>
</tr>
</tbody>
</table>

Write the delay calculation delays for the design in SDF format to
*filename*. If -corner is not specified the min/max delays are across
all corners. With -corner the min/max delays for *corner* are written.
The SDF TIMESCALE is same as the time_unit in the first liberty file
read.

<table>
<tbody>
<tr class="odd">
<td><strong>write_timing_model</strong></td>
<td><p>[-library_name <em>lib_name</em>]<br />
[-cell_name <em>cell_name</em>]</p>
<p>[-corner <em>corner</em>]<br />
<em>filename</em></p></td>
</tr>
<tr class="even">
<td>-library_name <em>lib_name</em></td>
<td>The name to use for the liberty library. Defaults to <em>cell_name</em>.</td>
</tr>
<tr class="odd">
<td>-cell_name <em>cell_name</em></td>
<td>The name to use for the liberty cell. Defaults to the top level module name.</td>
</tr>
<tr class="even">
<td>-corner <em>corner</em></td>
<td>The process corner to use for extracting the model.</td>
</tr>
<tr class="odd">
<td><em>filename</em></td>
<td>Filename for the liberty timing model.</td>
</tr>
</tbody>
</table>

The write_timing_model command constructs a liberty timing model for
the current design and writes it to *filename*. *cell_name* defaults to
the cell name of the top level block in the design.

The SDC used to extract the block should include the clock definitions.
If the block contains a clock network set_propagated_clock should be
used so the clock delays are included in the timing model. The following
SDC commands are ignored when bulding the timing model.

set_input_delay  
set_output_delay  
set_load  
set_timing_derate

Using set_input_transition with the slew from the block context will
be used will improve the match between the timing model and the block
netlist. Paths defined on clocks that are defined on internal pins are
ignored because the model has no way to include the clock definition.

The resulting timing model can be used in a hierarchical timing flow as
a replacement for the block to speed up timing analysis. This
hierarchical timing methodology does not handle timing exceptions that
originate or terminate inside the block. The timing model includes:

combinational paths between inputs and outputs  
setup and hold timing constraints on inputs  
clock to output timing paths

Resistance of long wires on inputs and outputs of the block cannot be
modeled in Liberty. To reduce inaccuracies from wire resistance in
technologies with resistive wires place buffers on inputs and ouputs.

The extracted timing model setup/hold checks are scalar (no input slew
dependence). Delay timing arcs are load dependent but do not include
input slew dependency.

<table>
<tbody>
<tr class="odd">
<td><strong>write_verilog</strong></td>
<td><p>[-sort]</p>
<p>[-include_pwr_gnd]<br />
[-remove_cells <em>lib_cells</em>]<br />
<em>filename</em></p></td>
</tr>
<tr class="even">
<td>-sort</td>
<td>Sort the instances in the netlist.</td>
</tr>
<tr class="odd">
<td>-include_pwr_gnd</td>
<td>Incluce power and ground pins on instances.</td>
</tr>
<tr class="even">
<td>-remove_cells <em>lib_cells</em></td>
<td>Liberty cells to remove from the verilog netlist. Use get_lib_cells, a list of cells names, or a cell name with wildcards.</td>
</tr>
<tr class="odd">
<td><em>filename</em></td>
<td>Filename for the liberty library.</td>
</tr>
</tbody>
</table>

The write_verilog command writes a verilog netlist to *filename*. Use
-sort to sort the instances so the results are reproducible across
operating systems. Use -remove_cells to remove instances of
*lib_cells* from the netlist.

# Filter Expressions

The get_cells, get_pins, get_ports and get_timing_edges functions
support filtering the returned objects by property values. Supported
filter expressions are shown below.

|                        |                                                                                                                   |
| ---------------------- | ----------------------------------------------------------------------------------------------------------------- |
| *property*             | Return objects with property value equal to 1.                                                                    |
| *property*==*value*    | Return objects with property value equal to value.                                                                |
| *property*=~*pattern* | Return objects with property value that matches pattern.                                                          |
| *property*\!=value     | Return objects with property value not equal to value.                                                            |
| *property*\!~value    | Return objects with property value that does not match pattern.                                                   |
| *expr1&\&e*xpr2        | Return objects with expr1 and expr2. expr1 and expr2 are one of the first three property value forms shown above. |
| *expr1||expr2*         | Return objects with expr1 or expr2. expr1 and expr2 are one of the first three property value forms shown above.  |

where *property* is an property supported by the get_property command.
Note that if there are spaces in the expression it must be enclosed in
quotes so that it is a single argument.

# Variables

|                          |                    |
| ------------------------ | ------------------ |
| **hierarchy_separator** | Any character**.** |

The hierarchy_separator separates instance names in a hierarchical
instance, net, or pin name. The default value is '/'.

|                                        |     |
| -------------------------------------- | --- |
| **sta_bidirect_net_paths_enabled** | 0|1 |

When set to 0, paths from bidirectional (inout) ports back through nets
are disabled. When set to 1, paths from bidirectional paths from the net
back into the instance are enabled. The default value is 0.

|                              |     |
| ---------------------------- | --- |
| **sta_continue_on_error** | 0|1 |

The include and read_sdc commands stop and report any errors
encountered while reading a file unless sta_continue_on_error is 1.
The default value is 0.

|                     |                            |
| ------------------- | -------------------------- |
| **sta_crpr_mode** | same_pin|same_transition |

When the data and clock paths of a timing check overlap (see
sta_crpr_enabled), pessimism is removed independent of whether of the
path rise/fall transitions. When sta_crpr_mode is same_transition,
the pessimism is only removed if the path rise/fall transitions are the
same. The default value is same_pin.

|                                       |     |
| ------------------------------------- | --- |
| **sta_cond_default_arcs_enabled** | 0|1 |

When set to 0, default timing arcs with no condition (Liberty timing
arcs with no “when” expression) are disabled if there are other
conditional timing arcs between the same pins. The default value is 1.

|                        |     |
| ---------------------- | --- |
| **sta_crpr_enabled** | 0|1 |

During min/max timing analysis for on_chip_variation the data and
clock paths may overlap. For a setup check the maximum path delays are
used for the data and the minimum path delays are used for the clock.
Because the gates cannot simultaneously have minimum and maximum delays
the timing check slack is pessimistic. This pessimism is known as Common
Reconvergent Pesssimism Removal, or “CRPR”. Enabling CRPR slows down the
analysis. The default value is 1.

|                                  |     |
| -------------------------------- | --- |
| **sta_dynamic_loop_breaking** | 0|1 |

When sta_dynamic_loop_breaking is 0, combinational logic loops are
disabled by disabling a timing arc that closes the loop. When
sta_dynamic_loop_breaking is 1, all paths around the loop are
reported. The default value is 0.

|                                        |     |
| -------------------------------------- | --- |
| **sta_gated_clock_checks_enabled** | 0|1 |

When sta_gated_clock_checks_enabled is 1, clock gating setup and
hold timing checks are checked. The default value is 1.

|                                      |     |
| ------------------------------------ | --- |
| **sta_input_port_default_clock** | 0|1 |

When sta_input_port_default_clock is 1 a default input arrival is
added for input ports that do not have an arrival time specified with
the set_input_delay command. The default value is 0.

|                                                       |     |
| ----------------------------------------------------- | --- |
| **sta_internal_bidirect_instance_paths_enabled** | 0|1 |

When set to 0, paths from bidirectional (inout) ports back into the
instance are disabled. When set to 1, paths from bidirectional ports
back into the instance are enabled. The default value is 0.

|                        |     |
| ---------------------- | --- |
| **sta_pocv_enabled** | 0|1 |

Enable parametric on chip variation using statistical timing analysis.
The default value is 0.

|                                 |     |
| ------------------------------- | --- |
| **sta_propagate_all_clocks** | 0|1 |

All clocks defined after sta_propagate_all_clocks is set to 1 are
propagated. If it is set before any clocks are defined it has the same
effect as

set_propagated_clock [all_clocks]

after all clocks have been defined. The default value is 0.

|                                          |     |
| ---------------------------------------- | --- |
| **sta_propagate_gated_clock_enable** | 0|1 |

When set to 1, paths of gated clock enables are propagated through the
clock gating instances. If the gated clock controls sequential elements
setting sta_propagate_gated_clock_enable to 0 prevents spurious
paths from the clock enable. The default value is 1.

|                                             |     |
| ------------------------------------------- | --- |
| **sta_recovery_removal_checks_enabled** | 0|1 |

When sta_recovery_removal_checks_enabled is 0, recovery and removal
timing checks are disabled. The default value is 1.

|                                  |         |
| -------------------------------- | ------- |
| **sta_report_default_digits** | integer |

The number of digits to print after a decimal point. The default value
is 2.

|                                       |     |
| ------------------------------------- | --- |
| **sta_preset_clear_arcs_enabled** | 0|1 |

When set to 1, paths through asynchronous preset and clear timing arcs
are searched. The default value is 0.

Alphabetical Index

all_clocks 6all_inputs 6all_outputs 6all_registers 6check_setup
7Command Line Arguments 1Commands 6connect_pin
7create_generated_clock 9create_voltage_area 10current_design
10current_instance 10define_corners 11delete_clock
11delete_from_list 11delete_generated_clock 11delete_instance
11delete_net 12disconnect_pin 12elapsed_run_time 12Example Command
Scripts 1Filter Expressions 80find_timing_paths 13get_cells
14get_clocks 15get_fanin 16get_fanout 16get_full_name
17get_lib_pins 18get_libs 18get_name 20get_nets 19get_pins
20get_ports 21get_property 21get_timing_edges 24group_path
25hierarchy_separator 80include 26link_design 26make_instance
26make_net 27Power Analysis 2read_liberty 27read_saif 28read_sdc
28read_sdf 28read_spef 29read_vcd 31read_verilog 31redirection
4replace_activity_annotation 31replace_cell
31report_annotated_check 32report_annotated_delay
33report_check_types 36report_checks 34report_clock_latency
37report_clock_min_period 38report_clock_properties
38report_clock_skew 38report_dcalc 39report_disabled_edges
39report_edges 39report_instance 40report_lib_cell 40report_net
40report_parasitic_annotation 40report_power
41report_pulse_width_checks 41report_slews 42report_tns
42report_units 42report_wns 43report_worst_slack
43set_assigned_check 43set_assigned_delay
44set_assigned_transition 45set_case_analysis
46set_clock_gating_check 46set_clock_groups 47set_clock_latency
47set_clock_transition 48set_clock_uncertainty 49set_cmd_units
50set_data_check 51set_disable_inferred_clock_gating
51set_disable_timing 51set_drive 52set_driving_cell
53set_false_path 54set_fanout_load 55set_hierarchy_separator
55set_ideal_latency 55set_ideal_network 55set_ideal_transition
55set_input_delay 55set_input_transition
57set_level_shifter_strategy 57set_level_shifter_threshold
57set_load 57set_logic_dc 58set_logic_one 58set_logic_zero
59set_max_area 59set_max_capacitance 59set_max_delay
59set_max_dynamic_power 60set_max_fanout 60set_max_leakage_power
60set_max_time_borrow 60set_max_transition 61set_min_capacitance
61set_min_delay 62set_min_pulse_width 62set_multicycle_path
63set_operating_conditions 64set_output_delay
65set_port_fanout_number 66set_power_activity
66set_propagated_clock 67set_pvt 67set_resistance 69set_sense
68set_timing_derate 69set_units 70set_wire_load_min_block_size
71set_wire_load_mode 71set_wire_load_model
71set_wire_load_selection_group 71SPEF
30sta_bidirect_net_paths_enabled 80sta_cond_default_arcs_enabled
81sta_continue_on_error 80sta_crpr_enabled 81sta_crpr_mode
81sta_dynamic_loop_breaking 81sta_gated_clock_checks_enabled
81sta_input_port_default_clock
81sta_internal_bidirect_instance_paths_enabled 81sta_pocv_enabled
82sta_preset_clear_arcs_enabled 82sta_propagate_all_clocks
82sta_propagate_gated_clock_enable
82sta_recovery_removal_checks_enabled 82sta_report_default_digits
82suppress_msg 72TCL Interpreter 3Timing Analysis using SDF 2Timing
Analysis with Multiple Process Corners 2unset_case_analysis
72unset_clock_latency 72unset_clock_transition
72unset_clock_uncertainty 73unset_data_check
73unset_disable_inferred_clock_gating 74unset_disable_timing
74unset_input_delay 74unset_output_delay 75unset_path_exceptions
75unset_propagated_clock 76unset_timing_derate 76unsuppress_msg
76user_run_time 76Variables 80verilog netlist
31with_output_to_variable 76write_path_spice 77write_sdc
77write_sdf 78write_timing_model 78write_verilog 79

Version 2.6.0, Sep 23, 2024  
Copyright (c) 2024, Parallax Software, Inc.

This program is free software: you can redistribute it and/or modify it
under the terms of the GNU General Public License as published by the
Free Software Foundation, either version 3 of the License, or (at your
option) any later version.

This program is distributed in the hope that it will be useful, but
WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General
Public License for more details.

You should have received a copy of the GNU General Public License along
with this program. If not, see \<https://www.gnu.org/licenses/>.
