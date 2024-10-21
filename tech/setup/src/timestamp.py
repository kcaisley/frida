#!/usr/bin/env python

from __future__ import print_function
import os
import time
import shutil
import re
import general

import logging


def now():
    ts = time.strftime("_%Y%m%d_%H%M", time.localtime())
    return ts


def filemod(filename):
    ts = time.strftime(
        "_%Y%m%d_%H%M", time.localtime(os.path.getmtime(filename)))
    return ts


def foldermod(folder):
    maxts = filemod(folder)
    for (root, dirs, files) in os.walk(folder):
        for file in files:
            maxts = max(maxts, filemod(root + '\\' + file))

    return maxts


def make(keep, files):
    bufiles = []
    for filename in files:
        if not (os.path.isfile(filename) or os.path.isdir(filename)):
            logging.info('This is not a filename or directory, no timestamp created: ' + filename)
            print('This is not a filename  or directory, no timestamp created: ' + filename)
            bufiles.append('? ' + filename)
            continue
        if os.path.isdir(filename):
            isfile = False
            ans = input(filename + ' is a folder, continue? Y/[N] : ')
            if ans not in ['y', 'Y']:
                continue
        else:
            isfile = True

        if isfile:
            ts = filemod(filename)
        else:
            ts = foldermod(filename)

        (fn_core, fn_ext) = os.path.splitext(filename)
        fn_core += ts
        bufilename = ''.join((fn_core, fn_ext))
        if not os.path.isfile(bufilename):
            os.rename(filename, bufilename)
        else:
            n = 1
            bufilename = ''.join((fn_core+'_'+str(n), fn_ext))
            while os.path.isfile(bufilename):
                n += 1
                bufilename = ''.join((fn_core+'_'+str(n), fn_ext))
            os.rename(filename, bufilename)

        if keep:
            # copy back
            if isfile:
                shutil.copy2(bufilename, filename)
            else:
                shutil.copytree(bufilename, filename)
            print('+ ', end='')
        else:
            print('- ', end='')
        print(bufilename)
        bufiles.append(bufilename)
    return bufiles


def erase(keep, overwrite, files):
    for filename in files:
        (fn_core, fn_ext) = os.path.splitext(filename)
        pattern = r"(.*)_\d{8}_\d{4}(?:_\d+)?$"
        if not (os.path.isfile(filename) or os.path.isfile(filename)
                and re.search(pattern, fn_core)):
            logging.info("This is not a filename or doesn't have a timestamp " +
                         "format in its name, no timestamp removed: " + filename)
            print("This is not a filename or doesn't have a timestamp format " +
                  "in its name, no timestamp removed: " + filename)
            continue
        if os.path.isdir(filename):
            isfile = False
            ans = input(filename + ' is a folder, continue? Y/[N] : ')
            if ans not in ['y', 'Y']:
                continue
        else:
            isfile = True

        origfn_core = re.sub(pattern, r'\g<1>', fn_core)
        origfilename = ''.join((origfn_core, fn_ext))
        if os.path.isfile(origfilename):
            if overwrite:
                os.remove(origfilename)
            else:
                make(False, [origfilename])
        os.rename(filename, origfilename)

        if keep:
            if isfile:
                shutil.copy2(origfilename, filename)
            else:
                shutil.copytree(origfilename, filename)
            print('+ ', end='')
        else:
            print('- ', end='')
        print(origfilename)


def argparse_setup(subparsers):
    parser_ts_mk = subparsers.add_parser(
            'make', help='make backup file with timestamp in filename')
    parser_ts_mk.add_argument('-k', '--keep', required=False, default=False, 
                              action='store_true', help='keep the original file')
    parser_ts_mk.add_argument(
            '-f', '--files', required=True, nargs=general.argparse.REMAINDER,
            help='make backup of these files')

    parser_ts_ers = subparsers.add_parser(
            'erase', help='erase timestamp from backup file')
    parser_ts_ers.add_argument('-keep', '--keep', required=False, default=False, 
                               action='store_true', help='keep the timestamp file')
    parser_ts_ers.add_argument('-o', '--overwrite', required=False, default=False, 
                               action='store_true',
                               help='overwrite potentially existing non-stamped file')
    parser_ts_ers.add_argument(
            '-f', '--files', required=True, nargs=general.argparse.REMAINDER,
            help='erase timestamp of these files')


def argparse_eval(args):
    # make a dict of args
    dictargs = vars(args)
    funcdict = {'make': (make,
                         [dictargs.get('keep'),
                          dictargs.get('files'), ]),
                'erase': (erase,
                          [dictargs.get('keep'),
                           dictargs.get('overwrite'),
                           dictargs.get('files'), ]),
                }
    return funcdict


if __name__ == "__main__":
    general.logsetup()
    general.myargparse(argparse_setup, argparse_eval, 'v20240320')
