# -*- coding: utf-8 -*-

import filecmp
import os
import shutil
import subprocess
# import logging      # in case you want to add extra logging
import general


def release(src=None, dst=None, svntop=True, dryrun=False):
    if src is None:
        src = r'T:/LTB_for_S/'
    if dst is None:
        dst = r'S:/tools/caeleste_tools/LayoutToolbox/'
    if svntop:
        dc = filecmp.dircmp(src, dst, ['.svn'])
        svnstat = subprocess.run('svn st', cwd=src, stdout=subprocess.PIPE)
        if len(svnstat.stdout) != 0:
            print('src folder not completely in sync with svn revision')
            print('\nsvn st:')
            print(svnstat.stdout.decode())
            cont = input('Continue? Y/[N]')
            if cont not in ['y', 'Y']:
                print('Aborted by User')
                return -1
    else:
        dc = filecmp.dircmp(src, dst)

    for f in dc.right_only:
        if os.path.isdir(dst+f):
            print('del dir: ' + dst + f)
            if not dryrun:
                shutil.rmtree(dst + f)
        elif os.path.isfile(dst+f):
            print('del file: ' + dst + f)
            if not dryrun:
                os.remove(dst + f)
        else:
            print('Right alien: ' + dst + f)

    for f in dc.left_only:
        if os.path.isdir(src+f):
            print('cp dir: ' + src + f)
            if not dryrun:
                shutil.copytree(src + f, dst + f)
        elif os.path.isfile(src+f):
            print('cp file: ' + src + f)
            if not dryrun:
                shutil.copy2(src + f, dst + f)
        else:
            print('Left alien: ' + src + f)

    for cf in dc.common_files:
        # print('  common file: ' + src + cf)
        if not filecmp.cmp(src + cf, dst + cf):
            print('overwrite file: ' + src + cf)
            if not dryrun:
                shutil.copy2(src + cf, dst + cf)
    for cd in dc.common_dirs:
        # print('  common dirs: ' + src + cd)
        release(src + cd + '/', dst + cd + '/', False, dryrun)

    if svntop:
        print('\n\nSVN INFO: ' + src)
        svninfo = subprocess.run('svn info', cwd=src, stdout=subprocess.PIPE)
        revstart = svninfo.stdout.find(b'Revision: ')
        revend = svninfo.stdout.find(b'\r', revstart)
        revnr = svninfo.stdout[revstart+10:revend].decode()
        svnstat = subprocess.run('svn st', cwd=src, stdout=subprocess.PIPE)
        if len(svnstat.stdout) != 0:
            suffix = '_withchanges'
        else:
            suffix = ''
        print(svninfo.stdout.decode())
        print('SVN STATUS (empty after this is very ok)\n----------\n')
        print(svnstat.stdout.decode())
        if not dryrun:
            with open(dst + 'svninfo' + suffix + '.' + revnr, 'bw') as sif:
                sif.write(svninfo.stdout)
                sif.write(b'\r\nSVN STATUS\r\n----------\r\n')
                sif.write(svnstat.stdout)

    return 0


def argparse_setup(subparsers):
    parser_ltb_rls = subparsers.add_parser('release',
                                           help='release all LTB files')
    parser_ltb_rls.add_argument('-s', '--source', required=False,
                                help='the source dir, default: ' +
                                r'T:/LTB_for_S/')
    parser_ltb_rls.add_argument('-d', '--dest', required=False,
                                help='the destination dir, default: ' +
                                r'S:/tools/caeleste_tools/LayoutToolbox/')
    parser_ltb_rls.add_argument('-t', '--svntop', default=False,
                                action='store_true', required=False,
                                help='This is an svn top folder')
    parser_ltb_rls.add_argument('--dryrun', default=False,
                                action='store_true', required=False,
                                help='dry running, no copy, no delete')


def argparse_eval(args):
    # make a dict of args
    dictargs = vars(args)
    funcdict = {'release': (release,
                            [dictargs.get('source'),
                             dictargs.get('dest'),
                             dictargs.get('svntop'),
                             dictargs.get('dryrun')])
                }
    return funcdict


if __name__ == "__main__":
    general.logsetup()
    general.myargparse(argparse_setup, argparse_eval, 'v20221005')
