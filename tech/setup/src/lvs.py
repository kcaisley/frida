#!/usr/bin/env python

"""lvs.py: helper functions to prepare Calibre LVS starting from a source
netlist and a layout GDS.
NOTE: Since september 2017, Tanner LVS is no longer supported."""

from __future__ import print_function

import csv
import os
# import sys
import re
import time
import logging      # in case you want to add extra logging
import subprocess

import general
import settings
import LTBsettings
import LTBfunctions
import spice
import timestamp

USERset = settings.USERsettings()
PROJset = settings.PROJECTsettings()
# logger = logging.getLogger(__name__)


def prepare_lvs_dir_server(project, cellname, simserver=None, linuxusername=None):
    logging.info('Prepare LVS dir server')
    USERset.load()
    if simserver is None:
        simserver = USERset.get_str('simserver')
    if linuxusername is None:
        linuxusername = USERset.get_str('linuxusername')

    general.check_linux_samba(simserver, linuxusername)

    sambalvspaths = LTBsettings.sambalvspaths(project, cellname, simserver,
                                              linuxusername)
    general.prepare_dirs(sambalvspaths)


def prepare_lvs_ctrlfile(project, cellname, LVSrulefile=None,
                         LVSincludefile=None, linuxusername=None,
                         fs=None, fl=None, repmax=None, ignoreports=None,
                         zerotol=None, virtconnect=None, hardsubconn=False,
                         layoutnetlistreuse=False):
    global USERset
    USERset.load()
    global PROJset
    PROJset.loaddefault(project)
    PROJset.load()
    projectcheck = PROJset.get_str('projectname')
    if projectcheck != project:
        warning = ('\nWARNING!! \nSelected project (' + project +
                   ') does not match the projectname defined in ' +
                   LTBsettings.projectsettings() + ' (' + projectcheck + ').')
        # print(warning)
        # general.error_log(warning)
        raise Exception(warning)

    if linuxusername is None:
        linuxusername = USERset.get_str('linuxusername')
    if LVSincludefile is None:
        LVSincludefile = PROJset.get_str('LVSincludefile')
    if LVSrulefile is None:
        LVSrulefile = PROJset.get_str('LVSrulefile')
    if fs is None:
        fs = 'RC'
    if fl is None:
        fl = 'RC'
    if repmax is None:
        repmax = '50'
    if ignoreports is None:
        ignoreports = 'NO'
    if zerotol is None:
        zerotol = 'NO'
    if virtconnect is None:
        virtconnect = 'NO'

    if virtconnect not in ['NO', 'COLON', 'NAME']:
        raise ValueError('virtconnect value not supported')
    else:
        if virtconnect == 'COLON':
            virtconnecttext = """VIRTUAL CONNECT COLON YES
VIRTUAL CONNECT REPORT YES UNSATISFIED
VIRTUAL CONNECT REPORT MAXIMUM ALL"""
        elif virtconnect == 'NAME':
            virtconnecttext = """VIRTUAL CONNECT COLON NO
VIRTUAL CONNECT NAME ?
VIRTUAL CONNECT REPORT YES UNSATISFIED
VIRTUAL CONNECT REPORT MAXIMUM ALL"""
        else:
            virtconnecttext = """VIRTUAL CONNECT COLON NO
VIRTUAL CONNECT REPORT NO
"""

    hardsubconntext = ''
    if hardsubconn:
        hardsubconntext = '#DEFINE HARDSUBCONN'

    ctrlfilename = LTBsettings.lvsctrlfilepath(project, cellname) + cellname + '.LVSctrl'

    header = '''//
//  Rule file generated on ''' + time.asctime() + r'''
//     by lvs.py\prepare_lvs_ctrlfile
//
//      *** PLEASE DO NOT MODIFY THIS FILE ***
//      *** unless you know what you're doing ***
//      *** preferably ask for a feature request ***
//
//

'''
    if layoutnetlistreuse:
        layout = ('LAYOUT PATH  "' +
                  LTBsettings.linuxlvssvdbfilepath(project, cellname, linuxusername) +
                  cellname + '.sp"\n')
        layout += 'LAYOUT PRIMARY "' + cellname + '"\n'
        layout += 'LAYOUT SYSTEM SPICE\n\n'
    else:
        layout = ('LAYOUT PATH  "' +
                  LTBsettings.linuxlvsgdsfilepath(project, cellname, linuxusername) +
                  cellname + '.gds"\n')
        layout += 'LAYOUT PRIMARY "' + cellname + '"\n'
        layout += 'LAYOUT SYSTEM GDSII\n\n'

    source = ('SOURCE PATH  "' +
              LTBsettings.linuxlvsnetlistfilepath(project, cellname, linuxusername) +
              cellname + '.sp"\n')
    source += 'SOURCE PRIMARY "' + cellname + '"\n'
    source += 'SOURCE SYSTEM SPICE\n\n'

    if LTBsettings.linuxlvssvdbfilepath(project, cellname, linuxusername)[-1] == '/':
        svdbdir = LTBsettings.linuxlvssvdbfilepath(project, cellname, linuxusername)[:-1]
    else:
        svdbdir = LTBsettings.linuxlvssvdbfilepath(project, cellname, linuxusername)
    svdb = 'MASK SVDB DIRECTORY "' + svdbdir + '" QUERY\n\n'
    report = ('LVS REPORT "' +
              LTBsettings.linuxlvsresultfilepath(project, cellname, linuxusername) +
              cellname + '.lvs.report"\n\n')

    options = '''
LVS REPORT OPTION S
LVS FILTER UNUSED OPTION ''' + fs + ''' SOURCE
LVS FILTER UNUSED OPTION ''' + fl + ''' LAYOUT
LVS REPORT MAXIMUM ''' + repmax + '''

LVS INJECT LOGIC NO
LVS RECOGNIZE GATES NONE

LVS REDUCE PARALLEL MOS YES
LVS REDUCE SPLIT GATES NO
LVS SHORT EQUIVALENT NODES NO


LVS ABORT ON SOFTCHK NO
LVS ABORT ON SUPPLY ERROR NO
LVS IGNORE PORTS ''' + ignoreports + '''
LVS SHOW SEED PROMOTIONS NO
LVS SHOW SEED PROMOTIONS MAXIMUM 50

LVS ISOLATE SHORTS NO

LVS SPICE ALLOW INLINE PARAMETERS YES

''' + virtconnecttext + '''

LVS EXECUTE ERC YES
ERC RESULTS DATABASE "erc.results"
ERC SUMMARY REPORT "erc.summary" REPLACE HIER
ERC CELL NAME NO
ERC MAXIMUM RESULTS 1000
ERC MAXIMUM VERTEX 4096

DRC ICSTATION YES

#DEFINE ZEROTOL ''' + zerotol + '''

''' + hardsubconntext + '''

'''
    include = 'INCLUDE "' + LVSincludefile + '"\n\n'
    rulefile = 'INCLUDE "' + LVSrulefile + '"\n\n'

    cal23fix = 'LVS SPICE REDEFINE PARAM YES\n\n'

    general.write(ctrlfilename, (header + layout + source + svdb + report +
                                 options + include + rulefile + cal23fix), False)

    calcmdfilename = LTBsettings.lvscellfilepath(project, cellname) + 'cal1.cmd'
    lfolder = LTBsettings.linuxlvscellfilepath(project, cellname, linuxusername)
    cal1txt = ''
    if PROJset.get_type('calibreEnvironment') is not None:
        cal1txt += 'source ' + PROJset.get_str('calibreEnvironment') + '\n'
    cal1txt += ('calibre -lvs -hier ' + lfolder + cellname + '.LVSctrl > ' +
                lfolder + 'cal1.log')
    general.write(calcmdfilename, cal1txt, False, True)


