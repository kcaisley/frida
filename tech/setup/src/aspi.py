import os
# import sys
import re
import time
import json

import logging      # in case you want to add extra logging
import general
import spice
# import LTBfunctions
import LTBsettings
# import laygen
import settings
import pickle

USERset = settings.USERsettings()

# ASPI_COMMONS = ['VASPI_common_9dice', 'VASPI_common_BETA2',
#                 'VASPI_common_and_bal_S4']
ASPI_COMMONS = r'VASPI_common\w*'
# ASPI_ADDRESS = ['VASPI_adresbit_9dice', 'VASPI_adresbit',
#                 'monitors_VASPI_adresbit']
ASPI_ADDRESS = r'\w*VASPI_adresbit\w*'
# ASPI_DATA = ['VASPI_databit_9dice', 'VASPI_databit',
#              'monitors_VASPI_databit']
ASPI_DATA = r'\w*VASPI_databit\w*'


class ASPIError(general.LTBError):
    pass


class ASPI_Register():
    def __init__(self, pysch, address, cellname='', data='', load='',
                 clk='', regaddress=None, ):
        # self.pysch = pysch
        self.address = spice.Address(address)
        self.cellname = self.address.subcktname(pysch)
        # for all known common blocks, the data, load and clock lines are
        # called exactly the same: 'SPI_data', 'SPI_load' and 'SPI_clock'.
        self.spiData = (self.address + 'SPI_data').highestnetname(pysch)
        self.spiLoad = (self.address + 'SPI_load').highestnetname(pysch)
        self.spiClk = (self.address + 'SPI_clock').highestnetname(pysch)
        # for all ASPI blocks, data transfers from 'next' to 'previous' in
        # every following address and data block.
        self.chain = [self.address]
        self.regaddr = 0
        self.regaddrwidth = 0
        self.datawidth = 0
        self.data = {}
        self.ndata = {}

    def control_bits():
        pass


def allUniqueInstancesOfSubckt(pysch, mysubckt):
    # print(' aUIOS(' + mysubckt + ')')
    registers = []
    for subckt in pysch.subckts:
        for item in subckt.content:
            if item.isInstance() and (item.getsubcktname() == mysubckt):
                # registers.append(subckt.name + '/' + item.name)
                for x in allUniqueInstancesOfSubckt(pysch, subckt.name):
                    registers.append(x + '/' + item.name)
    if len(registers) == 0:
        return [mysubckt]
    return registers


def aspi_check(regs):
    # address collision (especially with Variable address widths)

    # if equal address: data/ndata is the same

    # if hnn part of bus: MSB-LSB word in same order as data/ndata

    pass


def export(project, cellname, filetype='txt', backup=True, outfile=None,
           force=False, skip_analysis=False):
    # outfile check
    if outfile is not None:
        if os.path.isdir(outfile):
            raise general.LTBError('outfile should be filename, not a folder name')
        if filetype == 'all':
            warning = ('Same filename for the multiple output file formats ' +
                       'will cause all but 1 to be overwritten. Suffixes ' +
                       'will be added.')
            print(warning)
            logging.warning(warning)

    pklfile = ('{}ASPI_{}_{}.pkl'
               ).format(LTBsettings.varfilepath(project), project,
                        cellname)

    if skip_analysis and os.path.isfile(pklfile):
        with open(pklfile, 'rb') as pkl:
            regs = pickle.load(pkl)
    else:
        if skip_analysis:
            warning = ('No pickled register information found, ' +
                       '(re)doing analysis anyway.')
            logging.warning(warning)
            print(warning)
            time.sleep(10)
        # extract ASPI data from netlist
        regs = aspi2reg(project, cellname, force)
        #
        general.prepare_dir_for(pklfile)
        with open(pklfile, 'wb') as pkl:
            pickle.dump(regs, pkl)

    # check ASPI
    if not force:
        aspi_check(regs)

    #export to desired file format
    if filetype == 'txt':
        aspi2txt(regs, project, cellname, backup, outfile, force)
    elif filetype == 'json':
        aspi2json(regs, project, cellname, backup, outfile, force)
    elif filetype == 'csv':
        aspi2csv(regs, project, cellname, backup, outfile, force)
    elif filetype == 'all':
        if outfile is None:
            aspi2txt(regs, project, cellname, backup, outfile, force)
            aspi2json(regs, project, cellname, backup, outfile, force)
            aspi2csv(regs, project, cellname, backup, outfile, force)
        else:
            aspi2txt(regs, project, cellname, backup, outfile+'_txt', force)
            aspi2json(regs, project, cellname, backup, outfile+'_json', force)
            aspi2csv(regs, project, cellname, backup, outfile+'_csv', force)

        # aspi2csv(project, cellname, backup, outfile, force)


