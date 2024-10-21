# Some high-level functions for general use
import os
import sys
import re
import random
import LTBsettings
import argparse
import time
import logging
import timestamp


class LTBError(Exception):
    """general LTBError"""
    pass


class Obsoleting(Exception):
    """Raise an error for functions that are not supposed to be used anymore."""
    pass


class myArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        import sys as _sys
        from gettext import gettext as _

        """error(message: string)

        Prints a usage message incorporating the message to stderr and
        exits.

        If you override this in a subclass, it should not return -- it
        should either exit or raise an exception.
        """
        self._print_message('Wrong arguments for this module: ' +
                            repr(_sys.argv) + '\n')
        self.print_usage(_sys.stderr)
        args = {'prog': self.prog, 'message': message}
        logging.info('Wrong arguments for this module: ' + repr(_sys.argv) +
                     '\n' + self.format_usage() +
                     _('%(prog)s: error: %(message)s\n') % args)
        self.exit(2, _('%(prog)s: error: %(message)s\n') % args)


def myargparse(argparse_setup, argparse_eval, version='', defaultargs=None, skipsleep=False):
    parser = myArgumentParser()
    # parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--version', action='version',
                        version='%(prog)s ' + version)

    subparsers = parser.add_subparsers(
            title='subcommands', dest='command', help='REQUIRED sub-command')
    argparse_setup(subparsers)

    logging.info('ARGPARSE %s: %s', 'sys.argv', str(sys.argv))
    try:
        args = parser.parse_args()
    except SystemExit:
        # All debug info already logged using general.myArgumentParser.error()
        # logging.debug('args sysexit')
        # logging.info('%s: %s', 'sys.argv', str(sys.argv))
        if not skipsleep:
            time.sleep(2)
        raise
    except Exception:
        logging.exception('Argparse exception')
        import traceback
        print(traceback.format_exc())
        if not skipsleep:
            time.sleep(10)
        raise

    if args.command is None:
        if defaultargs is None:
            print('\nNo arguments given for this module: ' + sys.argv[0] +
                  '.  No action.')
            parser.print_usage()
            logging.info('No arguments given for this module: ' + sys.argv[0] +
                         '.  No action.\n' + parser.format_usage())
            if not skipsleep:
                time.sleep(2)
            return
        else:
            print('\nNo arguments given for this module: ' + sys.argv[0] +
                  '.  Default args: ' + repr(defaultargs))
            parser.print_usage()
            logging.info('No arguments given for this module: ' + sys.argv[0] +
                         '.  Default args: ' + repr(defaultargs) + '\n' + parser.format_usage())
            args = parser.parse_args(defaultargs)
    # else:
    try:
        funcdict = argparse_eval(args)
        func = funcdict[args.command][0]
    except KeyError:
        msg = ('Accepted args for module, but no action executed.  ' +
               'argparse_setup() and argparse_eval() apparently do ' +
               'not match.  Contact developer to solve it.')
        print(msg)
        logging.error(msg)
        if not skipsleep:
            time.sleep(10)
    except Exception:
        logging.exception('Argparse eval exception')
        import traceback
        print(traceback.format_exc())
        if not skipsleep:
            time.sleep(10)
        raise

    params = funcdict[args.command][1]

    module = func.__module__
    if module == '__main__':
        module = sys.argv[0].split('\\')[-1].split('.')[0]

    funccall = (module + '.' + func.__name__ +
                '(' + ', '.join(repr(x) for x in params) + ')')
    print(funccall)
    logging.info('>>> import ' + module + ';' + funccall)
    try:
        returnval = func(*params)
    except Exception:
        # error_log('Arguments for this module: ' + repr(sys.argv))
        # error_log()
        logging.exception('Unrecoverable error')
        logging.debug('\nimport ' + module + '\n' +
                      module + '.' + func.__name__ +
                      '(' + ', '.join(repr(x) for x in params) + ')\n')
        import traceback
        print(traceback.format_exc())
        if not skipsleep:
            time.sleep(10)
        raise
    except KeyboardInterrupt:
        logging.exception('User Abort (KeyboardInterrupt)')
        raise

    if returnval is not None:
        msg = ('EVAL ARGPARSE => ' + str(returnval) +
               '\n(sys.argv: ' + str(sys.argv) + ')')
        logging.info(msg)
        print(msg)
        if not skipsleep:
            time.sleep(2)

    print('\n\nEnd successfully.\n')
    if not skipsleep:
        time.sleep(.5)


