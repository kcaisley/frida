# import math
import time
import re
# from typing import Optional, Any

import general
import laygen


# import sys
# import re
# import timestamp
#
# import logging      # in case you want to add extra logging
# import general
# import LTBfunctions
import LTBsettings
# import settings


def gen_missing_ports(infile, outfile, backup=True):
    if infile is None:
        infile = LTBsettings.laygenfilepath() + 'sdl_gmp_in.txt'
    if outfile is None:
        outfile = LTBsettings.laygenfilepath() + 'sdl_gmp_out.c'

    pattern = r'Pin "(\S+)" not found in instance ""'
    ports = []
    with open(infile, 'r') as f:
        for line in f:
            for match in re.finditer(pattern, line):
                ports.append(match.groups()[0])
    print('\n'.join(ports))
    batchtext = export_autogen(ports)
    general.write(outfile, batchtext, backup)
    laygen.laygenstandalone2bound(outfile)


def export_autogen(ports):
    assert isinstance(ports, list)
    assert all(isinstance(x, str) for x in ports)

    coordy = 0
    coordx = 0

    batchtext = "// From sdl.py\n"
    batchtext += "// Created: " + time.ctime() + ")\n\n"
    batchtext += r"""module gen_missing_ports
{
#include <stdlib.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <ctype.h>
#include <math.h>

#define EXCLUDE_LEDIT_LEGACY_UPI
#include <ldata.h>
//#include "X:\LEdit\technology\settings.c"
//#include "X:\LEdit\general\update2newcell.c"
#include "S:\technologies\setup\tech2layoutparams\tech2layoutparams.c

"""
    batchtext += '''void layoutbatch()
{
    LFile activefile = LFile_GetVisible();
    LCell activecell = LCell_GetVisible();
    LWindow activeWindow;
    LPoint coord;
    LPort newPort;        

'''
    for port in ports:
        batchtext += ('\t\tcoord = LPoint_Set(' + str(coordx) + ', ' +
                      str(coordy) + ');\n')
        batchtext += ('\t\tnewPort = LPort_New(activecell, ' +
                      'tech2layer("defaultlabellayer"), "' + port +
                      '", coord.x, coord.y, coord.x, coord.y);\n')
        batchtext += ('\t\tLPort_SetTextAlignment(newPort, ' +
                      'PORT_TEXT_MIDDLE | PORT_TEXT_CENTER);\n')
        batchtext += '\t\tLPort_SetTextSize(newPort, 250);\n\n'
        coordx += 5000

    batchtext += '''
    LDisplay_Refresh();
}
}

layoutbatch();
'''
    return batchtext


def argparse_setup(subparsers):
    parser_sdl_gmp = subparsers.add_parser(
        'gen_missing_ports', help=('Creates c-file for execution in L-Edit to' +
                                   ' generate new ports based on sdl warning ' +
                                   'text'))
    parser_sdl_gmp.add_argument(
        '-i', '--infile', default=None,
        help=('the path to the sdl warning text file (default: ' +
              LTBsettings.laygenfilepath() + 'sdl_gmp_in.txt)'))
    parser_sdl_gmp.add_argument(
        '-o', '--outfile', default=None,
        help=('the path to the output C file (default: ' +
              LTBsettings.laygenfilepath() + 'sdl_gmp_out.c)'))
    parser_sdl_gmp.add_argument(
        '--nobackup', dest='backup', default=True, action='store_false',
        help='Avoids creation of backup files of previous output files.')


def argparse_eval(args):
    # make a dict of args
    dictargs = vars(args)
    funcdict = {'gen_missing_ports': (gen_missing_ports,
                                      [dictargs.get('infile'),
                                       dictargs.get('outfile'),
                                       dictargs.get('backup')])
                }
    return funcdict


if __name__ == "__main__":
    general.myargparse(argparse_setup, argparse_eval, 'v20240213')