def aspi2json(regs, project, cellname, backup=True, outfile=None, force=False):
    if outfile is None:
        outfile = ('{}ASPI_{}_{}.json'
                   ).format(LTBsettings.varfilepath(project), project,
                            cellname)

    registersData = {}
    for AR in regs:
        regname = 'r{:02}'.format(AR.regaddr)
        print('regname: ' + regname)
        fullname = regname
        # get fields
        fields = []
        databit = 0
        while databit < AR.datawidth:
            print('databit: ' + str(databit))
            datalength = 1
            if str(AR.data[databit][0]).endswith('<0>'):
                fieldname = str(AR.data[databit][0])[:-3]
                print('fieldname: ' + fieldname)
                while databit + datalength <= AR.datawidth:
                    print('?? {} == {}'.format(
                            str(AR.data[databit + datalength - 1][0]),
                            '{}<{}>'.format(fieldname, datalength - 1)))
                    if (str(AR.data[databit + datalength - 1][0]) ==
                            '{}<{}>'.format(fieldname, datalength - 1)):
                        datalength += 1
                    else:
                        datalength -= 1
                        break
                else:
                    datalength -= 1
            else:
                fieldname = str(AR.data[databit][0])
            fields.append({'name': fieldname,
                           'bit0pos': databit,
                           'datalength': datalength,
                           'defvalue': 0,
                           'value': 0})

            databit += datalength

        registersData[regname] = {'name': regname,
                                  'addr': AR.regaddr,
                                  'datalength': AR.datawidth,
                                  'addrlength': AR.regaddrwidth,
                                  'fullname': fullname,
                                  'fields': fields}
    jsondict = {"ProjectName": project,
                "ConfigName": 'spi_dump',
                "RegistersData": registersData}
    # regs = aspi2reg(project, cellname, force)

    general.prepare_write(outfile, backup)
    with open(outfile, 'w') as filehandler:
        json.dump(jsondict, filehandler, indent=1)
    print('\nOutput json file written here: ' + outfile + '\n')


