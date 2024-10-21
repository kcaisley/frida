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


class LayerSummaryError(Exception):
    pass


def analyse(tech, infile, outfile, rawtech = False):
    layers = []
    
    with open(infile, "r") as fpin:
        headerfound = False
        for line in fpin:
            if not headerfound:
                if line.startswith("file,"):
                    headerfound = True
                    if not rawtech:
                        techcolheader = line.find('tech_manual,')
                        if techcolheader >0:
                            techcol = line.count(',', 0, techcolheader)
                        else:
                            raise LayerSummaryError('No tech_manual column found in ' + infile)
                    else:
                        techcolheader = line.find('tech,')
                        if techcolheader >0:
                            techcol = line.count(',', 0, techcolheader)
                        else:
                            raise LayerSummaryError('No tech column found in ' + infile)
                continue
            
            if line.split(',')[techcol] != tech:
                continue
            
            pattern = r",([^:,]+)::([^/]*)/([^,]*)"
            for x in re.finditer(pattern, line):
                if x.groups() not in layers:
                    layers.append(x.groups())
    
    layers.sort(key=lambda col: (int(col[1]),int(col[2]),col[0]))
    
    txt = ''
    gdsnr = None
    gdsdt = None
    for layer in layers:
        if layer[1] == gdsnr and layer[2] == gdsdt and (gdsnr != '-1' and gdsdt != '-1'):
            txt += ',' + layer[0]
        else:
            if gdsnr is not None or gdsdt is not None:
                txt += '\n'
            txt += layer[1] + ',' + layer[2] + ',' + layer[0]
            gdsnr = layer[1]
            gdsdt = layer[2]
    
    general.write(outfile, txt, True)


def argparse_setup(subparsers):
    parser_lsum_ana = subparsers.add_parser(
            'analyse', help='analyse layersummary')
    parser_lsum_ana.add_argument('-t', '--tech', required=True,
                                default=None, help='the tech name ' +
                                '(for example: tsl018, xc018, ...)')
    parser_lsum_ana.add_argument('-i', '--infile', required=True,
                                default=None, help='the input filename (for' +
                                ' example: L:\\laygen\\allLayers_alltech.csv)')
    parser_lsum_ana.add_argument('-o', '--outfile', required=True,
                                default=None, help='the output filename (for' +
                                ' example: L:\\laygen\\layer_ana_tsl018.csv)')
    parser_lsum_ana.add_argument('-r', '--rawtech', required=False,
                                default=False, action='store_true',
                                help='use the raw tech column iso the manual ' +
                                'one')


def argparse_eval(args):
    # make a dict of args
    dictargs = vars(args)
    funcdict = {'analyse': (analyse,
                            [dictargs.get('tech'),
                             dictargs.get('infile'),
                             dictargs.get('outfile'),
                             dictargs.get('rawtech')])
                }
    return funcdict


if __name__ == "__main__":
    general.logsetup()
    general.myargparse(argparse_setup, argparse_eval, 'v20231009')
