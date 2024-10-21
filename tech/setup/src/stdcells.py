import spice
import settings
import logging      # in case you want to add extra logging
import general
import LTBsettings


USERset = settings.USERsettings()
PROJset = settings.PROJECTsettings()


def filter(project, cellname=None, libraryname=None, backup=True, force=False):
    global USERset
    USERset.load()
    global PROJset
    PROJset.loaddefault(project)
    PROJset.load()
    projectcheck = PROJset.get_str('projectname')
    if projectcheck != project:
        warning = ('\nWARNING!! \nSelected project (' + project +
                   ') does not match the projectname defined in ' +
                   LTBsettings.projectsettings() + ' (' + projectcheck + ').')
        logging.warning(warning)
        raise Exception(warning)

    check = not force
    # # read netlist
    # fullnetlist = spice.netlist(project, cellname)
    #
    # #add lvsstuff that would be added by lvs tool (
    #                              lvs.prepare_lvs_source(project, cellname) )
    # #fullnetlist.write('T:\\' + project + '0.sp')
    # #print("\nfullnetlist.write('T:\\padme_inv0.sp')\n\n")
    # caelestefolder = USERset.get_str('caelestefolder')
    # includefilename = PROJset.get_str('sourceinclude').replace(
    #         '/caeleste',caelestefolder)
    # fullnetlist.read(includefilename, overwrite=False, afterNotbefore=False,
    #                  evalinclude=True, caelestefolder=caelestefolder)
    # #fullnetlist.write('T:\\' + project + '1.sp')
    # fullpysch = fullnetlist.export2py()
    fullpysch = spice.netlist2fullpy(project, cellname, check=check)
    # do not use fullpy, because you will get double definitions of subckts
    # later in the process
    # but you need the fullpy to get the full list of parameters
    verifypysch = spice.netlist2py(project, cellname, check=check)
    if cellname is not None:
        fullpysch = fullpysch.trim(cellname)

    if libraryname is None:
        libraryname = 'stdcells'
    # verifypysch = spice.PySchematic(fullpysch.getsource())
    # verifypysch.addparams2top(fullpysch.toplevel.getparams())

    # prepare set for all stdcells
    allstdcells = set()

    # fill set with stdcells, assuming they contain a cell 'PAGEFRAME'.
    # now PAGEFRAME exports design info.
    for subckt in fullpysch.subckts:
        if subckt.getdesign() == libraryname:
            # subckt.setname(subckt.getrealname())
            # take care to verify realcellname and design well
            allstdcells.add(subckt)
        # for spitem in subckt.content:
        #     if spitem.isInstance() and spitem.getsubcktname() == 'PAGEFRAME':
        #         allstdcells.add(subckt)
        # if subckt.getname() == 'PAGEFRAME':
        #     verifypysch.add(subckt)

    # prepare list of cells to verify with and without parameters
    # all of those are put in the verification schematic
    noparamcellstoverify = []
    paramcellstoverify = []

    for stdcell in allstdcells:
        if len(stdcell.getparams()) == 0:
            noparamcellstoverify.append(stdcell)
#            verifypysch.add(stdcell)
        else:
            paramcellstoverify.append(stdcell)
#            verifypysch.add(stdcell)

    noparamcellstoverify.sort()
    paramcellstoverify.sort()

    verificationcellname = ('_all_' + libraryname + '_used_in_' + project +
                            (('_' + cellname) if cellname is not None else ''))
    verificationcell = spice.Subckt(verificationcellname, ['sub', 'gnd'], '')
    # add instances of all cells in new cell '__verify'

    print('Stdcells without parameters:')
    for stdcell in noparamcellstoverify:
        print('{:32} {:60}'.format(stdcell.getname(),
                                   str(stdcell.getparams())))
        # instname = 'X' + stdcell.getname()
        # subcktname = stdcell.getname()
        # # ports = [instname + '_' + portname for portname in stdcell.ports]
        # portsuffix  = '%03d' % countinstanced
        # ports = [(portsuffix + '_' + p if p not in ['sub','gnd'] else p)
        #          for p in stdcell.ports]
        # paramstring = {}
        # newinstance = spice.Instance(instname, subcktname, ports,
        #                              paramstring)
        # verificationcell.add(newinstance)
        # countinstanced += 1

    print('Stdcells with parameters: (default values)')
    for stdcell in paramcellstoverify:
        print('{:32} {:60}'.format(stdcell.getname(),
                                   str(stdcell.getparams())))