def aspi2txt(regs, project, cellname, backup=True, outfile=None, force=False):
    if outfile is None:
        outfile = ('{}ASPI_{}_{}.txt'
                   ).format(LTBsettings.varfilepath(project), project,
                            cellname)
    text = ''

    spictrls = []
    longestnetname = 0
    longestfullnetname = 0
    maxaddrwidth = 0
    maxdecaddrwidth = 0
    for reg in regs:
        spictrl = 'Data: {}\nClk: {}\nLoad: {}\n'.format(reg.spiData,
                                                         reg.spiClk,
                                                         reg.spiLoad)
        if spictrl not in spictrls:
            spictrls.append(spictrl)

        for (netname, fullnetname, othernames) in reg.data.values():
            longestnetname = max(longestnetname, len(netname))
            longestfullnetname = max(longestfullnetname, len(fullnetname))
        for (netname, fullnetname, othernames) in reg.ndata.values():
            longestnetname = max(longestnetname, len(netname))
            longestfullnetname = max(longestfullnetname, len(fullnetname))

        maxaddrwidth = max(maxaddrwidth, reg.regaddrwidth)
        maxdecaddrwidth = max(maxdecaddrwidth, len(str(reg.regaddr)))

    if len(spictrls) > 1:
        text += '-- Multiple SPI control line sets --\n'
        text += '\n'.join(spictrls)

    lastspictrl = ''
    overview = ''
    details = '\nRegister Details\n-----------------\n'

    prevaddr = -1
    prevreg = [0, 0]
    count = 1
    occ = ''
    for reg in regs:
        spictrl = 'Data: {}\nClk: {}\nLoad: {}\n'.format(reg.spiData,
                                                         reg.spiClk,
                                                         reg.spiLoad)
        if spictrl != lastspictrl:
            text += overview
            text += '\n\n-- SPI control line set --\n'
            text += spictrl
            overview = '\nRegister Overview\n-----------------\n'

        if reg.regaddr != prevaddr:
            if count != 1:
                overview += '  {} occurences:\n'.format(count)
                overview += occ
            overview += ('Address: {: >' + str(maxdecaddrwidth) + '}  [' +
                         '{: >2} bit] {:>' + str(maxaddrwidth) + '}'
                         ).format(reg.regaddr, reg.regaddrwidth,
                                  ('{:0' + str(reg.regaddrwidth) + 'b}'
                                   ).format(reg.regaddr))
            overview += '   Data: {: >2} bits\n'.format(reg.datawidth)
            prevaddr = reg.regaddr
            prevreg = [reg.regaddrwidth, reg.datawidth]
            count = 1
            occ = '    - {}\n'.format(reg.address)
        else:
            count += 1
            occ += '    - {}'.format(reg.address)
            if prevreg != [reg.regaddrwidth, reg.datawidth]:
                occ += ('   Different Adress/Data width: a{}d{}\n'
                        ).format(reg.regaddrwidth, reg.datawidth)
            else:
                occ += '\n'

        details += ('Address: {}  [{} bit] {:0'+str(reg.regaddrwidth)+'b}\n'
                    ).format(reg.regaddr, reg.regaddrwidth, reg.regaddr)
        details += 'SPI Entry Cell: {}\n'.format(reg.address)
        details += 'Data: {} bits\n'.format(reg.datawidth)
        ddetails = '\n'
        nddetails = '\n'
        for x in range(len(reg.data) - 1, -1, -1):
            ddetails += (' data<{:2}>: {:' + str(longestnetname+2) + '} [{:' +
                         str(longestfullnetname+2) + '}]' + ' // {}\n'
                         ).format(x, reg.data[x][0], reg.data[x][1],
                                  str(reg.data[x][2]))
            nddetails += ('ndata<{:2}>: {:' + str(longestnetname+2) + '} [{:' +
                          str(longestfullnetname+2) + '}]' + ' // {}\n'
                          ).format(x, reg.ndata[x][0], reg.ndata[x][1],
                                   str(reg.ndata[x][2]))
        details += ddetails + nddetails + '\n'

        lastspictrl = spictrl
    text += overview + details
    general.write(outfile, text, backup)
    print('\nOutput txt file written here: ' + outfile + '\n')


