import re
import time
# import logging      # in case you want to add extra logging
import subprocess

import general
import timestamp
import settings
import LTBsettings
import LTBfunctions


USERset = settings.USERsettings()
PROJset = settings.PROJECTsettings()

def drc2csv(project=None, cellname=None, filename=None, outfile=None):
    global USERset
    USERset.load()
    sep = USERset.get_type('CSVseparator')
    CSVheader = USERset.get_type('CSVheadersep')

    if filename is None:
        drcresultsfilename = (LTBsettings.drcresultfilepath(project, cellname) +
                              cellname + '.drc.results')
    else:
        drcresultsfilename = filename
    if outfile is None:
        csvoutfilename = (LTBsettings.drcresultfilepath(project, cellname) + cellname +
                          '_drc.csv')
    else:
        csvoutfilename = outfile

    with open(drcresultsfilename, 'r') as drcresultsfile:
        drctext = drcresultsfile.read()

    pattern = (r'(?P<rulename>.+)\n(?P<number>\d+).+\nRule File ' +
               r'(?:Title|Pathname):.+\n(?P<ruledescr>.+)')
    if CSVheader:
        csvtext = sep.join(['sep=', '\n'])
    else:
        csvtext = ''

    count = 0
    errorcount = 0
    for a in re.finditer(pattern, drctext, re.M):
        count += 1
        csvtext += sep.join([a.groupdict()['rulename'], a.groupdict()['number'],
                             a.groupdict()['ruledescr'] + '\n'])
        errorcount += int(a.groupdict()['number'])

    if count == 0:
        # lf11is drc result
        pattern = (r'(?P<rulename>\S+)\n(?P<number>\d+).+\n\s*(?P=rulename)' +
                   r'.+?{(?P<ruledescr>[^}]+)}')
        for a in re.finditer(pattern, drctext, re.M):
            count += 1
            csvtext += sep.join([a.groupdict()['rulename'],
                                 a.groupdict()['number'],
                                 a.groupdict()['ruledescr'].replace('\n', '')
                                 + '\n'])
            errorcount += int(a.groupdict()['number'])

    general.write(csvoutfilename, csvtext, True)

    print(str(errorcount) + ' errors on ' + str(count) + ' DRC rules.')
    print('Report summary written to: ' + csvoutfilename)


def drc_split_result(project=None, cellname=None, filename=None, maxerr=500):
    if filename is None:
        drcresultsfilename = (LTBsettings.drcresultfilepath(project, cellname) +
                              cellname + '.drc.results')
    else:
        drcresultsfilename = filename

    keepdrcresultsfilename = timestamp.make(True, [drcresultsfilename])[0]
    state = 0
    
    with open(keepdrcresultsfilename, 'r') as readfile:
      with open(drcresultsfilename, 'w') as writefile:
        for line in readfile:
            if state == 0:  #first line
                assert line.startswith(cellname)
                writefile.write(line)
                state = 1
            elif state == 1:   #rule name
                rulename = line.rstrip()
                print('rulename: ' + rulename, end = '')
                CN_in_result = False
                CN_last = ''
                state = 2
            elif state == 2:   #rule count and date
                rlinesplit = line.split(' ')
                rulecount = int(rlinesplit[0])
                assert rulecount == int(rlinesplit[1])
                copyline = int(rlinesplit[2])
                path_comment = ''
                state = 3
            elif state == 3:   #Rule File Pathname and comment
                copyline -= 1
                path_comment += line
                if copyline == 0:
                    if rulecount <= maxerr:
                        print('')
                        writefile.write(rulename + '\n')
                        writefile.write(' '.join(rlinesplit))
                        writefile.write(path_comment)
                        state = 4
                        returnstate = 4
                    else:
                        subrules = (rulecount - 1)//maxerr + 1
                        print(' ->    / ' + str(subrules))
                        ptrnsuffix = '_{:0' + str(len(str(subrules))) + 'd}/{:d}\n'
                        newrlinesplit = rlinesplit
                        state = 14
                        returnstate = 14
            elif state == 4:   # separate error header (when total count for this err type <= maxerr)
                assert line[:2] in ['p ', 'e ']
                writefile.write(line)
                plinesplit = line.split(' ')
                assert int(plinesplit[1]) <= rulecount
                if int(plinesplit[1]) == rulecount:
                    returnstate = 1
                copyline = int(plinesplit[2])
                state = 99
            elif state == 14:   # separate error header (when total count for this err type > maxerr)
                assert line[:2] in ['p ', 'e ']
                plinesplit = line.split(' ')
                if int(plinesplit[1]) % maxerr == 1:
                    rulesuffix = int(plinesplit[1])//maxerr + 1
                    txtsuffix = ptrnsuffix.format(rulesuffix, subrules)
                    if rulesuffix == subrules:
                        # newrlinesplit = rlinesplit
                        newrlinesplit[0] = str(((rulecount-1) % maxerr) + 1)
                        newrlinesplit[1] = newrlinesplit[0]

                    else:
                        # newrlinesplit = rlinesplit
                        newrlinesplit[0] = str(maxerr)
                        newrlinesplit[1] = newrlinesplit[0]
                    writefile.write(rulename + txtsuffix)
                    writefile.write(' '.join(newrlinesplit))
                    writefile.write(path_comment)

                plinesplit[1] = str((int(plinesplit[1])-1) % maxerr+1)
                writefile.write(' '.join(plinesplit))
                if plinesplit[1] == newrlinesplit[0]:
                    if rulesuffix == subrules:
                        returnstate = 1
                copyline = int(plinesplit[2])
                state = 99
            elif state == 99:  #copy still so many lines but check if first line starts with 'CN '
                if line.startswith ('CN '):
                    CN_in_result = True
                    CN_last = line
                else:
                    if CN_in_result and plinesplit[1] == '1':
                        writefile.write(CN_last)
                    copyline -= 1
                writefile.write(line)
                if copyline == 0:
                    state = returnstate
                else:
                    state = 100
            elif state == 100:  #copy still so many lines 
                copyline -= 1
                writefile.write(line)
                if copyline == 0:
                    state = returnstate
            

