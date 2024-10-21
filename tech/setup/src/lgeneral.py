import time


def servertime():
    print(time.time())
    return(0)


def argparse_setup(subparsers):
    parser_stat_fin = subparsers.add_parser('finished',
                                            help='Is calibre finished?')
    # parser_stat_tim =
    subparsers.add_parser('servertime', help='what is the servers "now"?')

    parser_stat_fin.add_argument('-p', '--project', required=True,
                                 help='the PROJECT name')
    parser_stat_fin.add_argument('-c', '--cellname', help='the CELL name')
    parser_stat_fin.add_argument('-v', '--vertype',
                                 choices=['lvs', 'drc', 'xor', 'yld'],
                                 help='verification type')
    parser_stat_fin.add_argument('-l', '--layer', default='all',
                                 help='verification type')
    parser_stat_fin.add_argument('-t', '--timestamp', type=float, default=0,
                                 help=('ignore files modified before this ' +
                                       'timestamp (seconds since Unix epoch)'))


def argparse_eval(args):
    if args.command == 'finished':
        print('finished(' + str(args.project) + ',' + str(args.cellname) +
              ',' + str(args.vertype) + ',' + str(args.layer) + ',' +
              str(args.timestamp) + ')')
        exitval = finished(args.project, args.cellname, args.vertype,
                           args.layer, args.timestamp)
        print('\n\nEnd successfully.\n')
    elif args.command == 'servertime':
        # print('servertime()')
        exitval = servertime()
        # print('\n\nEnd successfully.\n')
    else:
        return False, None
    return True, exitval


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


def logsetup(errorlog=False):
    """logsetup(errorlog=True)
    set-up the default logging for the LayoutToolbox
    all logging with severity >= logging.DEBUG are stored in
        ~/bin/calibre_bg.log
    except if errorlog is False. All logging with severity >= logging.ERROR
    are stored in
        LTBsettings.ltbpath() + LTBerror.log

    LTBerror/log is cleared every time a new Python instance runs it, so it
    contains only the errors of the last Python run.
    Only up to 10 LTBerror.log files are kept, similar to what
    RotatingFileHandler does, but there is a new file per kernel launch and
    only when errors do occur.
    """
    loggingfilename = os.path.expanduser('~') + '/bin/calibre_bg.log'
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
        errorlogfilename = os.path.expanduser('~') + '/bin/calibre_bg_error.log'
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

