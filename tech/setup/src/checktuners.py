# -*- coding: utf-8 -*-
"""
Created on Wed Jan 17 15:21:21 2018

@author: Koen
"""
# import logging      # in case you want to add extra logging
import general
import LTBsettings

import spice


def fan_onlydown(fullpy, subckt, portname, level, maxlevel, hierarchy,
                 verbose=0):
    assert level < maxlevel
    if verbose > 0:
        print('  ' * level + '>' + subckt.name + '.' + portname)
    retlist = []
    foundsomethingdeeper = False
    for instance in sorted(subckt.content):
        if instance.isInstance():
            if portname in instance.ports:
                portindex = instance.ports.index(portname)
                deepersubcktname = instance.getsubcktname()
                deepersubckt = fullpy.getSubckt(deepersubcktname)
                deeperportname = deepersubckt.ports[portindex]
                if verbose > 0:
                    print('  ' * (level+1) + '-' + instance.name + '.' +
                          portname)
                deeperhierarchy = hierarchy + instance.name + '.'
                retlist.extend(fan_onlydown(fullpy, deepersubckt,
                                            deeperportname, level + 1,
                                            maxlevel, deeperhierarchy))
                foundsomethingdeeper = True
    if not foundsomethingdeeper:
        retlist = [hierarchy + portname + ' (' + subckt.name + ')']

    return retlist

# def fan_dotdown(fullpy, subckt, portname, level, maxlevel, hierarchy,
#                 verbose=0):
#    """fan_onlydown, but with . compatibility"""
#
#    # go down as long as we have dots in portname
#    firstdot = portname.find('.')
#    retlist = []
#    if firstdot != -1:
#        instancename = portname[:firstdot]
#        if verbose >0:
#            print(instancename)
#        foundsomethingdeeper = False
#        for instance in sorted(subckt.content):
#            if verbose >0:
#                print(instance.name+'?')
#            if instance.isInstance() and instance.name == instancename:
#                deepersubcktname = instance.getsubcktname()
#                deepersubckt = fullpy.getSubckt(deepersubcktname)
#                deeperportname = portname[firstdot+1:]
#                if verbose >0:
#                    print('  ' * (level+1) + '-' + portname)
#                deeperhierarchy = hierarchy + instance.name + '.'
#                retlist.extend(fan_dotdown(fullpy, deepersubckt,
#                                           deeperportname, level + 1,
#                                           maxlevel, deeperhierarchy))
#                foundsomethingdeeper = True
#        if not foundsomethingdeeper:
#            raise Exception('Instance hierarchy not found in schematic')
#        return retlist
#    else:
#        return fan_onlydown(fullpy, subckt, portname, level, maxlevel,
#                            hierarchy)


def fan(fullpy, subckt, portname, level, maxlevel, hierarchy, up, upsubckts='',
        verbose=0):
    """fan_dotdown, but go up as high as possible first"""
    if upsubckts == '':
        upsubckts = subckt.name

    # go down as long as we have dots in portname
    firstdot = portname.find('.')
    retlist = []
    if firstdot != -1:
        instancename = portname[:firstdot]
        if verbose > 0:
            print(instancename)
        foundsomethingdeeper = False
        for instance in sorted(subckt.content):
            if verbose > 0:
                print(instance.name+'?')
            if instance.isInstance() and instance.name == instancename:
                deepersubcktname = instance.getsubcktname()
                deepersubckt = fullpy.getSubckt(deepersubcktname)
                deeperportname = portname[firstdot+1:]
                if verbose > 0:
                    print('  ' * (level+1) + '-' + portname)
                deeperhierarchy = hierarchy + instance.name + '.'
                upsubckts += '.' + deepersubcktname
                retlist.extend(fan(fullpy, deepersubckt, deeperportname,
                                   level + 1, maxlevel, deeperhierarchy, up,
                                   upsubckts))
                foundsomethingdeeper = True
        if not foundsomethingdeeper:
            raise Exception('Instance hierarchy not found in schematic')
        return retlist
    elif up:
        if verbose > 0:
            print('  ' * (level+1) + hierarchy + portname)
        # print('----------')
        # print('hierarchy: ' + hierarchy)
        # print('portname: ' + portname)
        # print('upsubckts: ' + upsubckts)
        if hierarchy != '' and portname in subckt.ports:
            # print("hierarchy.split('.')[-2]: " + hierarchy.split('.')[-2])
            # print("upsubckts.split('.')[-2]: " + upsubckts.split('.')[-2])
            highersubckt = fullpy.getSubckt(upsubckts.split('.')[-2])
            # print('highersubckt: ' + highersubckt.name)
            higherinstname = hierarchy.split('.')[-2]
            # print('higherinstname: ' + higherinstname)

            # print("find portname '" + portname + "' in subckt def of " +
            #       subckt.name)
            portindex = subckt.ports.index(portname)
            # print('portindex: ' + str(portindex))
            for instance in sorted(highersubckt.content):
                # print(instance.name+'?')
                if instance.isInstance() and instance.name == higherinstname:
                    higherportname = instance.ports[portindex]
            tmphier = hierarchy.split('.')
            tmphier.pop(-2)
            higherhierarchy = '.'.join(tmphier)
            higherupsubckts = '.'.join(upsubckts.split('.')[:-1])
            # print('higherhierarchy: ' + higherhierarchy)
            # print('higherportname: ' + higherportname)
            # print('higherupsubckts: ' + higherupsubckts)
            retlist.extend(fan(fullpy, highersubckt, higherportname, level + 1,
                               maxlevel, higherhierarchy, up, higherupsubckts))
        else:
            retlist.extend(fan_onlydown(fullpy, subckt, portname, level + 1,
                                        maxlevel, hierarchy))
    else:
        return fan_onlydown(fullpy, subckt, portname, level + 1, maxlevel,
                            hierarchy)

    return retlist


