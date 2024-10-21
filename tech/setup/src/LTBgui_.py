import os
import sys
import time
import guifunctions
import logging      # in case you want to add extra logging
import general
# from tkinter import *
from tkinter import (StringVar, VERTICAL, SINGLE, Grid, Tk, Listbox, IntVar,
                     Checkbutton)
# from tkinter.ttk import *
from tkinter.ttk import (Frame, Notebook, Label, Combobox, Button, Entry,
                         Scrollbar)


class LTBgui(Frame):
    # create 3 tabs (at least
    # 1st tab: setup
    #    view and modify user.ini
    # 2nd tab: from schematic 2 layout
    #    that what's already there now
    # 3rd tab: verification
    #    auto-copy from linux2win
    #    boost mode
    # 4th tab: licenses
    #    lmstat (whois) viewer for different licenses
    def __init__(self, master):
        """ initialize a Frame"""
        Frame.__init__(self, master)
        self.grid()
        self.create_widgets()

    def create_widgets(self):
        self.guiTab = Notebook(self, width=750, height=360)
        self.guiTab.grid(row=1, column=1, sticky='nesw')

        self.lblcol0 = Label(self, text='')
        self.lblcol0.grid(row=0, column=0, rowspan=3)
        self.lblcol2 = Label(self, text='')
        self.lblcol2.grid(row=0, column=2, rowspan=3)
        self.lblRow0 = Label(self, text='')
        self.lblRow0.grid(row=0, column=1, columnspan=9)
        self.lblRow2 = Label(self, text='')
        self.lblRow2.grid(row=2, column=1, columnspan=9)

        lg = LayoutGen(self)
        self.guiTab.add(lg, text='Layout Generation')

        ver = Verification(self)
        self.guiTab.add(ver, text='Verification')

#        lic = Licensing(self)
#        self.guiTab.add(lic, text='Licensing')

        # ini = UserSettings(self)
        # self.guiTab.add(ini, text='User Settings')

        if True:
            for col in range(3):
                # self.grid_columnconfigure(col, weight=1)
                if col == 1:
                    Grid.columnconfigure(self, col, weight=1)
                else:
                    Grid.columnconfigure(self, col, weight=2)
            for row in range(3):
                # self.grid_rowconfigure(row, weight=1)
                if row == 1:
                    Grid.rowconfigure(self, row, weight=1)
                else:
                    Grid.rowconfigure(self, row, weight=2)
        print('So far, so good.')