def prepare_drc_dir_server(project, cellname, simserver=None, linuxusername=None):
    global USERset
    USERset.load()
    if simserver is None:
        simserver = USERset.get_str('simserver')
    if linuxusername is None:
        linuxusername = USERset.get_str('linuxusername')

    general.check_linux_samba(simserver, linuxusername)

    sambadrcpaths = LTBsettings.sambadrcpaths(project, cellname, simserver,
                                              linuxusername)
    general.prepare_dirs(sambadrcpaths)


def prepare_drc_ctrlfile(project, cellname, DRCrulefile=None,
                         linuxusername=None):
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
    if DRCrulefile is None:
        if PROJset.get_type('DRCrulefile') is None:
            raise settings.SettingsError('DRCrulefile not defined in project.ini')
        DRCrulefile = PROJset.get_str('DRCrulefile')
    if DRCrulefile == '**TOP**':
        if PROJset.get_type('DRCTOPrulefile') is None:
            raise settings.SettingsError('DRCTOPrulefile not defined in project.ini')
        DRCrulefile = PROJset.get_str('DRCTOPrulefile')
    if DRCrulefile == '**ant**':
        if PROJset.get_type('ANTrulefile') is None:
            raise settings.SettingsError('ANTrulefile not defined in project.ini')
        DRCrulefile = PROJset.get_str('ANTrulefile')
    if DRCrulefile == '**stitch**':
        if PROJset.get_type('DRCstitchrulefile') is None:
            raise settings.SettingsError('DRCstitchrulefile not defined in project.ini')
        DRCrulefile = PROJset.get_str('DRCstitchrulefile')

    ctrlfilename = LTBsettings.drcctrlfilepath(project, cellname) + cellname + '.DRCctrl'

    header = r'''//
//  Rule file generated on ''' + time.asctime() + r'''
//     by drc.py\prepare_drc_ctrlfile
//
//      *** PLEASE DO NOT MODIFY THIS FILE ***
//      *** unless you know what you're doing ***
//      *** preferably ask for a feature request ***
//
//

'''
    layout = ('LAYOUT PATH  "' +
              LTBsettings.linuxdrcgdsfilepath(project, cellname, linuxusername) +
              cellname + '.gds"\n')
    layout += 'LAYOUT PRIMARY "' + cellname + '"\n'
    layout += 'LAYOUT SYSTEM GDSII\n\n'

    results = ('DRC RESULTS DATABASE "' +
               LTBsettings.linuxdrcresultfilepath(project, cellname, linuxusername) +
               cellname + '.drc.results" ASCII \n')
    results += 'DRC MAXIMUM RESULTS 1000\n'
    results += 'DRC MAXIMUM VERTEX 4096\n\n'
    results += 'DRC CELL NAME NO\n'
    results += ('DRC SUMMARY REPORT "' +
                LTBsettings.linuxdrcresultfilepath(project, cellname, linuxusername) +
                cellname + '.drc.summary" REPLACE HIER\nDRC KEEP EMPTY NO\n\n')

    options = '''
VIRTUAL CONNECT COLON NO
VIRTUAL CONNECT REPORT NO

DRC ICSTATION YES

'''

    rulefile = 'INCLUDE "' + DRCrulefile + '"\n\n'

    general.write(ctrlfilename, header+layout+results+options+rulefile, False)

    calcmdfilename = LTBsettings.drccellfilepath(project, cellname) + 'cal1.cmd'
    lfolder = LTBsettings.linuxdrccellfilepath(project, cellname, linuxusername)
    cal1txt = ''
    if PROJset.get_type('calibreEnvironment') is not None:
        cal1txt += 'source ' + PROJset.get_str('calibreEnvironment') + '\n'
    cal1txt += ('calibre -drc -hier ' + lfolder + cellname + '.DRCctrl > ' +
                lfolder + 'cal1.log')
    general.write(calcmdfilename, cal1txt, False, True)


