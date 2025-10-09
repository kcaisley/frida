# Viva (Cadence Visualization and Analysis) Help

## Command Line Options

```
viva usage:
  [-help | -h | -H]	Displays this message.
  [-V]			Provides Cadence release version.
  [-W]			Provides Cadence release subversion.
  [-log logfileName]	Logs session to logfileName.
  [-autolog logfileName]	Logs session to logfileName. Auto append sequencial number to logfileName if a file already exist.
  [-nocdsinit]		Skip reading the cdsinit file.
  [-noblink]		Turn off blinking.
  [-45]			Enhanced drawing of 45 degree diagonal lines.
  [-noxshm]		Prevents use of X Shared Memory Access.
  [-nograph]		Starts software in non-graphical mode.
			Should only use this option to replay logfiles
			that have been created interactively.
  [-nographE]		Emulate non-graphical mode.
			Uses the default display or that specified with the
			-display command line option, but otherwise is similar
			to the -nograph option.  Note that windows and forms
			will be drawn on the display specified.  Nograph
			emulation can also be invoked by defining the
			environment variable CDS_NOGRAPH_DISPLAY to specify
			the display along with the -nograph command line option
			or this option.
  [-replay inputLog]	Specifies the log file to replay.
  [-restore fileName]	Specifies the session file to restore.
viva specific options:
   [-datadir <dir>]           Opens a given database (psf directory) on the Results Browser.
                              Multiple entries will open multiple databases.
   [-load_graph <wave.grf>]   Opens viva and loads a given graph file.

   [-viva_logging]            Adds viva specific log file entries to be used in replay.
```

## Common Usage Examples

### Opening simulation results:
```bash
viva -datadir /users/kcaisley/frida/spice/tb_adc_2conv.raw
```

### Opening results with a saved graph file:
```bash
viva -datadir /users/kcaisley/frida/spice/tb_adc_2conv.raw -load_graph wave.grf
```

### Opening multiple databases:
```bash
viva -datadir /path/to/sim1.raw -datadir /path/to/sim2.raw
```