def prepare_lvs_source(project, cellname, libname, sourceincludetech=None,
                       sourceincludeproject=None, force=False):
    import subprocess
    global PROJset
    PROJset.loaddefault(project)
    PROJset.load()
    projectcheck = PROJset.get_str('projectname')
    if projectcheck != project:
        warning = ('\nWARNING!! \nSelected project (' + project +
                   ') does not match the projectname defined in ' +
                   LTBsettings.projectsettings() + ' (' + projectcheck + ').')
        # print(warning)
        # general.error_log(warning)
        raise Exception(warning)

    if sourceincludetech is None:
        sourceincludetech = PROJset.get_type('sourceincludetech')

    if sourceincludeproject is None:
        sourceincludeproject = PROJset.get_type('sourceincludeproject')

    # support comment in cellname, anything after the '___'
    # tried before: _# (illegal GDS character)
    #               _$ (linux system variable prefix)
    triple_underscore = cellname.find('___')
    if triple_underscore != -1:
        realcellname = cellname[:triple_underscore]
    else:
        realcellname = cellname

    # support lvs cell, this is a cell with a cellname ending with __lvs
    # (generally, the lvs cell conatains the real cell as instance)
    # lvs MUST be lowercase, uppercase is reserved for parameters
    underscore_lvs = realcellname.find('__lvs')
    while underscore_lvs != -1:
        realcellname = (realcellname[:underscore_lvs] +
                        realcellname[underscore_lvs+5:])
        underscore_lvs = realcellname.find('__lvs')

    # support version cell, this is a cell with a cellname ending with
    #    __v<number>
    # the v MUST be lowercase, uppercase is reserved for parameters
    m = re.search(r'__v\d+$', realcellname)
    while m is not None:
        realcellname = realcellname[:m.start()]
        m = re.search(r'__v\d+$', realcellname)

    # All that's left now should be the real cellename (as in schematic),
    # followed by all (if any) parameters those parameters are seperated from
    # the cellname by a '__', and are seperated from each other by a '_'
    # parameters MUST be in alphabetical order, as a uppercase first letter,
    # and followed by the value not containing a single underscore, unless that
    # single underscore is followed by a number, then that underscore replaces
    # a '.'
    double_underscore = realcellname.find('__')
    if double_underscore != -1:
        rawparamstring = realcellname[double_underscore+1:]
        realcellname = realcellname[:double_underscore]
        paramstring = re.sub('_([0-9])', r'.\1', rawparamstring)
        # general.error_log('rawparamstring: ' + rawparamstring)
        # general.error_log('paramstring: ' + paramstring)
        cellnameparams = re.findall('_[A-Z]+[^_]+', paramstring)
        # should be sorted in the cellname, otherwise it sorts the param values
        # in case of duplicate first letter
        # cellnameparams.sort()
    else:
        cellnameparams = []

    includestmt = ''
    if sourceincludetech is not None:
        includestmt += r'.include ' + sourceincludetech
    if sourceincludeproject is not None:
        includestmt += '\n.include ' + sourceincludeproject

    spfilename = LTBsettings.seditfilepath(project) + realcellname + '.sp'
    nlrfilename = LTBsettings.crcmdfilepath(project) + realcellname + '.nlr'

    LTBfunctions.copynetlist_proj2ltb(project, backup=True)
    if not os.path.isfile(spfilename):
        extrainfo = [spfilename]
        spfilename = LTBsettings.seditfilepath(project) + project + '.sp'
        if not os.path.isfile(spfilename):
            extrainfo.append(spfilename)
            raise Exception('Source Spice file not found:\n' +
                            '\n'.join(extrainfo))
    spnlrfilename = LTBsettings.crschematicfilepath(project) + cellname + '.sp'
    spsfilename = LTBsettings.lvsnetlistfilepath(project, cellname) + cellname + '.sp'

    # use ciruitreducer (or not)
    circuitreducer = False
    # strip top-level spfile from unused subckts in cellname
    # subcktdefcellname might be <designname>_<realcellname>
    if libname.startswith('rh_'):
        libname = libname[3:]
    libcellname = libname + '_' + realcellname
    newlibcellname = realcellname + '_' + libname
    with open(spfilename, 'r') as spfile:
        newlibreal = 0
        libreal = 0
        justreal = 0
        for line in spfile:
            if line.startswith('.subckt ' + newlibcellname + ' '):
                newlibreal += 1
            if line.startswith('.subckt ' + libcellname + ' '):
                libreal += 1
            if line.startswith('.subckt ' + realcellname + ' '):
                justreal += 1
        if newlibreal + libreal + justreal != 1:
            if newlibreal + libreal + justreal == 0:
                raise Exception(newlibcellname + ' and ' + libcellname +
                                ' and ' + realcellname + ' not defined in ' +
                                spfilename + '.')
            else:
                raise Exception('More than one of those: (' + newlibcellname +
                                ', ' + libcellname + ', ' + realcellname +
                                ') defined in ' + spfilename +
                                '. Which one to choose?')
        else:
            subcktdefcellname = (newlibcellname*newlibreal +
                                 libcellname*libreal +
                                 realcellname*justreal)

    if circuitreducer:
        with open(nlrfilename, 'w') as nlrfile:
            nlrfile.write('import ' + spfilename + '\n')
            if subcktdefcellname != realcellname:
                nlrfile.write('fork ' + subcktdefcellname + ' ' +
                              realcellname + '\n')
            nlrfile.write('root ' + realcellname + '\n')
            nlrfile.write('trim\n')
            nlrfile.write('export ' + spnlrfilename + ' -topckt\n')

        try:
            subprocess.call(['circuitreducer', nlrfilename])
        # except FileNotFoundError: (not Py2 compatible)
        except Exception:
            raise Exception('circuitreducer seems not (properly) installed, ' +
                            'also check path environment variable.')

        trimfilename = spnlrfilename
    else:
        spice.netlist2trimnetlist_realname(project, realcellname, libname,
                                           force=force, evalinclude=True)
        trimfilename = (LTBsettings.pyschematicfilepath(project) +
                        realcellname + '.spy')

    with open(trimfilename, 'r') as spnlrfile, \
            open(spsfilename, 'w') as spsfile:
        #   copy comment header from original spice file
        with open(spfilename, 'r') as spfile:
            comment = ''
            for line in spfile:
                if len(line) > 0:
                    if len(line) > 0:
                        if line[0] == '*':
                            comment += line
                        else:
                            break
        spsfile.write(comment)
        #   add include statement after the first non-comment empty line
        spnlrtext = spnlrfile.read()
        double_newline = spnlrtext.find('\n\n')
        spsfile.write(spnlrtext[:double_newline])
        spsfile.write('\n\n' + includestmt)
        #   write all the rest of the file
        spsfile.write(spnlrtext[double_newline:])

        #   find last subckt statement (this is the top/lvs level)
        topckt = spnlrtext.rfind('.subckt')
        #   remove all preceding stuff from memory
        spnlrtext = spnlrtext[topckt:]

        #   find topckt definition
        topckt = spnlrtext.rfind('.subckt')
        if topckt != 0:
            raise Exception(realcellname + ' not defined in ' + spnlrfilename +
                            '. Did it exist in ' + spfilename + '?')

        searchfrom = topckt
        while True:
            newline = spnlrtext.find('\n', searchfrom)
            searchfrom = newline + 1
            if spnlrtext[searchfrom] != '+':
                endtopckthead = newline
                break

        topcktdefinition = spnlrtext[topckt:endtopckthead]

        # general.error_log('topcktdefinition = ' + repr(topcktdefinition))
        # print('topcktdefinition = ' + repr(topcktdefinition))

        #   analyse topckt definition
        # whitespace also allows \n+, a newline followed by a 'plus'
        whitespace = r'(?:(?:\n[+])|\s)'
        portnamechars = r'[A-Za-z0-9_<>+]'
        negativelookahead = r'[=A-Za-z0-9_<>+]'
        # pattern = (r'^[.]subckt(\s+\w+)((?:\s+\w+(?=\s+(?!=)))+)' +
        #            r'((?:\s+\w+\s*=\s*\S+)*)')
        # pattern = (r'^[.]subckt(' + whitespace + r'+\w+)((?:' + whitespace +
        #            r'+'+ portnamechars + '+(?=\s+(?!=)))+)((?:' +
        #            whitespace + r'+\w+' + whitespace + r'*=' + whitespace +
        #            r'*\S+)*)')
        # pattern = (r'^[.]subckt(' + whitespace + r'+\w+)((?:' + whitespace +
        #            r'+'+ portnamechars + '+(?=\s?(?!=)))+)((?:' +
        #            whitespace + r'+\w+' + whitespace + r'*=' + whitespace +
        #            r'*\S+)*)')
        pattern = (r'^[.]subckt(' + whitespace + r'+\w+)((?:' + whitespace +
                   r'+' + portnamechars + r'+(?=\s?(?!' + negativelookahead +
                   r')))+)((?:' + whitespace + r'+\w+' + whitespace + r'*=' +
                   whitespace + r'*\S+)*)')
        m = re.match(pattern, topcktdefinition)
        # general.error_log('pattern = ' + repr(pattern))
        # print('pattern = ' + repr(pattern))

        if m is None:
            raise Exception(realcellname + ' not defined in ' +
                            spfilename + '.')
        assert realcellname == m.groups()[0].strip()
        ports = m.groups()[1]
        params = m.groups()[2]
        if params == '':
            topcktcall = 'X1 ' + m.groups()[1] + '\n+  ' + realcellname
            if len(cellnameparams) != 0:
                raise Exception("Number of params (derived from cellname)" +
                                " in '" + cellname + "' not equal to source.")
            # LTB-25 skip generation of param_lvs in case of a
            #        non-parameterized cell (and non-lvs and non-version)
            if realcellname == cellname:
                return
        else:
            # parampattern = r'(?:\s+(\w+)\s*=\s*(\S+))+'
            # parampattern = (r'(?:' + whitespace + r'+(\w+)' + whitespace +
            #                 r'*=' + whitespace + r'*(\S+))+')
            parampattern = (r'(?:' + whitespace + r'+(\w+)' + whitespace +
                            r'*=' + whitespace + r'*(\S+))')
            param_values = re.findall(parampattern, params)
            param_values.sort(key=lambda x: x[0].upper())
            realparams = ''
            if len(cellnameparams) == len(param_values):
                for x in range(len(cellnameparams)):
                    if cellnameparams[x][1] == param_values[x][0][0].upper():
                        realparams += ' ' + param_values[x][0] + ' = '
                        realparams += cellnameparams[x][2:]
                    else:
                        info = ('layout: ' + repr(cellnameparams) +
                                '\n source: ' + repr(param_values))
                        raise Exception("letters of params in '" + cellname +
                                        "' not equal to source.\nINFO: " +
                                        info)
            else:
                info = ('layout: ' + repr(cellnameparams) + '\n source: ' +
                        repr(param_values))
                raise Exception("Number of params (derived from cellname)" +
                                " in '" + cellname + "' not equal to source." +
                                "\nINFO:" + info)

            topcktcall = ('X1 ' + ports + '\n+  ' + realcellname + '\n+  ' +
                          realparams)

        spsfile.write('\n\n.subckt ' + cellname + ' ' + ports)
        spsfile.write('\n\n' + topcktcall + '\n\n')
        spsfile.write('.ends\n\n')


