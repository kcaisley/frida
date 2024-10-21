#!/usr/bin/env python

"""investigate.py: helper functions to quickly analyze licenses for LTB"""

from __future__ import print_function
import os
import time
import subprocess
# import logging      # in case you want to add extra logging
import general
import settings
import msvcrt
import sys

USERset = settings.USERsettings()


class TimeoutExpired(Exception):
    pass


def gridcheck(project=None, projectsdrive=None, outfile=None):
    global USERset
    USERset.load()
    sep = USERset.get_type('CSVseparator')
    CSVheader = USERset.get_type('CSVheadersep')

    if projectsdrive is None:
        projectsdrive = 'N'
    projectsdrive += ':\\'
    tic = time.time()

    if project is not None:
        startdrive = os.path.join(projectsdrive, 'projects', project)
    else:
        startdrive = os.path.join(projectsdrive, 'projects')
    if outfile is None:
        outfile = r'T:\schematicGrids_tcl_analysis.csv'

    if CSVheader:
        txt = sep.join(['sep=', '\n'])
    else:
        txt = ''

    txt += analyze_settings(None)
    print(analyze_settings(None))
    try:
        for root, dirs, files in os.walk(startdrive, 'projects'):
            if root.endswith('technology'):
                if 'SchematicGrids.tcl' in files:
                    #grid_compliant(os.path.join(root, 'SchematicGrids.tcl'))
                    txt += analyze_settings(os.path.join(root, 'SchematicGrids.tcl'))
                    print(analyze_settings(os.path.join(root, 'SchematicGrids.tcl')))

                else:
                    print('-')
        toc = time.time()
        general.write(outfile, txt, True)
    except KeyboardInterrupt:
        general.write(outfile, txt, True)
        raise

    print('elapsed time: '+ str(toc-tic) + ' seconds')


def grid_compliant(path):
    global USERset
    USERset.load()
    sep = USERset.get_type('CSVseparator')

    with open(path, 'r') as fp:
        text = fp.read()
        # if text != 'setup schematicgrid set -units iu -majorgridsize 512 -majorgridstyle dots -majorgriddisplayed true -minorgridsize 32 -minorgridstyle dots -minorgriddisplayed true -snapgridsize 32 -portinstancesize 8 -snapcursor true ':
        #     print('X ' + str(text) + '(' + path + ')')
        # else:
        #     print('V ' + str(text) + '(' + path + ')')

        if ('-majorgridsize 512' not in text) or ('-minorgridsize 32' not in text):
            print('X' + sep + str(text) + sep + path)
        else:
            print('V' + sep + str(text) + sep + path)


def analyze_settings(path):
    global USERset
    USERset.load()
    sep = USERset.get_type('CSVseparator')

    fields = ['units', 'majorgridsize', 'majorgridstyle', 'majorgriddisplayed',
              'minorgridsize', 'minorgridstyle', 'minorgriddisplayed',
              'snapgridsize', 'portinstancesize', 'snapcursor']
    ret = ''
    if path is None:
        for field in fields:
            ret += "'-" + field + sep
        ret += 'path'
    else:
        with open(path, 'r') as fp:
            text = fp.read()
            for field in fields:
                index = text.find('-' + field)
                start = text.find(' ',index)
                end = text.find(' ',start+1)
                ret += text[start+1:end] + sep
            ret += path

    return ret + '\n'


def argparse_setup(subparsers):
    parser_lic_inv = subparsers.add_parser(
            'gridcheck', help='check grid settings over all projects')
    parser_lic_inv.add_argument('-p', '--project', required=False,
                                default=None, help='project name ' +
                                '(default: None (=all))')
    parser_lic_inv.add_argument('-d', '--projectsdrive', required=False,
                                default=None, help='projects disk drive ' +
                                '(default: N)')


def argparse_eval(args):
    # make a dict of args
    dictargs = vars(args)
    funcdict = {'gridcheck': (gridcheck,
                              [dictargs.get('project'),
                               dictargs.get('projectsdrive')])
                }
    return funcdict


if __name__ == "__main__":
    general.logsetup()
    general.myargparse(argparse_setup, argparse_eval, 'v20230807', ['daily_check'])
