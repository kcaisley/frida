import json
import pathlib

try:
    import colorama
except ModuleNotFoundError:
    colorama = None
import logging      # in case you want to add extra logging
import general
import settings
import LTBsettings


class UnknownTechnology(general.LTBError):
    pass


PROJset = settings.PROJECTsettings()

# info on gdsII file format:
# http://boolean.klaasholwerda.nl/interface/bnf/gdsformat.html#rec_header
_BGNSTR = 5
_STRNAME = 6
_ENDSTR = 7
_BOUNDARY = 8
_PATH = 9
_TEXT = 12
_LAYER = 13
_DATATYPE = 14
_TEXTTYPE = 22
_ENDLIB = 4


def layers_used(gdsfilename, seperate_ports_polygons=False):
    alllayers = []
    polygonlayers = []
    portlayers = []

    gds = pathlib.Path(gdsfilename)
    if gds.exists():
        size = gds.stat().st_size

    pct = 0
    checkevery = 100000
    checkprogress = checkevery
    header = b''
    cellname = b''
    prevheader = header
    endlib = False
    with open(gds, 'rb') as stream:
        while not endlib:
            checkprogress -= 1
            if checkprogress == 0:
                checkprogress = checkevery
                print('.', end='')
                if int(stream.tell() * 100 / size) > pct:
                    pct = int(stream.tell() * 100 / size)
                    print(str(pct) + '%')

            prevheader = header
            header = stream.read(4)
            headersize = header[0]*256+header[1]
            headertype = header[2]
            datasize = headersize - 4
            assert datasize >= 0
            # if datasize < 0:
            #     if prevheader==ENDLIB
            #     print(stream.tell() + ' :' + header +
            #           ' (after: '  + prevheader + ')')
            #     datasize == 0

            if headertype == _ENDLIB:
                endlib = True
            elif headertype == _STRNAME:
                data = stream.read(datasize)
                cellname = data
            elif headertype == _LAYER:
                assert datasize == 2
                data = stream.read(datasize)
                gdsnr = data[0]*256+data[1]
                if data[0] != 0:
                    print('WARNING: ')
                    if prevheader[2] == _BOUNDARY:
                        print('Polygon', end='')
                    elif prevheader[2] == _TEXT:
                        print('Port/Label', end='')
                    else:
                        print('Object')
                    print(' with GDSnr > 256', end='')
                    print(' in cell with name: ' + cellname[:-1].decode())
                prevprevheader = prevheader
                # prevheader = header
                header = stream.read(4)
                headersize = header[0]*256+header[1]
                headertype = header[2]
                datasize = headersize - 4
                assert headertype in [_DATATYPE, _TEXTTYPE]
                assert datasize == 2
                data = stream.read(datasize)
                gdsdt = data[0]*256+data[1]
                if data[0] != 0:
                    print('WARNING: ')
                    if prevprevheader[2] == _BOUNDARY:
                        print('Polygon', end='')
                    elif prevprevheader[2] == _TEXT:
                        print('Port/Label', end='')
                    else:
                        print('Object')
                    print(' with GDSdt > 256', end='')
                    print(' in cell with name: ' + cellname[:-1].decode())

                if seperate_ports_polygons:
                    if prevprevheader[2] == _BOUNDARY:
                        if (gdsnr, gdsdt) not in polygonlayers:
                            polygonlayers.append((gdsnr, gdsdt))
                    elif prevprevheader[2] == _TEXT:
                        if (gdsnr, gdsdt) not in portlayers:
                            print('Port/Label on layer (' + str(gdsnr) + ', ' +
                                  str(gdsdt) + ') first occurence in  cell ' +
                                  'with name: ' + cellname[:-1].decode())
                            portlayers.append((gdsnr, gdsdt))

                if (gdsnr, gdsdt) not in alllayers:
                    alllayers.append((gdsnr, gdsdt))
            else:
                stream.seek(datasize, 1)
    if seperate_ports_polygons:
        return portlayers, polygonlayers
    else:
        return alllayers