def prepare_lvs_copy2linux(project, cellname, simserver=None,
                           linuxusername=None, layoutnetlistreuse=False,
                           sourcenetlistreuse=False):
    import shutil
    global USERset
    USERset.load()

    if simserver is None:
        simserver = USERset.get_str('simserver')
    if linuxusername is None:
        linuxusername = USERset.get_str('linuxusername')

    general.check_linux_samba(simserver, linuxusername)

    src = LTBsettings.lvsctrlfilepath(project, cellname) + cellname + '.LVSctrl'
    dst = LTBsettings.linux2samba(
            LTBsettings.linuxlvsctrlfilepath(project, cellname, linuxusername),
            simserver) + cellname + '.LVSctrl'
    shutil.copy2(src, dst)

    if not layoutnetlistreuse:
        src = LTBsettings.lvsgdsfilepath(project, cellname) + cellname + '.gds'
        dst = LTBsettings.linux2samba(
                LTBsettings.linuxlvsgdsfilepath(project, cellname, linuxusername),
                simserver) + cellname + '.gds'
        file_stats = general.os.stat(src)
        print('Copying gds to server ... (' + 
              str(round(file_stats.st_size / (1024 * 1024), 2)) + ' Mb)')
        shutil.copy2(src, dst)

    if not sourcenetlistreuse:
        src = LTBsettings.lvsnetlistfilepath(project, cellname) + cellname + '.sp'
        dst = LTBsettings.linux2samba(
                LTBsettings.linuxlvsnetlistfilepath(project, cellname, linuxusername),
                simserver) + cellname + '.sp'
        file_stats = general.os.stat(src)
        print('Copying netlist to server ... (' + 
              str(round(file_stats.st_size / (1024 * 1024), 2)) + ' Mb)')
        shutil.copy2(src, dst)

    src = LTBsettings.lvscellfilepath(project, cellname) + 'cal1.cmd'
    dst = LTBsettings.linux2samba(LTBsettings.linuxlvscellfilepath(
            project, cellname, linuxusername), simserver) + 'cal1.cmd'
    shutil.copy2(src, dst)


