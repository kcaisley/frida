
*
* StrongARM Comparator Latch
* 
* Function: High-speed dynamic comparator with regenerative latch
* Operation: Two-phase clocked operation
*   - Reset phase (clk=0): All internal nodes pulled high, outputs reset
*   - Evaluate phase (clk=1): Differential pair evaluates, regenerative feedback decides
*
* Topology:
*   - Differential input pair (mninp/mninn) with shared tail current
*   - Cross-coupled regenerative latch (mnnfbp/mnnfbn, mppfbp/mppfbn)  
*   - Clock-controlled switches for reset operation
*   - Tail current source with clock control
*
* Device Functions:
*   mntail     - Main tail current source, controlled by clock
*   mntailbias - Additional tail biasing/stability
*   mninp      - Positive input transistor (inp)
*   mninn      - Negative input transistor (inn)
*   mnnfbp     - NMOS regenerative feedback (positive side)
*   mnnfbn     - NMOS regenerative feedback (negative side)
*   mpswmp     - PMOS reset switch for positive mid-node (midp)
*   mpswmn     - PMOS reset switch for negative mid-node (midn)
*   mpswop     - PMOS reset switch for positive output (outp)
*   mpswon     - PMOS reset switch for negative output (outn)
*   mptailsw   - PMOS tail switch for reset
*   mppfbp     - PMOS regenerative feedback (positive side)
*   mppfbn     - PMOS regenerative feedback (negative side)
*

.subckt latch clk inn inp outn outp vdd vss
mntail tail clk vss vss nmos
mninn midn inn tail vss nmos
mntailbias tail vss vss vss nmos
mninp midp inp tail vss nmos
mnnfbp outn outp midp vss nmos
mnnfbn outp outn midn vss nmos
mpswmn midn clk vdd vdd pmos
mpswop outp clk vdd vdd pmos
mpswmp midp clk vdd vdd pmos
mptailsw tail clk vdd vdd pmos
mppfbp outp outn vdd vdd pmos
mppfbn outn outp vdd vdd pmos
mpswon outn clk vdd vdd pmos
.ends latch
