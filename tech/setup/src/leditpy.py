#!/usr/bin/env python

"""leditpy.py: wrapper around externalized functions called from L-Edit
L-Edit supports no other python than its own (2.6.6).
In order to not be limited by history, development continues in Py3
It is made into an executable that is on its turn called by L-Edit.
"""

import general
import background
import lvs
import drc
import yld
import xor
import laygen
import leditlib
import mirror_files
import polygon
import sdl

def argparse_setup(subparsers):
    background.argparse_setup(subparsers)
    lvs.argparse_setup(subparsers)
    drc.argparse_setup(subparsers)
    xor.argparse_setup(subparsers)
    laygen.argparse_setup(subparsers)
    mirror_files.argparse_setup(subparsers)
    yld.argparse_setup(subparsers)
    leditlib.argparse_setup(subparsers)
    polygon.argparse_setup(subparsers)
    sdl.argparse_setup(subparsers)


def argparse_eval(args):
    funcdict = {}
    funcdict.update(background.argparse_eval(args))
    funcdict.update(lvs.argparse_eval(args))
    funcdict.update(drc.argparse_eval(args))
    funcdict.update(xor.argparse_eval(args))
    funcdict.update(laygen.argparse_eval(args))
    funcdict.update(mirror_files.argparse_eval(args))
    funcdict.update(yld.argparse_eval(args))
    funcdict.update(leditlib.argparse_eval(args))
    funcdict.update(polygon.argparse_eval(args))
    funcdict.update(sdl.argparse_eval(args))
    return funcdict


if __name__ == "__main__":
    general.logsetup()
    general.myargparse(argparse_setup, argparse_eval, 'v20240212')