def prepare_drc_copy2linux(project, cellname, simserver=None,
                           linuxusername=None):
    import shutil
    global USERset
    USERset.load()

    if simserver is None:
        simserver = USERset.get_str('simserver')
    if linuxusername is None:
        linuxusername = USERset.get_str('linuxusername')

    general.check_linux_samba(simserver, linuxusername)

    src = LTBsettings.drcctrlfilepath(project, cellname) + cellname + '.DRCctrl'
    dst = LTBsettings.linux2samba(LTBsettings.linuxdrcctrlfilepath(
            project, cellname, linuxusername), simserver) + cellname + '.DRCctrl'
    shutil.copy2(src, dst)

    src = LTBsettings.drcgdsfilepath(project, cellname) + cellname + '.gds'
    dst = LTBsettings.linux2samba(LTBsettings.linuxdrcgdsfilepath(
            project, cellname, linuxusername), simserver) + cellname + '.gds'
    file_stats = general.os.stat(src)
    print('Copying gds to server ... (' + 
          str(round(file_stats.st_size / (1024 * 1024), 2)) + ' Mb)')
    shutil.copy2(src, dst)
    
    src = LTBsettings.drccellfilepath(project, cellname) + 'cal1.cmd'
    dst = LTBsettings.linux2samba(LTBsettings.linuxdrccellfilepath(
            project, cellname, linuxusername), simserver) + 'cal1.cmd'
    shutil.copy2(src, dst)


def prep_cal_drc(project, cellname, simserver=None, linuxusername=None):
    global USERset
    USERset.load()

    if simserver is None:
        simserver = USERset.get_str('simserver')
    if linuxusername is None:
        linuxusername = USERset.get_str('linuxusername')
    no_antispoof = general.check_linux_plink(simserver, linuxusername)

    calcommand = ('-v drc -p ' + project + ' -c '+ cellname +
                  ' calibre -drc -hier ' + LTBsettings.linuxdrcctrlfilepath(
                  project, cellname, linuxusername) + cellname + '.DRCctrl')

    calcommand = ('python /home/' + linuxusername + '/bin/calibre_bg.py ' +
                  'prepare ' + calcommand)

    plinkcommand = ['plink', '-ssh', linuxusername + '@' + simserver,
                    no_antispoof, calcommand]

    print(plinkcommand)
    # tmp fix
    # print('\nStop this window from blocking your progress in L-Edit: Press ' +
    #       '[Ctrl]+[C] 2x')
    # print('Your verification will continue runnning on the Linux machine. ')
    p = subprocess.Popen(plinkcommand, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE)
    (output, error) = p.communicate()
    if error != '':
        Exception(error)


def drc_sequence(project, cellname, simserver=None, linuxusername=None,
                 DRCrulefile=None):
    print('prepare ctrlfile...')
    prepare_drc_ctrlfile(project, cellname, DRCrulefile, linuxusername)
    print('prepare directories @ server...')
    prepare_drc_dir_server(project, cellname, simserver, linuxusername)
    print('copy files to server...')
    prepare_drc_copy2linux(project, cellname, simserver, linuxusername)
    print('prepare Calibre1 run @ server...')
    prep_cal_drc(project, cellname, simserver, linuxusername)