def error_log(text=None, logfilename=None, dateinfo=True):
    from datetime import datetime
    import traceback
    logging.warning("Obsoleting function 'error_log', use logging.error() instead. ", stack_info=True)

    datetext = datetime.now().strftime("%A, %d %B %Y %H:%M")
    if logfilename is None:
        logfilename = LTBsettings.ltbpath() + 'PythonError.log'
    if not os.path.isfile(logfilename):
        prepare_dir_for(logfilename)
        with open(logfilename, 'w'):
            pass
            # close()

    with open(logfilename, 'a') as logfile:
        if text is None:
            logtext = 'Exception raised @ ' + datetext + '\n'
            logfile.write(logtext)
            traceback.print_exc(file=logfile)
            logfile.write('\n')
        else:
            if dateinfo:
                logtext = 'Debug info @ ' + datetext + '\n' + text + '\n'
            else:
                logtext = text + '\n'
            logfile.write(logtext)


def rotatelog(filename, maxCount=9):
    if os.path.isfile(filename):
        count = filename.split('.')[-1]
        if count.isdecimal():
            if int(count) >= maxCount:
                os.remove(filename)
                return
            rotatefilename = ('.'.join(filename.split('.')[:-1]) +
                              '.' + str(int(count)+1))
        else:
            rotatefilename = filename + '.1'

        rotatelog(rotatefilename)
        try:
            os.rename(filename, rotatefilename)
        except PermissionError:
            # This means the log file exists and is in use (by a running Python
            # program using the same log file), a random session identifier is
            # added to distinguish between different programs runnning
            logging.info('rotatelog failed, errors added to existing file.')


def filecroptail(filename, maxsize, cropsize, startpattern=''):
    assert maxsize > cropsize
    if not os.path.isfile(filename):
        return

    filesize = os.path.getsize(filename)
    if filesize < maxsize:
        return

    with open(filename, 'r') as fh:
        txt = fh.read()

    startpattern = (r'[a-z]{4} \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3} ' +
                    'INFO: ARGPARSE')
    match = re.search(startpattern, txt[filesize - cropsize:])

    if match:
        newtxt = txt[filesize - cropsize + match.start():]
    else:
        newtxt = txt[filesize - cropsize:]

    with open(filename, 'w') as fh:
        fh.write(newtxt)


def logsetup(errorlog=True):
    """logsetup(errorlog=True)
    set-up the default logging for the LayoutToolbox
    all logging with severity >= logging.DEBUG are stored in
        LTBsettings.ltbpath() + LTB.log
    except if errorlog is False. All logging with severity >= logging.ERROR
    are stored in
        LTBsettings.ltbpath() + LTBerror.log

    LTBerror/log is cleared every time a new Python instance runs it, so it
    contains only the errors of the last Python run.
    Only up to 10 LTBerror.log files are kept, similar to what
    RotatingFileHandler does, but there is a new file per kernel launch and
    only when errors do occur.
    """
    loggingfilename = LTBsettings.ltbpath() + 'LTB.log'
    # print('loggingfilename: ' + str(loggingfilename))
    if not os.path.isfile(loggingfilename):
        prepare_dir_for(loggingfilename)
    else:
        # crop log file to decent size of max 10~11 Mb
        Mb = 1024*1024
        startpatt = (r'[a-z]{4} \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3} ' +
                     'INFO: ARGPARSE')
        filecroptail(loggingfilename, 11*Mb, 10*Mb, startpatt)

    sessionid = ''
    for x in range(4):
        sessionid += chr(random.randrange(97, 123))

    logging.basicConfig(filename=loggingfilename,
                        format=(sessionid + ' %(asctime)s %(levelname)s: ' +
                                '%(message)s ' +
                                '(%(name)s %(module)s %(funcName)s)'),
                        level=logging.DEBUG)

    if errorlog:
        # LTBerror.log catches all (real) errors, but overwrites the log file
        # for every relaunch of the kernel.  You can use the content of this
        # file for immediate feedback.
        errorlogfilename = LTBsettings.ltbpath() + 'LTBerror.log'
        rotatelog(errorlogfilename)

        # delay = True -> no errors means no log file written
        errorhandler = logging.FileHandler(errorlogfilename, mode='a',
                                           delay=True)
        errorfmt = sessionid + ' %(asctime)s %(levelname)s: %(message)s'
        errorformat = logging.Formatter(errorfmt)
        errorhandler.setFormatter(errorformat)
        errorhandler.setLevel(logging.ERROR)
        # add handler to root logger
        logging.getLogger('').addHandler(errorhandler)