class LayoutGen(Frame):
    """A gui for the LayoutToolbox, the LayoutGen part"""

    def __init__(self, master):
        """ initialize a Frame"""
        Frame.__init__(self, master)
        self.grid()
        self.create_widgets()

    def create_widgets(self):
        if True:
            self.dictcells = {}
            self.dictinstances = {}
        if True:
            self.lblPrj = Label(self, text='Project:')
            self.lblPrj.grid(row=0, column=0, sticky='e')

            self.project = StringVar()
            self.project.set('')
            self.cmbPrj = Combobox(self, textvariable=self.project)
            self.cmbPrj.grid(row=0, column=1, sticky='ew')
            self.cmbPrj['values'] = guifunctions.projectslist()
            self.cmbPrj.bind('<<ComboboxSelected>>', self.projectselect)

            self.btnPrj = Button(self, text='>> [F5]', width=7)
            self.btnPrj.grid(row=0, column=2, columnspan=2, sticky='e')
            self.btnPrj['command'] = self.projectselect
            self.btnPrj.bind('<KeyPress-Return>', self.projectselect)
            self.bind_all('<F5>', self.projectselect)

            self.lblPrjSel = Label(self, text=self.project.get(), width=20)
            self.lblPrjSel.grid(row=0, column=4, columnspan=1)

            self.btnPrjDir = Button(self, text='Create ProjectDir')
            self.btnPrjDir.grid(row=0, column=5, columnspan=3, sticky='we')
            self.btnPrjDir['command'] = self.createprojectdir
            self.btnPrjDir.bind('<KeyPress-Return>', self.createprojectdir)
            self.btnPrjDir_enabledisable()

            self.frcVal = IntVar()
            self.frcCheck = Checkbutton(self, text='force',
                                        variable=self.frcVal)
            self.frcCheck.grid(row=0, column=9, sticky='e')

            self.lblcol08 = Label(self, text='')
            self.lblcol08.grid(row=0, column=8, rowspan=1)
            self.lblRow1 = Label(self, text='')
            self.lblRow1.grid(row=1, column=0, columnspan=9)

        if True:
            self.lblCell = Label(self, text='Cell Name:')
            self.lblCell.grid(row=3, column=0, sticky='e')

            self.cellfilter = StringVar()
            self.cellfilter.set('[Filter]')
            evalCommand = self.register(self.evalcellfilter)
            self.entCellFilter = Entry(
                    self, width=40, textvariable=self.cellfilter,
                    validate='all', validatecommand=(evalCommand, '%d', '%V',
                                                     '%P'))
            self.entCellFilter.grid(row=3, column=1, columnspan=2, sticky='ew')
            # self.entCellFilter.bind('<Button-1>', self.entCellselect)

            self.cellslistfilt = StringVar()

            self.cellyScroll = Scrollbar(self, orient=VERTICAL)
            self.cellyScroll.grid(row=4, rowspan=2, column=3, sticky='nsw')
            # self.cellxScroll = Scrollbar(self, orient=HORIZONTAL)
            # self.cellxScroll.grid(row=6, column=1, columnspan=2, sticky=E+W)
            self.listCellFilter = Listbox(
                    self, width=40, listvariable=self.cellslistfilt,
                    selectmode=SINGLE, activestyle='dotbox', height=5,
                    yscrollcommand=self.cellyScroll.set)
            # self.listCellFilter = Listbox(self, width=40,
            #         listvariable=self.cellslistfilt, selectmode=SINGLE,
            #         activestyle='dotbox', height=5,
            #         yscrollcommand=self.cellyScroll.set,
            #         xscrollcommand=self.cellxScroll.set)
            self.listCellFilter.grid(row=4, rowspan=2, column=1, columnspan=2,
                                     sticky='nsew')
            self.cellyScroll['command'] = self.listCellFilter.yview
            # self.cellxScroll['command'] = self.listCellFilter.xview
            self.listCellFilter.bind('<<ListboxSelect>>', self.cellselect)
            self.listCellFilter.bind('<KeyPress-Return>', self.cellselectEnter)

            self.cellname = StringVar()
            self.lblCellSel = Label(self, text=self.cellname.get(),
                                    relief='ridge')
            self.lblCellSel.grid(row=3, column=4, columnspan=4, sticky='ew')
            self.lblCellSelFile = Label(self, text='')
            self.lblCellSelFile.grid(row=4, column=4, columnspan=4, sticky='w')
            self.lblCellSelFileMod = Label(self, text='')
            self.lblCellSelFileMod.grid(row=5, column=4, columnspan=4,
                                        sticky='nw')

            self.btnN2S = Button(self, text='Filter lib: >')
            self.btnN2S.grid(row=3, column=9, sticky='ew')
            self.btnN2S['command'] = self.netlist2stdcells
            self.btnN2S.bind('<KeyPress-Return>', self.netlist2stdcells)

            self.libfilter = StringVar()
            self.libfilter.set('stdcells')
            self.entLibFilter = Entry(self, width=10,
                                      textvariable=self.libfilter)
            self.entLibFilter.grid(row=3, column=10, sticky='ew')

            self.btnN2G = Button(self, text='Autogenerate')
            self.btnN2G.grid(row=4, column=9, columnspan=2, sticky='ew')
            self.btnN2G['command'] = self.netlist2autogen
            self.btnN2G.bind('<KeyPress-Return>', self.netlist2autogen)

            self.btnN2W = Button(self, text='Create WRL')
            self.btnN2W.grid(row=5, column=9, columnspan=2, sticky='new')
            self.btnN2W['command'] = self.netlist2wrl
            self.btnN2W.bind('<KeyPress-Return>', self.netlist2wrl)

            self.btnN2L = Button(self, text='Autolabel')
            self.btnN2L.grid(row=6, column=9, columnspan=2, sticky='new')
            self.btnN2L['command'] = self.netlist2autolabel
            self.btnN2L.bind('<KeyPress-Return>', self.netlist2autolabel)

            self.btnCell_disable()

            self.lblcol38 = Label(self, text='')
            self.lblcol38.grid(row=3, column=8, rowspan=3)
            self.lblRow7 = Label(self, text='')
            self.lblRow7.grid(row=7, column=0)

        if True:
            self.lblInst = Label(self, text='Instances:')
            self.lblInst.grid(row=8, column=0, sticky='ne')

            self.instslist = StringVar()

            self.instyScroll = Scrollbar(self, orient=VERTICAL)
            self.instyScroll.grid(row=8, rowspan=6, column=3, sticky='nsw')
            # self.instxScroll = Scrollbar(self, orient=HORIZONTAL)
            # self.instyScroll.grid(row=11, column=1, columnspan=2, sticky=E+W)
            self.listInst = Listbox(
                    self, width=40, listvariable=self.instslist,
                    selectmode=SINGLE, activestyle='dotbox', height=5,
                    yscrollcommand=self.instyScroll.set)
            # self.listInst = Listbox(
            #         self, width=40, listvariable=self.instslist,
            #         selectmode=SINGLE, activestyle='dotbox', height=5,
            #         yscrollcommand=self.instyScroll.set,
            #         xscrollcommand=self.instyScroll.set)
            self.listInst.grid(row=8, rowspan=6, column=1, columnspan=2,
                               sticky='news')
            self.instyScroll['command'] = self.listInst.yview
            # self.instyScroll['command'] = self.listInst.xview
            self.listInst.bind('<<ListboxSelect>>', self.instselect)
            self.listInst.bind('<KeyPress-Return>', self.instselectEnter)

            self.instname = StringVar()
            self.lblInstSel = Label(self, text=self.instname.get(),
                                    relief='ridge')
            self.lblInstSel.grid(row=8, column=4, columnspan=4, sticky='ew')
            self.lblInstSelRange = Label(self, text='Instance Range:')
            self.lblInstSelRange.grid(row=9, column=4, sticky='nw')
            self.instSelRangeMin = StringVar()
            self.instSelRangeMin.set('0')
            self.instSelRangeMax = StringVar()
            self.instSelRangeMax.set('0')
            self.entInstSelRangeMin = Entry(self, width=5,
                                            textvariable=self.instSelRangeMin)
            self.entInstSelRangeMin.grid(row=9, column=5, sticky='ne')
            self.lblInstSelRangeSep = Label(self, text=' - ')
            self.lblInstSelRangeSep.grid(row=9, column=6, sticky='n')
            self.entInstSelRangeMin = Entry(self, width=5,
                                            textvariable=self.instSelRangeMax)
            self.entInstSelRangeMin.grid(row=9, column=7, sticky='nw')

            self.lblInstPos = Label(self, text='Position first element:')
            self.lblInstPos.grid(row=10, column=4, columnspan=4, sticky='w')
            self.instStartX = StringVar()
            self.instStartX.set('0')
            self.instStartY = StringVar()
            self.instStartY.set('0')
            self.lblInstPosX = Label(self, text='X:')
            self.lblInstPosX.grid(row=11, column=4, sticky='ne')
            self.entInstStartX = Entry(self, width=5,
                                       textvariable=self.instStartX)
            self.entInstStartX.grid(row=11, column=5, sticky='nw')
            self.lblInstPosY = Label(self, text='Y:')
            self.lblInstPosY.grid(row=11, column=6, sticky='ne')
            self.entInstStartY = Entry(self, width=5,
                                       textvariable=self.instStartY)
            self.entInstStartY.grid(row=11, column=7, sticky='nw')

            self.lblInstPitch = Label(self, text='Pitch definition:')
            self.lblInstPitch.grid(row=12, column=4, columnspan=4, sticky='w')
            self.instPitch = StringVar()
            self.instPitch.set('0 20 ' +
                               str(int(self.instSelRangeMax.get())+1))
            self.entInstPitch = Entry(self, width=30,
                                      textvariable=self.instPitch)
            self.entInstPitch.grid(row=13, column=4, columnspan=4, sticky='nw')

            self.btnN2P = Button(self, text='Autoplace')
            self.btnN2P.grid(row=8, column=9, columnspan=2, sticky='new')
            self.btnN2P['command'] = self.netlist2autoplace
            self.btnN2P.bind('<KeyPress-Return>', self.netlist2autoplace)
            self.btnInst_disable()

            self.lblcol88 = Label(self, text='')
            self.lblcol88.grid(row=8, column=8, rowspan=6)
            self.lblRow14 = Label(self, text='')
            self.lblRow14.grid(row=14, column=0)

        if False:
            for col in range(9):
                # self.grid_columnconfigure(col, weight=1)
                Grid.columnconfigure(self, col, weight=1)
            for row in range(14):
                # self.grid_rowconfigure(row, weight=1)
                Grid.rowconfigure(self, row, weight=1)
        if True:
            for col in range(10):
                # self.grid_columnconfigure(col, weight=1)
                if col == 8:
                    Grid.columnconfigure(self, col, weight=2)
                else:
                    Grid.columnconfigure(self, col, weight=1)
            for row in range(15):
                # self.grid_rowconfigure(row, weight=1)
                if row in [1, 7, 14]:
                    Grid.rowconfigure(self, row, weight=2)
                if row in [0, 3, 8, 13]:
                    Grid.rowconfigure(self, row, weight=0)
                else:
                    Grid.rowconfigure(self, row, weight=1)

    def projectselect(self, value=None):
        self.lblPrjSel['text'] = self.project.get()
        project = self.lblPrjSel['text']
        self.btnPrjDir_enabledisable()
        if guifunctions.iscreatedprojectdir(project):
            # copy .sp files from project netlist directory to LTB
            guifunctions.copynetlist_proj2ltb(project, backup=True)
        else:
            print('INFO: LTB project folder for ' + project + ' not complete.')
            print('      copying of netlist from default project dir to LTB ' +
                  'not executed.')
        self.loaddictcells()
        self.applycellfilter(self.cellfilter.get())
        self.clearcellselection()
        self.clearinstselection()

    def createprojectdir(self):
        project = self.lblPrjSel['text']
        guifunctions.createprojectdir(project)
        self.projectselect()
        # self.btnPrjDir_enabledisable()
        # # copy .sp files from project netlist directory to LTB
        # guifunctions.copynetlist_proj2ltb(project, backup=True)
        # self.loaddictcells()
        # self.applycellfilter(self.cellfilter.get())
        # self.clearcellselection()
        # self.clearinstselection()

    def btnPrjDir_enabledisable(self):
        project = self.lblPrjSel['text']
        # print(repr(project))
        if project == '' or ' ' in project:
            self.btnPrjDir.state(['disabled'])
        else:
            if not guifunctions.iscreatedprojectdir(project):
                self.btnPrjDir.state(['!disabled'])
            else:
                self.btnPrjDir.state(['disabled'])

    def applycellfilter(self, filter):
        if filter == '[Filter]':
            filter = ''

        # cellslist = guifunctions.cellslist(self.project.get())
        cellslist = []

        for cell in self.dictcells:
            if filter in cell:
                cellslist.append(cell)

        cellslist.sort()
        cellslistfiltstr = ' '.join(cellslist)
        self.cellslistfilt.set(cellslistfiltstr)
        self.clearcellselection()
        self.clearinstselection()

    def clearcellselection(self):
        # print('clearcellselection()')
        # self.listCellFilter.selection_set(-1)
        # self.listCellFilter.selection_clear(0)
        self.cellname.set('')
        self.lblCellSel['text'] = self.cellname.get()
        self.lblCellSelFile['text'] = ''
        self.lblCellSelFileMod['text'] = ''
        self.btnCell_disable()
        self.dictinstances = {}
        self.applyinstfilter()

    def evalcellfilter(self, action, reason, newval):
        if action == '-1':
            if reason == 'focusin' and self.cellfilter.get() == '[Filter]':
                self.cellfilter.set('')
            elif reason == 'focusout' and self.cellfilter.get() == '':
                self.cellfilter.set('[Filter]')
        else:
            self.applycellfilter(newval)
        return True

    def cellselectEnter(self, value=None):
        self.listCellFilter.selection_clear(0, 'end')
        self.listCellFilter.selection_set('active')
        # index = self.listCellFilter.curselection()
        self.listCellFilter.curselection()
        self.cellselect()

    def cellselect(self, value=None):
        index = self.listCellFilter.curselection()
        if len(index) == 1:
            self.cellname.set(eval(self.cellslistfilt.get())[index[0]])
            # print(self.cellname.get())
            # cellinfo = guifunctions.cellinfo(self.project.get(),
            #                                  self.cellname.get())
            cellinfo = self.dictcells[self.cellname.get()]
            self.lblCellSel['text'] = self.cellname.get()
            if len(cellinfo[0]) < 50:
                self.lblCellSelFile['text'] = cellinfo[0]
            else:
                self.lblCellSelFile['text'] = (cellinfo[0][:7] + ' ... ' +
                                               cellinfo[0][-40:])
            self.lblCellSelFileMod['text'] = time.ctime(cellinfo[1])
            self.btnCell_enable()
            self.loaddictinstances()
            self.applyinstfilter()

    def loaddictcells(self):
        self.dictcells = guifunctions.dictcells(self.project.get())
        # print(self.dictcells)

    def loaddictinstances(self):
        self.dictinstances = guifunctions.dictinstances(self.project.get(),
                                                        self.cellname.get())
        # print(self.dictinstances)

    def applyinstfilter(self, filter=''):
        if filter == '[Filter]':
            filter = ''

        instlist = []
        for instname in self.dictinstances:
            if filter in instname:
                instlist.append(instname)
        instliststr = ' '.join(instlist)

        self.instslist.set(instliststr)
        self.clearinstselection()

    def clearinstselection(self):
        # self.listInst.selection_set(0)
        # self.listInst.selection_clear(0)
        self.instname.set('')
        self.lblInstSel['text'] = self.instname.get()
        self.instSelRangeMin.set('0')
        self.instSelRangeMax.set('0')
        self.instStartX.set('0')
        self.instStartY.set('0')
        self.instPitch.set('0 20 ' + str(int(self.instSelRangeMax.get())+1))
        # self.lblCellSelFile['text'] = ''
        # self.lblCellSelFileMod['text'] = ''
        self.btnInst_disable()

    def instselectEnter(self, value=None):
        self.listInst.selection_clear(0, 'end')
        self.listInst.selection_set('active')
        # index = self.listInst.curselection()
        self.listInst.curselection()
        self.instselect()

    def instselect(self, value=None):
        index = self.listInst.curselection()
        if len(index) == 1:
            self.instname.set(eval(self.instslist.get())[index[0]])
            self.lblInstSel['text'] = self.instname.get()
            self.instSelRangeMin.set(
                    self.dictinstances[self.instname.get()][0])
            self.instSelRangeMax.set(
                    self.dictinstances[self.instname.get()][1])
            self.instPitch.set('0 20 ' +
                               str(int(self.instSelRangeMax.get())+1))
            self.btnInst_enable()

    def netlist2autogen(self):
        project = self.project.get()
        cellname = self.cellname.get()
        force = self.frcVal.get()
        guifunctions.netlist2autogen(project, cellname, force=force)

    def netlist2wrl(self):
        project = self.project.get()
        cellname = self.cellname.get()
        force = self.frcVal.get()
        guifunctions.netlist2wrl(project, cellname, force=force)

    def netlist2autolabel(self):
        project = self.project.get()
        cellname = self.cellname.get()
        force = self.frcVal.get()
        guifunctions.netlist2autolabel(project, cellname, force=force)

    def netlist2stdcells(self):
        project = self.project.get()
        cellname = self.cellname.get()
        lib = self.libfilter.get()
        force = self.frcVal.get()
        guifunctions.netlist2stdcells(project, cellname, lib, force=force)

    def btnCell_enable(self):
        self.btnN2S.state(['!disabled'])
        self.btnN2G.state(['!disabled'])
        self.btnN2W.state(['!disabled'])
        self.btnN2L.state(['!disabled'])

    def btnCell_disable(self):
        self.btnN2S.state(['disabled'])
        self.btnN2G.state(['disabled'])
        self.btnN2W.state(['disabled'])
        self.btnN2L.state(['disabled'])

    def netlist2autoplace(self):
        project = self.project.get()
        cellname = self.cellname.get()
        instnamerange = (
                self.instname.get() + '[' + self.instSelRangeMin.get() +
                ':' + self.instSelRangeMax.get() + ']')
        startx = self.instStartX.get()
        starty = self.instStartY.get()
        pitch = self.instPitch.get()
        guifunctions.netlist2autoplace(project, cellname, instnamerange,
                                       startx, starty, pitch)

    def btnInst_enable(self):
        self.btnN2P.state(['!disabled'])

    def btnInst_disable(self):
        self.btnN2P.state(['disabled'])


