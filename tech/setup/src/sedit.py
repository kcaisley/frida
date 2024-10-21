import re
import time
import pathlib
import logging      # in case you want to add extra logging
import pprint
import general


class Design():
    def __init__(self, path):
        """create a link to an S-Edit design using its file path.
        The design does not have to exist."""
        self.path = pathlib.Path(path)
        self.name = self.path.name
        self.liblist = self.path / 'libraries.list'
        self.design = self.path / 'design.edif'
        self.tannerfile = self.path / (self.name+'.tanner')
        self.xmlfile = self.path / 'dockinglayout.xml'
        self.allfiles = [self.liblist, self.design, self.tannerfile,
                         self.xmlfile]
        self.requiredfiles = [self.liblist, self.design, self.tannerfile]
        self.setup = self.path / 'setup'
        self.allfolders = [self.setup]
        self.allfilesfolders = self.allfiles + self.allfolders

    def __repr__(self):
        return "sedit.Design(" + repr(str(self.path)) + ")"

    def __eq__(self, other):
        if self.__class__ == other.__class__:
            if str(self.path).lower() == str(other.path).lower():
                return True
        return False

    def exists(self):
        for x in self.requiredfiles:
            if not x.exists():
                return False
        for x in self.allfilesfolders:
            if not x.exists():
                # print(str(x) + ' missing in Seditfolder.')
                pass
        return True

    def get_liblinks(self):
        if self.exists():
            with open(self.liblist) as llf:
                liblinklist = llf.readlines()
                if len(liblinklist) > 0 and liblinklist[-1][-1] != '\n':
                    logging.warning("Manually modified libraries.list in :'" +
                                    str(self.path) + "'")
                    liblinklist[-1] += '\n'
                return liblinklist
        else:
            raise Exception('non-existing library')

    def get_liblinkdict(self, nest=20, tree=['..']):
        # returns a dictionary
        # key = name of one of all depndent libraries
        # value = list of lists*
        # list*[0] = way towards this lib ('..' is top)
        # list*[1] = full path of the lib (should all be the same if correctly
        #                                  consolidated**)
        # ** use check_liblinkdict to verify
        liblinkdict = {}
        if self.exists():
            # do not forget to add itself!! (bad example: consolidated from
            #                                CASPAR2 @ 20170420)
            llpathname = self.path.name
            llpathlink = resolve2dots(str(self.path))
            liblinkdict[llpathname] = [[tree, llpathlink]]

            for ll in self.get_liblinks():
                if ll.startswith('..'):
                    llpath = self.path / ll[:-1]
                else:
                    llpath = pathlib.Path(ll[:-1])

                llpathname = llpath.name
                llpathlink = resolve2dots(str(llpath))

                liblinkdict[llpathname] = [[tree, llpathlink]]

            if nest > 0:
                for ll in self.get_liblinks():
                    if ll.startswith('..'):
                        llpath = self.path / ll[:-1]
                    else:
                        llpath = pathlib.Path(ll[:-1])

                    llpathname = llpath.name
                    llpathlink = resolve2dots(str(llpath))

                    if llpathname.lower() not in tree:
                        deeptree = tree + [llpathname.lower()]
                        subliblinkdict = Design(llpathlink).get_liblinkdict(
                                nest - 1, deeptree)
                        for key in subliblinkdict:
                            if key not in liblinkdict.keys():
                                liblinkdict[key] = []
                            for finaltree, link in subliblinkdict[key]:
                                liblinkdict[key].append([finaltree, link])
            else:
                print('maybe make nest longer: ' + repr(llpathname) +
                      'not in ' + str(tree))

        return liblinkdict

    def get_dependencies(self, keepCase=False):
        liblinkdict = self.get_liblinkdict()
        alllinks = set()

        for lib in liblinkdict:
            links = set()
            for tree, link in liblinkdict[lib]:
                if keepCase:
                    links.add(link)
                    alllinks.add(link)
                else:
                    links.add(link.lower())
                    alllinks.add(link.lower())
            if len(links) > 1:
                warning = ('Warning: Multiple links for same library in ' +
                           'design: ' + str(self.path))
                print(warning)
                logging.warning(warning)
        return alllinks

    def check_liblinkdict(self):
        liblinkdict = self.get_liblinkdict()

        text = ''

        for lib in liblinkdict:
            links = set()
            for tree, link in liblinkdict[lib]:
                links.add(link.lower())
            linkslist = list(links)
            linkslist.sort()
            if len(links) > 1:
                for liblink in linkslist:
                    if len(text) == 0:
                        text = ('Multiple links for same library in design: ' +
                                str(self.path) + '\n')
                        print(text[:-1])
                    text += '\t' + liblink + ':\n'
                    for tree, link in liblinkdict[lib]:
                        if link.lower() == liblink:
                            text += '\t\t' + '>'.join(tree) + ':\n'

        return text

    def findLibraryPathByName(self, libName):
        # A.C. @ 11/05/2018: By just a library-name (e.g. a string "spice");
        #        we get from the libraries.list the full path to this library
        for line in self.get_liblinks():
            if libName in line:
                if line[:-1].startswith('..'):
                    # print('the local path cell:' + str(self.path))
                    llpath = self.path / line[:-1]
                else:
                    llpath = pathlib.Path(line[:-1])
                llpathlink = resolve2dots(str(llpath))
                if (Design(llpathlink).name == libName):
                    return llpathlink
                else:
                    continue
        return None

    def get_dependencies_capitalRemain(self):
        # A.C. @ 11/05/2018: Same as get_dependencies but captial letters are
        #        kept, otherwise from the result you can not go back to the
        #        correct library if a capital letter is used!
        liblinkdict = self.get_liblinkdict()
        alllinks = set()

        for lib in liblinkdict:
            links = set()
            for tree, link in liblinkdict[lib]:
                links.add(link)
                alllinks.add(link)
            if len(links) > 1:
                warning = ('Warning: Multiple links for same library in ' +
                           'design: ' + str(self.path))
                print(warning)
                logging.warning(warning)
        return alllinks

    def replace_liblink(self, src, dst):
        strsrc = str(src)
        if strsrc[-1] != '\n':
            strsrc += '\n'
        strdst = str(dst)
        if strdst[-1] != '\n':
            strdst += '\n'
        if self.exists():
            with open(self.liblist, 'r') as llf:
                lllines = llf.readlines()
            changed = False
            for i in range(len(lllines)):
                if lllines[i].lower() == strsrc.lower():
                    lllines[i] = strdst
                    changed = True
                txt = ''.join(lllines)
            if changed:
                try:
                    general.write(str(self.liblist), txt, False)
                except PermissionError:
                    logging.info('PermissionError.  Retry again in 5 seconds.')
                    time.sleep(5)
                    general.write(str(self.liblist), txt, False)
            else:
                raise Exception('src link not found')
        else:
            raise Exception('non-existing library')

    def replace_liblink_beginofpath(self, src, dst):
        if self.exists():
            with open(self.liblist, 'r') as llf:
                lllines = llf.readlines()
            log = list(lllines)
            for i in range(len(lllines)):
                lllines[i] = re.sub('^' + src, dst, lllines[i], 0, re.I)
                log[i] = log[i][0:-1] + ' -> ' + lllines[i]
            txt = ''.join(lllines)
            logtxt = ''.join(log)
            general.write(str(self.liblist), txt, False)
        else:
            raise Exception('non-existing library')
        return logtxt

    def replace_librarydesignname(self, src, dst):
        if self.exists():
            with open(self.design, 'r') as designf:
                designtxt = designf.read()
            newdesigntxt = re.sub('([(]external )' + src + '(\\s)',
                                  '\\1' + dst + '\\2',
                                  designtxt, 0, re.I)
            newdesigntxt = re.sub('([(]libraryRef )' + src + '([)])',
                                  '\\1' + dst + '\\2',
                                  newdesigntxt, 0, re.I)
            try:
                general.write(str(self.design), newdesigntxt, False)
            except PermissionError:
                logging.info('PermissionError.  Retry again in 5 seconds.')
                time.sleep(5)
                general.write(str(self.design), newdesigntxt, False)
        else:
            raise Exception('non-existing library')

    def replace_designname(self, src, dst):
        if self.exists():
            with open(self.design, 'r') as designf:
                designtxt = designf.read()
            newdesigntxt = re.sub('([(]edif )' + src + '(\\s)',
                                  '\\1' + dst + '\\2',
                                  designtxt, 0, re.I)
            newdesigntxt = re.sub('([(]library )' + src + '(\\s)',
                                  '\\1' + dst + '\\2',
                                  newdesigntxt, 0, re.I)
            general.write(str(self.design), newdesigntxt, False)
        else:
            raise Exception('non-existing library')

    def has_liblinkto(self, other):
        if self == other:
            return True   # by definition
        if self.exists() and other.exists:
            for ll in self.get_liblinks():
                if ll.startswith('..'):
                    llpath = self.path / ll[:-1]
                else:
                    llpath = pathlib.Path(ll[:-1])

                llpathlink = resolve2dots(str(llpath))
                if str(other.path).lower() == llpathlink.lower():
                    return True
            else:
                return False
        else:
            raise Exception('non-existing library')

    def has_cell(self, cellname, other=None):
        if self.exists():
            if other is None or other == self:
                libname = 'library ' + self.name
            else:
                if not self.has_liblinkto(other):
                    return False
                libname = 'external ' + other.name
                if not other.has_cell(cellname):
                    raise Exception('cell ' + cellname + ' does not exist in' +
                                    ' given lib (' + str(other.path) + ').')
            with open(self.design) as designf:
                libstart = 0
                for lineno, line in enumerate(designf, 1):
                    if line == '\t(' + libname + '\n':
                        assert libstart == 0
                        libstart = lineno
                    if libstart > 0 and line == '\t\t(cell ' + cellname + '\n':
                        return True
                    if libstart > 0 and line == '\t)\n':
                        return False
        else:
            raise Exception('non-existing library')

    def find_instances(self, cellname, other=None):
        if self.exists():
            count = 0
            parentname = ''
            celllist = []
            if '-' not in self.name:
                libname = 'library ' + self.name
                checknextline = False
                followinglinestart = None
                followinglineend = None
            else:
                libname = 'library'
                checknextline = True
                followinglinestart = '\t\t(rename'
                followinglineend = self.name + '")\n'

            if other is None or other == self:
                cellref = '\t\t\t\t\t\t\t\t(cellRef ' + cellname + ')\n'
            else:
                cellref = '\t\t\t\t\t\t\t\t(cellRef ' + cellname + '\n'
                if not self.has_liblinkto(other):
                    return []
                if not other.has_cell(cellname):
                    raise Exception('cell ' + cellname + ' does not exist in' +
                                    'given lib (' + str(other.path) + ').')
            with open(self.design) as designf:
                libstart = 0
                for lineno, line in enumerate(designf, 1):
                    if line == '\t(' + libname + '\n':
                        assert libstart == 0
                        libstart = lineno
                        # print('libstart:' + str(libstart))
                    if (libstart > 0 and lineno == libstart + 1 and
                            checknextline):
                        assert line.startswith(followinglinestart)
                        assert line.endswith(followinglineend)
                    if libstart > 0 and line.startswith('\t\t(cell '):
                        parentname = line[8:-1]
                        # print('parentname: ' + parentname)
                        count = 0
                    if libstart > 0 and line == cellref:
                        count += 1
                        # print('count: ' + str(count))
                    if libstart > 0 and line.startswith('\t\t)'):
                        if count > 0:
                            celllist.append(parentname + '  ['+str(count)+']')
                            # print('store!')
                    if libstart > 0 and line == '\t)\n':
                        # print('exit!')
                        return celllist
        else:
            raise Exception('non-existing library')


