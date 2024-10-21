import sys
import general
import sedit
import settings
import spice

PROJset = settings.PROJECTsettings()


def designs_with_cell(celllib, cellname, projectdesignfolder=None):
    designlist = []
    if projectdesignfolder is None:
        pdf = r'S:\projects'
    elif projectdesignfolder == 'all':
        pdf = r'S:\projects'
    else:
        try:
            PROJset = settings.PROJECTsettings(projectdesignfolder)
        except Exception:
            pdf = str(projectdesignfolder)
        else:
            pdf = PROJset.get('schematicsfolder')

    print('pdf: ' + repr(pdf))
    allschematics = sedit.findschematicsin(pdf)

    if celllib.lower().startswith('scib'):
        lib = sedit.Design(r'S:\projects\scib\standard\schematic' + '\\' +
                           celllib[5:])
        print('lib: ' + str(lib))
    else:
        lib = sedit.Design(celllib)

    if lib.has_cell(cellname):
        for design in allschematics:
            if design.has_cell(cellname, lib):
                designlist.append(str(design.path))
        return designlist, pdf, str(lib.path), cellname
    else:
        raise Exception("'" + cellname + "' does not even exist in '" +
                        str(lib.path) + "'.")


def cells_with_cell(celllib, cellname, design):
    d = sedit.Design(design)

    if celllib.lower().startswith('scib'):
        lib = sedit.Design(r'S:\projects\scib\standard\schematic' + '\\' +
                           celllib[5:])
        print('lib: ' + str(lib))
    else:
        lib = sedit.Design(celllib)

    if lib.has_cell(cellname):
        if d.has_cell(cellname, lib):
            cells = d.find_instances(cellname, lib)
            return cells, design, str(lib.path), cellname
        else:
            return [], design, str(lib.path), cellname
    else:
        raise Exception("'" + cellname + "' does not even exist in '" +
                        str(lib.path) + "'.")


def findcell(celllib, cellname, projectdesignfolder=None, verbosity=1,
             outfilename=None):
    from datetime import datetime
    designlist, pdf, libpath, cellname = designs_with_cell(celllib, cellname,
                                                           projectdesignfolder)
    findcellreport = datetime.now().strftime("%A, %d %B %Y %H:%M")
    findcellreport += ('\nfindcell(' + str(celllib) + ',' + str(cellname) +
                       ',' + str(projectdesignfolder) + ',' + str(verbosity) +
                       ',' + str(outfilename) + ")\n\n")

    if len(designlist) == 0:
        findcellreport += ("'" + cellname + "' from '" + libpath +
                           "' NOT found in '" + pdf + "' (and below)\n")
    else:
        findcellreport += ("'" + cellname + "' from '" + libpath +
                           "' IS found in '" + pdf + "' (and below)\n")
        if verbosity > 0:
            for d in designlist:
                findcellreport += d + '\n'
                if verbosity > 1:
                    celllist, design, libpath, cellname = cells_with_cell(
                            celllib, cellname, d)
                    for c in celllist:
                        findcellreport += '\t' + c + '\n'
    findcellreport += '\n\n'
    if outfilename is None:
        sys.stdout.write(findcellreport)
    else:
        with open(outfilename, 'a') as outfile:
            outfile.write(findcellreport)


def subcktwithsubckt(TopPy, subcktname):
    chainofcells = ''
    retval = []
    for checkforsubckt in TopPy.subckts:
        for cont in checkforsubckt.content:
            if cont.isInstance():
                if cont.subcktname == subcktname:
                    print(cont.name + '    ' + checkforsubckt.name)
                    if len(retval) != 0:
                        # this is not the first encounter in this loop
                        print('DOUBLE!!')
                    print('>')
                    chainofcells = subcktwithsubckt(TopPy,
                                                    checkforsubckt.name)
                    print('a: ' + str(chainofcells))
                    for x in chainofcells:
                        retval.append(x + '\\' + cont.name + ' (' +
                                      str(cont.subcktname) + ')')
    print('<')
    if len(retval) == 0:
        return [subcktname]
    else:
        return retval


def numbersindesign(project, cell, outfile):
    TopPy = spice.netlist2py(project, cell)
    numberdict = {}
    listofchains = []
    for checkfornumber in TopPy.subckts:
        for cont in checkfornumber.content:
            if cont.isInstance():
                if cont.subcktname.startswith('number_'):
                    print(cont.subcktname + '    ' + checkfornumber.name)
                    if cont.subcktname in numberdict:
                        print('DOUBLE')
                    else:
                        numberdict[cont.subcktname] = []
                    chainofcells = subcktwithsubckt(TopPy, checkfornumber.name)
                    print('b: ' + str(chainofcells))
                    for x in chainofcells:
                        # listofchains.append((chainofcells + '\\' +
                        #                            checkfornumber.name))
                        numberdict[cont.subcktname].append(
                                x + '\\' + cont.name)
    outputtext = ''
    for x in sorted(numberdict.keys()):
        print(x + ': ' + str(numberdict[x]))
        if len(numberdict[x]) != 1:
            outputtext += '**\t' + x + ': '
            outputtext += ('\n**\t' + x + ': ').join(numberdict[x]) + '\n'
        else:
            outputtext += x + ': ' + str(numberdict[x][0]) + '\n'
    general.write(outfile, outputtext, True)


def argparse_setup(subparsers):
    parser_slc_findcell = subparsers.add_parser(
            'findcell', help='find a schematic cells in your design')
    parser_slc_findcell.add_argument(
            '-c', '--cellname', required=True,
            help='the CELL name to look for')
    parser_slc_findcell.add_argument(
            '-l', '--libfolder', required=True,
            help="the library of the CELL (path or 'scib\libname')")
    parser_slc_findcell.add_argument(
            '-s', '--searchfolder', default=None, help="the name of the root" +
            " folder containing the designs to be investigated. (default: " +
            r"'S:\projects' (= 'all')). if this is a project name, " +
            "searchfolder is project settings dependent " +
            "(project.schematicsfolder).")
    parser_slc_findcell.add_argument(
            '-v', '--verbosity',  type=int, default=1, help="0: shows used " +
            "or not used, 1: lists all designs using the cell, \n 2: shows " +
            r"the cells in the design using the cell.")
    parser_slc_findcell.add_argument(
            '-o', '--outfile',  default=None,
            help="Output file for the results.")

    parser_number = subparsers.add_parser(
            'numbers', help='Check numbers appear only once and where in your design')
    parser_number.add_argument(
            '-p', '--project', required=True,
            help="the project name")
    parser_number.add_argument(
            '-c', '--cellname', required=True,
            help='the top cell name')
    parser_number.add_argument(
            '-o', '--outfile',  default=None,
            help="Output file for the results.")


def argparse_eval(args):
    # make a dict of args
    dictargs = vars(args)
    funcdict = {'findcell': (findcell,
                             [dictargs.get('libfolder'),
                              dictargs.get('cellname'),
                              dictargs.get('searchfolder'),
                              dictargs.get('verbosity'),
                              dictargs.get('outfile')]),
                'numbers': (numbersindesign,
                            [dictargs.get('project'),
                             dictargs.get('cellname'),
                             dictargs.get('outfile')])
                }
    return funcdict


if __name__ == "__main__":
    general.logsetup()
    general.myargparse(argparse_setup, argparse_eval, 'v20221005')
