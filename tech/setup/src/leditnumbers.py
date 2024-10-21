# -*- coding: utf-8 -*-
"""
Created on Fri Mar 25 11:06:32 2016

@author: Koen
"""
import sys
# import logging      # in case you want to add extra logging
import general
import LTBsettings


def prepare_autogen():
    batchtext = '// From leditnumbers.generate\n'
    batchtext += 'module batch_module\n'
    batchtext += '{\n'
    batchtext += '#include <stdlib.h>\n'
    batchtext += '#include <stdarg.h>\n'
    batchtext += '#include <stdio.h>\n'
    batchtext += '#include <string.h>\n'
    batchtext += '#include <ctype.h>\n'
    batchtext += '#include <math.h>\n'
    batchtext += '\n'
    batchtext += '#define EXCLUDE_LEDIT_LEGACY_UPI\n'
    batchtext += '#include <ldata.h>\n'
    batchtext += r'#include "X:\LEdit\general\globals.c"' + '\n'
    batchtext += r'#include "X:\LEdit\technology\project.c"' + '\n'
    batchtext += (r'#include "S:\technologies\setup\tech2layoutparams' +
                  r'\tech2layoutparams.c"' + '\n')

    batchtext += '\n'

    batchtext += 'void layoutbatch()\n'
    batchtext += '{\n'
    batchtext += 'LFile activefile;\n'
    batchtext += 'LCell newCell;\n'
    batchtext += 'LCell activeCell;\n'
    batchtext += 'LPoint coord;\n'
    batchtext += 'coord = LPoint_Set(0,0);\n'
    batchtext += 'LPort newPort;\n'
    batchtext += 'LWindow activeWindow;\n'
    batchtext += 'char info[512];\n'
    # batchtext += 'LSelection SelectforMult;\n'
    batchtext += 'activefile = LFile_GetVisible();\n\n'

    batchtext += 'activeCell = LCell_Find(activefile, "autogeninfo");\n'
    batchtext += 'if (activeCell == NULL) {\n'
    batchtext += '\tactiveCell  = LCell_New(activefile, "autogeninfo");}\n'
    batchtext += 'LCell_MakeVisible(activeCell);\n'
    batchtext += 'LSelection_SelectAll();\n'
    batchtext += 'LSelection_Move( 0, -1000 );\n'
    batchtext += 'LPort_New(activeCell, tech2layer("defaultlabellayer"), "'
    batchtext += r'\\'.join(' '.join(sys.argv).split('\\'))
    batchtext += '", 0, 0, 0, 0);\n\n'
    return batchtext


