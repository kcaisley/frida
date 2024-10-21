# Default read-only settings of the LayoutToolbox
# most are path locations


def v2commonexcelfile():
    return r'S:\technologies\setup\v2common\v2common.xlsx'


def projectsexcelfile():
    return r'S:\technologies\setup\projects\projects.xlsx'


def tech2layoutparamsexcelfile():
    return r'S:\technologies\setup\tech2layoutparams\tech2layoutparams.xlsx'


def defaulttech2layoutparams():
    """Expected file for tech-specific Layout params"""
    return r'S:\technologies\setup\tech2layoutparams\tech2layoutparams.c'


def defaultgdssheet():
    """Expected file for gds translation table"""
    return r'S:\technologies\setup\tech2layoutparams\gdssheet.json'


def viasexcelfilepath():
    return 'S:\\technologies\\setup\\vias\\'


def viasexcelfile(technology):
    return viasexcelfilepath() + technology + '.xlsx'


def ltbpath():
    """Expected location for all LayoutToolbox stuff"""
    path = 'T:\\LayoutToolbox\\'
    return path


def settingspath():
    """Expected location for all LayoutToolbox settings"""
    path = ltbpath() + 'settings\\'
    return path


def usersettings():
    """Expected file for user-specific LayoutToolbox settings"""
    filename = settingspath() + 'user.ini'
    return filename


def projectsettings():
    """Expected file for user-specific LayoutToolbox settings"""
    filename = settingspath() + 'project.ini'
    return filename


def defaultprojectsettings():
    """Expected file for user-specific LayoutToolbox settings"""
    filename = 'S:\\technologies\\setup\\projects\\projects.ini'
    return filename


def leditsettings():
    """Expected file for user-specific LayoutToolbox settings"""
    filename = settingspath() + 'ledit.c'
    return filename


def allprojectspath():
    """Expected location for all LayoutToolbox projects"""
    path = ltbpath() + 'projects\\'
    return path


def projectpath(project):
    """Expected location for all LayoutToolbox project data"""
    path = allprojectspath() + project + '\\'
    return path


def seditfilepath(project):
    """Expected location for S-Edit schematic export"""
    path = projectpath(project) + 'sedit\\'
    return path


def pyschematicfilepath(project):
    """Expected location for SpiceNetlist export"""
    path = seditfilepath(project) + 'pysch\\'
    return path


def crcmdfilepath(project):
    """Expected location for CircuitReducer command files"""
    path = seditfilepath(project) + 'CRcmd\\'
    return path


def crschematicfilepath(project):
    """Expected location for CircuitReducer output files"""
    path = seditfilepath(project) + 'CRsch\\'
    return path


def layoutfilepath(project):
    """Expected location for all files required during layout phase"""
    path = projectpath(project) + 'layout\\'
    return path


def autogenfilepath(project):
    """Expected location for all autogen files"""
    path = layoutfilepath(project) + 'autogen\\'
    return path


def wrlfilepath(project):
    """Expected location for all autogen files"""
    path = layoutfilepath(project) + 'wrl\\'
    return path


def autolabelfilepath(project):
    """Expected location for all autolabel files"""
    path = layoutfilepath(project) + 'autolabel\\'
    return path


def autoplacefilepath(project):
    """Expected location for all autoplace files"""
    path = layoutfilepath(project) + 'autoplace\\'
    return path


def lvsfilepath(project):
    """Expected location for all files required during LVS"""
    path = projectpath(project) + 'lvs\\'
    return path


def lvscellfilepath(project, cellname):
    """Expected location for all files required during LVS for a given cell"""
    path = lvsfilepath(project) + cellname + '\\'
    return path


def lvsgdsfilepath(project, cellname):
    """Expected location for gds files required during LVS for a given cell"""
    path = lvscellfilepath(project, cellname)
    return path


def lvsctrlfilepath(project, cellname):
    """Expected location for ctrl files required during LVS for a given cell"""
    path = lvscellfilepath(project, cellname)
    return path


def lvsnetlistfilepath(project, cellname):
    """Expected location for netlist files required during LVS for a given cell"""
    path = lvscellfilepath(project, cellname)
    return path


def lvsresultfilepath(project, cellname):
    """Expected location for LVS result files for a given cell"""
    path = lvscellfilepath(project, cellname)
    return path


def lvssvdbfilepath(project, cellname):
    """Expected location for LVS extracted netlist files for a given cell"""
    path = lvscellfilepath(project, cellname) + 'svdb\\'
    return path


def lvspaths(project, cellname):
    # Return project-specific paths required for LVS
    paths = [ltbpath(),
             allprojectspath(),
             projectpath(project),
             seditfilepath(project),
             crcmdfilepath(project),
             crschematicfilepath(project),
             lvsfilepath(project),
             lvscellfilepath(project, cellname),
             lvssvdbfilepath(project, cellname)]
    return paths