#        print(stdcell.getname() + ':\n\t\t\t\t' + str(stdcell.getparams()))

    cellstoverify = noparamcellstoverify + paramcellstoverify

    # tlports = ['sub', 'gnd']

    countinstanced = 1
    for stdcell in cellstoverify:
        listofparams = fullpysch.getParamsUsedSubckt(stdcell.getname())
        listofparams.sort()
        for params in listofparams:
            # instname = 'X' + stdcell.getname() + params.export_autogen()
            instname = 'Xstdcell<%d>' % (countinstanced)
            print('{: <.15} {: <.30} {}'.format(instname, stdcell.getname(),
                                                params))
            # instname = 'X' + stdcell.getname()
            subcktname = stdcell.getname()
            # ports = [instname + '_' + portname for portname in stdcell.ports]
            portsuffix = '%.3s%03d_' % (stdcell.getrealname(), countinstanced)
            ports = [(portsuffix + '_' + p if p not in ['sub', 'gnd'] else p)
                     for p in stdcell.ports]
            # tlports.extend([port for port in ports if port not in
            #                 ['sub','gnd']])
            verificationcell.addports([port for port in ports if port not in
                                       ['sub', 'gnd']])
            paramstring = params
            newinstance = spice.Instance(instname, subcktname, ports,
                                         paramstring)
            verificationcell.add(newinstance)
            countinstanced += 1

    # verificationcell.ports = tlports

    if False:
        subcktslist = list(fullpysch.subckts)
        subcktslist.sort()
        for stdcell in paramcellstoverify:
            # print used stdcell with potentially different param value
            print(stdcell.getname() + ':\n\t' + str(stdcell.getparams()))
            for subckt in subcktslist:
                contentl = list(subckt.content)
                contentl.sort()
                for spitem in contentl:
                    if (spitem.isInstance() and
                            spitem.getrealsubcktname() == stdcell.getname() and
                            spitem.getsubcktdesign() == libraryname):
                        print('    @' + subckt.getname() + ':')
                        nonvalues = False
                        for param in spitem.getparams():
                            if spitem.getparams().isNumValue(param):
                                print('\tValue: ' + repr(param) + ': ' +
                                      str(spitem.getparams()[param]))
                            else:
                                nonvalues = True
                                print('\tNotValue: ' + repr(param) + ': ' +
                                      str(spitem.getparams()[param]))
                        if nonvalues:
                            print('\t\t' + str(subckt.getparams()))
                            # # recursively look for those
                        else:
                            # # add inst to verificationcell
                            # instname = ('X' + stdcell.getname() +
                            #             spitem.getparams().export_autogen())
                            # if not verificationcell.hasContent(instname):
                                # subcktname = stdcell.getname()
                                # portsuffix  = '%03d' % countinstanced
                                # ports = [(portsuffix + '_' + p if p not in
                                #          ['sub','gnd'] else p) for p in
                                #          stdcell.ports]
                                # paramstring = spitem.getparams()
                                # newinstance = spice.Instance(instname,
                                #                              subcktname,
                                #                              ports,
                                #                              paramstring)
                                # verificationcell.add(newinstance)
                                # countinstanced += 1
                            pass

    verifypysch.add(verificationcell)
    verifypysch = verifypysch.trim(verificationcellname)
    filepath = LTBsettings.seditfilepath(project)
    stdcellfile = filepath + verificationcellname + '.sp'

    print(stdcellfile)

    verifypysch.export_spicefile(stdcellfile, backup=backup)

    return verifypysch


