"""
This tool can be used to mirror files from a source directory to a destination
directory. You can specify one file using `destination` and `source` or define
many files using `source_map` (a csv with source,destination file per line).
"""

import os
import sys
import time
import shutil
import subprocess
import logging      # in case you want to add extra logging
import msvcrt
import general
import LTBsettings
import settings
import lvs
import csv4txt


USERset = settings.USERsettings()


class TimeoutExpired(Exception):
    pass


def input_with_timeout(prompt, timeout, timer=time.monotonic):
    sys.stdout.write(prompt)
    sys.stdout.flush()
    endtime = timer() + timeout
    result = []
    while timer() < endtime:
        if msvcrt.kbhit():
            result.append(msvcrt.getwche()) #XXX can it block on multibyte characters?
            if result[-1] == '\r':
                return ''.join(result[:-1])
        time.sleep(0.04) # just to yield to other processes/threads
    raise TimeoutExpired


def filecopy(file_list):
    for (source, dest) in file_list:
        if os.path.isfile(source):
            print('cp ' + source)
            print('  -> ' + dest)
            shutil.copy2(source, dest)
#            with open(source, 'rb') as fin:
#                with open(dest, 'wb') as fout:
#                    filedata = fin.read()
#                    fout.write(filedata)


def mirrorrun(file_list, justonce=False, timeout=0):
    if timeout == 0:
        print('Press Ctrl+C to terminate')
        print('Trying to copy eternally...')
    else:
        print('Trying to copy for '+str(timeout) + ' seconds...')

    if justonce:
        print('... until all files are copied only once.')
    else:
        print('... all files continuously.')

    start = time.time()

    letsdoitagain = True
    last_checked_map = {}
    success = []
    while letsdoitagain:
        for t in file_list:
            source_folder = os.path.normpath(t[0])
            destination_folder = os.path.normpath(t[1])

            for fileordir in os.listdir(source_folder):
                source_file = source_folder + os.sep + fileordir
                if os.path.isfile(source_file):
                    destination_file = destination_folder + os.sep + fileordir
                    try:
                        stat = os.stat(source_file)
                    except OSError as e:
                        print("Encountered a OSError, skipping file:")
                        print(e)
                        continue
                    last_time = last_checked_map.get(source_file)

                    if not last_time or stat.st_mtime > last_time:
                        filecopy([(source_file, destination_file)])
                        last_checked_map[source_file] = stat.st_mtime
                        print("File %s changed, updated %s" % (
                            source_file, destination_file))
                        success.append(t)

        if justonce:
            for t in success:
                file_list.remove(t)
            success = []

        time.sleep(1)
        if timeout:
            letsdoitagain = time.time() - start < timeout


def mirror(source, destination, source_map):
    if not (source_map or (source and destination)):
        raise ValueError("You must provide either a source_map of files " +
                         "and/or a source and destination file")

    file_list = []

    if source and destination:
        file_list.append((source, destination,))
    # only one True is probably a mistake from above
    elif source or destination:
        raise ValueError("No matching source-destination combo. source: " +
                         str(source) + ", destination: " + str(destination))

    if source_map:
        source_map_file = os.path.normpath(source_map)
        with open(source_map_file, 'r') as f:
            for line in f.readlines():
                file_list.append(tuple(line.strip().split(",")))

    mirrorrun(file_list)