def translate(gdsinfilename, gdsoutfilename=None, transtable=None):
    gds = pathlib.Path(gdsinfilename)
    if gds.exists():
        size = gds.stat().st_size

    checkevery = 1000
    checkprogress = checkevery
    header = b''
    cellname = b''
    prevheader = header
    endlib = False

    pb = None
    up = 0

    with open(gds, 'rb') as stream:
        with open(gdsoutfilename, 'wb') as streamout:
            while not endlib:
                checkprogress -= 1
                if checkprogress == 0:
                    checkprogress = checkevery
                    pb = general.progressbar(stream.tell() / size, 50, pb, up)

                prevheader = header
                header = stream.read(4)
                headersize = header[0]*256+header[1]
                headertype = header[2]
                datasize = headersize - 4
                assert datasize >= 0
                # if datasize < 0:
                #     if prevheader==ENDLIB
                #     print(stream.tell() + ' :' + header +
                #           ' (after: '  + prevheader + ')')
                #     datasize == 0

                if headertype == _ENDLIB:
                    endlib = True
                    streamout.write(header)

                elif headertype == _STRNAME:
                    data = stream.read(datasize)
                    cellname = data
                    streamout.write(header)
                    streamout.write(data)

                elif headertype == _LAYER:
                    assert datasize == 2
                    data = stream.read(datasize)
                    gdsnr = data[0]*256+data[1]
                    if data[0] != 0:
                        print('WARNING: ')
                        up += 1
                        if prevheader[2] == _BOUNDARY:
                            print('Polygon', end='')
                        elif prevheader[2] == _TEXT:
                            print('Port/Label', end='')
                        else:
                            print('Object')
                        print(' with GDSnr > 256', end='')
                        print(' in cell with name: ' + cellname[:-1].decode())
                        up += 1
                    prevheader = header
                    header = stream.read(4)
                    headersize = header[0]*256+header[1]
                    headertype = header[2]
                    datasize = headersize - 4
                    assert headertype in [_DATATYPE, _TEXTTYPE]
                    assert datasize == 2
                    data = stream.read(datasize)
                    gdsdt = data[0]*256+data[1]

                    (newgdsnr, newgdsdt) = transtable[(gdsnr, gdsdt)]

                    streamout.write(prevheader)
                    streamout.write(bytes([int(newgdsnr/256), newgdsnr % 256]))
                    streamout.write(header)
                    streamout.write(bytes([int(newgdsdt/256), newgdsdt % 256]))

                else:
                    data = stream.read(datasize)
                    streamout.write(header)
                    streamout.write(data)

    print('\nOutput GDSII file written here: ' + gdsoutfilename + '\n')


def findgdsfilename(project=None, cellname=None, vertype=None,
                    gdsfilename=None):
    if gdsfilename is None:
        if project is None or cellname is None:
            raise Exception('Not enough info: project: ' + str(project) +
                            ', cellname: ' + str(cellname))
        if vertype is None:
            lvsgds = pathlib.Path(LTBsettings.lvsgdsfilepath(project, cellname)) / (
                    cellname + '.gds')
            drcgds = pathlib.Path(LTBsettings.drcgdsfilepath(project, cellname)) / (
                    cellname + '.gds')

            if not lvsgds.exists() and not drcgds.exists():
                raise Exception('GDSfile not in lvs/drc folder, both not ' +
                                'found: \n' + str(lvsgds) + '\n' + str(drcgds))
            if lvsgds.exists() and drcgds.exists():
                gdsfile = [lvsgds, drcgds][
                        lvsgds.stat().st_mtime < drcgds.stat().st_mtime]
            else:
                # there is only one, select is True/False result on table
                gdsfile = [lvsgds, drcgds][drcgds.exists()]
            return gdsfile
        else:
            if vertype == 'drc':
                gdsfile = pathlib.Path(LTBsettings.drcgdsfilepath(project, cellname)) / (
                    cellname + '.gds')
            elif vertype == 'lvs':
                gdsfile = pathlib.Path(LTBsettings.lvsgdsfilepath(project, cellname)) / (
                    cellname + '.gds')
            elif vertype == 'xor1':
                gdsfile = pathlib.Path(LTBsettings.xorgds1filepath(project, cellname)) / (
                        cellname + '.gds')
            elif vertype == 'xor2':
                gdsfile = pathlib.Path(LTBsettings.xorgds1filepath(project, cellname)) / (
                        cellname + '.gds')
            elif vertype == 'yld':
                gdsfile = pathlib.Path(LTBsettings.yldgdsfilepath(project)) / (
                    cellname + '.gds')
            else:
                Exception('unknown verification type')
            return gdsfile
    else:
        return pathlib.Path(gdsfilename)


