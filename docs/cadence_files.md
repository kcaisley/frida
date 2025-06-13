lf start script
siemens calibre startup fix
tower 180 start script working now
attaching vs reference technology libraries
sos manager not working
SELinux blocking operation of some Cadence tools (like AMS)







### File notes:


Library manager obtains form settings from the .cdsenv file only and not from the .cdsinit file.

The Library Manager searches for the .cdsenv file in the following locations, in the specified order:

- install_dir/tools/dfII/etc/tools/cdsLibManager (This file contains the default settings.)
- install_dir/tools/dfII/local
- $HOME
- $CWD
Virtuoso does not look for the .cdsenv file in the current directory by default, although the Library Manager does.




- Any library can either reference a technology library or attach to a technology library. A design library must do one or the other to have access to technology data during a design session. A technology library can also reference or attach to another technology library; alternatively, it can be standalone by doing neither, using only the cdsDefTechLib default technology data. Choosing whether to reference or attach a technology library depends upon whether or not designers need to specify technology data during their design sessions.
- Referencing a technology database from a design library or another technology library protects the integrity of any read-only data in the effective technology library while providing a writable local library where designers can define technology data. Referencing is preferable to attachment when designers need a writable local technology database in which to add technology data (such as data output by LEFIN).
- Attaching is preferable in cases where designers use only predefined technology data, which is typically read-only.


In this case, all TOWER designs should *attach* the ts018_prim library, as it contains:

../ts18is_Rev_6.3.6/HOTCODE/amslibs/cds_oa/cdslibs/ts18sl/devices/ts018_oa_compana_6M1L/6.2/ref_libs/ts018_prim/tech.db

virtuoso ascii technology file -> openaccess tech db
(compiled with virtuoso technology file manager)



Are .layermap files converted into display.drf files when using cadence?

_____.layermap
#Layer Name     Layer Purpose  Layer Stream Number  Datatype Stream Number

met1           drawing        8                    0              
met2           drawing        18                   0              
met3           drawing        28                   0              
met4           drawing        38                   0              
lay4           drawing        8                    0              
lay13          drawing        18                   0              
met5           drawing        48                   0              
met6           drawing        58                   0


display.drf
drDefineDisplay(
;( DisplayName   #Colors   #Stipples   #LineStyels )
 ( display        256        256        256  )
)

; -----------------------------------------------------------------
; ------ Display information for the display device 'display'. ------
; -----------------------------------------------------------------
drDefineColor(
;( DisplayName   ColorName   Red   Green   Blue   Blink )
 ( display       white       255    255    255  )
 ( display       silver      217    230    255  )
 ( display       cream       255    255    204  )
 ( display       pink        255    191    242  )
 ( display       magenta     255    0      255  )
 ( display       lime        0      255    0    )
 ( display       tan         255    230    191  )
 ( display       cyan        0      255    255  )
 ( display       cadetBlue   57     191    255  )
 ( display       yellow      255    255    0    )
 ( display       orange      255    128    0    )
 ( display       red         255    0      0    )
 ( display       purple      153    0      230  )
 ( display       green       0      204    102  )
 ( display       brown       191    64     38   )
 ( display       blue        0      0      255  )
 ( display       slate       140    140    166  )
...


lib.defs -> cds.lib

../ts18is_Rev_6.3.6/HOTCODE/amslibs/cds_oa/cdslibs/ts18sl/devices/ts018_oa_compana_6M1L/6.2/ref_libs/ts018_prim/techfile.tf

../ts18is_Rev_6.3.6/HOTCODE/amslibs/cds_oa/cdslibs/ts18sl/devices/ts018_oa_compana_6M1L/6.2/ref_libs/ts018_prim/tech.db


could find anything in the analog PDK w/ .tech .def .lef

But the digital PDK has some .lefs:

/mnt/md127/eda/kits/TOWER/digital/tsl18fs190svt_wb_Rev_2022.12$ find . -type f -name "*.lef"
./lib/lef/tsl18fs190svt_wb.lef
./tech/lef/4M1L/tsl180l4.lef
./tech/lef/3M1T/tsl180l3_mt.lef
./tech/lef/5M1F/tsl180l5_0l1f.lef
./tech/lef/4M1L1R/tsl180l4_1l1r.lef
./tech/lef/3M1T3/tsl180l3_mt3.lef
./tech/lef/5M1T/tsl180l5_mt.lef
./tech/lef/6M1L/tsl180l6.lef
./tech/lef/6M1T/tsl180l6_mt.lef
./tech/lef/4M0L/tsl180l4_0l.lef
./tech/lef/4M1F/tsl180l4_0l1f.lef
./tech/lef/5M1L/tsl180l5.lef
./tech/lef/4M1L1F/tsl180l4_1l1f.lef
./tech/lef/3M0L/tsl180l3_0l.lef
./tech/lef/3M0L1F/tsl180l3_0l1f.lef
./tech/lef/5M1T3/tsl180l5_mt3.lef
./tech/lef/7M1L1R/tsl180l7_1l1r.lef
./tech/lef/3M1L/tsl180l3.lef
./tech/lef/4M1T3/tsl180l4_mt3.lef
./tech/lef/4M1T/tsl180l4_mt.lef
./tech/lef/3M1F/tsl180l3_0l1f.lef




files:

tech.db imported cadence specific version of ___.tech
data.dm
lib.defs
cds.lib