def clearfile(filename, backup):
    if os.path.isfile(filename):
        if backup:
            timestamp.make(False, [filename])
        else:
            os.remove(filename)


def prepare_dir_for(filename):
    (folder, file) = os.path.split(filename)
    if file == '':
        raise Exception("Lowest folder level in '" + filename +
                        "' not a folder?")
    if not os.path.isdir(folder):
        if not os.path.isdir(os.path.split(folder)[0]):
            # if the higher level does not exist, first create that one
            # (recursively)
            prepare_dir_for(folder)
        # (and then) create it
        os.mkdir(folder)


def prepare_write(filename, backup):
    clearfile(filename, backup)
    prepare_dir_for(filename)


def write(filename, txt, backup, binary=False, encoder=""):
    openmode = 'w'
    if binary:
        openmode += 'b'
    prepare_write(filename, backup)
    with open(filename, openmode) as filehandler:
        if binary:
            filehandler.write(txt.encode())
        else:
            filehandler.write(txt)


def prepare_dirs(pathlist):
    import os
    for path in pathlist:
        if not os.path.isdir(path):
            # catch the situation where path ends with a separator
            # (Win: r'\' Unix '/')
            # otherwise prepare_dir_for will find file == '' and raise an
            # Exception
            (directory, file) = os.path.split(path)
            if file == '':
                path = directory

            try:
                prepare_dir_for(path)
                os.mkdir(path)
            except Exception:
                # Will there come some issues in the future that we could
                # catch?
                raise


def isprepared_dirs(pathlist):
    import os
    for path in pathlist:
        if not os.path.isdir(path):
            return False
    return True


def check_linux_samba(simserver, linuxusername):
    smbdir = LTBsettings.linux2samba(
            LTBsettings.linuxuserhomepath(linuxusername), simserver)

    if not os.path.isdir(smbdir):
        raise Exception("Samba seems not to be working (properly). \n" +
                        "Check the credentials (Navigate to '\\\\" +
                        simserver + "' in Windows Explorer and try '" +
                        smbdir + "' too).")