def layersummary(project=None, cellname=None, vertype=None, gdsfilename=None,
                 source=None, outfile=None):
    gdstable = {}
    logtxt = ''

    if source is None:
        if project is not None:
            global PROJset
            PROJset.loaddefault(project)
            PROJset.load()
            projectcheck = PROJset.get_str('projectname')
            if projectcheck != project:
                warning = ('\nWARNING!! \nSelected project (' + project +
                           ') does not match the projectname defined in ' +
                           LTBsettings.projectsettings() + ' (' +
                           projectcheck + ').')
                # print(warning)
                # general.error_log(warning)
                raise Exception(warning)
            source = PROJset.get_str('technologyname')
            print('source: ' + source)
            logtxt += 'source: ' + source + '\n'

    if source is not None:
        gdssheet = json.load(open(LTBsettings.defaultgdssheet(),'r'))
        techs = []
        for tech in gdssheet:
            techs.append(tech['name'])

        if source not in techs:
            warn = 'unknown source technology: ' + str(source)
            print(warn)
            logging.warning(warn)
        else:
            gdstable = gdssheet[techs.index(source)]

    gdsfile = findgdsfilename(project, cellname, vertype, gdsfilename)

    if gdsfile is None:
        raise Exception('GDS file not found')
    else:
        print('GDS File: ' + str(gdsfile))
        logtxt += 'GDS File: ' + str(gdsfile) + '\n'

    if outfile is None:
        outfile = gdsfile.parent / (gdsfile.stem + '_layersummary.log')

    portlayers, polygonlayers = layers_used(gdsfile,
                                            seperate_ports_polygons=True)

    for layers, kind in [(portlayers, 'Port'), (polygonlayers, 'Polygon')]:
        layers.sort()
        print('\n' + kind + ' layers used:')
        logtxt += '\n' + kind + ' layers used:\n'

        for gdsnr, gdsdt in layers:
            layer = gdstable.get(str([gdsnr, gdsdt])[1:-1])
            if layer is None:
                print(str(gdsnr) + ' / ' + str(gdsdt))
                logtxt += str(gdsnr) + ' / ' + str(gdsdt) + '\n'
            else:
                print(str(gdsnr) + ' / ' + str(gdsdt) + '   [' + layer + ']')
                logtxt += (str(gdsnr) + ' / ' + str(gdsdt) + '   [' + layer +
                           ']\n')

    general.write(outfile, logtxt, True)


def techtranslate(project=None, cellname=None, vertype=None, gdsfilename=None,
                  source=None, dest=None):

    if colorama is not None:
        colorama.init()

    if source is None:
        if project is not None:
            global PROJset
            PROJset.loaddefault(project)
            PROJset.load()
            projectcheck = PROJset.get_str('projectname')
            if projectcheck != project:
                warning = ('\nWARNING!! \nSelected project (' + project +
                           ') does not match the projectname defined in ' +
                           LTBsettings.projectsettings() + ' (' +
                           projectcheck + ').')
                # print(warning)
                # general.error_log(warning)
                raise Exception(warning)
            source = PROJset.get_str('technologyname')
            print('source: ' + source)

    gdssheet = json.load(open(LTBsettings.defaultgdssheet(),'r'))
    techs = []
    for tech in gdssheet:
        techs.append(tech['name'])

    if source is None or source not in techs:
        raise UnknownTechnology('unknown source technology: ' + str(source))

    if dest is None or dest not in techs:
        raise UnknownTechnology('unknown dest technology: ' + str(dest))

    gdsfile = findgdsfilename(project, cellname, vertype, gdsfilename)

    if gdsfile is None:
        raise Exception('GDS file not found')
    else:
        print('GDS File: ' + str(gdsfile))

    gdstable_src = gdssheet[techs.index(source)]

    gdstable_dst = gdssheet[techs.index(dest)]

    layers = layers_used(gdsfile)

    layers.sort()
    print('Layer translation table:')

    transtable = {}
    for gdsnr, gdsdt in layers:
        if colorama is not None:
            colorrst = colorama.Fore.RESET
        else:
            colorrst = ""
        layername = gdstable_src.get(str([gdsnr, gdsdt])[1:-1])
        if layername is None:
            if colorama is not None:
                colorname = colorama.Fore.YELLOW
            else:
                colorname = ""
            transtable[(gdsnr, gdsdt)] = (0, 0)
        else:
            colorname = ""
            gdsdest = gdstable_dst.get(layername)
            if gdsdest is None:
                transtable[(gdsnr, gdsdt)] = (0, 0)
            else:
                transtable[(gdsnr, gdsdt)] = [int(x) for x in gdstable_dst[layername].split(',')]

        if transtable[(gdsnr, gdsdt)] == (0, 0):
            if colorama is not None:
                colordest = colorama.Fore.YELLOW
            else:
                colordest = ""
        else:
            colordest = ""

        print(str(gdsnr) + ' / ' + str(gdsdt) + '   ' + colorname + '[' +
              str(layername) + ']' + colorrst + ' ' + str((gdsnr, gdsdt)) +
              ' => ' + colordest + str(transtable[(gdsnr, gdsdt)]) + colorrst)

    print('\nAnd now it should start stranslating, fingers crossed.\n')

    gdsoutfilename = str(gdsfile)[:-4] + '_' + dest + '.gds'
    translate(gdsfile, gdsoutfilename, transtable)