def prep_cal_lvs(project, cellname, simserver=None, linuxusername=None):
    global USERset
    USERset.load()

    if simserver is None:
        simserver = USERset.get_str('simserver')
    if linuxusername is None:
        linuxusername = USERset.get_str('linuxusername')
    no_antispoof = general.check_linux_plink(simserver, linuxusername)

    calcommand = ('-v lvs -p ' + project + ' -c '+ cellname +
                  ' calibre -lvs -hier ' + LTBsettings.linuxlvsctrlfilepath(
                  project, cellname, linuxusername) + cellname + '.LVSctrl')

    calcommand = ('python /home/' + linuxusername + '/bin/calibre_bg.py ' +
                  'prepare ' + calcommand)

    plinkcommand = ['plink', '-ssh', linuxusername + '@' + simserver,
                    no_antispoof, calcommand]

    print(plinkcommand)
    # tmp fix
    # print('\nStop this window from blocking your progress in L-Edit: ' +
    #       'Press [Ctrl]+[C] 2x')
    # print('Your verification will continue runnning on the Linux machine. ')
    p = subprocess.Popen(plinkcommand, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE)
    (output, error) = p.communicate()
    if error != '':
        Exception(error)


def lvs_sequence(project, cellname, libname, sourceincludetech=None,
                 sourceincludeproject=None, force=False, simserver=None,
                 linuxusername=None, LVSrulefile=None, LVSincludefile=None,
                 fs=None, fl=None, repmax=None, ignoreports=None, zerotol=None,
                 virtconnect=None, hardsubconn=False, layoutnetlistreuse=False,
                 sourcenetlistreuse=False):
    if not sourcenetlistreuse:
        print('prepare netlist...')
        prepare_lvs_source(project, cellname, libname, sourceincludetech,
                           sourceincludeproject, force)
    print('prepare ctrlfile...')
    prepare_lvs_ctrlfile(project, cellname, LVSrulefile, LVSincludefile,
                         linuxusername, fs, fl, repmax, ignoreports,
                         zerotol, virtconnect, hardsubconn,
                         layoutnetlistreuse)
    print('prepare directories @ server...')
    prepare_lvs_dir_server(project, cellname, simserver, linuxusername)
    print('copy files to server...')
    prepare_lvs_copy2linux(project, cellname, simserver, linuxusername,
                           layoutnetlistreuse, sourcenetlistreuse)
    print('prepare Calibre1 run @ server...')
    prep_cal_lvs(project, cellname, simserver, linuxusername)