def aspi2csv(regs, project, cellname, backup=True, outfile=None, force=False):
    global USERset
    USERset.load()
    sep = USERset.get_type('CSVseparator')
    CSVheader = USERset.get_type('CSVheadersep')
    
    if outfile is None:
        outfile = ('{}ASPI_{}_{}.csv'
                   ).format(LTBsettings.varfilepath(project), project,
                            cellname)
    if CSVheader:
        text = sep.join(['sep=', '\n'])
    else:
        text = ''

    spictrls = []
    headspictrl = sep.join(['Data', 'Clk', 'Load', '\n'])
    for reg in regs:
        spictrl = sep.join(['{}', '{}', '{}\n']).format(reg.spiData, reg.spiClk,
                                                        reg.spiLoad)
        if spictrl not in spictrls:
            spictrls.append(spictrl)

    if len(spictrls) > 1:
        text += '-- Multiple SPI control line sets --\n'
        text += headspictrl
        text += '\n'.join(spictrls)
        text += '\n\n'

    lastspictrl = ''
    overview = ''
    details = '\nRegister Details\n-----------------\n'

    prevaddr = -1
    prevreg = [0, 0]

    for reg in regs:
        spictrl = sep.join(['{}', '{}', '{}\n']).format(reg.spiData, reg.spiClk,
                                                        reg.spiLoad)
        if spictrl != lastspictrl:
            text += overview
            text += '-- SPI control line set --\n'
            text += headspictrl + spictrl
            overview = '\nRegister Overview\n-----------------\n'
            overview += sep.join(['Address', 'width', '[binary]', 
                                  'Register data width', 'SPI Entry Cell\n'])

        if reg.regaddr == prevaddr:
            if prevreg != [reg.regaddrwidth, reg.datawidth]:
                overview += '!!! '
        else:
            prevreg = [reg.regaddrwidth, reg.datawidth]
            prevaddr = reg.regaddr

        overview += (sep.join(['{}', '{}-bit', '{}']
                     ).format(reg.regaddr, reg.regaddrwidth,
                              ("'{:0" + str(reg.regaddrwidth) + "b}'"
                               ).format(reg.regaddr)))
        overview += sep + '{}-bit'.format(reg.datawidth)
        overview += sep + '{}\n'.format(reg.address)

        details += sep.join(['Address:', '{}', '{} bit', 
                             "'{:0" + str(reg.regaddrwidth) + "b}'", '']
                    ).format(reg.regaddr, reg.regaddrwidth, reg.regaddr)
        details += sep.join(['Register data width:', '{} bits', '']
                    ).format(reg.datawidth)
        details += sep.join(['SPI Entry Cell:', '{}\n']).format(reg.address)
        details += sep.join(['Data bit', 'Net name (highest level)', 
                             'Net spice address',
                             'Alternative net names (other hierarchies)\n'])
        ddetails = ''
        nddetails = ''
        for x in range(len(reg.data) - 1, -1, -1):
            ddetails += sep.join([' data<{:2}>', '{}', '[{}]', '{}\n']
                         ).format(x, reg.data[x][0], reg.data[x][1],
                                  sep.join(reg.data[x][2]))
            nddetails += sep.join(['ndata<{:2}>', '{}', '[{}]', '{}\n']
                          ).format(x, reg.ndata[x][0], reg.ndata[x][1],
                                   sep.join(reg.ndata[x][2]))
        details += ddetails + nddetails + '\n'

        lastspictrl = spictrl
    text += overview + details
    general.write(outfile, text, backup)
    print('\nOutput csv file written here: ' + outfile + '\n')


