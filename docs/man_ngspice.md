
```bash
$ ngspice --help

Usage: ngspice [OPTION]... [FILE]...
Simulate the electical circuits in FILE.

  -a  --autorun             run the loaded netlist
  -b, --batch               process FILE in batch mode
  -c, --circuitfile=FILE    set the circuitfile
  -D, --define=variable[=value] define variable to true/[value]
  -i, --interactive         run in interactive mode
  -n, --no-spiceinit        don't load the local or user's config file
  -o, --output=FILE         set the outputfile
  -p, --pipe                run in I/O pipe mode
  -r, --rawfile=FILE        set the rawfile output
      --soa-log=FILE        set the outputfile for SOA warnings
  -s, --server              run spice as a server process
  -t, --term=TERM           set the terminal type
  -h, --help                display this help and exit
  -v, --version             output version information and exit
```



```bash
$ man ngspice

NAME
       ngspice - circuit simulator derived from SPICE3f5

SYNOPSIS
       ngspice [options] [file ...]

DESCRIPTION
       This man page is just a small overview.  The primary documentation of ngspice is in the ngspice User's Manual, which is available as a pdf or html file.

OPTIONS
       -n  or  --no-spiceinit
              Don't try to source the file ".spiceinit" upon startup. Normally ngspice tries to find the file in the current directory, and if it is not found then in the user's home directory.

       -t term  or  --term=term
              The program is being run on a terminal with mfb name term.

       -b  or  --batch
              Run  in batch mode.  ngspice will read the standard input or the specified input file and do the simulation.  Note that if the standard input is not a terminal, ngspice will default to
              batch mode, unless the -i flag is given.

       -s  or  --server
              Run in server mode.  This is like batch mode, except that a temporary rawfile is used and then written to the standard output, preceded by a line with a single "@", after  the  simula‐
              tion is done.  This mode is used by the ngspice daemon.

       -i  or  --interactive
              Run  in  interactive  mode.  This is useful if the standard input is not a terminal but interactive mode is desired.  Command completion is not available unless the standard input is a
              terminal, however.

       -r rawfile  or  --rawfile=file
              Use rawfile as the default file into which the results of the simulation are saved.

       -c circuitfile  or  --circuitfile=circuitfile
              Use circuitfile as the default input deck.

       -h  or  --help
              Display a verbose help on the arguments available to the program.

       -v  or  --version
              Display a version number and copyright information of the program.

       -a  or  --autorun
              FIXME

       -o outfile  or  --output=outfile
              All logs generated during a batch run (-b) will be saved in outfile.

       -p  or  --pipe
              Allow a program (e.g., xcircuit) to act as a GUI frontend for ngspice through a pipe.  Thus ngspice will assume that the pipe is a tty and allows one to run in interactive mode.

       Further arguments are taken to be SPICE input decks, which are read and saved.  (If batch mode is requested then they are run immediately.)
ENVIRONMENT
       SPICE_LIB_DIR

       SPICE_EXEC_DIR

       SPICE_HOST

       SPICE_BUGADDR

       SPICE_EDITOR

       SPICE_ASCIIRAWFILE  default  0
              Format of the rawfile.  0 for binary, and 1 for ascii.

       SPICE_NEWS  default  $SPICE_LIB_DIR/news
              A file which is copied verbatim to stdout when ngspice starts in interactive mode.

       SPICE_MFBCAP  default  $SPICE_LIB_DIR/mfbcap

       SPICE_HELP_DIR  default  $SPICE_LIB_DIR/helpdir

       SPICE_SCRIPTS  default  $SPICE_LIB_DIR/scripts
              In this directory the spinit file will be searched.

       SPICE_PATH  default  $SPICE_EXEC_DIR/ngspice

       various undocumented ngspice centric environment variables :

       NGSPICE_MEAS_PRECISION

       SPICE_NO_DATASEG_CHECK

       Common environment variables :

       TERM LINES COLS DISPLAY HOME PATH EDITOR SHELL

       POSIXLY_CORRECT

FILES
       $SPICE_LIB_DIR/scripts/spinit
              The System's Initialisation File.

       .spiceinit  or  $HOME/.spiceinit
              The User's Initialisation File.

SEE ALSO
       sconvert(1), ngnutmeg(1), mfb(3), writedata(3), and
       ngspice User's Manual at http://ngspice.sourceforge.net/docs.html
```