def parse_lvs_report(project, cellname):
    global USERset
    USERset.load()
    global PROJset
    PROJset.loaddefault(project)
    PROJset.load()
    projectcheck = PROJset.get_str('projectname')
    if projectcheck != project:
        warning = ('\nWARNING!! \nSelected project (' + project +
                   ') does not match the projectname defined in ' +
                   LTBsettings.projectsettings() + ' (' + projectcheck + ').')
        # print(warning)
        # general.error_log(warning)
        raise Exception(warning)

    rprtfilename = (LTBsettings.lvsresultfilepath(project, cellname) + cellname +
                    '.lvs.report')
    prsrprtfilename = (LTBsettings.lvsresultfilepath(project, cellname) + cellname +
                       '.lvs.report.prs')

    parsestate = 0
    # 0 = copy-paste state
    # 1 = in header of 'INCORRECT NETS'
    # 2 = in body of incorrect nets, in net description header
    # 3 = in net description body
    # 4 = in net description body of nets to be skipped
    with open(rprtfilename, 'r') as fin:
      with open(prsrprtfilename, 'w') as fout:
        for line in fin:
            if parsestate == 0:
                fout.write(line)
                if line == (' '*35 + 'INCORRECT NETS\n'):
                    parsestate = 1
                    continue
            elif parsestate == 1:
                fout.write(line)
                if line == '*'*110+'\n':
                    netdescrheader = ''
                    errornumber = ''
                    parsestate = 2
                    continue
            elif parsestate in [2, 3, 4]:
                if line == '*'*110+'\n':
                    fout.write(line)
                    parsestate = 0
                    continue
                if parsestate == 2:
                    netdescrheader += line
                    if errornumber == '':
                        ptrn = r'^\s*(\d+)\s+Net\s+'
                        match = re.match(ptrn, line)
                        if match is not None:
                            errornumber == match.groups()[0]
                            splitnetcount = 0
                    else:
                        splitnetcount += 1
                    if 'Connections On This Net' in line:
                        ptrn = (r'\s*--- (\d+) Connections On This Net ---' +
                                r'\s+--- \1 Connections On This Net ---.*')
                        if re.match(ptrn, line) is not None:
                            if splitnetcount != 1:
                                fout.write(netdescrheader)
                            parsestate = 4
                            continue
                        else:
                            fout.write(netdescrheader)
                            netdescrheader = ''
                            parsestate = 3
                            continue
                elif parsestate == 3:
                    fout.write(line)
                    if line == '-'*110+'\n':
                        netdescrheader = ''
                        errornumber = ''
                        parsestate = 2
                        continue
                elif parsestate == 4:
                    if line == '-'*110+'\n':
                        netdescrheader = line
                        errornumber = ''
                        parsestate = 2
                        continue
            else:
                raise Exception('unknown state for parsestate.')