def obsolete(project, cellname=None, listofcells=None, backup=True):
    global USERset
    USERset.load()
    sep = USERset.get_type('CSVseparator')
    CSVheader = USERset.get_type('CSVheadersep')
    global PROJset
    PROJset.loaddefault(project)
    PROJset.load()
    projectcheck = PROJset.get_str('projectname')
    if projectcheck != project:
        warning = ('\nWARNING!! \nSelected project (' + project +
                   ') does not match the projectname defined in ' +
                   LTBsettings.projectsettings() + ' (' + projectcheck + ').')
        # print(warning)
        # general.error_log(warning)
        raise Exception(warning)

    if listofcells is None:
        listofcells = (r'S:\projects\scib\standard\schematic' +
                       r'\lib_maintenance\non_SEditfiles\obsolete.csv')

    if CSVheader:
        output = sep.join(['sep=', '\n'])
    else:
        output = ''

    output += 'OBSOLETE CELLS\n'
    obscells = set()
    firstline = True
    sep_scr = sep
    with open(listofcells, 'r') as lc:
        for line in lc:   # including newlines
            if firstline:
                firstline = False
                if line.startswith('sep='):
                    sep_src = line[4]
                    continue  # for line in lc
            design, cell = line[:-1].split(sep_scr)
            obscells.add((design, cell))
            output += 'Cell: ' + cell + ' | Design: ' + design + '\n'

    fullpysch = spice.netlist2fullpy(project, cellname, check=False)

    output += 'CELLS CONTAINING OBSOLETE CELLS\n'

    for subckt in fullpysch.subckts:
        if (subckt.design, subckt.realname) in obscells:
            found = ('\n' + subckt.realname + ' (' + subckt.design +
                     ') [.subckt ' + subckt.name + ']')
            # print(found + ' used in:')
            output += found + ' used in:' + '\n'
            for parent in fullpysch.subckts:
                for inst in parent.getcontent():
                    if inst.isInstance():
                        if inst.subcktname == subckt.name:
                            where = ('* ' + parent.realname + ' (' +
                                     str(parent.design) + ')')
                            # print(where)
                            output += where + '\n'
                            break

    print(output)


def obsoletelist(libraries, liblocation=None, outfile=None, backup=True):
    global USERset
    USERset.load()
    sep = USERset.get_type('CSVseparator')
    CSVheader = USERset.get_type('CSVheadersep')
    if liblocation is None:
        liblocation = r'S:\projects\scib\standard\schematic'
    if outfile is None:
        outfile = (r'S:\projects\scib\standard\schematic' +
                   r'\lib_maintenance\non_SEditfiles\obsolete.csv')

    obscells = []
    for lib in libraries:
        filename = liblocation + '\\' + lib + r'\design.edif'
        with open(filename, 'r') as edif:
            lineno = 0

            for line in edif:
                lineno += 1
                if line.startswith('\t\t(cell '):
                    cell = line[8:-1]
                if line == '\t\t}\n':
                    cell = ''
                if 'obsol' in line.lower():
                    obscells.append((lib, cell))
                    print(str(lineno) + ': ' + cell + '(' + lib + ')')
    obscells.sort()
    prev = sep
    if CSVheader:
        writetxt = sep.join(['sep=', '\n'])
    else:
        writetxt = ''

    for x in obscells:
        this = sep.join([x[0],x[1]])
        if this != prev:
            writetxt += this + '\n'
        prev = this
    general.write(outfile, writetxt, backup)

