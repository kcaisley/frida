Okay, so for the time being, I don't have the resources or time to take advantage of the sweeps, optimizer, and performance aggregator features. Instead, we will just assume that the only netlists to be considered are the ones already created in results/tb and results/subckt. All netlists which are created should be simulated and analyzed.
What I want to do is:


# Feature 1: Adding a make analyses step, with a analyses.py file.

Rewrite the existing tb netstruct/functions so that the part of the json struct for generating the netlist devices and waveforms is left exactly as it is. But instead of also specifying the analysis types and save statements in the same struct, we will instead use the notation provided by pyopus. Here is a blurb about analyses:

"The first thing you need to enter is the name of the simulator used by the analysis. The simulator setup determines the simulator and the input netlist modules that you can use in this analysis. Under Simulator options you can specify the simulator options passed via the netlist. Any values specified here override the values specified in the simulator setup. The same holds for the netlist parameters specified for a particular analysis.

The op analysis uses two input file modules: def and tb. The first one defines the opamp subcircuit while the second one uses this subcircuit definition in the top level circuit for adding subcircuit instance x1 which represents the opamp. Note how we did not add the MOS transistor models here. This is because we are going to add the models when we will be defining the corners for the simulation of the circuit. Typically device models are part of a corner definition because we want to simulate the circuit’s performance for various extreme MOS models."

We will essentially be giving the pyopus tool a list of def and tb circuits pre-generated, rather than just two single files.

Please keep the textual description of the testbench we are creating, as this is still relevant. One thing is that you'll need to manually list out the various node names and device op point characteristics which you'll extract. Only get the ones which are needed for the analysis you're performing, for transient simulations, etc:

"Finally, Simulator output directives specify what quantities the simulator should save in the output file. By default these are node potentials and certain branch currents (i.e. the ones that flow through voltage sources and inductors). If you want to save anything else you shuld specify it here.

We first specify the Default save directive which saves the above mentioned voltages and currents. If we do not do this only the quantities listed under save directives will be saved. The second save directive specifies that the simulator should save the values of Vgs, Vth, Vds, and Vdsat for all MOS transitors. This is done with the Device Property save directive. For this directive one must specify a space-separated list of instances and a space-separated list of quantities. You can use the hash syntax for specifying these two lists. The expression can use the variables defined under the Predefined variables node in the project tree. The expressions are evaluated at simulation. In our example

ipath(mosList, 'x1', 'm0')

generates the list of simulator’s built-in MOS transistor instances corresponding to all MOS transistors in the circuits.

m0:xmn1:x1 m0:xmn2:x1 m0:xmn3:x1 m0:xmn4:x1 m0:xmn5:x1 m0:xmp1:x1 m0:xmp2:x1 m0:xmp3:x1

Similarly you can enter all other analyses. See Miller opamp design with PyOPUS for the details on other analyses."

Regarding corners and device libraries, since we want to support different technologies, and also support pdk agnostic naming of corners, I think we won't use the corners feature of the tool. Instead have the include statements actually as part of the input tb netlist.

So essentially, when I run make analyses, I want to use the pyopus to grab the tb netlists, and then append the analysis and save statements that they produce. Critically, I think these statements should essentially be the same for all of our different designs!

Then it can write out these final netlists in results/analyses/

# Part 2: A rewrite of make sim

Next, I would like to completely rewrite our simulation.py file, using the
https://fides.fe.uni-lj.si/pyopus/download/0.12/docsrc/_build/html/simulator.html
https://fides.fe.uni-lj.si/pyopus/download/0.12/docsrc/_build/html/simulator.spectre.html

I've moved our old file to the /src directory, which you can still consider if you need any details, for example where the spectre binary is stored, or what the license server is called, but your goal is to be able to run simulations on the remote jupiter.physik.uni-bonn.de and juno.physi.uni-bonn.de server using the remote running feature here:

https://fides.fe.uni-lj.si/pyopus/download/0.12/docsrc/_build/html/tutorial.parallel.vm.using-mpi.html