class Verification(Frame):
    """A gui for the LayoutToolbox, the Verification part"""

    def __init__(self, master):
        """ initialize a Frame"""
        Frame.__init__(self, master)
        self.grid()
        self.create_widgets()

    def create_widgets(self):
        if True:
            self.lblPrj = Label(self, text='Project:')
            self.lblPrj.grid(row=0, column=0, sticky='e')

            self.project = StringVar()
            self.project.set('')
            self.cmbPrj = Combobox(self, textvariable=self.project)
            self.cmbPrj.grid(row=0, column=1, sticky='ew')
            self.cmbPrj['values'] = guifunctions.projectslist()
            self.cmbPrj.bind('<<ComboboxSelected>>', self.projectselect)
            self.lblPrjSel = Label(self, text=self.project.get(), width=40)
            self.lblPrjSel.grid(row=0, column=4, columnspan=4)

            self.btnChk = Button(self, text='Check for results')
            self.btnChk.grid(row=0, column=9, sticky='ew')
            self.btnChk['command'] = self.checkresults
            self.btnChk.bind('<KeyPress-Return>', self.checkresults)
            self.btnChk_enabledisable()

    def projectselect(self, value=None):
        self.lblPrjSel['text'] = self.project.get()
        # project = self.lblPrjSel['text']
        self.lblPrjSel['text']
        self.btnChk_enabledisable()

    def checkresults(self):
        pass

    def btnChk_enabledisable(self):
        project = self.lblPrjSel['text']
        # print(repr(project))
        if project == '' or ' ' in project:
            self.btnChk.state(['disabled'])
        else:
            if not guifunctions.iscreatedprojectdir(project):
                self.btnChk.state(['disabled'])
            else:
                self.btnChk.state(['!disabled'])


