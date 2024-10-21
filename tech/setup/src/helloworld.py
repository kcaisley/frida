import sys
print(sys.version)
import time
import logging      # in case you want to add extra logging
import lgeneral


def extra(name):
    print("Hello " + name + ",")
    print("You are running Python version " + sys.version.split()[0])

def argparse_setup(subparsers):
    parser_hw = subparsers.add_parser(
        'extra', help=('runs hello world with extra arguments'))
    parser_hw.add_argument(
        '-n', '--name', default=None,
        help=('the name of the object to greet.'))

def argparse_eval(args):
    # make a dict of args
    dictargs = vars(args)
    print('argparse_eval( ' + repr(args) + ' )')
    funcdict = {'extra': (extra,
                          [dictargs.get('name')])
                }
    return funcdict

#if __name__ == "__main__":
lgeneral.logsetup()
lgeneral.myargparse(argparse_setup, argparse_eval, 'v20240308')


print(sys.version)
logging.info(sys.version)

time.sleep(5)
