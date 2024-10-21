# -*- coding: utf-8 -*-
"""
Created on Fri Mar 25 11:06:32 2016

@author: Koen
"""
import os
import general


def clear():
    tclfilename = os.path.expanduser(
      r'~\AppData\Roaming\Tanner EDA\scripts\startup\seditnumbers.tcl')
    if os.path.exists(tclfilename):
        os.remove(tclfilename)


def generate(low, high):
    lowbits = int(low)
    highbits = int(high)

    tclfilename = os.path.expanduser(
        r'~\AppData\Roaming\Tanner EDA\scripts\startup\seditnumbers.tcl')
    with open(tclfilename, 'w') as tclfile:
        tcl_00 = (r'design open {S:\projects\scib\standard\schematic\numbers' +
                  r'\numbers.tanner}' + '\n\n')
        tclfile.write(tcl_00)

        for bit in range(lowbits, highbits + 1):
            for nr in range(2**bit):
                bitstr = str(bit)
                form = '{:0' + str(len(str(2**bit))) + 'd}'
                nrstr = form.format(nr)
                binform = '{:0' + str(bit) + 'b}'
                binval = binform.format(nr)
                cellname = 'number_' + bitstr + '_' + nrstr
                print(bitstr + ' ' + nrstr + ' ' + binval)

                tcl_01 = (r'cell copy -design {numbers\numbers} -cell ' +
                          r'number_b_n -to_design {numbers\numbers} ' +
                          '-to_cell ' + cellname +
                          ' -overwrite -dependencies none\n')
                tcl_02 = ('cell open -design numbers -cell ' + cellname +
                          ' -type schematic\n' +
                          'port -type Other\n' +
                          'mode draw port\n' +
                          'port -text vss -orientation west -size 8pt ' +
                          '-autoincrement 1 -repeat false -confirm true\n' +
                          'point click 1 1\n' +
                          'mode draw port\n' +
                          'port -text vdd -orientation west -size 8pt ' +
                          '-autoincrement 1 -repeat false -confirm true\n' +
                          'point click 1 1.5\n')
                tcl_03 = ('mode draw instance\n' +
                          'instance -cell short -design devices -view ' +
                          'view_1 -rotate 270000000 -type symbol -interface ' +
                          'view_1\n')
                y0 = 1
                yinc = 0.125
                y = y0
                for x in range(bit):
                    tcl_03 += 'point click 2 ' + str(y) + '\n'
                    y += yinc
                tcl_03 += 'mode escape\n'

                tcl_04 = 'port -type InOut\n'
                y = y0
                for x in range(bit):
                    tcl_04 += ('mode draw port\n' +
                               'port -text number<' + str(x) +
                               '> -orientation east -size 8pt -autoincrement' +
                               ' 1 -repeat false -confirm true\n')
                    tcl_04 += 'point click 2 ' + str(y) + '\n'
                    y += yinc

                tcl_05 = 'port -type Netlabel\n'
                y = y0
                for x in range(bit-1, -1, -1):
                    vddvss = 'vdd' if binval[x] == '1' else 'vss'
                    tcl_05 += ('mode draw port\n' +
                               'port -text ' + vddvss + ' -orientation west ' +
                               '-size 8pt -autoincrement 1 -repeat false ' +
                               '-confirm true\n')
                    tcl_05 += 'point click 1.625 ' + str(y) + '\n'
                    y += yinc

                if bit == 1:
                    tcl_06 = ('window open -cell ' + cellname + ' -type ' +
                              'symbol\n' +
                              'point click 0 0.0625\n' +
                              'property set Name -system -value number<0>\n' +
                              'point click 0 -0.0625\n' +
                              'property set Name -system -value {' + bitstr +
                              ' bits}\n'
                              'point click 0 -0.1875\n' +
                              'property set Name -system -value ' + str(nr) +
                              '\n\n')
                else:
                    tcl_06 = ('window open -cell ' + cellname + ' -type ' +
                              'symbol\n' +
                              'point click 0 0.0625\n' +
                              'property set Name -system -value number<0:' +
                              str(bit-1) + '>\n' +
                              'point click 0 -0.0625\n' +
                              'property set Name -system -value {' + bitstr +
                              ' bits}\n'
                              'point click 0 -0.1875\n' +
                              'property set Name -system -value ' + str(nr) +
                              '\n\n')

                tclfile.write(tcl_01 + tcl_02 + tcl_03 + tcl_04 + tcl_05 +
                              tcl_06)


def argparse_setup(subparsers):
    parser_gen = subparsers.add_parser(
            'generate',
            help='Creates S-Edit tcl-file to generate numbers library')
    parser_gen.add_argument(
            '-n', required=True,
            help='the number of bits, lowest value of the span')
    parser_gen.add_argument(
            '-N', required=True,
            help='the number of bits, highest value of the span')

    subparsers.add_parser('clear', help='clears generated tcl-file from ' +
                          'auto-startup folder.')


def argparse_eval(args):
    # make a dict of args
    dictargs = vars(args)
    funcdict = {'generate': (generate,
                             [dictargs.get('n'),
                              dictargs.get('N')]),
                'clear': (clear,
                          [])
                }
    return funcdict


if __name__ == "__main__":
    general.logsetup()
    general.myargparse(argparse_setup, argparse_eval, 'v20221005')