# class Licensing(Frame):
#    """A gui for the LayoutToolbox, the Licensing part"""
#
#    def __init__(self, master):
#        """ initialize a Frame"""
#        Frame.__init__(self, master)
#        self.grid()
#        self.create_widgets()
#
#    def create_widgets(self):
#        if True:
#            self.lblPrj = Label(self, text='Project:')
#            self.lblPrj.grid(row=0, column=0, sticky='e')
#
#            self.project = StringVar()
#            self.project.set('')
#            self.cmbPrj = Combobox(self, textvariable=self.project)
#            self.cmbPrj.grid(row=0, column=1, sticky='ew')
#            self.cmbPrj['values'] = guifunctions.projectslist()
#            self.cmbPrj.bind('<<ComboboxSelected>>', self.projectselect)
#            self.lblPrjSel = Label(self, text=self.project.get(), width=40)
#            self.lblPrjSel.grid(row=0, column=4, columnspan=4)
#
#            self.btnChk = Button(self, text='Check for results')
#            self.btnChk.grid(row=0, column=9, sticky='ew')
#            self.btnChk['command'] = self.checkresults
#            self.btnChk.bind('<KeyPress-Return>', self.checkresults)
#            self.btnChk_enabledisable()
#
#    def projectselect(self, value=None):
#        self.lblPrjSel['text'] = self.project.get()
#        # project = self.lblPrjSel['text']
#        self.lblPrjSel['text']
#        self.btnChk_enabledisable()
#
#    def checkresults(self):
#        pass
#
#    def btnChk_enabledisable(self):
#        project = self.lblPrjSel['text']
#        # print(repr(project))
#        if project == '' or ' ' in project:
#            self.btnChk.state(['disabled'])
#        else:
#            if not guifunctions.iscreatedprojectdir(project):
#                self.btnChk.state(['disabled'])
#            else:
#                self.btnChk.state(['!disabled'])