def aspi2reg(project, cellname, force=False):
    debug = 0
    altnames = True
    rawpysch = spice.netlist2py(project, cellname, check=not(force))
    pysch = rawpysch.trim(cellname)

    print('Looking for ASPI access points, cell names matching the following')
    print(' pattern: ' + str(ASPI_COMMONS))
    print()
    aspi_cmn_cells = [x.name for x in pysch.subckts if
                      re.match(ASPI_COMMONS, x.name) is not None]
    print('aspi_cmn_cells:')
    print(aspi_cmn_cells)
    print()

    registers = []
    for aspi_cmn in aspi_cmn_cells:
        registers.extend(allUniqueInstancesOfSubckt(pysch, aspi_cmn))

    print('len(registers):' + str(len(registers)))
    regs_addr = []
    for i, x in enumerate(registers):
        # regs_addr.append(spice.Address(x + '/' ))
        regs_addr.append(ASPI_Register(pysch, x + '/'))

    for i, AR in enumerate(regs_addr):
        print('for ' + str(i) + ' in ' + str(len(registers)))
        print(str(i) + ') ' + ('' if AR.address.isvalid(pysch) else '!!! ') +
              str(AR.address) + ' [' + AR.cellname + ']')
        # print('input ASPI lines: ' ', '.join([AR.spiData, AR.spiClk,
        #                                       AR.spiLoad]))
        # print()

        # build chain of next to previous
        while True:
            nextnet = AR.chain[-1] + 'next'
            # print('nextnet: ' + nextnet)
            # print('nextnet.highestnetname(pysch): ' +
            #       nextnet.highestnetname(pysch))

            # fanout = nextnet.highestnetname(pysch).fanout(pysch)
            fanout = nextnet.expandnetname(pysch, short=True)
            # print('fanout:\n    ' +
            #       '\n    '.join([str(x) for x in fanout]))
            # prevnet is the net that has the name previous (in the next cell)
            prevnet = [x for x in fanout if str(x.netname) == 'previous']
            if len(prevnet) == 0:
                break
            elif len(prevnet) > 1:
                raise ASPIError('next should go to no more previous ports ' +
                                'than 1 other block')
            else:
                nextcell = [x for x in fanout if str(x.netname) == 'previous']
            #     print('nextcell: ' + str(nextcell))
                assert len(nextcell) == 1
                nextadress = prevnet[0] - 1
            #     print('nextadress: ' + nextadress)
                AR.chain.append(nextadress)
        # print('AR.chain:\n   ' + '\n   '.join(AR.chain))
        a = 0
        d = 0
        for i, address in enumerate(AR.chain):
            if i == 0:
                assert (re.match(ASPI_COMMONS, address.subcktname(pysch))
                        is not None)
                state = 'c'
            else:
                assert (re.match(ASPI_COMMONS, address.subcktname(pysch))
                        is None)
                if i == 1:
                    assert (re.match(ASPI_ADDRESS, address.subcktname(pysch))
                            is not None)
                    state = 'a'
                    a += 1
                else:
                    if state == 'a':
                        if (re.match(ASPI_DATA, address.subcktname(pysch))
                                is not None):
                            state = 'd'
                            # d += 1  // counted later
                        if state == 'a':
                            assert (re.match(ASPI_ADDRESS,
                                             address.subcktname(pysch))
                                    is not None)
                            a += 1
                    if state == 'd':
                        assert (re.match(ASPI_DATA, address.subcktname(pysch))
                                is not None)
                        d += 1
        print('c' + 'a' + str(a) + 'd' + str(d))
        AR.regaddrwidth = a
        AR.datawidth = d

        # print('LSB first  ' + ('{:0'+str(AR.regaddrwidth)+'}').format(0))
        regaddr = 0
        for bitno, x in enumerate(AR.chain[1:a+1]):
            print('bitno: ' + str(bitno))
            id_hnn = [(x + 'id').highestnetname(pysch)]
            prevsize = 0
            all_id_hnn = id_hnn

            size = len(all_id_hnn)
            power = [x.netname.ispower() for x in all_id_hnn]
            while (not (max(power) or min(power))) and prevsize != size:
                print('  size: ' + str(size))
                prevsize = size
                new_all_id = []
                for hnn in all_id_hnn:
                    new_all_id.extend(hnn.expandnetname(pysch))

                power = [x.netname.ispower() for x in new_all_id]
                if max(power) or min(power):
                    logging.debug('project: ' + project + ' cellname: ' +
                                  cellname + ', hnn (' + str(hnn) + ') ' +
                                  'does not suggest being a power net, ' +
                                  'while a lower level does.')
                    print('Make sure the address bits connect to top-level ' +
                          'nets that are called *vcc* or *vee* or *vdd* or ' +
                          '*vss*. Not doing so slows the extraction down a lot')
                    break  # while

                all_id_hnn_set = set()
                for expnn in new_all_id:
                    for expnnfo in expnn.fanout(pysch, short=True):
                        all_id_hnn_set.add(expnnfo.highestnetname(pysch))

                all_id_hnn = list(all_id_hnn_set)

                size = len(all_id_hnn)
                power = [x.netname.ispower() for x in all_id_hnn]

            if (max(power) != min(power) and max(power) and min(power)):
                raise ASPIError('Positive and negative power found in ' +
                                str(id_hnn))
            elif max(power) == 1:
                addressbit = 1
            elif min(power) == -1:
                addressbit = 0

            regaddr += addressbit * 2**bitno

        AR.regaddr = regaddr
        print('AR.regaddr: ' + str(AR.regaddr) + ' [' + str(AR.regaddrwidth) +
              ' bit] ' + ('{:0'+str(AR.regaddrwidth)+'b}').format(AR.regaddr))

        # AR.data = []
        # AR.ndata = []
        for bitno, x in enumerate(AR.chain[a+1:a+d+1]):
            data_hnn = (x + 'data').highestnetname(pysch)
            ndata_hnn = (x + 'ndata').highestnetname(pysch)

            for dnd, hnn in enumerate([data_hnn, ndata_hnn]):
                othernames = []
                if altnames:
                    expanded = hnn.expandnetname(pysch)
                    for net in expanded:
                        if (not net.netname.isunnamed() and
                                str(net.netname) not in othernames):
                            othernames.append(str(net.netname))
                if dnd == 0:
                    AR.data[bitno] = (hnn.netname, hnn.definition, othernames)
                else:
                    AR.ndata[bitno] = (hnn.netname, hnn.definition, othernames)
                print((('n' if dnd else ' ') + 'data<{:2}>: {}  [ {} ] // {}'
                       ).format(bitno, hnn.netname, hnn.definition,
                                str(othernames)))

    regs_addr.sort(key=lambda x: [x.spiData, x.spiClk, x.spiLoad, x.regaddr,
                                  x.address])
    return regs_addr