def result_summary(project, foldername):
    files = os.listdir(LTBsettings.lvscellfilepath(project, foldername))
    cellnames = []
    for file in files:
        if file.endswith('.gds'):
            cellnames.append(file[:-4])
    assert len(cellnames) > 0
    if len(cellnames) == 1:
        cellname = cellnames[0]
    if len(cellnames) > 1:
        cellname = [x for x in cellnames if len(x) == min([len(x) for x in cellnames])][0]
    assert cellname + '.lvs.report' in files
    assert cellname + '.lvs.report.ext' in files

    fieldnames=['Date', 'Cellname', 'Result', 'NonStandard options',
                'Net errors', 'Port errors', 'Instance errors', 'Property errors',
                'Soft-connect', 'LVS.VCpos', 'LVS.VCname',
                'LVS.exportHiddenObjects', 'LVS.reuseLayout', 'LVS.reuseSource',
                'LVS.filterSource', 'LVS.filterLayout', 'LVS.reportMax',
                'LVS.ignorePorts', 'LVS.zeroTol', 'LVS.virtConnect',
                'LVS.hardsubconn', 'LVS.force']
    result = {}
    lvsrprtfile = LTBsettings.lvscellfilepath(project, foldername) + cellname + '.lvs.report'
    extrprtfile = LTBsettings.lvscellfilepath(project, foldername) + cellname + '.lvs.report.ext'
    optionsfile = LTBsettings.lvscellfilepath(project, foldername) + 'LVSoptions.log'
    with open(lvsrprtfile, 'r') as lvsrprt, open(extrprtfile, 'r') as extrprt, open(optionsfile, 'r') as options:
        field = 'Date'
        lvsrprt.seek(0,0)
        for line in lvsrprt:
            if line.startswith('CREATION TIME:'):
                result[field] = time.strftime("%Y%m%d_%H%M", time.strptime(line[14:].strip()))
                break
        else:
            logging.info('Date not found')

        field = 'Cellname'
        result[field] = cellname

        field = 'Result'
        lvsrprt.seek(0,0)
        lineofinterest = -1
        for lineno, line in enumerate(lvsrprt):
            if 'OVERALL COMPARISON RESULTS' in line:
                lineofinterest = lineno + 6
            if lineno == lineofinterest:
                if ' CORRECT ' in line:
                    result[field] = ':-)'
                    extrprt.seek(0,0)
                    for extline in extrprt:
                        if 'Stamping conflict' in extline:
                            result[field] = ':-/'
                            break
                    break
                elif 'INCORRECT' in line:
                    result[field] = 'X'
                    break
                elif 'NOT COMPARED' in line:
                    result[field] = 'NC'
                    break
                else:
                    result[field] = '?'
                    logging.info('LVS result not understood:' + line)
                    break
        else:
            result[field] = '?'
            logging.info('LVS result not found')

        field = 'Net errors'
        lvsrprt.seek(0, 0)
        startcount = False
        count = 0
        for line in lvsrprt:
            if not startcount and ' INCORRECT NETS' in line:
                startcount = True
            if startcount:
                if '*'*100 in line:
                    if count != 0:
                        break
                    else:
                        count += 1
                elif '-'*100 in line:
                    count += 1
        result[field] = str(count)

        field = 'Port errors'
        lvsrprt.seek(0, 0)
        startcount = False
        count = -1
        for line in lvsrprt:
            if not startcount and ' INCORRECT PORTS' in line:
                startcount = True
            elif startcount:
                if '*'*100 in line:
                    if count != -1:
                        break
                    else:
                        count += 1
                elif count > -1 and len(line.strip())>0:
                    count += 1
        result[field] = str(max(count, 0))

        field = 'Instance errors'
        lvsrprt.seek(0, 0)
        startcount = False
        count = 0
        for line in lvsrprt:
            if not startcount and ' INCORRECT INSTANCES' in line:
                startcount = True
            if startcount:
                if '*'*100 in line:
                    if count != 0:
                        break
                    else:
                        count += 1
                if '-'*100 in line:
                    count += 1
        result[field] = str(count)

        field = 'Property errors'
        lvsrprt.seek(0, 0)
        startcount = False
        firsterrno = -1
        lasterrno = -2
        for line in lvsrprt:
            if not startcount and ' PROPERTY ERRORS' in line:
                startcount = True
            if startcount:
                if '*'*100 in line:
                    if firsterrno != -1:
                        break
                    else:
                        firsterrno += 1
                elif len(line)>7 and line[:7] not in ['DISC#  ', '*******', '       ']:
                    if firsterrno == 0:
                        firsterrno = int(line[:6])
                        lasterrno = int(line[:6])
                    else:
                        lasterrno = int(line[:6])
        result[field] = str(lasterrno - firsterrno + 1)

        field = 'Soft-connect'
        extrprt.seek(0,0)
        startcount = False
        count = 0
        for extline in extrprt:
            if 'Stamping conflict' in extline:
                count += 1
        result[field] = str(count)

        optnonstd = []

        fulloption = options.read(1024)
        for field, std in [('LVS.VCpos', ''), ('LVS.VCname', ''),
                           ('LVS.exportHiddenObjects', '1'), ('LVS.reuseLayout', '0'),
                           ('LVS.reuseSource', '0'), ('LVS.filterSource', 'RC'),
                           ('LVS.filterLayout', 'RC'), ('LVS.reportMax', '50'),
                           ('LVS.ignorePorts', 'NO'), ('LVS.zeroTol', 'NO'),
                           ('LVS.virtConnect', 'NO'), ('LVS.hardsubconn', '0'),
                           ('LVS.force', '0')]:
            m = re.search('LTB: ' + field + ' = (.*)', fulloption)
            result[field] = '' if m is None else m.groups()[0]
            if result[field] != std:
                optnonstd.append(field)

        field = 'NonStandard options'
        result[field] = '/'.join(optnonstd)


    csvfilename = LTBsettings.lvsfilepath(project) + 'lvs_summary.csv'
    rows = []
    newfile = False
    rewrite = False
    try:
        with open(csvfilename, 'r') as csvf:
            for line in csvf:
                rfieldnames = line.strip().split((','))
                break
        with open(csvfilename, 'r', newline='') as csvf:
            # dialect = csv.Sniffer().sniff(csvf.read(1024))
            reader = csv.DictReader(csvf, fieldnames=rfieldnames)
            print(reader.fieldnames)
            if fieldnames != reader.fieldnames:
                # if the header does not match the fieldnames, file will be rewritten
                for fn in reader.fieldnames:
                    if fn not in fieldnames:
                        fieldnames.append(fn)
                for row in reader:
                    rows.append(row)
                print('rewrite = True')
                rewrite = True

    except FileNotFoundError:
        print('newfile = True')
        newfile = True

    if newfile or rewrite:
        if rewrite:
            timestamp.make(False, [csvfilename])
        with open(csvfilename, 'w', newline='') as csvf:
            writer = csv.DictWriter(csvf, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

    with open(csvfilename, 'a', newline='') as csvf:
        writer = csv.DictWriter(csvf, fieldnames=fieldnames)
        writer.writerow(result)

def argparse_setup(subparsers):
    parser_lvs_pld = subparsers.add_parser(
            'prepare_lvs_dir', help='prepare all folders for LVS for a given' +
            ' project/cellname')
    parser_lvs_pld.add_argument(
            '-p', '--project', required=True, help='the PROJECT name')
    parser_lvs_pld.add_argument(
            '-c', '--cellname', required=True, help='the CELL name')

    parser_lvs_plds = subparsers.add_parser(
            'prepare_lvs_dir_server', help='prepare all folders for LVS for ' +
            'a given project on the Calibre server')
    parser_lvs_plds.add_argument(
            '-p', '--project', required=True, help='the PROJECT name')
    parser_lvs_plds.add_argument(
            '-c', '--cellname', required=True, help='the CELL name')
    parser_lvs_plds.add_argument(
            '-s', '--server', default=None, help='the (linux) Calibre server' +
            r' (default: defined in T:\LayoutToolbox\settings\user.ini)')
    parser_lvs_plds.add_argument(
            '-u', '--username', default=None, help='your username on the ' +
            '(linux) Calibre server (default: defined in ' +
            r'T:\LayoutToolbox\settings\user.ini)')

    parser_lvs_pls = subparsers.add_parser(
            'prepare_lvs_source', help='prepare source netlist file for a ' +
            'given project and cellname')
    parser_lvs_pls.add_argument(
            '-p', '--project', required=True, help='the PROJECT name')
    parser_lvs_pls.add_argument(
            '-c', '--cellname', required=True, help='the CELL name')
    parser_lvs_pls.add_argument(
            '-l', '--libname', required=True, help='the LIBRARY name')
    parser_lvs_pls.add_argument(
            '-it', '--includetech', default=None, help='technology dependent' +
            ' include (default: defined in ' +
            r'S:\technologies\setup\projects\projects.ini)')
    parser_lvs_pls.add_argument(
            '-ip', '--includeproject', default=None, help='project dependent' +
            ' include (default: defined in ' +
            r'S:\technologies\setup\projects\projects.ini)')
    parser_lvs_pls.add_argument(
            '-f', '--force', required=False, default=False,
            action='store_true', help="force netlist generation, don't stop " +
            "on negative check result")

    parser_lvs_plc = subparsers.add_parser(
            'prepare_lvs_ctrlfile', help='prepare LVS control file for a ' +
            'given project and cellname and options')
    parser_lvs_plc.add_argument(
            '-p', '--project', required=True, help='the PROJECT name')
    parser_lvs_plc.add_argument(
            '-c', '--cellname', required=True, help='the CELL name')
    parser_lvs_plc.add_argument(
            '-u', '--username', default=None, help='your username on the ' +
            '(linux) Calibre server (default: defined in ' +
            r'T:\LayoutToolbox\settings\user.ini)')
    parser_lvs_plc.add_argument(
            '-r', '--rulefile', default=None, help='LVS rule file (default: ' +
            r'defined in S:\technologies\setup\projects\projects.ini)')
    parser_lvs_plc.add_argument(
            '-i', '--lvsinclude', default=None, help='LVS include file (' +
            'default: defined in ' +
            r'S:\technologies\setup\projects\projects.ini)')
    parser_lvs_plc.add_argument(
            '-ofs', '--filtersource', default=None, help='LVS option FILTER ' +
            'SOURCE (default: RB)')
    parser_lvs_plc.add_argument(
            '-ofl', '--filterlayout', default=None, help='LVS option FILTER ' +
            'LAYOUT (default: RB)')
    parser_lvs_plc.add_argument(
            '-orm', '--reportmax', default=None, help='LVS option max number' +
            ' of LVS errors reported (default: 50)')
    parser_lvs_plc.add_argument(
            '-oip', '--ignoreports', default=None, help='LVS option IGNORE ' +
            'PORTS [YES|NO] (default: NO)')
    parser_lvs_plc.add_argument(
            '-ozt', '--zerotol', default=None, help='LVS option ZERO ' +
            'TOLERANCE (default: NO)')
    parser_lvs_plc.add_argument(
            '-ovc', '--virtconnect', default=None, help='LVS option VIRTUAL ' +
            'CONNECT (default: NO)')
    parser_lvs_plc.add_argument(
            '-hsc', '--hardsubconn', default=False, action='store_true',
            help='add "#DEFINE HARDSUBCONN" (default: False)')
    parser_lvs_plc.add_argument(
            '-lnr', '--layoutnetlistreuse', default=False, action='store_true',
            help='Reuse the last extracted layout netlist (default: False)')

    parser_lvs_plc2l = subparsers.add_parser(
            'prepare_lvs_copy2linux', help='copy files to linux Calibre ' +
            'server for a given project and cellname')
    parser_lvs_plc2l.add_argument(
            '-p', '--project', required=True, help='the PROJECT name')
    parser_lvs_plc2l.add_argument(
            '-c', '--cellname', required=True, help='the CELL name')
    parser_lvs_plc2l.add_argument(
            '-s', '--server', default=None, help='the (linux) Calibre server' +
            r' (default: defined in T:\LayoutToolbox\settings\user.ini)')
    parser_lvs_plc2l.add_argument(
            '-u', '--username', default=None, help='your username on the ' +
            '(linux) Calibre server (default: defined in ' +
            r'T:\LayoutToolbox\settings\user.ini)')
    parser_lvs_plc2l.add_argument(
            '-lnr', '--layoutnetlistreuse', default=False, action='store_true',
            help='Reuse the last extracted layout netlist (default: False)')
    parser_lvs_plc2l.add_argument(
            '-snr', '--sourcenetlistreuse', default=False, action='store_true',
            help='Reuse the last prepared source netlist (default: False)')

    parser_lvs_pcl = subparsers.add_parser(
            'prep_cal_lvs', help='prepare Cal1 helper command files')
    parser_lvs_pcl.add_argument(
            '-p', '--project', required=True, help='the PROJECT name')
    parser_lvs_pcl.add_argument(
            '-c', '--cellname', required=True, help='the CELL name')
    parser_lvs_pcl.add_argument(
            '-s', '--server', default=None, help='the (linux) Calibre server' +
            r' (default: defined in T:\LayoutToolbox\settings\user.ini)')
    parser_lvs_pcl.add_argument(
            '-u', '--username', default=None, help='your username on the ' +
            '(linux) Calibre server (default: defined in ' +
            r'T:\LayoutToolbox\settings\user.ini)')
    parser_lvs_pcl.add_argument(
            '-nobg', '--nobackground', dest='background', default=True,
            action='store_false', help='runs not in background')

    parser_lvs_seq = subparsers.add_parser(
            'lvs_sequence', help='assumes project folder exists and runs the '
            'whole sequence to do LVS on a given project and cellname ' +
            'with several options')
    parser_lvs_seq.add_argument(
            '-p', '--project', required=True, help='the PROJECT name')
    parser_lvs_seq.add_argument(
            '-c', '--cellname', required=True, help='the CELL name')
    parser_lvs_seq.add_argument(
            '-l', '--libname', required=True, help='the LIBRARY name')
    parser_lvs_seq.add_argument(
            '-it', '--includetech', default=None, help='technology dependent' +
            ' include (default: defined in ' +
            r'S:\technologies\setup\projects\projects.ini)')
    parser_lvs_seq.add_argument(
            '-ip', '--includeproject', default=None, help='project dependent' +
            ' include (default: defined in ' +
            r'S:\technologies\setup\projects\projects.ini)')
    parser_lvs_seq.add_argument(
            '-f', '--force', required=False, default=False,
            action='store_true', help="force netlist generation, don't stop " +
            "on negative check result")
    parser_lvs_seq.add_argument(
            '-s', '--server', default=None, help='the (linux) Calibre server' +
            r' (default: defined in T:\LayoutToolbox\settings\user.ini)')
    parser_lvs_seq.add_argument(
            '-u', '--username', default=None, help='your username on the ' +
            '(linux) Calibre server (default: defined in ' +
            r'T:\LayoutToolbox\settings\user.ini)')
    parser_lvs_seq.add_argument(
            '-r', '--rulefile', default=None, help='LVS rule file (default: ' +
            r'defined in S:\technologies\setup\projects\projects.ini)')
    parser_lvs_seq.add_argument(
            '-i', '--lvsinclude', default=None, help='LVS include file (' +
            'default: defined in ' +
            r'S:\technologies\setup\projects\projects.ini)')
    parser_lvs_seq.add_argument(
            '-ofs', '--filtersource', default=None, help='LVS option FILTER ' +
            'SOURCE (default: RB)')
    parser_lvs_seq.add_argument(
            '-ofl', '--filterlayout', default=None, help='LVS option FILTER ' +
            'LAYOUT (default: RB)')
    parser_lvs_seq.add_argument(
            '-orm', '--reportmax', default=None, help='LVS option max number' +
            ' of LVS errors reported (default: 50)')
    parser_lvs_seq.add_argument(
            '-oip', '--ignoreports', default=None, help='LVS option IGNORE ' +
            'PORTS [YES|NO] (default: NO)')
    parser_lvs_seq.add_argument(
            '-ozt', '--zerotol', default=None, help='LVS option ZERO ' +
            'TOLERANCE (default: NO)')
    parser_lvs_seq.add_argument(
            '-ovc', '--virtconnect', default=None, help='LVS option VIRTUAL ' +
            'CONNECT (default: NO)')
    parser_lvs_seq.add_argument(
            '-hsc', '--hardsubconn', default=False, action='store_true',
            help='add "#DEFINE HARDSUBCONN" (default: False)')
    parser_lvs_seq.add_argument(
            '-lnr', '--layoutnetlistreuse', default=False, action='store_true',
            help='Reuse the last extracted layout netlist (default: False)')
    parser_lvs_seq.add_argument(
            '-snr', '--sourcenetlistreuse', default=False, action='store_true',
            help='Reuse the last prepared source netlist (default: False)')

    parser_lvs_plr = subparsers.add_parser(
            'parse_lvs_report', help='parse lvs report file for a ' +
            'given project and cellname')
    parser_lvs_plr.add_argument(
            '-p', '--project', required=True, help='the PROJECT name')
    parser_lvs_plr.add_argument(
            '-c', '--cellname', required=True, help='the CELL name')
    # disable Cal1 switch, there is only one type of licanse available for the
    # moment
    # parser_lvs_seq.add_argument(
    #         '-c1', '--Calibre1', default=False, action='store_true',
    #         help='Reuse the last prepared source netlist (default: False)')


def argparse_eval(args):
    # make a dict of args
    dictargs = vars(args)
    funcdict = {'prepare_lvs_dir': (LTBfunctions.prepare_lvs_dir,
                                    [dictargs.get('project'),
                                     dictargs.get('cellname')]),
                'prepare_lvs_dir_server': (prepare_lvs_dir_server,
                                           [dictargs.get('project'),
                                            dictargs.get('cellname'),
                                            dictargs.get('server'),
                                            dictargs.get('username')]),
                'prepare_lvs_source': (prepare_lvs_source,
                                       [dictargs.get('project'),
                                        dictargs.get('cellname'),
                                        dictargs.get('libname'),
                                        dictargs.get('includetech'),
                                        dictargs.get('includeproject'),
                                        dictargs.get('force')]),
                'prepare_lvs_ctrlfile': (prepare_lvs_ctrlfile,
                                         [dictargs.get('project'),
                                          dictargs.get('cellname'),
                                          dictargs.get('rulefile'),
                                          dictargs.get('lvsinclude'),
                                          dictargs.get('username'),
                                          dictargs.get('filtersource'),
                                          dictargs.get('filterlayout'),
                                          dictargs.get('reportmax'),
                                          dictargs.get('ignoreports'),
                                          dictargs.get('zerotol'),
                                          dictargs.get('virtconnect'),
                                          dictargs.get('hardsubconn'),
                                          dictargs.get('layoutnetlistreuse')]),
                'prepare_lvs_copy2linux': (prepare_lvs_copy2linux,
                                           [dictargs.get('project'),
                                            dictargs.get('cellname'),
                                            dictargs.get('server'),
                                            dictargs.get('username'),
                                            dictargs.get('layoutnetlistreuse'),
                                            dictargs.get('sourcenetlistreuse')
                                            ]),
                'prep_cal_lvs': (prep_cal_lvs,
                                 [dictargs.get('project'),
                                  dictargs.get('cellname'),
                                  dictargs.get('server'),
                                  dictargs.get('username')]),
                'lvs_sequence': (lvs_sequence,
                                 [dictargs.get('project'),
                                  dictargs.get('cellname'),
                                  dictargs.get('libname'),
                                  dictargs.get('includetech'),
                                  dictargs.get('includeproject'),
                                  dictargs.get('force'),
                                  dictargs.get('server'),
                                  dictargs.get('username'),
                                  dictargs.get('rulefile'),
                                  dictargs.get('lvsinclude'),
                                  dictargs.get('filtersource'),
                                  dictargs.get('filterlayout'),
                                  dictargs.get('reportmax'),
                                  dictargs.get('ignoreports'),
                                  dictargs.get('zerotol'),
                                  dictargs.get('virtconnect'),
                                  dictargs.get('hardsubconn'),
                                  dictargs.get('layoutnetlistreuse'),
                                  dictargs.get('sourcenetlistreuse')]),
                'parse_lvs_report': (parse_lvs_report,
                                     [dictargs.get('project'),
                                      dictargs.get('cellname')])
                }
    return funcdict


if __name__ == "__main__":
    general.logsetup()
    general.myargparse(argparse_setup, argparse_eval, 'v20241003')