def count(project, cellname=None, libraryname=None, force=False, noparams=False, 
          outfile=None, backup=True):
    report = 'count(' +repr(project)+', '+repr(cellname)+', '+repr(libraryname)+', '+repr(force)+', '+repr(noparams)+', '+repr(outfile)+', '+repr(backup)+'): \n\n'
    global USERset
    USERset.load()
    global PROJset
    PROJset.loaddefault(project)
    PROJset.load()
    if outfile is None:
        outfile = ('{}count_{}_{}{}.txt'
                   ).format(LTBsettings.varfilepath(project), cellname, 
                            'all' if libraryname is None else libraryname, 
                            '_np' if noparams else '')
                   
    else:
        if os.path.isdir(outfile):
            raise general.LTBError('outfile should be filename, not a folder name')

    projectcheck = PROJset.get_str('projectname')
    if projectcheck != project:
        warning = ('\nWARNING!! \nSelected project (' + project +
                   ') does not match the projectname defined in ' +
                   LTBsettings.projectsettings() + ' (' + projectcheck + ').')
        logging.warning(warning)
        raise Exception(warning)

    check = not force
    fullpysch = spice.netlist2fullpy(project, cellname, check=check)
    verifypysch = spice.netlist2py(project, cellname, check=check)
    if cellname is not None:
        fullpysch = fullpysch.trim(cellname)

    allstdcells = set()
    for subckt in fullpysch.subckts:
        if libraryname is None or subckt.getdesign() == libraryname:
            allstdcells.add(subckt)
    noparamcellstoverify = []
    paramcellstoverify = []

    for stdcell in allstdcells:
        if len(stdcell.getparams()) == 0:
            noparamcellstoverify.append(stdcell)
#            verifypysch.add(stdcell)
        else:
            paramcellstoverify.append(stdcell)
    noparamcellstoverify.sort()
    paramcellstoverify.sort()
    cellstoverify = noparamcellstoverify + paramcellstoverify
    countinstanced = 1
    report += 'cellname:\tamount\t(netlistcellname(if != cellname)'
    if libraryname is None:
        report += '\t[library]'
    report += '\n'
    for stdcell in cellstoverify:
        if noparams:
            print ('** '+ stdcell.getname())
            number = fullpysch.countSubcktParamsInCell(stdcell,None,cellname,None)
            print(number)
            report += stdcell.getrealname() + ':\t' + str(number) + '\t'
            if stdcell.getrealname() != stdcell.getname():
                report += '(' + stdcell.getname() + ')'
            if libraryname is None:
                report += '\t[?]' if stdcell.getdesign() is None else '\t[' + stdcell.getdesign() + ']'
            report += '\n'
        else:
            listofparams = fullpysch.getParamsUsedSubckt(stdcell.getname())
            listofparams.sort()
            totalnumber = 0
            for params in listofparams:
                print(params)
                paramsAGstr = params.export_autogen()
                print ('** '+ stdcell.getname() + paramsAGstr)
                number = fullpysch.countSubcktParamsInCell(stdcell,params,cellname, spice.Params())
                print(number)
                report += stdcell.getrealname() + paramsAGstr + ':\t' + str(number) + '\t'
                if stdcell.getrealname() != stdcell.getname():
                    report += '(' + stdcell.getname() + ')'
                if libraryname is None:
                    report += '\t[?]' if stdcell.getdesign() is None else '\t[' + stdcell.getdesign() + ']'
                report += '\n'    
                totalnumber += number
            if totalnumber != number:
                report += stdcell.getrealname() + ' (allparams):\t' + str(totalnumber) + '\t'
                if stdcell.getrealname() != stdcell.getname():
                    report += '(' + stdcell.getname() + ')'
                if libraryname is None:
                    report += '\t[?]' if stdcell.getdesign() is None else '\t[' + stdcell.getdesign() + ']'
                report += '\n'    
    print(report)
    general.write(outfile, report, backup)
    
