
- Enclosed layout transistors (ELTs) used to be needed as in rectangular layout the parasitic FET on side of channel is significant, as LOCOS was poorly defined
- But now in more modern processes, the use of shallow trench isolation (STI) creates a more cleanly defined edge of the transistor which minimizes the existance of a parasitic FET.

It includes DRC and LVS rules, SPICE models, technology files, verification and extraction files, execution scripts, symbol library and parametric cells (PCells)

OpenAccess file format comes with APIs for C++, C#, Perl, Python, Ruby and Tcl.

[Blog describing some issues](https://semiwiki.com/x-subscriber/silvaco/5601-custom-ic-design-flow-with-openaccess/)

Interoperable PDK (iPDK) came from TSMC starting in 2007, and by 2009 the first 65nm iPDK was ready. The iPDK Alliance called IPL controls the iPDK specification and members include: Altera (Intel), Ciranova, Mentor Graphics, Pulsic, SpringSoft, Synospys and TSM with Xilinx and STMicroelectronics as advisors. With iPDK the foundry and partners spend less time on PDK development. The Interoperable PDK Libraries Alliance 
(IPL), working with TSMC, standardized on using Ciranova’s PyCell approach (based on Python rather than SKILL) and created the iPDK which is supported by all the layout editors (even Virtuoso, at least unofficially).

As with much in the EDA industry, there will be multiple standards so OpenPDK is yet another approach, this time from Si2.org, using an XML structured file and translators for main vendor tools. Each supplier creates their own parser to create the standardized exchange format. An OPDK can also create an iPDK. There is a second portable PDK standard anyway called OpenPDK, being done under the umbrella of Si2, although the work just started last year and hasn’t yet delivered actual PDKs. Supported by Global foundaries. Si2 is perceived by other EDA vendors as being too close to Cadence (they also nurture OpenAccess and CPF, which both started off internally inside Cadence)


All of this IC design reuse sounds really promising and liberating, however there are some issue for you to aware of. There can be subtle differences between Cadence PDK (using Skill), iPDK (Tcl), custom PDK (Tcl, Python, Perl). 

tsmcn65 ivpcell
What is a ivpcell?



[From Si2 website](https://si2.org/os-downloads/):

OpenPDK Coalition

The OpenPDK (Process Design Kit) Coalition was founded in 2010 to define a set of open standards allowing an OpenPDK to be created (once) and translated into specific EDA vendor tools and foundry formats. This allows for maximum portability across foundries and agnosticism among EDA tools. The Si2 OpenPDK standard enables greater efficiency in PDK development, verification, and delivery, providing equal support to foundries, EDA tool vendors, IP providers, and end-users.

Specifications

    OpenPDK Open Process Specification (OPS): This specification enables foundries to study and create electronic versions of DRM and to gather early feedback on completeness.
    OPS 1.2 supports the creation of a techfile/oaTech.db for foundry-specific layer information. This includes grids, connectivity, display information, and version information. This release also integrates the Device Parameters (previously called Design Parameters) and Tool Interface standards into OPS.
    OpenPDK PCell Standard (PCell v1.0 is compatible with OPS 1.2)
    OpenPDK Design Parameter and Callback Specification V1.0
    OpenPDK Schematic Symbol Standard V1.0


The term "callback" is used for a number of different situations, but in general it's a means of having a function that gets called when some kind of event occurs. In this case it's called when the simulation finishes. In some cases the callback is a complete SKILL expression which is just evaluated using evalstring, but in others you provide the name of the function to call (or in an increasing number of cases, you can also provide the function object which is beneficial when using SKILL++). In this case you're doing just that - providing the name of the function to call.

# Opensource EDA in Europe
The US isn't dominating contributions to open source EDA. OpenROad -> OpenLane is US based but..
Actually, the many of the important and essential tools in open source EDA are fundamentally being developed in Europe (e.g. klayout (Munich), yosys (Vienna), nextpnr (Vienna/Heidelberg), ngspice (Duisburg)).
