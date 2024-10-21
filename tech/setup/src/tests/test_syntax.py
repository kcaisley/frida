# -*- coding: utf-8 -*-

# Not really testing something, but at least importing most files for some basic syntax checking
# Test fails if one of those cannot import due to syntax errors.

import inspect
import sys
import os

print(os.getcwd())
cwd = os.getcwd()
if (cwd.endswith('tests')):
    sys.path.append(cwd[:-6])
print(sys.path)
    
import aspi
import background
import calqmgr
import checktuners
import daily_check
import dist2exe
import drc
import general
import guifunctions
import layersummary
import laygen
import leditlib
import leditnumbers
import leditpy
import license
import LTBcheck
import LTBfunctions
#import LTBgui_
import LTBsettings
import lvs
import mirror_files
import mygdsii
import projectsetup
import release
import sedit
import seditlibcopy
import seditnumbers
import sedittools
import settings
import spice
#import starrouting
#import starrouting_fcts
import stdcells
import techsetup
import timestamp
import unused_cells
import vias
import xor
import yld


def test_all_argparse():
    for x in globals():
        if not x.startswith('@'):
            print('inspect.ismodule('+x+'):')
            print(eval('inspect.ismodule('+x+')'))
            if eval('inspect.ismodule('+x+')'):
                print("'argparse_setup' in dir(" + x + ")")
                if (eval("'argparse_setup' in dir(" + x + ")") and
                        eval("'argparse_eval' in dir(" + x + ")")):
                    print('general.myargparse(' + x + '.argparse_setup' +
                         ', ' + x + '.argparse_eval, "justtest", ["-h"], True)')
                    try:
                        eval('general.myargparse(' + x + '.argparse_setup' +
                            ', ' + x + '.argparse_eval, "justtest", ["-h"], True)')
                    except SystemExit:
                        continue


if __name__ == "__main__":
    print(sys.path)
    test_all_argparse()
