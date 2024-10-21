# -*- lib.coding: utf-8 -*-
"""
Created on Wed May  9 10:47:24 2018
Function: getting all unused cells based on a list of used toplevel-cells
@author: Arne Crouwels
"""

import sedit
import csv


class unused_cells():
    def __init__(self, listOfTopCells, topLibraryLocation):
        """CONSTRUCTOR sets all fields for the unused-class based on two
        inputs:
            a list of top-cells (strings of the cell-names) and the
            full top-library location where those top-cells are located into
            It has been assumed that all top-cells would always be located
            into one library
            E.G.: unused_cells(['top'],r'T:\\SENSATION\\TestProject\\top2')"""
        self.libTop = sedit.Design(topLibraryLocation)
        self.fullCellList = self.getFullCellListFromAllLibraries(self.libTop)
        # Build-up the list of topcells based on the name-string and the
        # library-location-string
        self.topCells = []
        for cells in listOfTopCells:
            self.topCells.append(sedit.Cell(cells, self.libTop))
        # Calls the fillOutAllParents-funtion that will fill in the
        # list of parents in all cell-objects; see comment at the function
        # itself.
        self.fillOutAllParents(self.topCells, self.fullCellList, True)
        # Calls the function that lists up all unused cells and places them
        # in the orphanCell-list
        self.orphanCells = self.listAllUnusedCells(self.fullCellList)
        # Calls the function that writes out the unused cell in an CSV
        # (cell, library-name) for the designer to be marked for deletion.
        self.writeOutOrphansCSV(self.orphanCells)

    def getCellsFromLib(self, designLibrary):
        """This function accepts a design-library (an SEDIT-object) and creates
        a list of all existing cells (used or unused) in this library.
        It well seek through the design's edif-file to build up this list."""
        if designLibrary.exists():
            libstart = 0
            libstop = 0
            cellsInLib = []
            ownLibraryLine = '\t(library ' + designLibrary.name + '\n'
            containsCellLine = '\t\t(cell '
            with open(designLibrary.design) as designf:
                # this will start reading through the edif-file
                for lineno, line in enumerate(designf,1):
                    # First check that we are looking in the current library
                    # We don't want to start listing the used cells from other
                    # libraries, that would lead to doubles since we will list
                    # through those libraries as well
                    if line == ownLibraryLine:
                        assert libstart == 0 and libstop == 0
                        libstart = lineno
                    # For completeness; we also look out of the end of the
                    # cell's library;
                    if (libstart != 0) and (line == '\t)\n'):
                        assert libstop == 0
                        libstop = lineno
                        # print('debugging feature:   returned         '+ line)
                        return cellsInLib
                    if (libstart != 0) and (containsCellLine in line):
                        # to find staring position of the child's cell name
                        startCellName = (line.find(containsCellLine) +
                                         len(containsCellLine))
                        stopCellName = line.find('\n')
                        # store the name of this child
                        cellName = line[startCellName:stopCellName]
                        cellsInLib.append(sedit.Cell(cellName,designLibrary))
        else:
            raise Exception('non-existing library')

    def getFullCellListFromAllLibraries(self,startDesign):
        """Started from the given design-library(an SEDIT-object), it will seek
        through all dependent libraries and fills out a full list of all cells
        in the current library AND in all used libraries.
        IT IGNORES THE SCIB-LIBRARIES SINCE UNUSED CELLS OF THOSE LIBRARIES
        SHOULD NEVER BEEN DELETED."""
        scib_lib = '\\scib\\standard\\schematic\\'
        listOfCells = []
        usedLibs = startDesign.get_dependencies(True)
        lib_counter = 1
        length_of_libraries = len(usedLibs)
        print("[!] Start populating full cell-list of all libraries - total " +
              "libraries to go over: " + str(length_of_libraries))
        for lib in usedLibs:
            print('[!] Populating cell-list - library ' + str(lib_counter) +
                  ' of ' + str(length_of_libraries))
            lib_counter += 1
            if scib_lib in lib:
                print('[!] Populating cell-list - SCIB-library found -- ' +
                      'ignoring since no cells may be enlisted for deletion')
                pass
            else:
                libLink = sedit.Design(lib)
                listOfCells = listOfCells + self.getCellsFromLib(libLink)
        return listOfCells

    def fillOutAllParents(self, listTopCells, listOfAllCells, atTopLevel):
        """This function uses recursion to follow the entire tree of used
        cells; started from the toplevel. It will fill-out for each cells by
        which cell it is used.
        Furthermore; it will do this untill it reaches a cell of the
        SCIB-library. There it will stop; CELLS OF THOSE LIBRARIES SHOULD
        NEVER BEEN DELETED
        atTopLevel expects a boolean that points out whether the function is
        called with the the top-cell list or whether it is called by recursion.
        the constructor function is the only function that calls this function
        with the toplevel-list; so there the True-boolean is given.
        Internally; the False-boolean is given."""
        scib_lib = '\\scib\\standard\\schematic\\'
        if atTopLevel:
            for elementCell in listTopCells:
                specTopCell = self.findCellfromList(elementCell,
                                                    listOfAllCells)
                specTopCell.cellIsTopCell()
        for elementCell in listTopCells:
            for child in elementCell.childrenList:
                if (scib_lib in str(child.designLib.path)):
                    pass
                else:
                    # maybe better to return index and refere to that item as
                    # being allCells[index].usedby(Cell)
                    specChild = self.findCellfromList(child, listOfAllCells)
                    # IF the cell has already a parent; the recursive function
                    # already runned thourgh all the levels below this cell and
                    # no use of redoing this!
                    # This part checks that no parents have been filled in yet,
                    # then the recursive function has to run through all lower
                    # levels of the cell
                    if not child.isUsed():
                        specChild.usedby(elementCell)
                        if len(child.childrenList):
                            self.fillOutAllParents([child], listOfAllCells,
                                                   False)
                    else:
                        # if this cell has already a parent; just fill in that
                        # a new parent is found and go back ato the next child!
                        specChild.usedby(elementCell)
        # print("+++++++++ FillOut has finished for ===> " + str(listTopCells))

    def listAllUnusedCells(self, listOfAllCells):
        """Based on the list of all cells; it will ask to each cell to give
        back all of its parents. If that list is empty; it's an unused cell.
        This will be listed to generated the unused cell list. A cell is unused
        when the have no parents (and are thus orphans) AND when they are no
        top-cells (based on the topFlag)
        this field is filled in by the fillOutAllParents."""
        orphanCells = []
        for cell in listOfAllCells:
            if cell.isUsed() or cell.topFlag:
                pass
            else:
                orphanCells.append(cell)
        return orphanCells

    def findCellfromList(self, theCell, cellList):
        """this function will start running through a list of cells (cellList)
        and stops when it find the occurence of an esisting cell.
        two cells are equeal when both their name and library are equal."""
        for cellObj in cellList:
            if cellObj == theCell:
                return cellObj
        raise ValueError('[!] The cell you are looking for is not found in ' +
                         'the list of all cells - Unrecoverable error - for ' +
                         str(theCell))

    def writeOutOrphansCSV(self, theOrphanCells):
        """A function that writes out a CSV-file based on a list you give.
        Here, it's used to write out all orphan cells towards a CSV-file."""
        with open(str(self.libTop.path) + '_unusedCells.csv', 'w',
                  newline='') as myfile:
            wr = csv.writer(myfile, quoting=csv.QUOTE_ALL)
            wr.writerow(["Cell name", "Library name"])
            for orphan in theOrphanCells:
                wr.writerow([orphan.name, orphan.designLib.name])

# unused_cells(["monitor_pixel_array"],
#              (r"S:\projects\scib\IPblocks\monitorsets\monitorset7" +
#               r"\schematic\monitorset"))