You can read how to spawn a run on a remote host like this:
https://fides.fe.uni-lj.si/pyopus/download/0.12/docsrc/_build/html/tutorial.parallel.vm.02-spawn.html

One feature you might need to retain from the old simulate.py file, is the ability to check how many licenses are available. But for now you can assume the max you can start at any given time between the two computers is 40 simulations.

# Part 3: Measurements

Everything we want to plot must be collected by the evaluator. Therefore we add some mesurements that result in vectors from which we draw the x-y data for the plots (measures dcvin, dcvout, dccomvin, dccomvout, and dccom_m1vdsvdsat).

Let's rewrite our measure.py file so that when I run make meas, it reads the simulation .raw files, and does the necessary post processing.

To create a measure statement, you should put it in the block/[cellname].py file a syntax like this:

	# Finally, we define what we want to measure. For every performance 
	# we specify the analysis that generates the simulation results 
	# from which the performance is extracted. We can specify the formula 
	# for extracting the result as either a Python expression or a Python 
	# script that stores the result in the __result variable. 
	# For every performance we also specify the list of corners for which 
	# the performance will be evaluated. If no corners are apecified the 
	# performance is evaluated across all listed corners. 
	# Performances are scalars by default. For vector performances this 
	# must be specified explicitly. 
	measures = {
		# Supply current
		'isup': {
			'analysis': 'op', 
			'corners': [ 'nominal', 'worst_power', 'worst_speed' ], 
			'expression': "__result=-i('vdd')"
		}, 
		# Output voltage at zero input voltage
		'out_op': {
			'analysis': 'op', 
			'corners': [ 'nominal', 'worst_power', 'worst_speed' ], 
			'expression': "v('out')"
		},
		# Vgs overdrive (Vgs-Vth) for mn2, mn3, and mn1. 
		'vgs_drv': {
			'analysis': 'op', 
			'corners': [ 'nominal', 'worst_power', 'worst_speed', 'worst_one', 'worst_zero' ], 
			'expression': "array(list(map(m.Poverdrive(p, 'vgs', p, 'vth'), ipath(saveInst, 'x1', 'm0'))))", 
			'vector': True
		}, 


The trick is that many of our measurements are rather complicated, so you will need to break out many of the expressions as custom functions. The tool already includes a couple premap measurements: https://fides.fe.uni-lj.si/pyopus/download/0.12/docsrc/_build/html/evaluator.measure.html

But you will also need to write some new ones to cover the test cases specifed. For now let's just work on the comparator. You can adapt functions which were already prototyped in our old measure.py file: which I've copied to: src/measure.py

You can find more information about measure here: https://fides.fe.uni-lj.si/pyopus/download/0.12/docsrc/_build/html/tutorial.evaluation.02-evaluator.html

In the main() function of measure.py, you can do essentially: 

# Construct performane evaluator
pe=PerformanceEvaluator(heads, analyses, measures, variables=variables, debug=0)

Remember we need to use the load_module from common.py to get the different stuff from our specific cell's .py file.

# Part 4: A rewrite of make plot:

Everything we want to plot must be collected by the evaluator, which we defined in the previous step. 

	visualisation = {
		# Window list with axes for every window
		# Most of the options are arguments to MatPlotLib API calls
		# Every plot window has its unique name by which we refer to it
		'graphs': {
			# One window for the DC response
			'dc': {
				'title': 'Amplifier DC response', 
				'shape': { 'figsize': (6,8), 'dpi': 80 }, 
				# Define the axes
				# Every axes have a unique name by which we refer to them
				'axes': {
					# The first vertical subplot displays the differential response
					'diff': {
						# Argument to the add_subplot API call
						'subplot': (2,1,1), 
						# Extra options
						'options': {}, 
						# Can be rect (default) or polar, xscale and yscale have no meaning when grid is polar
						'gridtype': 'rect',
						# linear by default, can also be log
						'xscale': { 'type': 'linear' }, 	
						'yscale': { 'type': 'linear' }, 	
						'xlimits': (-3e-3, -1e-3), 
						'xlabel': 'Vdif=Vinp-Vinn [V]', 
						'ylabel': 'Vout [V]', 
						'title': '', 
						'legend': False, 
						'grid': True, 
					}, 
					# The second vertical subplot displays the common mode response
					'com': {
						'subplot': (2,1,2), 
						'options': {}, 
						'gridtype': 'rect', 		
						'xscale': { 'type': 'linear' }, 
						'yscale': { 'type': 'linear' }, 
						'xlimits': (0.0, 2.0),
						'xlabel': 'Vcom=Vinp=Vinn [V]', 
						'ylabel': 'Vout [V]', 
						'title': '', 
						'legend': False, 
						'grid': True, 
					}
				}
			},
			# Another window for the M1 Vds overdrive in common mode
			'm1vds': {
				'title': 'M1 Vds-Vdsat in common mode', 
				'shape': { 'figsize': (6,4), 'dpi': 80 }, 
				'axes': {
					'dc': {
						# This time we define add_axes API call
						'rectangle': (0.12, 0.12, 0.76, 0.76), 
						'options': {}, 
						'gridtype': 'rect', 		# rect (default) or polar, xscale and yscale have no meaning when grid is polar
						'xscale': { 'type': 'linear' }, 	# linear by default
						'yscale': { 'type': 'linear' }, 	# linear by default
						'xlimits': (0.0, 2.0), 
						'xlabel': 'Vcom=Vinp=Vinn [V]', 
						'ylabel': 'M1 Vds-Vdsat [V]', 
						'title': '', 
						'legend': False, 
						'grid': True, 
					}, 
				}
			}
		},
		# Here we define the trace styles. If pattern mathces a combination 
		# of (graph, axes, corner, trace) name the style is applied. If 
		# multiple patterns match one trace the style is the union of matched
		# styles where matched entries that appear later in this list override 
		# those that appear earlier. 
		# The patterns are given in the format used by the :mod:`re` Python module. 
		'styles': [ 
			{
				# A default style (red, solid line)
				'pattern': ('^.*', '^.*', '^.*', '^.*'), 
				'style': {
					'linestyle': '-',
					'color': (0.5,0,0)
				}
			}, 
			{
				# A style for traces representing the response in the nominal corner
				'pattern': ('^.*', '^.*', '^nom.*', '^.*'),
				'style': {
					'linestyle': '-',
					'color': (0,0.5,0)
				}
			}
		], 
		# List of traces. Every trace has a unique name. 
		'traces': {
			# Differential DC response in all corners
			'dc': {
				# Window an axes where the trace will be plotted
				'graph': 'dc', 
				'axes': 'diff', 
				# Result vector used for x-axis data
				'xresult': 'dcvin',
				# Result vector used for y-axis data
				'yresult': 'dcvout', 
				# Corners for which the trace will be plotted
				# If not specified or empty, all corners where xresult is evaluated are plotted
				'corners': [ ],	
				# Here we can override the style matched by style patterns
				'style': {
					'linestyle': '-',
					'marker': '.', 
				}
			}, 
			# Common mode DC response in all corners
			'dccom': {
				'graph': 'dc', 
				'axes': 'com', 
				'xresult': 'dccomvin',
				'yresult': 'dccomvout', 
				'corners': [ ],	
				'style': {	
					'linestyle': '-',
					'marker': '.', 
				}
			},
				# Vds overdrive for M1 in common mode, nominal corner only
			'm1_vds_vdsat': {
				'graph': 'm1vds', 
				'axes': 'dc', 
				'xresult': 'dccomvin',
				'yresult': 	'dccom_m1vdsvdsat', 
				'corners': [ 'nominal' ],	
				'style': {	
					'linestyle': '-',
					'marker': '.', 
				}
			}
		}
	}
	
	
In the ploy.py file you can have a flow like this:

# Construct plotter
plotter=EvalPlotter(visualisation, pe, debug=1)

# Evaluate performance
results=pe(inParams)

# Plot
plotter()

# Cleanup intermediate files
pe.finalize()

# Wait for windows to close
# If we don't do this the program crashes immediately after the windows appear
plt.join()