def LTBresult(project=None, cellname=None, veriftype=None, layers=None,
              new=False, timeout=0, simserver=None, linuxusername=None):
    """run mirrorrun to download results as soon as they are available.
    Take care, sometimes files are already there, but not final yet.
      drc: .drc.summary exists and ends with: TOTAL DRC Results Generated:...
      lvs: .lvs.report exists and ends with: Total Elapsed time:...
      to save on traffic (certainly from home): check if finished on server!
    """

    if project is None:
        raise Exception('Not yet implemented')
    if cellname is None:
        raise Exception('Not yet implemented')
    if veriftype not in ['lvs', 'drc', 'xor', 'yld']:
        raise Exception('Not yet implemented')

    global USERset
    USERset.load()

    if simserver is None:
        simserver = USERset.get_str('simserver')
    if linuxusername is None:
        linuxusername = USERset.get_str('linuxusername')

    no_antispoof = general.check_linux_plink(simserver, linuxusername)

    start = time.time()
    letsdoitagain = True
    resultready = False

    if new == 0:
        filenewerthan = ''
    elif new == 1:
        # check date of filecheckmaster (youngest of output files) locally,
        # so that only a newer is awaited for:
        mtime = None
        if veriftype == 'yld':
            for layer in layers.split(','):
                filecheckmaster = cellname + '.yld.report_' + layer
                dest = LTBsettings.yldresultfilepath(project) + filecheckmaster
                if os.path.isfile(dest):
                    if mtime is None:
                        mtime = os.path.getmtime(dest)
                    else:
                        mtime = min(mtime, os.path.getmtime(dest))
        else:
            if veriftype == 'drc':
                filecheckmaster = cellname + '.drc.summary'
                dest = LTBsettings.drcresultfilepath(project, cellname) + filecheckmaster
            elif veriftype == 'xor':
                filecheckmaster = cellname + '.xor.summary'
                dest = LTBsettings.xorresultfilepath(project, cellname) + filecheckmaster
            elif veriftype == 'lvs':
                filecheckmaster = cellname + '.lvs.report'
                dest = LTBsettings.lvsresultfilepath(project, cellname) + filecheckmaster
            if os.path.isfile(dest):
                mtime = os.path.getmtime(dest)
        if mtime is None:
            filenewerthan = ' -t 0'
        else:
            # mtime = 0
            filenewerthan = ' -t ' + str(mtime)
    elif new == 2:
        # previously I expected the cliuent and server time to be pretty much
        # in sync. That is not always the case and ruins the functionality

        # mtime = time.time()

        # So: ask the servertime first
        timecommand = ('python /home/' + linuxusername +
                       '/bin/calibre_status.py servertime')
        plinkcommand = ['plink', '-ssh', linuxusername + '@' + simserver,
                        no_antispoof, timecommand]
        print(str(plinkcommand))
        p = subprocess.run(plinkcommand, stdout=subprocess.PIPE)
        now = p.stdout.decode()
        logging.debug('servertime (now): ' + now)
        filenewerthan = ' -t ' + now
    else:
        raise ValueError('Wrong parameter value for new')

    # sample faster in the beginning, increase *5 after 10 times
    tentimesfast = 10
    startsleeptime = 2
    dfltsleeptime = startsleeptime
    justcount = 0
    for layer in layers.split(','):
        while not resultready:
            justcount += 1
            print(str(justcount))
            if veriftype == 'yld':
                checkcommand = ('python /home/' + linuxusername +
                                '/bin/calibre_status.py finished -p ' +
                                project + ' -v ' + veriftype + ' -c ' +
                                cellname + ' -l ' + layer + filenewerthan)
            else:
                checkcommand = ('python /home/' + linuxusername +
                                '/bin/calibre_status.py finished -p ' +
                                project + ' -v ' + veriftype + ' -c ' +
                                cellname + filenewerthan)
            plinkcommand = ['plink', '-ssh', linuxusername + '@' + simserver,
                            no_antispoof, checkcommand]

            print(str(plinkcommand))
            # subprocess.run vs. subprocess.Popen  =
            # wait for process to end vs. don't wait
            p = subprocess.run(plinkcommand, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
    #        (output, error) = p.communicate()
    #        if len(output) >0:
    #            print(output.decode())
    #        if len(error) >0:
    #            print('ERROR: '+ error.decode())
    #
    #        if error != '':
    #            Exception(error)
            if p.returncode == 0:
                print('Yes!')
                resultready = True
                break
            elif p.returncode == 2:
                print('Not finished')
            elif p.returncode == 3:
                print('Old results exist')
            elif p.returncode == 4:
                print('No results found')
            elif p.returncode == 1:
                # returncode 1 happens during sysexit with an exception
                print('Oh no..')
                logging.warning('Oh no...: ' + p.stdout.decode() + ' | ' +
                                p.stderr.decode())
                raise Exception('unexpected output')
            else:
                print('Oh no no....')
                logging.warning('Oh no no...: ' + p.stdout.decode() + ' | ' +
                                p.stderr.decode())
                raise Exception('unexpected output')

            if dfltsleeptime < 30:
                if tentimesfast > 0:
                    tentimesfast -= 1
                else:
                    tentimesfast = 10
                    dfltsleeptime *= 5

            if timeout > 0:
                # make sure it does the check again 1 second before timeout
                # sleeptime should be at least 1 second
                sleeptime = max(1, min(dfltsleeptime,
                                       time.time() - start + timeout - 1))
            else:
                sleeptime = dfltsleeptime
            print('Z' + 'z' * max(0, int(sleeptime-1)))
            try:
                answer = input_with_timeout("[L] copy log file  [R] reset sleeptime to 2s  [X] exit  ? ", sleeptime)
            except TimeoutExpired:
                print('\nChecking calibre status...')
            else:
                if answer is not None:
                    print('\n')
                    if answer in ('l', 'L'):
                        print('Trying to copy Calibre logfile...')
                        log_filename = 'cal1.log'
                        if veriftype == 'drc':
                            source = LTBsettings.linuxdrccellfilepath(
                                    project, cellname, linuxusername) + log_filename
                            dest = LTBsettings.drccellfilepath(project, cellname) + log_filename
                        elif veriftype == 'yld':
                            pass
                        elif veriftype == 'xor':
                            source = LTBsettings.linuxxorresultfilepath(
                                    project, cellname, linuxusername) + log_filename
                            dest = LTBsettings.xorresultfilepath(project, cellname) + log_filename
                        elif veriftype == 'lvs':
                            source = LTBsettings.linuxlvscellfilepath(
                                    project, cellname, linuxusername) + log_filename
                            dest = LTBsettings.lvsresultfilepath(project, cellname) + log_filename
                        if veriftype != 'yld':
                            sambasource = LTBsettings.linux2samba(source, simserver)
                            file_list = [[sambasource, dest]]
                            filecopy(file_list)
                            print('Should be here: ' + dest)
                    if answer in ('r', 'R'):
                        dfltsleeptime = 2
                        print('dfltsleeptime = ' + repr(dfltsleeptime))
                    if answer in ('x', 'X'):
                        print('Bye bye')
                        return

        if resultready:
            file_list = []

            if veriftype == 'drc':
                files = [cellname + '.drc.results', cellname + '.drc.summary',
                         'cal1.log']
                for file in files:
                    source = LTBsettings.linuxdrccellfilepath(
                            project, cellname, linuxusername) + file
                    # resultready means result ready, we're assuming all files
                    # are checked or that not all have to be checked
                    # if source not in p.stdout.decode():
                    #     raise Exception('File not checked...')
                    sambasource = LTBsettings.linux2samba(source, simserver)
                    dest = LTBsettings.drccellfilepath(project, cellname) + file
                    file_list.append((sambasource, dest,))
            elif veriftype == 'yld':
                files = [cellname + '.yld.results_' + layer,
                         cellname + '.drc.summary_' + layer]
                for file in files:
                    source = LTBsettings.linuxyldresultfilepath(
                            project, linuxusername) + file
                    if source not in p.stdout.decode():
                        raise Exception('File not checked...')
                    sambasource = LTBsettings.linux2samba(source, simserver)
                    dest = LTBsettings.yldresultfilepath(project) + file
                    file_list.append((sambasource, dest,))
            elif veriftype == 'xor':
                files = [cellname + '.xor.results', cellname + '.xor.summary', 
                         cellname + '.xor.gds', 'cal1.cmd', 'cal1.log']
                for file in files:
                    source = LTBsettings.linuxxorresultfilepath(
                            project, cellname, linuxusername) + file
                    # resultready means result ready, we're assuming all files 
                    # are checked or that not all have to be checked
                    # if source not in p.stdout.decode():
                    #     raise Exception('File not checked...')
                    sambasource = LTBsettings.linux2samba(source, simserver)
                    dest = LTBsettings.xorresultfilepath(project, cellname) + file
                    file_list.append((sambasource, dest,))
            elif veriftype == 'lvs':
                files = [cellname + '.lvs.report', cellname + '.lvs.report.ext',
                         'svdb\\' + cellname + '.sp', 'cal1.log']
                for file in files:
                    source = LTBsettings.linuxlvscellfilepath(
                            project, cellname, linuxusername) + file
                    sambasource = LTBsettings.linux2samba(source, simserver)
                    dest = LTBsettings.lvsresultfilepath(project, cellname) + file
                    file_list.append((sambasource, dest,))

            filecopy(file_list)
        else:
            raise Exception('Calibre result not downloaded within timeout')

        if veriftype == 'lvs':
            lvs.result_summary(project, cellname)
            inputcsv = LTBsettings.lvsfilepath(project) + 'lvs_summary.csv'
            outputtxt = LTBsettings.lvsfilepath(project) + 'lvs_summary.txt'
            csv4txt.convert(inputcsv, outputtxt, header=True, reverse=True)


def posnumber(string):
    value = int(string)
    if value < 0:
        msg = "%r is not a numerical integer positive value" % string
        raise general.argparse.ArgumentTypeError(msg)
    return value


def argparse_setup(subparsers):
    parser_mir_run = subparsers.add_parser(
            'mirror', help=('Listen for file changes and mirror changed ' +
                            'files to a second location.'))
    parser_mir_run.add_argument('-s', '--source', help='The source file')
    parser_mir_run.add_argument('-d', '--destination',
                                help='The destination file')
    parser_mir_run.add_argument(
            '-m', '--source_map',
            help=('A CSV file mapping multiple source-destination ' +
                  'combinations.  Each line: [source],[destination]\n'))

    parser_mir_ltb = subparsers.add_parser(
            'LTBresult', help=('Listen for file changes of LTB results and ' +
                               'copy changed files to their default local ' +
                               'folder.'))
    # default parameters of add_argument:
    # default=None, Required=False, action='store', dest=<the obvious name>
    parser_mir_ltb.add_argument('-p', '--project', required=True,
                                help='the PROJECT name')
    parser_mir_ltb.add_argument('-c', '--cellname', help='the CELL name')
    parser_mir_ltb.add_argument(
            '-v', '--vertype', choices=['lvs', 'drc', 'xor', 'yld'],
            help='verification type')
    parser_mir_ltb.add_argument(
            '-l', '--layers', default='all',
            help='layers to analyze, seperated by ","')
    parser_mir_ltb.add_argument(
            '-n', '--new', type=int, choices=[0, 1, 2], default=0,
            help=('wait for a newer file, [0]: not, [1] than local file, ' +
                  '[2] than NOW'))
    parser_mir_ltb.add_argument('-t', '--timeout', type=posnumber, default=0,
                                help='timeout [seconds], default: 0 (eternal)')
    parser_mir_ltb.add_argument(
            '-s', '--server',
            help=('the (linux) DRC server (default: defined in ' +
                  r'T:\LayoutToolbox\settings\user.ini)'))
    parser_mir_ltb.add_argument(
            '-u', '--username',
            help=('your username on the (linux) DRC server (default: defined' +
                  r' in T:\LayoutToolbox\settings\user.ini)'))


def argparse_eval(args):
    # make a dict of args
    dictargs = vars(args)
    funcdict = {'mirror': (mirror,
                           [dictargs.get('source'),
                            dictargs.get('destination'),
                            dictargs.get('source_map')]),
                'LTBresult': (LTBresult,
                              [dictargs.get('project'),
                               dictargs.get('cellname'),
                               dictargs.get('vertype'),
                               dictargs.get('layers'),
                               dictargs.get('new'),
                               dictargs.get('timeout'),
                               dictargs.get('server'),
                               dictargs.get('username')])
                }
    return funcdict


if __name__ == "__main__":
    general.logsetup()
    general.myargparse(argparse_setup, argparse_eval, 'v20241003')
