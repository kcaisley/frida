# import sys
# import re
import time
# # issues with export order...

import general
import settings
import LTBsettings
import LTBfunctions


USERset = settings.USERsettings()
PROJset = settings.PROJECTsettings()


def prepare_yld_dir_server(project, cellname, simserver=None, linuxusername=None):
    global USERset
    USERset.load()
    if simserver is None:
        simserver = USERset.get_str('simserver')
    if linuxusername is None:
        linuxusername = USERset.get_str('linuxusername')

    general.check_linux_samba(simserver, linuxusername)

    sambayldpaths = LTBsettings.sambayldpaths(project, cellname, simserver,
                                              linuxusername)
    general.prepare_dirs(sambayldpaths)


def prepare_yld_ctrlfile(project, cellname, YLDrulefile=None, layers='all',
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
    if YLDrulefile is None:
        if PROJset.get_type('YLDrulefile') is None:
            raise settings.SettingsError('YLDrulefile not defined in project.ini')
        YLDrulefile = PROJset.get_str('YLDrulefile')

    ctrlfilename = LTBsettings.yldctrlfilepath(project, cellname) + cellname + '.YLDctrl'

    alllayers = []
    if YLDrulefile.find('[') > 0 and YLDrulefile.find(']') > 0:
        assert YLDrulefile.find('[') < YLDrulefile.find(']')
        stralllayers = (
                YLDrulefile[YLDrulefile.find('[')+1:YLDrulefile.find(']')])
        alllayers = stralllayers.split(',')

    if layers == 'all':
        layers = alllayers
    else:
        layers = layers.split(',')

    header = '''//
//  Rule file generated on ''' + time.asctime() + r'''
//     by yld.py\prepare_yld_ctrlfile
//
//      *** PLEASE DO NOT MODIFY THIS FILE ***
//      *** unless you know what you're doing ***
//      *** preferably ask for a feature request ***
//
//

'''
    layout = ('LAYOUT PATH  "' +
              LTBsettings.linuxyldgdsfilepath(project, cellname, linuxusername) +
              cellname + '.gds"\n')
    layout += 'LAYOUT PRIMARY "' + cellname + '"\n'
    layout += 'LAYOUT WINDOW CLIP YES\n'
    layout += 'LAYOUT SYSTEM GDSII\n\n'

    options = '''
VIRTUAL CONNECT COLON NO
VIRTUAL CONNECT REPORT NO

DRC ICSTATION YES

'''
    if len(alllayers) == 0:
        results = ('DRC RESULTS DATABASE "' +
                   LTBsettings.linuxyldresultfilepath(project, cellname, linuxusername) +
                   cellname + '.yld.results" ASCII \n')
        results += 'DRC MAXIMUM RESULTS ALL\n'
        results += 'DRC MAXIMUM VERTEX ALL\n\n'
        results += 'DRC CELL NAME NO\n'
        results += ('DRC SUMMARY REPORT "' +
                    LTBsettings.linuxyldresultfilepath(project, cellname,
                                                       linuxusername) +
                    cellname + '.yld.summary" REPLACE HIER\n\n')
        rulefile = 'INCLUDE "' + YLDrulefile + '"\n\n'
        with open(ctrlfilename, 'w') as ctrlfile:
            ctrlfile.write(header)
            ctrlfile.write(layout)
            ctrlfile.write(results)
            ctrlfile.write(options)
            ctrlfile.write(rulefile)
    else:
        for layer in layers:
            assert layer in alllayers
            layerctrlfilename = ctrlfilename + '_' + layer
            layerYLDrulefile = (YLDrulefile[:YLDrulefile.find('[')] + layer +
                                YLDrulefile[YLDrulefile.find(']')+1:])
            results = ('DRC RESULTS DATABASE "' +
                       LTBsettings.linuxyldresultfilepath(project, cellname,
                                                          linuxusername) +
                       cellname + '.yld.results_' + layer + '" ASCII \n')
            results += 'DRC MAXIMUM RESULTS ALL\n'
            results += 'DRC MAXIMUM VERTEX ALL\n\n'
            results += 'DRC CELL NAME NO\n'
            results += ('DRC SUMMARY REPORT "' +
                        LTBsettings.linuxyldresultfilepath(project, cellname,
                                                           linuxusername) +
                        cellname + '.yld.summary_' + layer +
                        '" REPLACE HIER\n\n')

            rulefile = 'INCLUDE "' + layerYLDrulefile + '"\n\n'
            with open(layerctrlfilename, 'w') as ctrlfile:
                ctrlfile.write(header)
                ctrlfile.write(layout)
                ctrlfile.write(results)
                ctrlfile.write(options)
                ctrlfile.write(rulefile)


def prepare_yld_copy2linux(project, cellname, layers='all', YLDrulefile=None,
                           simserver=None, linuxusername=None):
    import shutil
    global USERset
    USERset.load()

    if simserver is None:
        simserver = USERset.get_str('simserver')
    if linuxusername is None:
        linuxusername = USERset.get_str('linuxusername')
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

    if YLDrulefile is None:
        if PROJset.get_type('YLDrulefile') is None:
            raise settings.SettingsError('YLDrulefile not defined in project.ini')
        YLDrulefile = PROJset.get_str('YLDrulefile')

    alllayers = []
    if YLDrulefile.find('[') > 0 and YLDrulefile.find(']') > 0:
        assert YLDrulefile.find('[') < YLDrulefile.find(']')
        stralllayers = (
                YLDrulefile[YLDrulefile.find('[')+1: YLDrulefile.find(']')])
        alllayers = stralllayers.split(',')

    if layers == 'all':
        layers = alllayers
    else:
        layers = layers.split(',')

    general.check_linux_samba(simserver, linuxusername)

    src = LTBsettings.yldgdsfilepath(project, cellname) + cellname + '.gds'
    dst = LTBsettings.linux2samba(
            LTBsettings.linuxyldgdsfilepath(project, cellname, linuxusername),
            simserver) + cellname + '.gds'
    shutil.copy2(src, dst)

    if len(alllayers) == 0:
        src = LTBsettings.yldctrlfilepath(project, cellname) + cellname + '.YLDctrl'
        dst = LTBsettings.linux2samba(
                LTBsettings.linuxyldctrlfilepath(project, cellname, linuxusername),
                simserver) + cellname + '.YLDctrl'
        shutil.copy2(src, dst)
    else:
        for layer in layers:
            assert layer in alllayers
            src = (LTBsettings.yldctrlfilepath(project, cellname) + cellname +
                   '.YLDctrl_' + layer)
            dst = LTBsettings.linux2samba(
                    LTBsettings.linuxyldctrlfilepath(project, cellname, linuxusername),
                    simserver) + cellname + '.YLDctrl_' + layer
            shutil.copy2(src, dst)


def cal_yld(project, cellname, RunPrep, layers='all', YLDrulefile=None,
            background=True, simserver=None, linuxusername=None):
    import subprocess
    global USERset
    USERset.load()

    if simserver is None:
        simserver = USERset.get_str('simserver')
    if linuxusername is None:
        linuxusername = USERset.get_str('linuxusername')
    no_antispoof = general.check_linux_plink(simserver, linuxusername)

    if RunPrep == 'run':
        calcommand = ('-v yld -p ' + project + ' -c '+ cellname +
                      ' calibre -drc ' +
                      LTBsettings.linuxyldctrlfilepath(project, cellname,
                                                       linuxusername) +
                      cellname + '.YLDctrl')
    elif RunPrep == 'prepare':
        calcommand = ('-v yld -p ' + project + ' -c '+ cellname +
                      ' calibre -drc -hier ' +
                      LTBsettings.linuxyldctrlfilepath(project, cellname,
                                                       linuxusername) +
                      cellname + '.YLDctrl')
    else:
        Exception('Unknown RunPrep command')

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

    if YLDrulefile is None:
        if PROJset.get_type('YLDrulefile') is None:
            raise settings.SettingsError('YLDrulefile not defined in project.ini')
        YLDrulefile = PROJset.get_str('YLDrulefile')

    alllayers = []
    if YLDrulefile.find('[') > 0 and YLDrulefile.find(']') > 0:
        assert YLDrulefile.find('[') < YLDrulefile.find(']')
        stralllayers = (
                YLDrulefile[YLDrulefile.find('[')+1: YLDrulefile.find(']')])
        alllayers = stralllayers.split(',')

    if layers == 'all':
        layers = ','.join(alllayers)

    if background:
        # nohup didn't work as intended, the calibre_bg.py has to be copied to
        # the user's /bin folder
        # nohup allows programs to continue in background if putty were closed
        # calcommand = 'nohup ' + calcommand
        # calibre_bg.py forks a process and actively ends the initial process
        # THAT LAST STATEMENT SEEMS NOT BE WORKING PROPERLY ON ALL MACHINES,
        # arrange tmp fix
        calcommand = ('python /home/' + linuxusername + '/bin/calibre_bg.py ' +
                      RunPrep + ' -l ' + layers + ' ' + calcommand)

        plinkcommand = ['plink', '-ssh', linuxusername + '@' + simserver,
                        no_antispoof, calcommand]

        print(plinkcommand)
        # tmp fix
        print('\nStop this window from blocking your progress in L-Edit: ' +
              'Press [Ctrl]+[C] 2x')
        print('Your verification will continue runnning on the Linux machine.')
        p = subprocess.Popen(plinkcommand, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        (output, error) = p.communicate()
        if error != '':
            Exception(error)
    else:
        for layer in layers.split(','):
            laycalcommand = calcommand + '_' + layer

            plinkcommand = ['plink', '-ssh', linuxusername + '@' + simserver,
                            no_antispoof, laycalcommand]

            print(plinkcommand)
            # tmp fix
            print('\nStop this window from blocking your progress in L-Edit:' +
                  ' Press [Ctrl]+[C] 2x')
            print('Your verification will continue runnning on the Linux ' +
                  'machine.')
            p = subprocess.Popen(plinkcommand, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE)
            (output, error) = p.communicate()
            if error != '':
                Exception(error)


def prep_cal_yld(project, cellname, layers=None, rulefile=None,
                 background=True, simserver=None, linuxusername=None):
    cal_yld(project, cellname, 'prepare', layers, rulefile, background=True,
            simserver=None, linuxusername=None)


def run_cal_yld(project, cellname, layers=None, rulefile=None,
                background=True, simserver=None, linuxusername=None):
    cal_yld(project, cellname, 'run', layers, rulefile, background=True,
            simserver=None, linuxusername=None)


def argparse_setup(subparsers):
    parser_yld_pyd = subparsers.add_parser(
            'prepare_yld_dir', help='prepare all folders for YLD for a ' +
            'given project')
    parser_yld_pyd.add_argument(
            '-p', '--project', required=True, help='the PROJECT name')
    parser_yld_pyd.add_argument(
            '-c', '--cellname', required=True, help='the CELL name')

    parser_yld_pyds = subparsers.add_parser(
            'prepare_yld_dir_server', help='prepare all folders for YLD for ' +
            'a given project on the Calibre server')
    parser_yld_pyds.add_argument(
            '-p', '--project', required=True, help='the PROJECT name')
    parser_yld_pyds.add_argument(
            '-c', '--cellname', required=True, help='the CELL name')
    parser_yld_pyds.add_argument(
            '-s', '--server', default=None, help='the (linux) Calibre server' +
            r' (default: defined in T:\LayoutToolbox\settings\user.ini)')
    parser_yld_pyds.add_argument(
            '-u', '--username', default=None, help='your username on the ' +
            '(linux) Calibre server (default: defined in ' +
            r'T:\LayoutToolbox\settings\user.ini)')

    parser_yld_pyc = subparsers.add_parser(
            'prepare_yld_ctrlfile', help='prepare YLD control file for a ' +
            'given project and cellname and options')
    parser_yld_pyc.add_argument(
            '-p', '--project', required=True, help='the PROJECT name')
    parser_yld_pyc.add_argument(
            '-c', '--cellname', required=True, help='the CELL name')
    parser_yld_pyc.add_argument(
            '-l', '--layers', default='all',
            help='layers to analyze, seperated by ","')
    parser_yld_pyc.add_argument(
            '-r', '--rulefile', default=None, help='YLD rule file (default: ' +
            'defined by YLDrulefile in ' +
            r'S:\technologies\setup\projects\projects.ini)')
    parser_yld_pyc.add_argument(
            '-u', '--username', default=None, help='your username on the ' +
            '(linux) Calibre server (default: defined in ' +
            r'T:\LayoutToolbox\settings\user.ini)')

    parser_yld_pyc2l = subparsers.add_parser(
            'prepare_yld_copy2linux', help='copy files to linux Calibre ' +
            'server for a given project and cellname')
    parser_yld_pyc2l.add_argument(
            '-p', '--project', required=True, help='the PROJECT name')
    parser_yld_pyc2l.add_argument(
            '-c', '--cellname', required=True, help='the CELL name')
    parser_yld_pyc2l.add_argument(
            '-l', '--layers', default='all',
            help='layers to analyze, seperated by ","')
    parser_yld_pyc2l.add_argument(
            '-r', '--rulefile', default=None, help='YLD rule file (default: ' +
            'defined by YLDrulefile in ' +
            r'S:\technologies\setup\projects\projects.ini)')
    parser_yld_pyc2l.add_argument(
            '-s', '--server', default=None, help='the (linux) Calibre server' +
            r' (default: defined in T:\LayoutToolbox\settings\user.ini)')
    parser_yld_pyc2l.add_argument(
            '-u', '--username', default=None, help='your username on the ' +
            '(linux) Calibre server (default: defined in ' +
            r'T:\LayoutToolbox\settings\user.ini)')

    parser_yld_pcy = subparsers.add_parser(
            'prep_cal_yld', help='prepare Cal1 helper command files')
    parser_yld_pcy.add_argument(
            '-p', '--project', required=True, help='the PROJECT name')
    parser_yld_pcy.add_argument(
            '-c', '--cellname', required=True, help='the CELL name')
    parser_yld_pcy.add_argument(
            '-l', '--layers', default='all',
            help='layers to analyze, seperated by ","')
    parser_yld_pcy.add_argument(
            '-r', '--rulefile', default=None, help='YLD rule file (default: ' +
            'defined by YLDrulefile in ' +
            r'S:\technologies\setup\projects\projects.ini)')
    parser_yld_pcy.add_argument(
            '-s', '--server', default=None, help='the (linux) Calibre ' +
            r'server (default: defined in T:\LayoutToolbox\settings\user.ini)')
    parser_yld_pcy.add_argument(
            '-u', '--username', default=None, help='your username on the ' +
            '(linux) Calibre server (default: defined in ' +
            r'T:\LayoutToolbox\settings\user.ini)')
    parser_yld_pcy.add_argument(
            '-nobg', '--nobackground', dest='background', default=True,
            action='store_false', help='runs not in background')

    parser_yld_rcy = subparsers.add_parser(
            'run_cal_yld', help='copy files to linux Calibre server for a ' +
            'given project and cellname')
    parser_yld_rcy.add_argument(
            '-p', '--project', required=True, help='the PROJECT name')
    parser_yld_rcy.add_argument(
            '-c', '--cellname', required=True, help='the CELL name')
    parser_yld_rcy.add_argument(
            '-l', '--layers', default='all',
            help='layers to analyze, seperated by ","')
    parser_yld_rcy.add_argument(
            '-r', '--rulefile', default=None, help='YLD rule file (default: ' +
            'defined by YLDrulefile in ' +
            r'S:\technologies\setup\projects\projects.ini)')
    parser_yld_rcy.add_argument(
            '-s', '--server', default=None, help='the (linux) Calibre server' +
            r' (default: defined in T:\LayoutToolbox\settings\user.ini)')
    parser_yld_rcy.add_argument(
            '-u', '--username', default=None, help='your username on the ' +
            '(linux) Calibre server (default: defined in ' +
            r'T:\LayoutToolbox\settings\user.ini)')
    parser_yld_rcy.add_argument(
            '-nobg', '--nobackground', dest='background', default=True,
            action='store_false', help='runs not in background')

    return subparsers


def argparse_eval(args):
    # make a dict of args
    dictargs = vars(args)
    funcdict = {'prepare_yld_dir': (LTBfunctions.prepare_yld_dir,
                                    [dictargs.get('project'),
                                     dictargs.get('cellname')]),
                'prepare_yld_dir_server': (prepare_yld_dir_server,
                                           [dictargs.get('project'),
                                            dictargs.get('cellname'),
                                            dictargs.get('server'),
                                            dictargs.get('username')]),
                'prepare_yld_ctrlfile': (prepare_yld_ctrlfile,
                                         [dictargs.get('project'),
                                          dictargs.get('cellname'),
                                          dictargs.get('rulefile'),
                                          dictargs.get('layers'),
                                          dictargs.get('username')]),
                'prepare_yld_copy2linux': (prepare_yld_copy2linux,
                                           [dictargs.get('project'),
                                            dictargs.get('cellname'),
                                            dictargs.get('layers'),
                                            dictargs.get('rulefile'),
                                            dictargs.get('server'),
                                            dictargs.get('username')]),
                'prep_cal_yld': (prep_cal_yld,
                                 [dictargs.get('project'),
                                  dictargs.get('cellname'),
                                  dictargs.get('layers'),
                                  dictargs.get('rulefile'),
                                  dictargs.get('background'),
                                  dictargs.get('server'),
                                  dictargs.get('username')]),
                'run_cal_yld': (run_cal_yld,
                                [dictargs.get('project'),
                                 dictargs.get('cellname'),
                                 dictargs.get('layers'),
                                 dictargs.get('rulefile'),
                                 dictargs.get('background'),
                                 dictargs.get('server'),
                                 dictargs.get('username')])
                }
    return funcdict


if __name__ == "__main__":
    general.logsetup()
    general.myargparse(argparse_setup, argparse_eval, 'v20240925')
