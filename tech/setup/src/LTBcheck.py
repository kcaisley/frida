# -*- coding: utf-8 -*-
"""
Created on Thu Mar  8 09:23:54 2018

@author: Koen
"""
import sys
import time
import logging      # in case you want to add extra logging
import general
import settings
import LTBsettings

USERset = settings.USERsettings()


def check_cal_server():
    global USERset

    commentifnotok = ''
    # This is no longer a showstopper, in case you are using a default
    # username (Win-Linux)
    # if not pathlib.Path(LTBsettings.usersettings()).exists():
    #     commentifnotok += ('FAIL: User settings not found...\n' +
    #                        'Calibre server check aborted.\n')
    #     return commentifnotok
    # else:
    #     commentifnotok += '> User settings file found.\n'

    USERset.load()
    simserver = USERset.get_str('simserver')
    linuxusername = USERset.get_str('linuxusername')
    caelestefolder = USERset.get_str('caelestefolder')

    if '' in [simserver, linuxusername, caelestefolder]:
        commentifnotok += ('FAIL: One or more settings not defined in ' +
                           LTBsettings.usersettings() + '\n')
        if '' in [simserver, linuxusername]:
            commentifnotok += '    Calibre server check aborted.\n'
            return commentifnotok
    else:
        commentifnotok += '> User settings content found.\n'

    commentifnotok += '  > simserver: ' + str(simserver) + '\n'
    commentifnotok += '  > linuxusername: ' + str(linuxusername) + '\n'

    try:
        retval = general.check_linux_plink(simserver, linuxusername)
    except:
        commentifnotok += 'FAIL: ' + str(sys.exc_info()[1]) + '\n'
        return commentifnotok

    if retval in ['', '-no-antispoof']:
        return ''


def check_project(projectname):
    PROJset = settings.PROJECTsettings(projectname)

    commentifnotok = ''

    if PROJset.isempty_alldefaults():
        commentifnotok += ('   Warning: No default project settings, project' +
                           ' name not existing or very incomplete in:\n')
        commentifnotok += ('            ' +
                           LTBsettings.defaultprojectsettings() + '\n')
        commentifnotok += ('            Check also: ' +
                           LTBsettings.projectsexcelfile() + '\n')

    try:
        PROJset.load()
    except Exception:
        loadcheck = PROJset.loadcheck()
        if loadcheck == 0:
            pass
        elif loadcheck == -1:
            commentifnotok += ('   FAIL: Project name (' + projectname +
                               ') does not match project name in settings ' +
                               'file: ' + LTBsettings.projectsettings() + '\n')
            commentifnotok += ('         Replace with project.ini file of ' +
                               'the correct project or just delete it to ' +
                               'use default project settings.\n')
        elif loadcheck == -2:
            commentifnotok += '   FAIL: Project settings are empty.\n'

    if PROJset.isnondefault_anyvalue():
        commentifnotok += ('   Warning: Actual values are not the default ' +
                           'project settings.\n')
        commentifnotok += ('          - check :' +
                           LTBsettings.projectsettings() + '\n')
        commentifnotok += ('            vs.   :' +
                           LTBsettings.defaultprojectsettings() + '\n')

        if PROJset.isempty_anyvalue_for_nonempty_default():
            commentifnotok += ('      Also: At least 1 actual value is empty' +
                               ' for a non-empty default project settings.\n')
    return commentifnotok


def check_ltb(checkall, calserver, ledit, project):
    if checkall or calserver or ledit or project != '':
        success = True
        if checkall or calserver:
            print('Check Calibre server ...')
            commentifnotok = check_cal_server()
            if commentifnotok == '':
                print('   Ok')
                success &= True
            else:
                print('   FAIL!')
                print(commentifnotok)
                logging.warning(commentifnotok)
                success &= False
        if checkall or ledit:
            print('Check L-Edit ...')
            print('   Not implemented yet')
        if project != '':
            print('Check Project-specific issues ...')
            commentifnotok = check_project(project)
            if commentifnotok == '':
                print('   Ok')
                success &= True
            else:
                print(commentifnotok)
                logging.warning(commentifnotok)
                success &= False
        if success:
            time.sleep(2)
        else:
            time.sleep(10)
    else:
        print('Nothing checked')


def argparse_setup(subparsers):
    parser_ltb_chk = subparsers.add_parser(
            'check_ltb', help='check LTB for known (installation) issues')
    parser_ltb_chk.add_argument(
            '-a', '--all', default=False, action='store_true',
            help='check as much as I can')
    parser_ltb_chk.add_argument(
            '-c', '--calserver', default=False, action='store_true',
            help='check Calibre server')
    parser_ltb_chk.add_argument(
            '-l', '--ledit', default=False, action='store_true',
            help='check L-Edit tool')
    parser_ltb_chk.add_argument(
            '-p', '--project', required=False, default='',
            help='check project-specific on this project name')


def argparse_eval(args):
    # make a dict of args
    dictargs = vars(args)
    funcdict = {'check_ltb': (check_ltb,
                              [dictargs.get('all'),
                               dictargs.get('calserver'),
                               dictargs.get('ledit'),
                               dictargs.get('project')])
                }
    return funcdict


if __name__ == "__main__":
    general.logsetup()
    general.myargparse(argparse_setup, argparse_eval, 'v20230926')