def check_linux_plink(simserver, linuxusername):
    import subprocess

    versioncommand = ['plink', '-V']
    try:
        p = subprocess.Popen(versioncommand, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
    except Exception:
        raise Exception('PuTTY seems not (properly) installed, also check ' +
                        'path environment variable')
    (output, error) = p.communicate()
    version = float(output.split(b'\r\n')[0].split()[-1])
    no_antispoof = '-no-antispoof' if version > 0.70 else ''

    testcommand = ['plink', '-ssh', '-batch', linuxusername + '@' + simserver,
                   no_antispoof, "echo '1'"]
    try:
        p = subprocess.Popen(testcommand, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        # print(p)
    # except FileNotFoundError: (not Py2 compatible)
    except Exception:
        raise Exception('PuTTY seems not (properly) installed, also check ' +
                        'path environment variable')

    (output, error) = p.communicate()
    if output == b'' and error.find(b"The server's host key is not cached in" +
                                    b" the registry.") != -1:
        raise Exception("server key not added to PuTTy registry. \nRun '" +
                        "plink -ssh " + linuxusername + '@' + simserver + ' ' +
                        no_antispoof + ' "echo ' + "'1'" + '"' +
                        "' from cmd line and accept.")
    if output != b'1\n':
        logging.warning(('unexpected output. output: %s, error: %s \n' +
                         'Investigating further.'), str(output), str(error))
        testcommand = ['plink', '-ssh', linuxusername + '@' + simserver,
                       no_antispoof, "echo '1'"]
        p = subprocess.Popen(testcommand, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        # output = subprocess.check_output(testcommand, stderr=subprocess.PIPE)
        try:
            (output, error) = p.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            p.kill()
            (output, error) = p.communicate()

        if error.find(b'Host does not exist') != -1 or error.find(
                b'Network error: Connection refused') != -1:
            raise Exception('Server not found: ' + str(testcommand))
        if output.find(b'login') != -1:
            raise Exception('key not added to PuTTY pageant or unspecified ' +
                            'user: ' + str(testcommand))
        if output.find(b'password') != -1:
            raise Exception('key not added to PuTTY pageant or invalid ' +
                            'user: ' + str(testcommand))

        raise Exception('Unknown output with: ' + str(testcommand))

    testcommand = ['plink', '-ssh', linuxusername + '@' + simserver,
                   no_antispoof, 'calibre']

    p = subprocess.Popen(testcommand, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE)
    (output, error) = p.communicate()
    if error.find(b'command not found') != -1:
        raise Exception('calibre seems not (properly) installed on server: ' +
                        str(testcommand))

    testcommand = ['plink', '-ssh', linuxusername + '@' + simserver,
                   no_antispoof, 'python --version']

    p = subprocess.Popen(testcommand, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE)
    (output, error) = p.communicate()
    if error.find(b'command not found') != -1:
        raise Exception('python seems not (properly) installed on server: ' +
                        str(testcommand))

    for script, version in [['calibre1.cmd', None],
                            ['evi_worker', None],
                            ['calibre_status.py', b'v20240531'],
                            ['calibre_bg.py', b'v20241003']]:
        filename = '\\\\'+simserver+'/'+linuxusername+'/bin/' + script
        if not os.path.isfile(filename):
            check_linux_samba(simserver, linuxusername)
            raise Exception(script + ' seems not to exist on ' +
                            'server: ' + str(simserver) +
                            '\n\nCopy X:\\docker\\' + script + ' to /home/' +
                            linuxusername +
                            '/bin/' + script + ' on the Calibre server.')
        if version is not None:
            testcommand = ['plink', '-ssh', linuxusername + '@' + simserver,
                           no_antispoof, 'python /home/' + linuxusername +
                           '/bin/' + script + ' --version']

            trysometimes = 50
            while trysometimes > 0:
                p = subprocess.Popen(testcommand, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE)
                (output, error) = p.communicate()
                if error == b'' and output == b'':
                    trysometimes -= 1
                    time.sleep(1)
                    logging.info('empty response, retry ' + str(trysometimes) +
                                 ' times more.')
                    print('empty response, retry')
                else:
                    trysometimes = 0
                    assert b'' in [error, output]
                    combined = error + output
            if not combined.startswith(script.encode()):
                raise Exception(script + ' seems not (properly) installed ' +
                                'on server.\ntestcommand: ' + str(testcommand) +
                                '\noutput: ' + output.decode() +
                                '\nerror: ' + error.decode() + '\nCopy X:\\docker\\' +
                                script + ' to /home/' + linuxusername +
                                '/bin/' + script + ' on the Calibre server.')
            if version not in combined:
                raise Exception(script + ' seems not to be the latest ' +
                                'version: ' + str(testcommand) + '\nexpected : ' +
                                script + ' ' + version.decode() +
                                '\ninstalled: ' + combined.decode() +
                                '\n\nCopy X:\\docker\\' + script + ' to /home/' +
                                linuxusername +
                                '/bin/' + script + ' on the Calibre server.')

    return no_antispoof


def progressbar(progress, length=50, prevreturn=None, up=0):
    """def progressbar(progress, length=50, prevreturn=None):
    prints a progressbar of 'length' number of characters on the previous line
    progress should be a number between 0 and 1, if outside that range the
    progress bar is printed in red
    if the return value is fed into the function with argument prevreturn,
    a motion will be visible.
    Do not print yourself anything between different progressbar calls for best
    results.  You can tweak the number of lines the cursor must move up by
    passing that value in up.  (Remember to print some newlines yourself before
    calling progressbar for the first time)
    """
    try:
        import colorama
    except ModuleNotFoundError:
        colorama = None
    if colorama is not None:
        colorama.init()

        if prevreturn is None:
            print('')
        if progress < 0:
            color = colorama.Fore.RED
            progress = 0
        elif progress > 1:
            color = colorama.Fore.RED
            progress = 1
        else:
            color = colorama.Fore.RESET

        done = int(length * progress)

        busy = ['-', '\\', '|', '/']
        if prevreturn in busy:
            motion = busy[(busy.index(prevreturn) + 1) % len(busy)]
        else:
            motion = busy[1]

        if progress == 1:
            todo = ''
        else:
            todo = motion + ' ' * (length - done - 1)

        pb = '*' * done + todo

        assert len(pb) == length

        curs = colorama.Cursor.UP(1 + up)
        colorreset = colorama.Fore.RESET
        print(curs + color + '[' + pb + ']' + colorreset)

        return motion
    else:
        if prevreturn is None:
            prevreturn = 0
            print('[' + ' '*length + ']')
            print(' ', end='')

        if progress < 0:
            print('Warning: progress < 0%  (' + str(progress*100) + '%)')
        elif progress > 1:
            print('Warning: progress > 100%  (' + str(progress * 100) + '%)')
        elif progress < prevreturn:
            print('Warning: progress going backwards (' +
                  str(prevreturn * 100) + '% -> ' + str(progress * 100) + '%)')

        done = int(length * progress)
        prevdone = int(length * prevreturn)

        print('*'*(done-prevdone), end='')

        return progress


class CalcError(LTBError):
    pass


def calc_synterr_find_operand(expr, offset):
    """Find operand from SyntaxError.
    Tested against finding spice accepted SI unit prefixes."""
    operators = "()+-*/"
    minfind = len(expr)
    for operator in operators:
        find = expr.find(operator, offset)
        if find != -1:
            minfind = min(find, minfind)
            # if minfind == len(expr):
            #     minfind = find
            # else:
            #     minfind = min(find, minfind)
    if minfind == -1:
        minfind = len(expr)

    maxrfind = -1
    for operator in operators:
        rfind = expr.rfind(operator, 0, offset)
        if rfind != -1:
            maxrfind = max(rfind, maxrfind)
            # if maxrfind == -1:
            #     maxrfind = rfind
            # else:
            #     maxrfind = max(rfind, maxrfind)
    # print("minfind: " + str(minfind))
    # print("maxrfind: " + str(maxrfind))
    return expr[maxrfind+1:minfind].strip().rstrip()


def calc(expr, namevaluedict={}, verbose=None, limit=100):
    """calc(expr, namevaluedict = {}, verbose = None, limit = 100):
    expression is a mathematical expression, supporting (in order of priority)
    brackets, floating point reprsentation with e for 10^x, **, *, /, -, +,
    namevaluedict is a dictionary with replacements for variable names and
    their values (single or multiple as list)
    limit is the maximum number of nestings that is allowed
    (to avoid never-ending loops)
    returns always a list with all possible unique solutions"""
    if limit == 0:
        raise Exception('Maximum nesting achieved')
    if verbose is None:
        verbose = 0
        # print('verbose: ' + repr(verbose))
    if verbose > 0:
        print('calc(' + repr(expr) + ', ' +
              'namevaluedict=' + repr(namevaluedict) + ', ' +
              'verbose=' + repr(verbose) + ', ' +
              'limit=' + repr(limit) + ')')

    name = ''
    try:
        calcval = eval(expr)
    except NameError as e:
        #     print(e)
        #     print(dir(e))
        #     print('e.args: ' + str(e.args))
        name = e.args[0].split("'")[1]
    except SyntaxError as e:
        # print(e)
        # print(dir(e))
        # print('e.args: ' + str(e.args))
        # print('e.filename: ' + str(e.filename))
        # print('e.lineno: ' + str(e.lineno))
        # print('e.msg: ' + str(e.msg))
        # print('e.offset: ' + str(e.offset))
        # print('e.print_file_and_line: ' + str(e.print_file_and_line))
        # print('e.print_file_and_line: ' + str(e.print_file_and_line))
        # print('e.with_traceback: ' + str(e.with_traceback))
        name = calc_synterr_find_operand(expr, e.offset)
    else:
        return [fancy_up_float(float(calcval))]

    # if name != '':
    if name in namevaluedict:
        values = namevaluedict[name]
        if not isinstance(values, list):
            values = [values]

        calcval = []
        for value in values:
            if verbose > 1:
                print('namevaluedict: ' + name + ' = ' + str(value))
            newexpr = expr.replace(name, str(value))
            calcval.extend(calc(newexpr, namevaluedict, verbose, limit-1))

        trim = list(set(calcval))
        trim.sort()
        if verbose > 1:
            print(trim)
        return trim
    else:
        raise CalcError(['?', name])


def fancy_up_float(number):
    if isinstance(number, float):
        strn = str(number)
        if '99999' in strn or '00000' in strn:
            if '99999' in strn:
                pos999000 = strn.find('99999')
            else:
                pos999000 = strn.find('00000')
            if '.' in strn:
                posdot = strn.find('.')
                if 'e' in strn:
                    pose = strn.find('e')
                    val = strn[:pose]
                    exp = int(strn[pose+1:])
                else:
                    val = strn
                    exp = 0
                fancyval = round(float(val), pos999000 - posdot)
                # return fancyval*10**exp
                if isinstance(fancyval, float) and isinstance(exp, int):
                    return eval(str(fancyval) + 'e' + str(exp))
                else:
                    raise Exception('TODO fix when this situation occurs')
            else:
                raise Exception('TODO fix when this situation occurs')
        else:
            return number
    else:
        print('FANCY_UP_FLOAT, type: ' + str(type(number)) + ', value: ' +
              str(number))
        return number