def argparse_setup(subparsers):
    parser_filt = subparsers.add_parser(
            'filter', help='Creates a new spice netlist containing all ' +
            'lower-level stdcells')
    parser_filt.add_argument(
            '-p', '--project', required=True, help='the PROJECT name')
    parser_filt.add_argument(
            '-c', '--cellname', required=True, help='the CELL name, hint: ' +
            'take the highest-level cell in your design')
    parser_filt.add_argument(
            '-d', '--designname', default=None, help='library name that ' +
            'should be considered (default: stdcells))')
    parser_filt.add_argument(
            '--nobackup', dest='backup', default=True, action='store_false',
            help='Avoids creation of backup files of previous output files.')
    parser_obs = subparsers.add_parser(
            'obsolete', help='Lists all cells that contain a cell ' +
            'known as obsolete')
    parser_obs.add_argument(
            '-p', '--project', required=True, help='the PROJECT name')
    parser_obs.add_argument(
            '-c', '--cellname', required=True, help='the CELL name, hint: ' +
            'take the highest-level cell in your design')
    parser_obs.add_argument(
            '-l', '--listofcells', default=None, help='csv file containing ' +
            'list of obsolete cells (default: ' +
            r'S:\projects\scib\standard\schematic' +
            r'\lib_maintenance\non_SEditfiles\obsolete.csv)')
    parser_obs.add_argument(
            '--nobackup', dest='backup', default=True, action='store_false',
            help='Avoids creation of backup files of previous output files.')
    parser_obsl = subparsers.add_parser(
            'obsoletelist', help='Generate list of obsolete cells based on ' +
            'information in the edif file')
    parser_obsl.add_argument(
            '-l', '--libraries', nargs='+',
            default=['stdcells', 'logic', 'io', 'monitors'],
            help="the considered libraries' names.  default: stdcells logic " +
            "io monitors")
    parser_obsl.add_argument(
            '-ll', '--librarylocation', default=None,
            help=r'Library location. S:\projects\scib\standard\schematic')
    parser_obsl.add_argument(
            '-o', '--outfile', default=None, help='csv file containing ' +
            'list of obsolete cells (default: ' +
            r'S:\projects\scib\standard\schematic' +
            r'\lib_maintenance\non_SEditfiles\obsolete.csv)')
    parser_obsl.add_argument(
            '--nobackup', dest='backup', default=True, action='store_false',
            help='Avoids creation of backup files of previous output files.')
    parser_count = subparsers.add_parser(
            'count', help='Counts the number of times each cell of a ' +
            'specific design occurs in a cell and its hierarchy')
    parser_count.add_argument(
            '-p', '--project', required=True, help='the PROJECT name')
    parser_count.add_argument(
            '-c', '--cellname', required=True, help='the CELL name, hint: ' +
            'take the highest-level cell in your design')
    parser_count.add_argument(
            '-d', '--designname', default=None, help='library name that ' +
            'should be considered (default: stdcells))')
    parser_count.add_argument(
            '-f', '--force', default=False,
            action='store_true', help=('forces execution with some checks ' +
                                       'disabled, NOT RECOMMENDED.'))
    parser_count.add_argument(
            '-np', '--noparams', default=False,action='store_true', 
            help=("doesn't discriminate between different parameter sets " +
                                       "(way faster)."))
    parser_count.add_argument(
            '-o', '--outfile', default=None,
            help=('location of the output file, default: T:\\LayoutToolbox' +
                  '\\projects\\<project>\\var\\count_<cellname>_<designname>[_np].txt'))
    parser_count.add_argument(
            '-nobu', '--nobackup', dest='backup', default=True,
            action='store_false', help='makes no backup (anymore)')


def argparse_eval(args):
    # make a dict of args
    dictargs = vars(args)
    funcdict = {'filter': (filter,
                           [dictargs.get('project'),
                            dictargs.get('cellname'),
                            dictargs.get('designname'),
                            dictargs.get('backup')]),
                'obsolete': (obsolete,
                             [dictargs.get('project'),
                              dictargs.get('cellname'),
                              dictargs.get('listofcells'),
                              dictargs.get('backup')]),
                'obsoletelist': (obsoletelist,
                                 [dictargs.get('libraries'),
                                  dictargs.get('librarylocation'),
                                  dictargs.get('outfile'),
                                  dictargs.get('backup')]),
                'count': (count,
                          [dictargs.get('project'),
                           dictargs.get('cellname'),
                           dictargs.get('designname'),
                           dictargs.get('force'),
                           dictargs.get('noparams'),
                           dictargs.get('outfile'),
                           dictargs.get('backup')])
                }
    return funcdict


if __name__ == "__main__":
    general.logsetup()
    general.myargparse(argparse_setup, argparse_eval, 'v20230926')