def argparse_setup(subparsers):
    parser_drc_csv = subparsers.add_parser(
            'drc2csv', help='creates a CSV file for Excel given a Calibre ' +
            'drc result file')
    parser_drc_csv.add_argument(
            '-p', '--project', default=None, help='the PROJECT name')
    parser_drc_csv.add_argument(
            '-c', '--cellname', default=None, help='the CELL name')
    parser_drc_csv.add_argument(
            '-f', '--filename', default=None,
            help=('the drc.result file name, default: the drc report of the ' +
                  r'cell in the drc result file location'))
    parser_drc_csv.add_argument(
            '-o', '--outfile', default=None,
            help=('the csv report file name, default: <cellname>_drc.csv in ' +
                  r'the drc result file location'))

    parser_drc_pdd = subparsers.add_parser(
            'prepare_drc_dir', help='prepare all folders for DRC for a ' +
            'given project/cellname')
    parser_drc_pdd.add_argument(
            '-p', '--project', required=True, help='the PROJECT name')
    parser_drc_pdd.add_argument(
            '-c', '--cellname', required=True, help='the CELL name')


    parser_drc_pdds = subparsers.add_parser(
            'prepare_drc_dir_server', help='prepare all folders for DRC for ' +
            'a given project on the Calibre server')
    parser_drc_pdds.add_argument(
            '-p', '--project', required=True, help='the PROJECT name')
    parser_drc_pdds.add_argument(
            '-c', '--cellname', required=True, help='the CELL name')
    parser_drc_pdds.add_argument(
            '-s', '--server', default=None, help='the (linux) Calibre server' +
            r' (default: defined in T:\LayoutToolbox\settings\user.ini)')
    parser_drc_pdds.add_argument(
            '-u', '--username', default=None, help='your username on the ' +
            '(linux) Calibre server (default: defined in ' +
            r'T:\LayoutToolbox\settings\user.ini)')

    parser_drc_pdc = subparsers.add_parser(
            'prepare_drc_ctrlfile', help='prepare DRC control file for a ' +
            'given project and cellname and options')
    parser_drc_pdc.add_argument(
            '-p', '--project', required=True, help='the PROJECT name')
    parser_drc_pdc.add_argument(
            '-c', '--cellname', required=True, help='the CELL name')
    parser_drc_pdc.add_argument(
            '-u', '--username', default=None, help='your username on the ' +
            '(linux) Calibre server (default: defined in' +
            r' T:\LayoutToolbox\settings\user.ini)')
    parser_drc_pdc.add_argument(
            '-r', '--rulefile', default=None, help='DRC rule file (default: ' +
            'defined by DRCrulefile in ' +
            r'S:\technologies\setup\projects\projects.ini) special cases: ' +
            '**TOP** ==> defined by DRCTOPrulefile in projects.ini.  ' +
            '**ant** ==> defined by ANTrulefile in projects.ini.  ' +
            '**stitch** ==> defined by DRCstitchrulefile in projects.ini.')

    parser_drc_pdc2l = subparsers.add_parser(
            'prepare_drc_copy2linux', help='copy files to linux Calibre ' +
            'server for a given project and cellname')
    parser_drc_pdc2l.add_argument(
            '-p', '--project', required=True, help='the PROJECT name')
    parser_drc_pdc2l.add_argument(
            '-c', '--cellname', required=True, help='the CELL name')
    parser_drc_pdc2l.add_argument(
            '-s', '--server', default=None, help='the (linux) Calibre server' +
            r' (default: defined in T:\LayoutToolbox\settings\user.ini)')
    parser_drc_pdc2l.add_argument(
            '-u', '--username', default=None, help='your username on the ' +
            '(linux) Calibre server (default: defined in ' +
            r'T:\LayoutToolbox\settings\user.ini)')

    parser_drc_pcd = subparsers.add_parser(
            'prep_cal_drc', help='prepare Cal1 helper command files')
    parser_drc_pcd.add_argument(
            '-p', '--project', required=True, help='the PROJECT name')
    parser_drc_pcd.add_argument(
            '-c', '--cellname', required=True, help='the CELL name')
    parser_drc_pcd.add_argument(
            '-s', '--server', default=None, help='the (linux) Calibre server' +
            r' (default: defined in T:\LayoutToolbox\settings\user.ini)')
    parser_drc_pcd.add_argument(
            '-u', '--username', default=None, help='your username on the ' +
            '(linux) Calibre server (default: defined in ' +
            r'T:\LayoutToolbox\settings\user.ini)')

    parser_drc_seq = subparsers.add_parser(
            'drc_sequence', help='assumes project folder exists and runs the '
            'whole sequence to do DRC on a given project and cellname ' +
            'with several options')
    parser_drc_seq.add_argument(
            '-p', '--project', required=True, help='the PROJECT name')
    parser_drc_seq.add_argument(
            '-c', '--cellname', required=True, help='the CELL name')
    parser_drc_seq.add_argument(
            '-s', '--server', default=None, help='the (linux) Calibre server' +
            r' (default: defined in T:\LayoutToolbox\settings\user.ini)')
    parser_drc_seq.add_argument(
            '-u', '--username', default=None, help='your username on the ' +
            '(linux) Calibre server (default: defined in ' +
            r'T:\LayoutToolbox\settings\user.ini)')
    parser_drc_seq.add_argument(
            '-r', '--rulefile', default=None, help='DRC rule file (default: ' +
            'defined by DRCrulefile in ' +
            r'S:\technologies\setup\projects\projects.ini) special cases: ' +
            '**TOP** ==> defined by DRCTOPrulefile in porjects.ini.  ' +
            '**ant** ==> defined by ANTrulefile in projects.ini.  ' +
            '**stitch** ==> defined by DRCstitchrulefile in porjects.ini.')

    parser_drc_spl = subparsers.add_parser(
            'drc_split_result', help='splits the drc results in the result ' +
            'file into smaller groups for browsing in L-Edit')
    parser_drc_spl.add_argument(
            '-p', '--project', required=True, help='the PROJECT name')
    parser_drc_spl.add_argument(
            '-c', '--cellname', required=True, help='the CELL name')
    parser_drc_spl.add_argument(
            '-f', '--filename', default=None,
            help=('the drc.result file name, default: the drc report of the ' +
                  r'cell in the drc result file location'))
    parser_drc_spl.add_argument(
            '-x', '--maxerr', required=True, type=int, 
            help='Max error count per rule')

