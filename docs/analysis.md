# potential spice/spectre features to improve analysis:

Spectre User:

Ch11 Analyses > Transient > pg279 Controlling output data

The parameters infonames and infotimes are used to define which info analyses
needs to be performed at which time point. By default, the time points and the analyses
defined using these parameters are paired.
tr1 tran stop=10n infotimes=[2n 5n] infonames=[info1 info2]
info1 info what=oppoint where=file file=info1
info2 info what=captab where=file file=info2
In the above example, the operating-point analysis info1 is performed at 2ns, and the
captap calculation info2 is performed at 5ns.


Ch11 Analyses > pg479 MC analysis

Ch12 Control Statements > pg633 info statment:

Printing the Node Capacitance Table
The Spectre simulator allows you to print node capacitance to an output file. This can help you in identifying possible causes of circuit performance problems due to capacitive loading. Use info1 info what = captab
The capacitance between nodes x and y is defined as...


Ch13, pg672: `Saveahdl options saveahdlvars=all`

Ch13, pg 677: For the sweep and montecarlo analyses, the names of the filenames are a concatenation of the parent analysis name, the iteration number, and the child analysis name.

Ch20, pg 1023: file name wildcards and variables
