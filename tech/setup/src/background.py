#!/usr/bin/env python
import time
import logging      # in case you want to add extra logging
import general
import subprocess


def bgCmd(run):
    subprocess.Popen(run)
    print('\n\nBusy successfully.\n')
    time.sleep(.5)


def bgLoop(interval, run):
    count = 0
    while True:
        subprocess.run(run)
        if (count%100 == 0):
            print(str(count) + ' ... ' + str(run))
            #print('\n\nBusy successfully.\n')
        else:
            if (count%10 == 0):
                print(str(int(count%100/10)), end = '', flush=True)
            else:
                print(str(count%10), end = '', flush=True)
        time.sleep(interval)
        count += 1


def cmd(run):
    print('\n\nStarting subprocces.\n')
    subprocess.run(run)
    print('\n\nSubprocces ended.\n')
    time.sleep(.5)


def argparse_setup(subparsers):
    parser_bgcmd = subparsers.add_parser(
            'bgCmd', help='run another command in background')
    parser_bgcmd.add_argument(
            '-r', '--run', required=True, nargs=general.argparse.REMAINDER,
            help='runcommand and potential arguments')

    parser_bgloop = subparsers.add_parser(
            'bgLoop', help='run another command in background, infinitely')
    parser_bgloop.add_argument(
            '-t', '--time',  type=int, required=True,
            help='time in seconds after which wait time after process finishing these processes are relaunched')
    parser_bgloop.add_argument(
            '-r', '--run', required=True, nargs=general.argparse.REMAINDER,
            help='runcommand and potential arguments')

    parser_cmd = subparsers.add_parser(
            'cmd', help='run another command, do not exit before subprocess has ended')
    parser_cmd.add_argument(
            '-r', '--run', required=True, nargs=general.argparse.REMAINDER,
            help='runcommand and potential arguments')


def argparse_eval(args):
    # make a dict of args
    dictargs = vars(args)
    funcdict = {'bgCmd': (bgCmd,
                          [dictargs.get('run')]),
                'bgLoop': (bgLoop,
                        [dictargs.get('time'),
                         dictargs.get('run')]),
                'cmd': (cmd,
                        [dictargs.get('run')])
                }
    return funcdict


if __name__ == '__main__':
    general.logsetup()
    general.myargparse(argparse_setup, argparse_eval, 'v20230901')