def argparse_eval(args):
    # make a dict of args
    dictargs = vars(args)
    funcdict = {'drc2csv': (drc2csv,
                            [dictargs.get('project'),
                             dictargs.get('cellname'),
                             dictargs.get('filename'),
                             dictargs.get('outfile')]),
                'prepare_drc_dir': (LTBfunctions.prepare_drc_dir,
                                    [dictargs.get('project'),
                                     dictargs.get('cellname')]),
                'prepare_drc_dir_server': (prepare_drc_dir_server,
                                           [dictargs.get('project'),
                                            dictargs.get('cellname'),
                                            dictargs.get('server'),
                                            dictargs.get('username')]),
                'prepare_drc_ctrlfile': (prepare_drc_ctrlfile,
                                         [dictargs.get('project'),
                                          dictargs.get('cellname'),
                                          dictargs.get('rulefile'),
                                          dictargs.get('username')]),
                'prepare_drc_copy2linux': (prepare_drc_copy2linux,
                                           [dictargs.get('project'),
                                            dictargs.get('cellname'),
                                            dictargs.get('server'),
                                            dictargs.get('username')]),
                'prep_cal_drc': (prep_cal_drc,
                                 [dictargs.get('project'),
                                  dictargs.get('cellname'),
                                  dictargs.get('server'),
                                  dictargs.get('username')]),
                'drc_sequence': (drc_sequence,
                                 [dictargs.get('project'),
                                  dictargs.get('cellname'),
                                  dictargs.get('server'),
                                  dictargs.get('username'),
                                  dictargs.get('rulefile')]),
                'drc_split_result': (drc_split_result,
                                 [dictargs.get('project'),
                                  dictargs.get('cellname'),
                                  dictargs.get('filename'),
                                  dictargs.get('maxerr')])
                }
    return funcdict


if __name__ == "__main__":
    general.logsetup()
    general.myargparse(argparse_setup, argparse_eval, 'v20241003')