try:
    # do not set a seperate error logger for the GUI, it can cause
    # PermissionErrors when the GUI ran into a problem, stayed open, followed
    # by any other (L-Edit-lauched) Python script. Find all issues in the
    # default LTB.log
    general.logsetup(False)
    root = Tk()
    root.title("A GUI for the Layout Toolbox")
    root.geometry('800x400')
    Grid.rowconfigure(root, 0, weight=1)
    Grid.columnconfigure(root, 0, weight=1)

    module = sys.argv[0]
    drive = os.getcwd()[0]
    icontype = 'LTBgui'
    if drive == 'S':
        icontype += 'S'
    # else:
    #     icontype += 'H'

    if '.exe' in module:
        icontype += 'X'
    # else:
    #     icontype += 'P'

    iconbitmapfiles = ['S:\\tools\\caeleste tools\\LayoutToolbox\\Python\\' +
                       icontype + '.ico']
    iconbitmapfiles.append('X:\\Python\\' + icontype + '.ico')
    for iconbitmapfile in iconbitmapfiles:
        if os.path.isfile(iconbitmapfile):
            root.iconbitmap(iconbitmapfile)
            break

    app = LTBgui(root)
    app.grid(row=0, column=0, sticky='news')
    if False:
        for col in range(10):
            # self.grid_columnconfigure(col, weight=1)
            if col == 8:
                Grid.columnconfigure(app, col, weight=2)
            else:
                Grid.columnconfigure(app, col, weight=1)
        for row in range(14):
            # self.grid_rowconfigure(row, weight=1)
            if row in [1, 7]:
                Grid.rowconfigure(app, row, weight=2)
            else:
                Grid.rowconfigure(app, row, weight=1)

    root.mainloop()
except Exception:
    logging.exception('LTB GUI issue!')
    import traceback
    print(traceback.format_exc())
    time.sleep(10)
    raise
