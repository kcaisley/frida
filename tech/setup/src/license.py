#!/usr/bin/env python

"""investigate.py: helper functions to quickly analyze licenses for LTB"""

from __future__ import print_function
import re
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


def whohas(licensename=None, simserver=None, linuxusername=None, verbose=True):
    global USERset
    USERset.load()
    if licensename is None:
        licensename = 'caltannerpvs'
    if simserver is None:
        simserver = USERset.get_str('simserver')
    if linuxusername is None:
        linuxusername = USERset.get_str('linuxusername')

    no_antispoof = general.check_linux_plink(simserver, linuxusername)
    plinkcommand = ['plink', '-ssh', linuxusername + '@' + simserver,
                    no_antispoof, 'lmstat -f', licensename]

    if verbose:
        print(plinkcommand)
    # tmp fix
    if verbose:
        print('\nRequesting license status. ')
    p = subprocess.Popen(plinkcommand, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE)
    (output, error) = p.communicate()

    stroutput = output.decode()
    if verbose:
        print('stroutput: ' + stroutput)

    patt = (r'Users of ' + licensename + r':  [(]Total of (\d+) licenses? ' +
            r'issued;  Total of (\d+) licenses? in use[)]')
    m1 = re.search(patt, stroutput)

    if m1 is not None:
        if m1.groups()[1] == '0':
            print('Free!!')
            return (None, None, [])
        if m1.groups()[0] == '0':
            print('License not available')
            return (None, None, [])
        else:
            patt = r'floating license\s+(\w+)[^\n]+ (\S+)[\n]'
            m2 = re.search(patt, stroutput[m1.end():])
            blockinguser = m2.groups()[0]
            print('blockinguser: ' + blockinguser)
            blockingsince = m2.groups()[1]
            print('blockingsince: ' + blockingsince)

            patt = r'\s+(\w+)[^\n]+ queued [^\n]+[\n]'
            m3 = re.finditer(patt, stroutput[m1.end()+m2.end():])
            inqueue = []
            for m in m3:
                inqueue.append(m.groups()[0])

            return (blockinguser, blockingsince, inqueue)
    else:
        raise Exception('License not found or output does not match pattern.')


def whatblocks(blockinguser, licensename='caltannerpvs', simserver=None,
               linuxusername=None):
    global USERset
    USERset.load()
    if simserver is None:
        simserver = USERset.get_str('simserver')
    if linuxusername is None:
        linuxusername = USERset.get_str('linuxusername')

    no_antispoof = general.check_linux_plink(simserver, linuxusername)

    plinkcommand = ['plink', '-ssh', linuxusername + '@' + simserver,
                    no_antispoof, 'ps jf -u', blockinguser]
    print(plinkcommand)
    print("\nRequesting blocker's processes ")
    p = subprocess.Popen(plinkcommand, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE)
    (output, error) = p.communicate()
    stroutput = output.decode()
    print('stroutput: ' + stroutput)

    patt = r'^((\d+).+mgls_asynch.+)'
    m = re.findall(patt, stroutput, re.M)
    if m is None:
        print('Cannot find what uses it, it might be released again')
    for am in m:
        print('mgls_asynch process line:' + am[0])
        procnumber = am[1]
        print('mgls_asynch process number:' + procnumber)

    patt = r'^(' + procnumber + '.+rve.+)'
    m = re.search(patt, stroutput, re.M)
    if m is not None:
        print(blockinguser + ' is using RVE (' + m.groups()[0] + ')')
        return procnumber
    else:
        patt = r'^(' + procnumber + '.+)'
        m = re.search(patt, stroutput, re.M)
        print(blockinguser + ' is using something (' + m.groups()[0] + ')')
        return procnumber


def investigate(licensename=None):
    blockinguser, blockingsince, inqueue = whohas(licensename)
    if blockinguser is None:
        return

    pid = whatblocks(blockinguser, licensename)

    # kill procnumber?


def queue(licensename='caltannerpvs', simserver=None,
          linuxusername=None):
    beep = True
    verbose = False
    global USERset
    USERset.load()
    if simserver is None:
        simserver = USERset.get_str('simserver')
    if linuxusername is None:
        linuxusername = USERset.get_str('linuxusername')

    while True:
        if verbose:
            print("running whohas()")

        blockinguser, blockingsince, inqueue = whohas(licensename,
                                                      verbose=verbose)
        if verbose:
            print("ended running whohas()")

        if blockinguser is None:
            print("It's free!")
        elif blockinguser == linuxusername:
            print('YOU ARE ON!')
            if len(inqueue) == 0:
                print('nobody waiting, keep going')
            else:
                if beep:
                    print('\a')
                print('***************************************')
                print('******  There is a queue behind! ******')
                print('***************************************')
                print('in queue: ' + ', '.join(inqueue))
        else:
            print("License is not free now.")
            print(blockinguser + ' is now using it.')
            if len(inqueue) == 0:
                print('Nobody in queue.')
            else:
                if len(inqueue) == 1:
                    print(str(len(inqueue)) + ' user in queue.')
                else:
                    print(str(len(inqueue)) + ' users in queue.')
                if linuxusername in inqueue:
                    pos = inqueue.index(linuxusername)
                    print('There are ' + str(pos) + ' users in front of you ' +
                          'in the queue')
                else:
                    print('You are not in the queue')

        try:
            answer = input_with_timeout("[B] toggle beep  [V] toggle verbosity  [X] exit  ? ", 10)
        except TimeoutExpired:
            print('\nGathering LM status...')
        else:
            if answer is not None:
                print('\n')
                if answer in ('b', 'B'):
                    beep = not beep
                    print('beep = ' + repr(beep))
                if answer in ('v', 'V'):
                    verbose = not verbose
                    print('verbose = ' + repr(verbose))
                if answer in ('x', 'X'):
                    print('Bye bye')
                    return


def argparse_setup(subparsers):
    parser_lic_inv = subparsers.add_parser(
            'investigate', help='investigate license (issues)')
    parser_lic_inv.add_argument('-l', '--license', required=False,
                                default=None, help='the licence name ' +
                                '(default: caltannerpvs)')

    parser_lic_who = subparsers.add_parser(
            'whohas', help='who blocks the license')

    parser_lic_who.add_argument('-l', '--license', required=False,
                                default=None, help='the licence name ' +
                                '(default: caltannerpvs)')

    parser_lic_what = subparsers.add_parser(
            'whatblocks', help='what process blocks the license')
    parser_lic_what.add_argument('-u', '--user', required=True,
                                 help=r'the user blocking the license')
    parser_lic_what.add_argument('-l', '--license', required=False,
                                 default=None, help='the licence name' +
                                 '(default: caltannerpvs)')

    parser_lic_que = subparsers.add_parser(
            'queue', help='keep an eye on the license queue.')
    parser_lic_que.add_argument('-l', '--license', required=False,
                                default=None, help='the licence name' +
                                '(default: caltannerpvs)')


def argparse_eval(args):
    # make a dict of args
    dictargs = vars(args)
    funcdict = {'investigate': (investigate,
                                [dictargs.get('license')]),
                'whohas': (whohas,
                           [dictargs.get('license')]),
                'whatblocks': (whatblocks,
                               [dictargs.get('user'),
                                dictargs.get('license'),
                                ]),
                'queue': (queue,
                          [dictargs.get('license')])
                }
    return funcdict


if __name__ == "__main__":
    general.logsetup()
    general.myargparse(argparse_setup, argparse_eval, 'v20210427', ['queue'])