def argparse_setup(subparsers):
    parser_aspi_exp = subparsers.add_parser(
            'export', help=('Exports a report from the ASPI cells found' +
                            'in the design.'))
    parser_aspi_exp.add_argument(
            '-p', '--project', required=True, help='the PROJECT name')
    parser_aspi_exp.add_argument(
            '-c', '--cellname', required=True, default=None,
            help='the CELL name (or all cells from project.sp)')
    parser_aspi_exp.add_argument(
            '-t', '--filetype', required=True,
            choices=['json', 'txt', 'csv', 'all'], help='the output file type')
    parser_aspi_exp.add_argument(
            '-o', '--outfile', default=None,
            help=('location of the output file, default: T:\\LayoutToolbox' +
                  '\\projects\\<project>\\var\\ASPI_<project>.<json/txt/csv>'))
    parser_aspi_exp.add_argument(
            '-nobu', '--nobackup', dest='backup', default=True,
            action='store_false', help='makes no backup (anymore)')
    parser_aspi_exp.add_argument(
            '-f', '--force', default=False,
            action='store_true', help=('forces execution with some checks ' +
                                       'disabled, NOT RECOMMENDED.'))
    parser_aspi_exp.add_argument(
            '-s', '--skip_analysis', default=False,
            action='store_true', help=('Skips time-consuming process of ' +
                                       'schematic analyis and takes analysis' +
                                       ' results of previous runs.'))


def argparse_eval(args):
    # make a dict of args
    dictargs = vars(args)
    funcdict = {'export': (export,
                           [dictargs.get('project'),
                            dictargs.get('cellname'),
                            dictargs.get('filetype'),
                            dictargs.get('backup'),
                            dictargs.get('outfile'),
                            dictargs.get('force'),
                            dictargs.get('skip_analysis')])
                }
    return funcdict


if __name__ == "__main__":
    general.logsetup()
    general.myargparse(argparse_setup, argparse_eval, 'v20230926')