def resolve2dots(path):
    # print('resolve2dots:')
    # print('path: ' + path)
    resolvedpath = path
    while '\\..\\' in resolvedpath:
        # print('temp resolvedpath: ' + resolvedpath)
        y = re.sub(r'\\[^\\]+\\[.][.]\\', r'\\', resolvedpath, 1)
        # print('y: ' + str(y))
        resolvedpath = y
    # print('resolvedpath: ' + resolvedpath)
    return resolvedpath


def findschematicsin(projectdesignfolder, exclude=[]):
    subpdf = [Design(projectdesignfolder)]
    i = 0
    while i < len(subpdf):
        # print('subpdf (' + str(i) + '): ')
        # pprint.pprint(subpdf)
        # added path length limitation to overcome issues after making it an
        # executable, probably no impact on functionality, it showed just as
        # many S-Edit folders (2018/03/05)
        # unfold = [Design(x) for x in subpdf[i].path.iterdir() if x.is_dir()]
        try:
            unfold = [Design(x) for x in subpdf[i].path.iterdir() if
                      x.is_dir()]
        except Exception:
            print('skipped: ' + str(subpdf[i].path))
            unfold = []

        for index_ex in range(len(exclude)):
            excl = pathlib.Path(exclude[index_ex])
            for index_unf in range(len(unfold)):
                if unfold[index_unf].path == excl:
                    # print('unfold (before): ')
                    # pprint.pprint(unfold)
                    exed = unfold.pop(index_unf)
                    print('excluded: ' + str(exed))
                    # print('unfold (after): ')
                    # pprint.pprint(unfold)
                    break  # for index_unf in range(len(unfold))

        i += 1
        if len(unfold) > 0:
            subpdf[i:i] = unfold
        if i % 250 == 0:
            print(str(i) + ' / ' + str(len(subpdf)) +
                  '   (' + str(subpdf[i-1].path) + ')')
    # #for x in subpdf:
    # #    print(x.path)
    print('Number of folders in ' + projectdesignfolder + ': ' +
          str(len(subpdf)))

    keep = [x for x in subpdf if x.exists()]
    # print('keep (' + str(i) + '): ')
    # pprint.pprint(keep)

    print('Number of S-Edit designs in ' + projectdesignfolder + ': ' +
          str(len(keep)))
    # for x in keep:
    #     print(x.path)

    return keep