def generate(project, n, N, high, low, pitch, zero, width):
    lowbits = int(n)
    highbits = int(N)
    yhigh = float(high)
    ylow = float(low)
    xpitch = float(pitch)
    xzero = float(zero)
    xwidth = float(width)

    laygenfilename = LTBsettings.autogenfilepath(project) + 'leditnumbers.c'
    batchtext = prepare_autogen()

    for bit in range(lowbits, highbits + 1):
        for nr in range(2**bit):
            bitstr = str(bit)
            form = '{:0' + str(len(str(2**bit))) + 'd}'
            nrstr = form.format(nr)
            binform = '{:0' + str(bit) + 'b}'
            binval = binform.format(nr)
            cellname = 'number_' + bitstr + '_' + nrstr
            print(bitstr + ' ' + nrstr + ' ' + binval)

            C_newcell = ('newCell = LCell_Find(activefile, "' + cellname +
                         '");\n')
            C_newcell += 'if (newCell != NULL) {\n'
            C_newcell += '\tLCell_MakeVisible(newCell);\n'
            C_newcell += '\tLSelection_SelectAll();\n'
            C_newcell += '\tLSelection_Clear();\n}\n'
            C_newcell += 'else {\n'
            C_newcell += ('\tnewCell  = LCell_New(activefile, "' + cellname +
                          '");\n')
            C_newcell += ('\tLFile_OpenCell(activefile, "' + cellname +
                          '");\n}\n')

            coordport = [round(xzero*1000), round((yhigh+ylow)/2*1000)]
            C_portset = ('coord = LPoint_Set(' + str(coordport[0]) +
                         ',' + str(round(yhigh*1000)) + ');\n')
            C_portset += ('newPort = LPort_New(newCell, tech2layer("M1text")' +
                          ', "vdd", coord.x, coord.y, coord.x, coord.y);\n')
            C_portset += ('LPort_SetTextAlignment(newPort, ' +
                          'PORT_TEXT_MIDDLE | PORT_TEXT_CENTER);\n')
            C_portset += 'LPort_SetTextSize(newPort, 250);\n'
            C_portset += ('coord = LPoint_Set(' + str(coordport[0]) +
                          ',' + str(round(ylow*1000)) + ');\n')
            C_portset += ('newPort = LPort_New(newCell, tech2layer("M1text")' +
                          ', "vss", coord.x, coord.y, coord.x, coord.y);\n')
            C_portset += ('LPort_SetTextAlignment(newPort, ' +
                          'PORT_TEXT_MIDDLE | PORT_TEXT_CENTER);\n')
            C_portset += 'LPort_SetTextSize(newPort, 250);\n\n'
            for x in range(bit):
                C_portset += ('coord = LPoint_Set(' + str(coordport[0]) +
                              ',' + str(coordport[1]) + ');\n')
                C_portset += ('newPort =' +
                              ' LPort_New(newCell, tech2layer("M2text")' +
                              ', "number<' + str(x) + '>", coord.x, ' +
                              'coord.y, coord.x, coord.y);\n')
                C_portset += ('LPort_SetTextAlignment(newPort, ' +
                              'PORT_TEXT_MIDDLE | PORT_TEXT_CENTER);\n')
                C_portset += 'LPort_SetTextSize(newPort, 250);\n'
                coordport[0] = round(coordport[0] + xpitch*1000)

            C_boxdraw = '\n'
            xbox = (round((xzero-xwidth/2)*1000), round((xzero+xwidth/2)*1000))
            for x in range(bit-1, -1, -1):
                y = round(yhigh*1000) if binval[x] == '1' else round(ylow*1000)
                C_boxdraw += ('LBox_New(newCell, tech2layer("M2"), ' +
                              str(xbox[0]) + ', ' + str(coordport[1]) +
                              ', ' + str(xbox[1]) + ', ' + str(y) + ');\n')
                xbox = [round(xbox[0] + xpitch*1000),
                        round(xbox[1] + xpitch*1000)]

            C_closecell = ('\nactiveWindow = LWindow_GetVisible();\n')
            C_closecell += 'if (Assigned(activeWindow)) {\n'
            C_closecell += '\tactiveCell = LWindow_GetCell(activeWindow);\n'
            C_closecell += '\tif (activeCell == newCell)\n'
            C_closecell += '\t\tif (LWindow_IsLast(activeWindow) == 0)\n'
            C_closecell += '\t\t\tLWindow_Close(activeWindow);\n}\n\n'

            batchtext += (C_newcell + C_portset + C_boxdraw + C_closecell)
    batchtext += '}  //layoutbatch\n}  //module\n\nlayoutbatch();\n\n'
    general.write(laygenfilename, batchtext, True)
    print('numbers batch file generated: ' + laygenfilename)


def argparse_setup(subparsers):
    parser_gen = subparsers.add_parser(
            'generate',
            help=('Creates L-Edit c-file to fill (existing, but possibly ' +
                  'empty) numbers library'))
    parser_gen.add_argument(
            '--project', required=True,
            help=('to store the C-file on an appropriate location in the ' +
                  'LTB project autogen folder'))
    parser_gen.add_argument(
            '-n', required=True,
            help='the number of bits, lowest value of the span')
    parser_gen.add_argument(
            '-N', required=True,
            help='the number of bits, highest value of the span')
    parser_gen.add_argument(
            '-1', '--high', required=True,
            help=('y position of the high connection in M2 (best to take ' +
                  'center of V1 to supply)'))
    parser_gen.add_argument(
            '-0', '--low', required=True,
            help=('y position of the low connection in M2 (best to take ' +
                  'center of V1 to supply)'))
    parser_gen.add_argument(
            '-p', '--pitch', required=True,
            help='pitch of the bits')
    parser_gen.add_argument(
            '-z', '--zero', required=True,
            help='x position (center of wire) of the LSB')
    parser_gen.add_argument(
            '-w', '--width', required=True,
            help='wire width (M2)')


def argparse_eval(args):
    # make a dict of args
    dictargs = vars(args)
    funcdict = {'generate': (generate,
                             [dictargs.get('project'),
                              dictargs.get('n'),
                              dictargs.get('N'),
                              dictargs.get('high'),
                              dictargs.get('low'),
                              dictargs.get('pitch'),
                              dictargs.get('zero'),
                              dictargs.get('width')]),
                }
    return funcdict


if __name__ == "__main__":
    general.logsetup()
    general.myargparse(argparse_setup, argparse_eval, 'v20221005')