def drcfilepath(project):
    """Expected location for all files required during DRC"""
    path = projectpath(project) + 'drc\\'
    return path


def drccellfilepath(project, cellname):
    """Expected location for all files required during DRC for a given cell"""
    path = drcfilepath(project) + cellname + '\\'
    return path


def drcgdsfilepath(project, cellname):
    """Expected location for gds files required during DRC for a given cell"""
    path = drccellfilepath(project, cellname)
    return path


def drcctrlfilepath(project, cellname):
    """Expected location for ctrl files required during DRC for a given cell"""
    path = drccellfilepath(project, cellname)
    return path


def drcresultfilepath(project, cellname):
    """Expected location for DRC result files for a given cell"""
    path = drccellfilepath(project, cellname)
    return path


def drcpaths(project, cellname):
    paths = [ltbpath(),
             allprojectspath(),
             projectpath(project),
             drcfilepath(project),
             drccellfilepath(project, cellname)]
    return paths


def yldfilepath(project):
    """Expected location for all files required during YLD"""
    path = projectpath(project) + 'yld\\'
    return path


def yldcellfilepath(project, cellname):
    """Expected location for all files required during DRC for a given cell"""
    path = yldfilepath(project) + cellname + '\\'
    return path


def yldgdsfilepath(project, cellname):
    """Expected location for gds files required during YLD"""
    path = yldcellfilepath(project, cellname)
    return path


def yldctrlfilepath(project, cellname):
    """Expected location for ctrl files required during YLD"""
    path = yldcellfilepath(project, cellname)
    return path


def yldresultfilepath(project, cellname):
    """Expected location for YLD result files"""
    path = yldcellfilepath(project, cellname)
    return path


def yldpaths(project, cellname):
    paths = [ltbpath(),
             allprojectspath(),
             projectpath(project),
             yldfilepath(project),
             yldcellfilepath(project, cellname)]
    return paths


def xorfilepath(project):
    """Expected location for all files required during XOR"""
    path = projectpath(project) + 'xor\\'
    return path


def xorcellfilepath(project, cellname):
    """Expected location for all files required during XOR for a given cellname"""
    path = xorfilepath(project) + cellname + '\\'
    return path


def xorgds1filepath(project, cellname):
    """Expected location for 1st gds files required during XOR for a given cellname"""
    path = xorcellfilepath(project, cellname) + 'gds1\\'
    return path


def xorgds2filepath(project, cellname):
    """Expected location for 2nd gds files required during XOR for a given cellname"""
    path = xorcellfilepath(project, cellname) + 'gds2\\'
    return path


def xorctrlfilepath(project, cellname):
    """Expected location for ctrl files required during XOR for a given cellname"""
    path = xorcellfilepath(project, cellname)
    return path


def xorresultfilepath(project, cellname):
    """Expected location for XOR result files for a given cellname"""
    path = xorcellfilepath(project, cellname)
    return path


def xorpaths(project, cellname):
    paths = [ltbpath(),
             allprojectspath(),
             projectpath(project),
             xorfilepath(project),
             xorgds1filepath(project, cellname),
             xorgds2filepath(project, cellname),
             xorctrlfilepath(project, cellname),
             xorresultfilepath(project, cellname)]
    return paths


def laygenfilepath():
    """Expected location for the bound LEdit Toolbox laygen file"""
    path = ltbpath() + 'laygen\\'
    return path


def laygenfilename():
    """Expected LEdit Toolbox laygen file"""
    file = laygenfilepath() + 'laygen.c'
    return file


def alltdbfilename():
    """Expected file location of collection of all .tdb files"""
    file = laygenfilepath() + 'alltdb.csv'
    return file


def tdbtechreffilename():
    """Expected file location of all .tdb files' tech references"""
    file = laygenfilepath() + 'tdbtechref.txt'
    return file


def varfilepath(project):
    """Expected location for ini and report/log files of various subtools"""
    path = projectpath(project) + 'var\\'
    return path


def allpaths(project):
    paths = [ltbpath(),
             settingspath(),
             allprojectspath(),
             projectpath(project),
             seditfilepath(project),
             pyschematicfilepath(project),
             crcmdfilepath(project),
             crschematicfilepath(project),
             layoutfilepath(project),
             autogenfilepath(project),
             wrlfilepath(project),
             autolabelfilepath(project),
             autoplacefilepath(project),
             lvsfilepath(project),
             drcfilepath(project),
             yldfilepath(project),
             xorfilepath(project),
             laygenfilepath(),
             varfilepath(project)]
    # lvsgdsfilepath(project),
    # lvsctrlfilepath(project),
    # lvsnetlistfilepath(project),
    # lvsresultfilepath(project),
    # lvssvdbfilepath(project),
    # drcgdsfilepath(project),
    # drcctrlfilepath(project),
    # drcresultfilepath(project),
    # yldgdsfilepath(project),
    # yldctrlfilepath(project),
    # yldresultfilepath(project),
    # xorgds1filepath(project),
    # xorgds2filepath(project),
    # xorctrlfilepath(project),
    # xorresultfilepath(project),

    return paths