class Cell():
    """This class represents a single cell in Sedit!
    Author of the Cell-class: Arne Crouwels"""
    def __init__(self, cellName, designLib):
        """Constructor function that builds up the cell-instance.
        A cell has a name cellName (string), is part of a library libName
        (sedit.Design-object)
        and has a list of cells where it is used in and a list of children
        (cells that build up current cell)
        This cell is automatically aware of it's children;
        the parents need to be added by the user self."""
        self.name = cellName
        self.designLib = designLib
        self.parentsList = set()
        self.childrenList = self.__enlist_children()
        self.topFlag = 0

    def __repr__(self):
        return "Seek.Cell(" + repr(str(self.name)) + ")"

    def __eq__(self, other):
        """A cell is equal to another cell if its name AND its library-origin
        is equal"""
        if self.__class__ == other.__class__:
            if self.name == other.name and self.designLib == other.designLib:
                return True
        else:
            return False

    def __hash__(self):
        return hash((self.name, self.designLib.name))

    def usedby(self, parentCell):
        """The parental cell should be a real cell-object, it will be added to
        the usedList. Void-return"""
        self.parentsList.add(parentCell)

    def isUsed(self):
        """Will check if the cell is used by any other cell (thus that it has
        any parents). If not, the cell us unused and false is returned"""
        if len(self.parentsList) == 0:
            return False
        else:
            return True

    def getUsedSetUsed(self):
        """Returns the list of cells where this cell is used in; e.g. the list
        of parents"""
        return self.parentsList

    def cellIsTopCell(self):
        """Creates a list of all cells that are used to build up the current
        cell. This function will seek through the edif-file to get all required
        information and will build up the correct cells and complete the list.
        This function will be called by a the contructor and has no external
        use. It will just rebuild the same list..."""
        self.topFlag = 1

    def __enlist_children(self):
        if self.designLib.exists():
            libname = 'library ' + self.designLib.name + '\n'
            with open(self.designLib.design) as designf:
                libstart = 0
                libstop = 0
                startLibName = 0
                stopLibName = 0
                cellstart = 0
                cellstop = 0
                startCellName = 0
                stopCellName = 0
                cellFound_lineno = 0
                nameless_cellReference_flag_lineno = 0
                namelessCellFound_lineno = 0
                listOfChildren = set()
                usedCellLine = '\t\t\t\t\t\t\t\t(cellRef'
                usedCellLibLine = '\t\t\t\t\t\t\t\t\t(libraryRef '
                localCellLibLine = '\t\t\t\t\t\t\t)\n'
                namelessCellsName = '\t\t\t\t\t\t\t\t\t(name '
                nolibafternamelesscell = '\t\t\t\t\t\t\t\t\t\t(display\n'
                nameleslibraryref = '\t\t\t\t\t\t\t\t\t(libraryRef '
                namelesendofblock = '\t\t\t\t\t\t\t(transform'

                # this will start reading through the edif-file
                for lineno, line in enumerate(designf, 1):
                    # First check that we are looking in the current library
                    # (if cell is double used and inserted thourgh external
                    # library, we don't want to end up with that cell's
                    # children!)
                    if line == '\t(' + libname:
                        assert libstart == 0 and libstop == 0
                        libstart = lineno
                    # For completeness; we also look out of the end of the
                    # cell's library;
                    if (libstart != 0) and (line == '\t)\n'):
                        assert libstop == 0
                        libstop = lineno
                    # if the cell is found in the library, the file knows to
                    # look for subcells from there on
                    # We'll check for the fact that we are checking in the
                    # correct library AND that the cell's name is correct
                    if (libstart != 0) and (line ==
                                            '\t\t(cell ' + self.name + '\n'):
                        assert cellstart == 0 and cellstop == 0
                        cellstart = lineno
                    # If the end of the current cell in the correct library is
                    # found (2 tabs and closing bracket);
                    # we know we investigated the full cell and return all its
                    # children.
                    # btw: if cellstart != 0 we are automatically in the
                    # correct library; otherwise this parameter could not have
                    # changed.
                    if (cellstart != 0) and (line == '\t\t)' + '\n'):
                        assert cellstop == 0
                        cellstop = lineno
                        # print("the current cell's edif-block starts from: " +
                        #       str(cellstart) + "and ends at: " +
                        #       str(cellstop))
                        return listOfChildren
                    # IF we are in the correct library and in the cell's block
                    # then we look for the children's cells.
                    if (cellstart != 0) and usedCellLine in line:
                        # cellFound_lineno should be 0 when we find a new
                        # cellRef; this parameter acts as a flag for where a
                        # new cell is found.
                        # this parameter will be used in the following
                        # if-statement to find the originating library of
                        # this cell.
                        # the build up is: at line x, a cell ref if found and
                        # at line x+1 the originating library is given.
                        # TOBECORRECTED: THE MONITORSETCASE WHERE CELLREFF IS
                        # EMPTY BUT A NAME BELOW CELLREF IS GIVEN AS THE CELL
                        # (WHEN MASTERCELL IS CHANGED BY DROPDOWN MENU)
                        # The assert checks: no new cell can be found when the
                        # cell has no closure (read: that it is determined what
                        # the library of the cell is through the latest
                        # if-section AND that a nameless cell has already been
                        # given a name)
                        assert ((cellFound_lineno == 0) and
                                (nameless_cellReference_flag_lineno == 0) and
                                (namelessCellFound_lineno == 0) and
                                (startCellName == 0) and (stopCellName == 0))
                        # to find staring position of the child's cell name
                        startCellName = (line.find(usedCellLine) +
                                         len(usedCellLine) + 1)
                        if line[-2] == ')':
                            stopCellName = line.find(')\n')
                        else:
                            stopCellName = line.find('\n')
                        # print("Referenced cell:" +
                        #       line[startCellName:stopCellName] +
                        #       "NoStringSpace!")
                        if startCellName >= stopCellName:
                            # print("[!] system logging: empty cellreference" +
                            #       "found- The linenumber of death: " +
                            #       str(lineno) + "the used cellName is: " +
                            #       line[startCellName:stopCellName] +
                            #       " It started at col: " +
                            #       str(startCellName) + " It stopt at col: " +
                            #       str(stopCellName))
                            nameless_cellReference_flag_lineno = lineno
                            startCellName = 0
                            stopCellName = 0
                            # trying to get the correct cellname will just
                            # fall out in an error - therefor just continue
                            # with the next for-loop step. There the cellname
                            # will be found
                            continue
                            # store the name of this child
                        childCellName = line[startCellName:stopCellName]
                        # prepare the flag to the linenumber to find in a
                        # following line it's originating library
                        cellFound_lineno = lineno
                    # if a nameless cell is found, the name is in the line
                    # below and we need to get the cellname from that location.
                    # until today; this only happens with cells of the same
                    # library; but an extra specific checkup might be useful...
                    if ((nameless_cellReference_flag_lineno != 0) and
                            (lineno == nameless_cellReference_flag_lineno +
                             1)):
                        assert ((namelessCellsName in line) and
                                (cellFound_lineno == 0) and
                                (namelessCellFound_lineno == 0) and
                                (startCellName == 0) and (stopCellName == 0))
                        startCellName = (line.find(namelessCellsName) +
                                         len(namelessCellsName))
                        stopCellName = line.find('\n')
                        childCellName = line[startCellName:stopCellName]
                        nameless_cellReference_flag_lineno = 0
                        namelessCellFound_lineno = lineno
                        # print('[!] Option found: cellname of nameless cell' +
                        #       'should be:' + childCellName + 'NoSpaces')
                    # when the flag is not equal to zero (thus a cellRef has
                    # been found) and the line is one more than where the
                    # cellRef has been found,
                    # we are at the position where the originating library
                    # should be found:
                    if ((cellFound_lineno != 0) and
                            (lineno == cellFound_lineno + 1)):
                        assert ((namelessCellFound_lineno == 0) and
                                (nameless_cellReference_flag_lineno == 0))
                        # print('alive' + str(cellFound_lineno))
                        # If the cell is coming from the current library as
                        # this cell, there will be no library reference and
                        # thus the library-path is the same path as the current
                        # cell
                        # If the cell was marked as a namelesscell; the next
                        # line will neither have any library information and
                        # it just gives display; only seen in case where cell
                        # is from same library as its parents library
                        if (line == localCellLibLine):
                            library_path = self.designLib.path
                        else:
                            # for sure check that this is true; otherwise
                            # something is really off and the program should
                            # only complain as hell to the user in stead of
                            # nicely continue!!
                            assert ((usedCellLibLine in line) and
                                    (startLibName == 0) and (stopLibName == 0))
                            startLibName = (line.find(usedCellLibLine) +
                                            len(usedCellLibLine))
                            stopLibName = line.find(')\n')
                            # Get the library-path sedit.resolve2dots(
                            #        str(childrenList[1].designLib.path))
                            library_name = line[startLibName:stopLibName]
                            if (self.designLib.findLibraryPathByName(
                                    library_name) is None):
                                raise Exception('[!] The library-name' +
                                                library_name +
                                                'the following child-cell: ' +
                                                str(childCellName))
                            library_path = resolve2dots(
                                    str(self.designLib.findLibraryPathByName(
                                            library_name)))
                            # print("latesterroronwednesday ------ " +
                            #       "Library path is given back correctly " +
                            #       "till here... ==> " + library_path)
                        assert childCellName != ''
                        childCell = Cell(childCellName, Design(library_path))
                        listOfChildren.add(childCell)
                        startLibName = 0
                        stopLibName = 0
                        startCellName = 0
                        stopCellName = 0
                        cellFound_lineno = 0
                        library_path = ''
                        # print('[!][!][!] FIND PRIMARY ASSET --> ' +
                        #       'SYSTEM UNDER ATTACK')
                        childCellName = ''
                        # print("the LibraryName that goes with the previous" +
                        #       " found cell equals: " +
                        #       line[startLibName:stopLibName])
                    if (namelessCellFound_lineno != 0):
                        assert ((cellFound_lineno == 0) and
                                (nameless_cellReference_flag_lineno == 0))
                        if lineno > namelessCellFound_lineno + 25:
                            raise Exception(
                                    '[!] A nameless cell was found but no ' +
                                    'library could be retreived -- Please ' +
                                    'contact Arne or Koen. Give him this ' +
                                    'error - issue is occuring in edif-file:' +
                                    str(self.designLib) + 'At line --' +
                                    str(namelessCellFound_lineno))
                        if ((lineno == namelessCellFound_lineno + 1) and
                                (line != nolibafternamelesscell)):
                            raise Exception(
                                    '[!] A nameless cell was found but edif ' +
                                    'structure is deviating -- Please ' +
                                    'contact Arne or Koen. Give him this ' +
                                    'error - issue is occuring in edif-file:' +
                                    str(self.designLib) + 'At line --' +
                                    str(namelessCellFound_lineno))
                        if nameleslibraryref in line:
                            assert(startLibName == 0) and (stopLibName == 0)
                            startLibName = (line.find(nameleslibraryref) +
                                            len(nameleslibraryref))
                            stopLibName = line.find(')\n')
                            # Get the library-path sedit.resolve2dots
                            # print('[!] The nameless cell was coming from' +
                            #       'external library: ' +
                            #       line[startLibName:stopLibName])
                            library_name = line[startLibName:stopLibName]
                            if (self.designLib.findLibraryPathByName(
                                    library_name) is None):
                                raise Exception(
                                        '[!] The library-name ' +
                                        library_name + ' the following ' +
                                        'child-cell: ' + str(childCellName))
                            library_path = resolve2dots(
                                    str(self.designLib.findLibraryPathByName(
                                            library_name)))
                        if namelesendofblock in line:
                            if library_path == '':
                                library_path = self.designLib.path
                                # print('[!] The nameless cell was coming ' +
                                #       'from same library as parent: ' +
                                #       self.designLib.name)
                            # print('[!][!][!] FIND PRIMARY ASSET --> ' +
                            #       childCellName + ' FOUND AND SHOULD ' +
                            #       'NEVER BY EMPTY!')
                            # print(line)
                            # print(str(lineno))
                            assert childCellName != ''
                            childCell = Cell(childCellName, Design(
                                    library_path))
                            listOfChildren.add(childCell)
                            startLibName = 0
                            stopLibName = 0
                            startCellName = 0
                            stopCellName = 0
                            namelessCellFound_lineno = 0
                            library_path = ''
                            childCellName = ''
        else:
            raise Exception('non-existing library ' + str(self.designLib) +
                            ' for the cell: ' + str(self.name))