def findcelllayer(project=None, cellname=None, vertype=None, gdsfilename=None,
                  gdslayer='0/0', port=False, polygon=False):
    gdsfile = findgdsfilename(project, cellname, vertype, gdsfilename)

    if gdsfile is None:
        raise Exception('GDS file not found')
    else:
        print('GDS File: ' + str(gdsfile))

    if not port and not polygon:
        port = True
        polygon = True

    findgdsnr = int(gdslayer.split('/')[0])
    findgdsdt = int(gdslayer.split('/')[1])

    layers = []
    gds = pathlib.Path(gdsfile)
    if gds.exists():
        size = gds.stat().st_size

    pct = 0
    checkevery = 100000
    checkprogress = checkevery
    header = b''
    cellname = b''
    # prevheader = header
    endlib = False
    with open(gds, 'rb') as stream:
        while not endlib:
            checkprogress -= 1
            if checkprogress == 0:
                checkprogress = checkevery
                print('.', end='')
                if int(stream.tell() * 100 / size) > pct:
                    pct = int(stream.tell() * 100 / size)
                    print(str(pct) + '%')

            prevheader = header
            header = stream.read(4)
            headersize = header[0]*256+header[1]
            headertype = header[2]
            datasize = headersize - 4
            assert datasize >= 0
            # if datasize < 0:
            #     if prevheader==ENDLIB
            #     print(stream.tell() + ' :' + header +
            #           ' (after: '  + prevheader + ')')
            #     datasize == 0

            if headertype == _ENDLIB:
                endlib = True

            if headertype == _STRNAME:
                data = stream.read(datasize)
                cellname = data
            elif headertype == _LAYER:
                assert datasize == 2
                data = stream.read(datasize)
                gdsnr = data[0]*256+data[1]
                prevprevheader = prevheader
                # prevheader = header
                header = stream.read(4)
                headersize = header[0]*256+header[1]
                headertype = header[2]
                datasize = headersize - 4
                assert headertype in [_DATATYPE, _TEXTTYPE]
                assert datasize == 2
                data = stream.read(datasize)
                gdsdt = data[0]*256+data[1]

                if not polygon and prevprevheader[2] == _BOUNDARY:
                    continue  # while
                if not port and prevprevheader[2] == _TEXT:
                    continue  # while

                if (gdsnr, gdsdt) == (findgdsnr, findgdsdt):
                    print(cellname)
            else:
                stream.seek(datasize, 1)
    return layers


def cellreplace(initialgdsfile, newgdsfile, outgdsfile, backup=True):
    infile = findgdsfilename(None, None, None, initialgdsfile)
    libfile = findgdsfilename(None, None, None, newgdsfile)

    if infile is None:
        raise Exception('Initial GDS file not found' + str(initialgdsfile))
    if libfile is None:
        raise Exception('Library GDS file not found' + str(newgdsfile))
    else:
        print('Initial GDS File: ' + str(gdsfile))

    general.prepare_write(outgdsfile, backup)
    with open(outfilename, 'w') as fp:
        json.dump(techdictlist, fp, indent=2)

    gdsfile = findgdsfilename(project, cellname, vertype, gdsfilename)