def linuxuserhomepath(linuxusername):
    """Expected location for user's home dir @ Linux side"""
    path = '/home/' + linuxusername + '/'
    return path


def linuxltbpath(linuxusername):
    """Expected location for all LayoutToolbox stuff @ Linux side"""
    path = linuxuserhomepath(linuxusername) + 'LayoutToolbox/'
    return path


def linuxallprojectspath(linuxusername):
    """Expected location for all LayoutToolbox projects @ Linux side"""
    path = linuxltbpath(linuxusername) + 'projects/'
    return path


def linuxprojectpath(project, linuxusername):
    """Expected location for all LayoutToolbox project data @ Linux side"""
    path = linuxallprojectspath(linuxusername) + project + '/'
    return path


def linuxlvsfilepath(project, linuxusername):
    """Expected location for all files required during LVS @ Linux side"""
    path = linuxprojectpath(project, linuxusername) + 'lvs/'
    return path


def linuxlvscellfilepath(project, cellname, linuxusername):
    """Expected location for all files required during LVS @ Linux side"""
    path = linuxlvsfilepath(project, linuxusername) + cellname + '/'
    return path


def linuxlvsgdsfilepath(project, cellname, linuxusername):
    """Expected location for gds files required during LVS @ Linux side"""
    path = linuxlvscellfilepath(project, cellname, linuxusername)
    return path


def linuxlvsctrlfilepath(project, cellname, linuxusername):
    """Expected location for ctrl files required during LVS @ Linux side"""
    path = linuxlvscellfilepath(project, cellname, linuxusername)
    return path


def linuxlvsnetlistfilepath(project, cellname, linuxusername):
    """Expected location for netlist files required during LVS @ Linux side"""
    path = linuxlvscellfilepath(project, cellname, linuxusername)
    return path


def linuxlvsresultfilepath(project, cellname, linuxusername):
    """Expected location for LVS result files @ Linux side"""
    path = linuxlvscellfilepath(project, cellname, linuxusername)
    return path


def linuxlvssvdbfilepath(project, cellname, linuxusername):
    """Expected location for LVS result files @ Linux side"""
    path =linuxlvscellfilepath(project, cellname, linuxusername) + 'svdb/'
    return path


def linuxdrcfilepath(project, linuxusername):
    """Expected location for all files required during DRC @ Linux side"""
    path = linuxprojectpath(project, linuxusername) + 'drc/'
    return path


def linuxdrccellfilepath(project, cellname, linuxusername):
    """Expected location for all files required during DRC @ Linux side"""
    path = linuxdrcfilepath(project, linuxusername) + cellname + '/'
    return path


def linuxdrcgdsfilepath(project, cellname, linuxusername):
    """Expected location for gds files required during DRC @ Linux side"""
    path = linuxdrccellfilepath(project, cellname, linuxusername)
    return path


def linuxdrcctrlfilepath(project, cellname, linuxusername):
    """Expected location for ctrl files required during DRC @ Linux side"""
    path = linuxdrccellfilepath(project, cellname, linuxusername)
    return path


def linuxdrcresultfilepath(project, cellname, linuxusername):
    """Expected location for DRC result files @ Linux side"""
    path = linuxdrccellfilepath(project, cellname, linuxusername)
    return path


def linuxyldfilepath(project, linuxusername):
    """Expected location for all files required during YLD @ Linux side"""
    path = linuxprojectpath(project, linuxusername) + 'yld/'
    return path


def linuxyldcellfilepath(project, cellname, linuxusername):
    """Expected location for all files required during YLD @ Linux side"""
    path = linuxyldfilepath(project, linuxusername) + cellname + '/'
    return path


def linuxyldgdsfilepath(project, cellname, linuxusername):
    """Expected location for gds files required during YLD @ Linux side"""
    path = linuxyldcellfilepath(project, cellname, linuxusername)
    return path


def linuxyldctrlfilepath(project, cellname, linuxusername):
    """Expected location for ctrl files required during YLD @ Linux side"""
    path = linuxyldcellfilepath(project, cellname, linuxusername)
    return path


def linuxyldresultfilepath(project, cellname, linuxusername):
    """Expected location for YLD result files @ Linux side"""
    path = linuxyldcellfilepath(project, cellname, linuxusername)
    return path


def linuxxorfilepath(project, linuxusername):
    """Expected location for all files required during XOR @ Linux side"""
    path = linuxprojectpath(project, linuxusername) + 'xor/'
    return path