# def fan_filter(fullpy, subckt, portname, level, maxlevel, hierarchy,
#                filterlist=None):
#    if level > maxlevel:
#        return
#    print('  ' * level + '>' + subckt.name + '.' + portname)
#    retlist = []
#    foundsomethingdeeper = False
#    for instance in sorted(subckt.content):
#        if instance.isInstance():
#            if portname in instance.ports:
#                portindex  = instance.ports.index(portname)
#                deepersubcktname = instance.getsubcktname()
#                deepersubckt = fullpy.getSubckt(deepersubcktname)
#                deeperportname = deepersubckt.ports[portindex]
#                print('  ' * (level+1) + '-' + instance.name + '.' + portname)
#                deeperhierarchy = hierarchy + '.' + instance.name
#                netfromdeeper = (fan(fullpy, deepersubckt, deeperportname,
#                                 level + 1, maxlevel, deeperhierarchy))
#                retlist.extend(netfromdeeper)
#                foundsomethingdeeper = True
#    if not foundsomethingdeeper:
#        retlist = [hierarchy + '.' + portname]
#
#    return retlist


def checktuners(project, cellname):
    fullpy = spice.netlist2fullpy(project, cellname)
    top = fullpy.getSubckt(cellname)
    tunerports = [x for x in top.ports if 'TUNER' in x.upper()]

    ntunerports = [x for x in tunerports if 'NTUNER' in x.upper()]
    ptunerports = [x for x in tunerports if 'PTUNER' in x.upper()]

    # filterlist = [['bondpad.out','bondpad.in']]

    output = ''
    for portlist, devname in [[ntunerports, 'nmos'], [ptunerports, 'pmos']]:
        for tuner in portlist:
            print(tuner)
            output += '='*80 + '\n'
            output += tuner + '\n'
            output += '-'*20 + '\n'
            retlist1 = fan(fullpy, top, tuner, 0, 20, '', False, verbose=0)
            retlist1a = fan_onlydown(fullpy, top, tuner, 0, 20, '', verbose=0)
            retlist1b = fan(fullpy, top, tuner, 0, 20, '', True, verbose=0)
            # retlist = fan_filter(fullpy, top, ntuner, 0, 10, '', filterlist)

            assert str(retlist1) == str(retlist1b)
            assert str(retlist1) == str(retlist1a)

            print('retlist1: ' + str(retlist1))

            for node in retlist1:
                output += node + '\n'
                assert node.split()[1] == '(bondpad)'
                assert node.split()[0][-3:] == 'out'
                portname = node.split()[0][:-3]+'in'
                retlist2 = fan(fullpy, top, portname, 0, 20, '', True)
                print('retlist2: ' + str(retlist2))
                for node2 in retlist2:
                    output += '  - ' + node2 + '\n'
                    if node2.split()[1] == '(rnp1)':
                        assert node2.split()[0][-1:] == 'a'
                        portname = node2.split()[0][:-1]+'b'
                        retlist3 = fan(fullpy, top, portname, 0, 40, '', True)
                        devs = {}
                        for node3 in retlist3:
                            devtype = node3.split()[1][1:-1]
                            portname = node3.split()[0]
                            subportname = portname.split('.')[-1]
                            do_output = True
                            if devname in devtype and subportname == 'G':
                                devs[devtype] = devs.get(devtype, 0) + 1
                                if devs[devtype] > 11:
                                    do_output = False
                                elif devs[devtype] > 10:
                                    output += ('    + ' + devtype + '.' +
                                               subportname + ' : ' + '...' +
                                               '\n')
                                    do_output = False
                            if do_output:
                                output += ('    + ' + devtype + '.' +
                                           subportname + ' : ' + node3 + '\n')
                        for k in devs:
                            times = devs[k]
                            if times > 10:
                                output += ('    + ' + 'and ' +
                                           str(times - 10) + ' times more ' +
                                           k + '.G\n')

    with open(LTBsettings.varfilepath(project) + cellname +
              '_tunercheck.log', 'w') as outf:
        outf.write(output)


def argparse_setup(subparsers):
    parser_ch_tun = subparsers.add_parser(
            'check_tuners', help='check tuners in a given project/cellname')
    parser_ch_tun.add_argument(
            '-p', '--project', required=True, help='the PROJECT name')
    parser_ch_tun.add_argument(
            '-c', '--cellname', required=True, help='the CELL name')


def argparse_eval(args):
    # make a dict of args
    dictargs = vars(args)
    funcdict = {'check_tuners': (checktuners,
                                 [dictargs.get('project'),
                                  dictargs.get('cellname')])
                }
    return funcdict


if __name__ == "__main__":
    general.logsetup()
    general.myargparse(argparse_setup, argparse_eval, 'v20221005')