def argparse_setup(subparsers):
    parser_lay_sum = subparsers.add_parser(
            'layersummary', help='list all layers used in the GDSII file')
    parser_lay_sum.add_argument(
            '-p', '--project', default=None, help='the PROJECT name')
    parser_lay_sum.add_argument(
            '-c', '--cellname', default=None, help='the CELL name')
    parser_lay_sum.add_argument(
            '-v', '--vertype', default=None,
            choices=['lvs', 'drc', 'xor1', 'xor2', 'yld'],
            help='verification type')
    parser_lay_sum.add_argument(
            '-f', '--filename', default=None,
            help=(r'the GDS file name (full path), default: the newest of ' +
                  r'the drc/lvs gds file location '))
    parser_lay_sum.add_argument(
            '-s', '--source', default=None,
            help=('the source technology of the GDS file ' +
                  '(Note: overrules project setting)'))
    parser_lay_sum.add_argument(
            '-o', '--outfile', default=None,
            help=('the layer summary log file, default: ' +
                  r'<cellname>_layersummary.log in the gds file location'))

    parser_lay_translate = subparsers.add_parser(
            'techtranslate',
            help='translate layers from one technology into another')
    parser_lay_translate.add_argument(
            '-p', '--project', default=None,
            help='the PROJECT name of the source GDS')
    parser_lay_translate.add_argument(
            '-c', '--cellname', default=None,
            help='the CELL name of the source GDS')
    parser_lay_translate.add_argument(
            '-v', '--vertype', default=None,
            choices=['lvs', 'drc', 'xor1', 'xor2', 'yld'],
            help='verification type')
    parser_lay_translate.add_argument(
            '-f', '--filename', default=None,
            help=r'the source GDS file name (full path)')
    parser_lay_translate.add_argument(
            '-s', '--source', default=None,
            help=('the source technology of the GDS file ' +
                  '(Note: overrules project setting)'))
    parser_lay_translate.add_argument(
            '-d', '--dest', required=True,
            help='the destination technology of the GDS file')

    parser_find_cell_layer = subparsers.add_parser(
            'findcelllayer',
            help='find the cell(s) using a certain GDS layer')
    parser_find_cell_layer.add_argument(
            '-p', '--project', default=None,
            help='the PROJECT name of the source GDS')
    parser_find_cell_layer.add_argument(
            '-c', '--cellname', default=None,
            help='the CELL name of the source GDS')
    parser_find_cell_layer.add_argument(
            '-v', '--vertype', default=None,
            choices=['lvs', 'drc', 'xor1', 'xor2', 'yld'],
            help='verification type')
    parser_find_cell_layer.add_argument(
            '-f', '--filename', default=None,
            help=r'the source GDS file name (full path)')
    parser_find_cell_layer.add_argument(
            '-g', '--gdslayer', required=True,
            help='GDSnr/dt that is looked for')
    parser_find_cell_layer.add_argument(
            '--port', default=False,
            action='store_true',
            help='Check for that layer used as port only')
    parser_find_cell_layer.add_argument(
            '--polygon', default=False,
            action='store_true',
            help='Check for that layer used as polygon only')

    parser_cell_replace = subparsers.add_parser(
            'cellreplace',
            help='replace the cells in a file with cells from another file')
    parser_cell_replace.add_argument(
            '-i', '--initialfile', required=True,
            help=r'the initial GDS file name (full path)')
    parser_cell_replace.add_argument(
            '-l', '--libfile', required=True,
            help='gds file with new (library) cell definitions (full path)')
    parser_cell_replace.add_argument(
           '-o', '--outfile', default=None, help='the path to the output file.')
    parser_cell_replace.add_argument(
            '--nobackup', dest='backup', default=True, action='store_false',
            help='Avoids creation of backup files of previous output files.')


def argparse_eval(args):
    # make a dict of args
    dictargs = vars(args)
    funcdict = {'layersummary': (layersummary,
                                 [dictargs.get('project'),
                                  dictargs.get('cellname'),
                                  dictargs.get('vertype'),
                                  dictargs.get('filename'),
                                  dictargs.get('source'),
                                  dictargs.get('outfile')]),
                'techtranslate': (techtranslate,
                                  [dictargs.get('project'),
                                   dictargs.get('cellname'),
                                   dictargs.get('vertype'),
                                   dictargs.get('filename'),
                                   dictargs.get('source'),
                                   dictargs.get('dest')]),
                'findcelllayer': (findcelllayer,
                                  [dictargs.get('project'),
                                   dictargs.get('cellname'),
                                   dictargs.get('vertype'),
                                   dictargs.get('filename'),
                                   dictargs.get('gdslayer'),
                                   dictargs.get('port'),
                                   dictargs.get('polygon')]),
                'cellreplace': (cellreplace,
                                [dictargs.get('initialfile'),
                                 dictargs.get('libfile'),
                                 dictargs.get('outfile'),
                                 dictargs.get('backup')])}
    return funcdict


if __name__ == "__main__":
    general.logsetup()
    general.myargparse(argparse_setup, argparse_eval, 'v20240909')