def linuxxorcellfilepath(project, cellname, linuxusername):
    """Expected location for all files required during XOR @ Linux side"""
    path = linuxprojectpath(project, linuxusername) + 'xor/' + cellname + '/'
    return path


def linuxxorgds1filepath(project, cellname, linuxusername):
    """Expected location for 1st gds files required during XOR @ Linux side"""
    path = linuxxorcellfilepath(project, cellname, linuxusername) + 'gds1/'
    return path


def linuxxorgds2filepath(project, cellname, linuxusername):
    """Expected location for 2nd gds files required during XOR @ Linux side"""
    path = linuxxorcellfilepath(project, cellname, linuxusername) + 'gds2/'
    return path


def linuxxorctrlfilepath(project, cellname, linuxusername):
    """Expected location for ctrl files required during XOR @ Linux side"""
    path = linuxxorcellfilepath(project, cellname, linuxusername)
    return path


def linuxxorresultfilepath(project, cellname, linuxusername):
    """Expected location for XOR result files @ Linux side"""
    path = linuxxorcellfilepath(project, cellname, linuxusername)
    return path


def linux2samba(path, simserver, caeleste_server=None):
    if 'home' in path:
        tmp = path.replace('/home/', '\\\\' + simserver + '\\')
    if path.startswith(r'/caeleste'):
        if caeleste_server is None:
            raise Exception('caeleste_server not defined')
        else:
            tmp = path.replace('/caeleste/', '\\\\' + caeleste_server + '\\')
    return tmp.replace('/', '\\')


def sambalvspaths(project, cellname, simserver, linuxusername):
    paths = [linux2samba(linuxuserhomepath(linuxusername), simserver),
             linux2samba(linuxltbpath(linuxusername), simserver),
             linux2samba(linuxallprojectspath(linuxusername), simserver),
             linux2samba(linuxprojectpath(project, linuxusername), simserver),
             linux2samba(linuxlvsfilepath(project, linuxusername), simserver),
             linux2samba(linuxlvsgdsfilepath(project, cellname, linuxusername), simserver),
             linux2samba(linuxlvsctrlfilepath(project, cellname, linuxusername), simserver),
             linux2samba(linuxlvsnetlistfilepath(project, cellname, linuxusername), simserver),
             linux2samba(linuxlvsresultfilepath(project, cellname, linuxusername), simserver),
             linux2samba(linuxlvssvdbfilepath(project, cellname, linuxusername), simserver)]
    return paths


def sambadrcpaths(project, cellname, simserver, linuxusername):
    paths = [linux2samba(linuxuserhomepath(linuxusername), simserver),
             linux2samba(linuxltbpath(linuxusername), simserver),
             linux2samba(linuxallprojectspath(linuxusername), simserver),
             linux2samba(linuxprojectpath(project, linuxusername), simserver),
             linux2samba(linuxdrcfilepath(project, linuxusername), simserver),
             linux2samba(linuxdrcgdsfilepath(project, cellname, linuxusername), simserver),
             linux2samba(linuxdrcctrlfilepath(project, cellname, linuxusername), simserver),
             linux2samba(linuxdrcresultfilepath(project, cellname, linuxusername), simserver)]
    return paths


def sambayldpaths(project, cellname, simserver, linuxusername):
    paths = [linux2samba(linuxuserhomepath(linuxusername), simserver),
             linux2samba(linuxltbpath(linuxusername), simserver),
             linux2samba(linuxallprojectspath(linuxusername), simserver),
             linux2samba(linuxprojectpath(project, linuxusername), simserver),
             linux2samba(linuxyldfilepath(project, linuxusername), simserver),
             linux2samba(linuxyldgdsfilepath(project, cellname, linuxusername), simserver),
             linux2samba(linuxyldctrlfilepath(project, cellname, linuxusername), simserver),
             linux2samba(linuxyldresultfilepath(project, cellname, linuxusername), simserver)]
    return paths


def sambaxorpaths(project, cellname, simserver, linuxusername):
    paths = [linux2samba(linuxuserhomepath(linuxusername), simserver),
             linux2samba(linuxltbpath(linuxusername), simserver),
             linux2samba(linuxallprojectspath(linuxusername), simserver),
             linux2samba(linuxprojectpath(project, linuxusername), simserver),
             linux2samba(linuxxorfilepath(project, linuxusername), simserver),
             linux2samba(linuxxorgds1filepath(project, cellname, linuxusername), simserver),
             linux2samba(linuxxorgds2filepath(project, cellname, linuxusername), simserver),
             linux2samba(linuxxorctrlfilepath(project, cellname, linuxusername), simserver),
             linux2samba(linuxxorresultfilepath(project, cellname, linuxusername), simserver)]
    return paths
