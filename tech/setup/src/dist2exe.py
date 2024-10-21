import os
import time
import shutil
import logging      # in case you want to add extra logging
import general


def move1(distfolder, outfolder, prg, backup):
    # first find the executable in the dist folder
    pathlist = []
    # as a file
    distfilepath = distfolder+prg+'.exe'
    outfilepath = outfolder+prg+'.exe'
    backupfilepath = outfolder+'backup\\'+prg+'.exe'
    pathlist.append((distfilepath, outfilepath, backupfilepath))
    # as a folder
    distfilepath = distfolder+prg
    outfilepath = outfolder+prg
    backupfilepath = outfolder+'backup\\'+prg
    pathlist.append((distfilepath, outfilepath, backupfilepath))

    for distfilepath, outfilepath, backupfilepath in pathlist:
        if os.path.exists(distfilepath):
            if os.path.exists(outfilepath):
                if backup:
                    mtime = time.localtime(os.path.getmtime(outfilepath))
                    suffix = '_{:4}{:02}{:02}'.format(
                            mtime.tm_year, mtime.tm_mon, mtime.tm_mday)
                    if os.path.exists(backupfilepath + suffix):
                        suffix = '_{:4}{:02}{:02}_{:02}{:02}{:02}'.format(
                                mtime.tm_year, mtime.tm_mon, mtime.tm_mday,
                                mtime.tm_hour, mtime.tm_min, mtime.tm_sec)
                    general.prepare_dir_for(backupfilepath + suffix)
                    shutil.move(outfilepath, backupfilepath + suffix)
                    print(outfilepath + ' --> ' + backupfilepath + suffix)
                else:
                    os.remove(outfilepath)
                    print(outfilepath + '   X ')
            else:
                general.prepare_dir_for(outfilepath)
            shutil.move(distfilepath, outfilepath)
            print(outfilepath + '  ok ')


def move(distfolder, outfolder, prglist, backup):
    for prg in prglist:
        move1(distfolder, outfolder, prg, backup)


def updateversion(folder):
    pyfiles = [os.path.join(folder, f) for f in os.listdir(folder) if
               f[-3:] == '.py' and os.path.isfile(os.path.join(folder, f))]
    now = time.strftime('%Y%m%d')
    # string split in order to not capture this itself
    findstring = "general.myargparse(argparse_setup, " + "argparse_eval, 'v"
    changedfiles = []
    for pyfile in pyfiles:
        # print(pyfile + ': ' + time.ctime(os.path.getmtime(pyfile)))
        # print(pyfile + ': ' +
        #       time.strftime('%Y%m%d', time.gmtime(os.path.getmtime(pyfile))))
        mod = time.strftime('%Y%m%d', time.gmtime(os.path.getmtime(pyfile)))
        with open(pyfile, 'r') as pyf:
            source = pyf.read()

        pos = source.find(findstring)
        if pos == -1:
            declared = '0'
        else:
            declared = source[pos+52:pos+60]
        logging.debug(pyfile + ' - modified: ' + mod + ' - declared: ' +
                      declared + ' (fileposition: ' + str(pos) + '/' +
                      str(len(source)) + ') ' + '63 =?= ' +
                      str(len(source) - pos))
        if pos != -1 and declared != mod:
            if len(source) - pos == 63:
                changedfiles.append(pyfile)
                logging.info('updated version string: ' + pyfile)
                updated = source[:pos+52] + now + source[pos+60:]
                general.write(pyfile, updated, False)
            else:
                logging.warning(pyfile + ' has not exactly the expected end')


def clear(folder):
    if os.path.exists(folder):
        shutil.rmtree(folder)


def argparse_setup(subparsers):
    parser_d2e_move = subparsers.add_parser(
            'move', help=("Moves programs (either '-onefile' executables or " +
                          "folder packages) from the distfolder to the " +
                          "output folder."))
    parser_d2e_move.add_argument('-p', '--programs', nargs='+', required=True,
                                 help='the program names (space separated)')
    parser_d2e_move.add_argument('-d', '--distfolder', required=False,
                                 default='X:\\Python\\dist\\',
                                 help=('location of the distribution files ' +
                                       '(default: X:\\Python\\dist\\)'))
    parser_d2e_move.add_argument('-o', '--outfolder', required=False,
                                 default='X:\\executables\\',
                                 help=('location of the output files ' +
                                       '(default: X:\\executables\\)'))
    parser_d2e_move.add_argument(
            '-nobu', '--nobackup', dest='backup', default=True,
            action='store_false',
            help=('A backup file/folder is automatically created if the ' +
                  'output file/folder already exists, except when the ' +
                  '[--nobackup] is flagged'))

    parser_d2e_udv = subparsers.add_parser(
            'updateversion', help=("Updates all version strings in source py" +
                                   "-files to their latest change date."))
    parser_d2e_udv.add_argument('-f', '--folder', default='X:\\python\\',
                                help='the source code folder')

    parser_d2e_clr = subparsers.add_parser(
            'clear', help=("clears build directory.  Recommended before " +
                           "making exe's as some hickups were discovered " +
                           "when this practice was not in place."))
    parser_d2e_clr.add_argument('-f', '--folder', default='X:\\python\\build',
                                help='the build folder')


def argparse_eval(args):
    # make a dict of args
    dictargs = vars(args)
    funcdict = {'move': (move,
                         [dictargs.get('distfolder'),
                          dictargs.get('outfolder'),
                          dictargs.get('programs'),
                          dictargs.get('backup')]),
                'updateversion': (updateversion,
                                  [dictargs.get('folder')]),
                'clear': (clear,
                          [dictargs.get('folder')])
                }
    return funcdict


if __name__ == "__main__":
    general.logsetup()
    general.myargparse(argparse_setup, argparse_eval, 'v20221005')
