import sys

from PySide2 import QtCore, QtWidgets, QtGui
from PySide2.QtUiTools import QUiLoader
from PySide2.QtCore import Qt

import numpy as np
# import random
import mlrose

import general
import starrouting_fcts as SR

loader = QUiLoader()

techRsq = {'lf11is': ['190', '140', '140', '140', '140', '60', '0', '0', '0'],
           'tsl018': ['80', '80', '80', '80', '80', '40', '0', '0', '0'],
           'umc018': ['77', '62', '62', '62', '62', '41', '0', '0', '0'],
           'xc018': ['77', '74', '74', '74', '74', '33', '0', '0', '0'],
           }


class MainUI(QtCore.QObject):  # Not a widget.
    def __init__(self, filename=None, outfile=None):
        super().__init__()
        print('filename: ' + str(filename))
        print('outfile: ' + str(outfile))
        self.ui = loader.load("starrouting.ui", None)
        # self.ui.setWindowTitle("MainWindow Title")

        self.met = [SR.Layer('M' + str(x), x, 0) for x in range(1, 10)]
        # group elements
        self.group_ledMxr = [self.ui.ledM1r, self.ui.ledM2r, self.ui.ledM3r,
                             self.ui.ledM4r, self.ui.ledM5r, self.ui.ledM6r,
                             self.ui.ledM7r, self.ui.ledM8r, self.ui.ledM9r]
        self.group_dim = [self.ui.ledSPxcenter, self.ui.ledSPytop,
                          self.ui.ledSPwidth, self.ui.ledSPlength,
                          self.ui.ledSPspace, self.ui.ledRAheight,
                          self.ui.ledHWytop, self.ui.ledHWwidth,
                          self.ui.ledHWspace, self.ui.ledLMx0center,
                          self.ui.ledLMybottom, self.ui.ledLMwidth,
                          self.ui.ledLMpitch]
        self.group_dimdict = {'sp': [self.ui.ledSPxcenter, self.ui.ledSPytop,
                                     self.ui.ledSPwidth, self.ui.ledSPlength,
                                     self.ui.ledSPspace],
                              'ra': [self.ui.ledRAheight],
                              'hw': [self.ui.ledHWytop, self.ui.ledHWwidth,
                                     self.ui.ledHWspace],
                              'lm': [self.ui.ledLMx0center,
                                     self.ui.ledLMybottom, self.ui.ledLMwidth,
                                     self.ui.ledLMpitch, self.ui.ledLMn]}
        self.group_metSel = {1: [self.ui.lblM1sel, self.ui.chkSPM1,
                                 self.ui.chkRAM1, self.ui.chkHWM1,
                                 self.ui.chkLMM1],
                             2: [self.ui.lblM2sel, self.ui.chkSPM2,
                                 self.ui.chkRAM2, self.ui.chkHWM2,
                                 self.ui.chkLMM2],
                             3: [self.ui.lblM3sel, self.ui.chkSPM3,
                                 self.ui.chkRAM3, self.ui.chkHWM3,
                                 self.ui.chkLMM3],
                             4: [self.ui.lblM4sel, self.ui.chkSPM4,
                                 self.ui.chkRAM4, self.ui.chkHWM4,
                                 self.ui.chkLMM4],
                             5: [self.ui.lblM5sel, self.ui.chkSPM5,
                                 self.ui.chkRAM5, self.ui.chkHWM5,
                                 self.ui.chkLMM5],
                             6: [self.ui.lblM6sel, self.ui.chkSPM6,
                                 self.ui.chkRAM6, self.ui.chkHWM6,
                                 self.ui.chkLMM6],
                             7: [self.ui.lblM7sel, self.ui.chkSPM7,
                                 self.ui.chkRAM7, self.ui.chkHWM7,
                                 self.ui.chkLMM7],
                             8: [self.ui.lblM8sel, self.ui.chkSPM8,
                                 self.ui.chkRAM8, self.ui.chkHWM8,
                                 self.ui.chkLMM8],
                             9: [self.ui.lblM9sel, self.ui.chkSPM9,
                                 self.ui.chkRAM9, self.ui.chkHWM9,
                                 self.ui.chkLMM9],
                             'sp': [self.ui.chkSPM1, self.ui.chkSPM2,
                                    self.ui.chkSPM3, self.ui.chkSPM4,
                                    self.ui.chkSPM5, self.ui.chkSPM6,
                                    self.ui.chkSPM7, self.ui.chkSPM8,
                                    self.ui.chkSPM9],
                             'ra': [self.ui.chkRAM1, self.ui.chkRAM2,
                                    self.ui.chkRAM3, self.ui.chkRAM4,
                                    self.ui.chkRAM5, self.ui.chkRAM6,
                                    self.ui.chkRAM7, self.ui.chkRAM8,
                                    self.ui.chkRAM9],
                             'hw': [self.ui.chkHWM1, self.ui.chkHWM2,
                                    self.ui.chkHWM3, self.ui.chkHWM4,
                                    self.ui.chkHWM5, self.ui.chkHWM6,
                                    self.ui.chkHWM7, self.ui.chkHWM8,
                                    self.ui.chkHWM9],
                             'lm': [self.ui.chkLMM1, self.ui.chkLMM2,
                                    self.ui.chkLMM3, self.ui.chkLMM4,
                                    self.ui.chkLMM5, self.ui.chkLMM6,
                                    self.ui.chkLMM7, self.ui.chkLMM8,
                                    self.ui.chkLMM9]}
        self.group_prjnet = [self.ui.ledProject, self.ui.ledNet]
        self.group_cost = [self.ui.ledCostSP_pen, self.ui.ledCostHW_pen,
                           self.ui.ledCostSP_fact, self.ui.ledCostHW_fact,
                           self.ui.ledCostClean_fact, self.ui.ledCostRavg_fact,
                           self.ui.ledCostRdelta_fact]
        self.group_costRslts = [self.ui.ledCostSPRslt, self.ui.ledCostHWRslt,
                                self.ui.ledCostCleanRslt,
                                self.ui.ledCostRavgRslt,
                                self.ui.ledCostRdeltaRslt,
                                self.ui.ledCostTotRslt]
        self.group_algSel = [self.ui.rdiDIYHC, self.ui.rdiMLRHC,
                             self.ui.rdiMLHC, self.ui.rdiMLSA,
                             self.ui.rdiMLGA, self.ui.rdiMLMIM]
        self.group_algVal = [self.ui.ledIter, self.ui.ledClimb,
                             self.ui.chkImmediately,
                             self.ui.ledMaxIters, self.ui.ledMaxAttempts,
                             self.ui.ledRestarts, self.ui.ledKeepPct,
                             self.ui.ledPopSize, self.ui.ledMutationProb]

        self.group_algTdec = [self.ui.rdiTDGeom, self.ui.rdiTDArith,
                             self.ui.rdiTDExp,
                             self.ui.ledTinit, self.ui.ledTmin,
                             self.ui.ledTdecay]

        # set all validators (and warningconnects)
        for led in self.group_ledMxr:
            led.setValidator(QtGui.QDoubleValidator())
            led.inputRejected.connect(self.warn_inputDouble)
        for led in self.group_dim:
            led.setValidator(QtGui.QDoubleValidator())
            led.inputRejected.connect(self.warn_inputDouble)
        self.ui.ledLMn.setValidator(QtGui.QIntValidator(1, 999))
        self.ui.ledLMn.inputRejected.connect(self.warn_inputInt)
        for led in self.group_cost:
            led.setValidator(QtGui.QDoubleValidator())
        self.ui.ledZoom.setValidator(QtGui.QDoubleValidator())
        self.ui.ledZoom.inputRejected.connect(self.warn_inputDouble)
        self.drw_zoom = float(self.ui.ledZoom.text())

        # set all connects
        self.ui.cmbTech.currentTextChanged.connect(self.tech_changed)
        self.ui.cmbTech.currentTextChanged.connect(self.res_changed)
        for led in self.group_ledMxr:
            led.editingFinished.connect(self.res_changed)

        # Load/Save
        self.ui.btnLoad.clicked.connect(self.dialog_open_file)
        self.ui.btnSave.clicked.connect(self.dialog_save_file)

        # Build StarRoute when Geo tab
        self.ui.tabWidget.currentChanged.connect(self.tabchange)

        # deselect led bxes with algorithm selection
        for rdi in self.group_algSel:
            rdi.toggled.connect(self.alg_select_toggle)
        self.alg_select_toggle(None)

        # Run Optim
        self.ui.btnRun.clicked.connect(self.updatecost)
        self.ui.btnRun.clicked.connect(self.run_optim)

        # Get_Equalwidth start widths
        self.ui.btnStateEW.clicked.connect(self.reset_state_equalwidth)
        self.ui.tblWState.cellChanged.connect(self.stateCellChanged)

        # Drawing canvas sliders
        self.ui.scrlHCanvas.valueChanged.connect(self.sliderchanged)
        self.ui.scrlVCanvas.valueChanged.connect(self.sliderchanged)

        # Zoom
        self.ui.ledZoom.editingFinished.connect(self.zoom_changed)

        # Autogen
        self.ui.btnAutogen.clicked.connect(self.autogen)

        self.ui.show()

        if filename is not None:
            self.open_file(filename)

    def alg_select_toggle(self, checked):
        # selection
        truth_table = [[1,1,1,0,0,0,0,0,0],  # DIY HC
                       [0,0,0,1,1,1,0,0,0],  # MLROSE RHC
                       [0,0,0,1,0,1,0,0,0],  # MLROSE HC
                       [0,0,0,1,1,0,0,0,0],  # MLROSE SA
                       [0,0,0,1,1,0,0,1,1],  # MLROSE GA
                       [0,0,0,1,1,0,1,1,1]   # MLROSE MIMIC
                       ]

        for selection, rdi in enumerate(self.group_algSel):
            if rdi.isChecked():
                break

        for i, val in enumerate(self.group_algVal):
            val.setEnabled(bool(truth_table[selection][i]))

        decay = selection == 3
        for element in self.group_algTdec:
            element.setEnabled(decay)


    def tech_changed(self, text):
        if text == 'Custom':
            for led in self.group_ledMxr:
                # led.setReadOnly(False)
                led.setEnabled(True)
        else:
            for i, led in enumerate(self.group_ledMxr):
                # led.setReadOnly(True)
                led.setEnabled(False)
                led.setText(techRsq[text][i])
        self.warn_reset()

    def res_changed(self):
        for i, led in enumerate(self.group_ledMxr):
            if float(led.text()) == 0:
                for j, lblchk in enumerate(self.group_metSel[i+1]):
                    if j == 0:
                        lblchk.setEnabled(False)
                    else:
                        lblchk.setChecked(False)
                        lblchk.setCheckable(False)
            else:
                for j, lblchk in enumerate(self.group_metSel[i+1]):
                    if j == 0:
                        lblchk.setEnabled(True)
                    else:
                        lblchk.setCheckable(True)
        self.warn_reset()

    def warn_reset(self):
        self.ui.lblWarning.setText('')

    def warn_inputDouble(self):
        self.ui.lblWarning.setText('Warning: input must be of numerical ' +
                                   'double format.')

    def warn_inputInt(self):
        self.ui.lblWarning.setText('Warning: input must be of numerical ' +
                                   'integer format.')

    def open_file(self, filename):
        with open(filename, 'r') as fp:
            index = int(fp.readline()[:-1])
            self.ui.cmbTech.setCurrentIndex(index)
            for led in self.group_ledMxr:
                led.setText(fp.readline()[:-1])
            for led in self.group_dim:
                led.setText(fp.readline()[:-1])
            self.ui.ledLMn.setText(fp.readline()[:-1])
            for i in range(9):
                for j, lblchk in enumerate(self.group_metSel[i+1]):
                    if j != 0:  # skip label
                        lblchk.setChecked(bool(int(fp.readline()[:-1])))
            for led in self.group_prjnet:
                led.setText(fp.readline()[:-1])
            for led in self.group_cost:
                led.setText(fp.readline()[:-1])
        self.ui.setWindowTitle('Star Routing Optimizer & Generator - [' +
                               filename + ']')

    def dialog_open_file(self):
        windowTitle = self.ui.windowTitle()
        if '[' in windowTitle:
            filenameproposal = windowTitle[
                    windowTitle.find('[') + 1: windowTitle.find(']')]
        else:
            filenameproposal = "T:/LayoutToolbox/projects/"

        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
                self.ui, "Open file...", filenameproposal,
                "StarRouteData (*.srd);;All files (*.*)")
        self.open_file(filename)
        self.create_starroute

    def dialog_save_file(self):
        windowTitle = self.ui.windowTitle()
        if '[' in windowTitle:
            filenameproposal = windowTitle[
                    windowTitle.find('[') + 1: windowTitle.find(']')]
        else:
            filenameproposal = ''
        filename, _ = QtWidgets.QFileDialog.getSaveFileName(
                self.ui, "Save As...", filenameproposal,
                "StarRouteData (*.srd);;All files (*.*)")
        self.ui.setWindowTitle('Star Routing Optimizer & Generator - [' +
                               filename + ']')
        with open(filename, 'w') as fp:
            fp.write(str(self.ui.cmbTech.currentIndex()) + '\n')
            for led in self.group_ledMxr:
                fp.write(led.text() + '\n')
            for led in self.group_dim:
                fp.write(led.text() + '\n')
            fp.write(self.ui.ledLMn.text() + '\n')
            for i in range(9):
                for j, lblchk in enumerate(self.group_metSel[i+1]):
                    if j != 0:  # skip label
                        if lblchk.isChecked():
                            fp.write('1\n')
                        else:
                            fp.write('0\n')
            for led in self.group_prjnet:
                fp.write(led.text() + '\n')
            for led in self.group_cost:
                fp.write(led.text() + '\n')

    def read_starprop(self):
        for metnr in range(9):
            self.met[metnr].setRsq(float(self.group_ledMxr[metnr].text())/1000)

        spdim = [float(self.group_dimdict['sp'][x].text()) for x in
                 range(len(self.group_dimdict['sp']))]
        spmet = [self.met[metnr] for metnr in range(9) if
                 self.group_metSel['sp'][metnr].isChecked()]
        sp = SR.StarpointProp(*spdim, spmet)

        radim = [float(self.group_dimdict['ra'][x].text()) for x in
                 range(len(self.group_dimdict['ra']))]
        ramet = [self.met[metnr] for metnr in range(9) if
                 self.group_metSel['ra'][metnr].isChecked()]
        ra = SR.RampProp(*radim, ramet)

        hwdim = [float(self.group_dimdict['hw'][x].text()) for x in
                 range(len(self.group_dimdict['hw']))]
        hwmet = [self.met[metnr] for metnr in range(9) if
                 self.group_metSel['hw'][metnr].isChecked()]
        hw = SR.HighwayProp(*hwdim, hwmet)

        lmdim = [float(self.group_dimdict['lm'][x].text()) for x in
                 range(len(self.group_dimdict['lm']))]
        lmmet = [self.met[metnr] for metnr in range(9) if
                 self.group_metSel['lm'][metnr].isChecked()]
        lm = SR.LastmileProp(*lmdim, lmmet)

        costparams = [float(self.group_cost[x].text()) for x in
                      range(len(self.group_cost))]
        cp = SR.CostParams(*costparams)

        return (sp, ra, hw, lm, cp)

    def create_starroute(self):
        sp, ra, hw, lm, cp = self.read_starprop()
        self.starprop = SR.Starroute(sp, ra, hw, lm, cp)
        print('CREATED: self.starprop = ' + repr(self.starprop))

    def update_starroute(self):
        sp, ra, hw, lm, cp = self.read_starprop()
        self.starprop.setGeometrysical(sp, ra, hw, lm)
        print('UPDATED: self.starprop = ' + repr(self.starprop))

    def tabchange(self, index):
        # print(dir(self))
        if index == 0:
            self.ui.btnAutogen.setEnabled(False)

        if index == 1:
            if 'starprop' not in dir(self):
                self.create_starroute()
            else:
                self.update_starroute()
            self.update_table_state()
            self.ui.btnAutogen.setEnabled(False)
        if index == 2:
            if 'state2d' in dir(self):
                self.draw_result()
                self.ui.btnAutogen.setEnabled(True)
        self.warn_reset()

    def run_DIY_Hillclimb(self, iterations, climb, immediately, initstate):
        SR.printlist(initstate.reshape(
                [self.starprop.lm.n+1, self.starprop.lm.n]))
        self.starprop.cost(initstate, verbose=True)
        self.starprop.R_evaluate(True)
        min_val=float(self.ui.ledPmin.text())
        max_val=float(self.ui.ledPmax.text())
        granularity=float(self.ui.ledPstep.text())
        iterations = int(self.ui.ledIter.text())
        state, cost = SR.hillclimb(self.starprop, initstate, min_val, max_val,
                                   granularity, iterations, climb, immediately)

        return state, cost

    def run_mlrose_optim(self, initstate):
        ## MLROSE implementation
        # ContinuousOpt(length, fitness_fn, maximize=True,
        # min_val=0, max_val=1, step=0.1)
        fitness_fnc = mlrose.CustomFitness(self.starprop.cost, 'continuous')
        problem = mlrose.ContinuousOpt(
                self.starprop.lm.n*(self.starprop.lm.n+1),
                fitness_fnc, maximize=False,
                min_val=float(self.ui.ledPmin.text()),
                max_val=float(self.ui.ledPmax.text()),
                step=float(self.ui.ledPstep.text()))

        # selection
        for selection, rdi in enumerate(self.group_algSel):
            if rdi.isChecked():
                break

        if selection == 1:  # mlrose Hill Climb
            state, cost = mlrose.random_hill_climb(
                    problem,
                    int(self.group_algVal[4].text()),
                    int(self.group_algVal[3].text()),
                    int(self.group_algVal[5].text()),
                    initstate,
                    curve=False,
                    random_state=None)
        elif selection == 2:  # mlrose Randomized Hill Climb
            state, cost = mlrose.hill_climb(
                    problem,
                    int(self.group_algVal[3].text()),
                    int(self.group_algVal[5].text()),
                    initstate,
                    curve=False,
                    random_state=None)
        elif selection == 3:  # mlrose Simulated Annealing
            if self.ui.rdiTDGeom.isChecked():
                schedule = mlrose.GeomDecay(
                        init_temp=float(self.ui.ledTinit.text()),
                        decay=float(self.ui.ledTdecay.text()),
                        min_temp=float(self.ui.ledTmin.text()))
            elif self.ui.rdiTDArith.isChecked():
                schedule = mlrose.ArithDecay(
                        init_temp=float(self.ui.ledTinit.text()),
                        decay=float(self.ui.ledTdecay.text()),
                        min_temp=float(self.ui.ledTmin.text()))
            elif self.ui.rdiTDExp.isChecked():
                schedule = mlrose.ExpDecay(
                        init_temp=float(self.ui.ledTinit.text()),
                        exp_const=float(self.ui.ledTdecay.text()),
                        min_temp=float(self.ui.ledTmin.text()))
            else:
                assert False
            state, cost = mlrose.simulated_annealing(
                    problem, schedule,
                    int(self.group_algVal[4].text()),
                    int(self.group_algVal[3].text()),
                    initstate,
                    curve=False,
                    random_state=None)
        elif selection == 4:  # mlrose Genetic Algorithm
            state, cost = mlrose.genetic_alg(
                    problem,
                    int(self.group_algVal[7].text()),
                    float(self.group_algVal[8].text()),
                    int(self.group_algVal[4].text()),
                    int(self.group_algVal[3].text()),
                    curve=False,
                    random_state=None)
        elif selection == 5:  # mlrose MIMIC
            print('MIMIC not compativble with this kind of problem.')
        else:
            state = initstate
            cost = 0

        return state, cost

    def run_optim(self):
        print('Before optim: ')
        SR.printlist(self.state2d)

        if self.group_algSel[0].isChecked():
            state, cost = self.run_DIY_Hillclimb(
                    int(self.group_algVal[0].text()),
                    float(self.group_algVal[1].text()),
                    bool(self.group_algVal[2].text()),
                    np.concatenate(self.state2d))
        else:
            state, cost = self.run_mlrose_optim(np.concatenate(self.state2d))

        print('After optim: ')
        self.state2d = state.reshape(
                [self.starprop.lm.n+1, self.starprop.lm.n])
        SR.printlist(self.state2d)
        verifycost = self.starprop.cost(state, verbose=True)
        if cost != verifycost:
            print('cost: '+ str(cost))
            print('verifycost: '+ str(verifycost))
            assert False
        self.starprop.R_evaluate(True)
        self.update_table_state()
        self.update_cost_detail()

    def updatecost(self):
        costparams = [float(self.group_cost[x].text()) for x in
                      range(len(self.group_cost))]
        cp = SR.CostParams(*costparams)
        self.starprop.setCostParams(cp)

    def update_cost_detail(self):
        details = self.starprop.cost_details()
        assert len(details)+1 == len(self.group_costRslts)
        for det in range(len(details)):
            self.group_costRslts[det].setText('{:3.2f}'.format(details[det]))
        self.group_costRslts[-1].setText('{:3.2f}'.format(sum(details)))

    def update_table_state(self):
        # startparam = self.starprop.W_equalwidth()
        self.state2d = self.starprop.W_get_state2d()
        self.enable_tblWState_cellchange = False
        # print(repr(self.state2d))
        self.ui.tblWState.setRowCount(len(self.state2d))
        self.ui.tblWState.setColumnCount(len(self.state2d[0]))
        for x in range(len(self.state2d)):
            for y in range(len(self.state2d[x])):
                value = self.state2d[x][y]
                if isinstance(value, float):
                    dispvalue = '{:3.2f}'.format(value)
                self.ui.tblWState.setItem(
                        x, y, QtWidgets.QTableWidgetItem(dispvalue))
        self.ui.tblWState.show()
        self.enable_tblWState_cellchange = True

    def reset_state_equalwidth(self):
        self.starprop.W_equalwidth()
        self.update_table_state()

    def stateCellChanged(self, x, y):
        if self.enable_tblWState_cellchange:
            try:
                newval = float(self.ui.tblWState.item(x, y).text())
            except ValueError:
                pass
            else:
                self.state2d[x][y] = newval
            self.update_table_state()

    def draw_result(self):
        self.starprop.calc_all_params()
        self.drw_tracks, self.drw_xrange, self.drw_yrange = (
                self.starprop.draw_tracks())
        #♣ self.drw_zoom = .5
        self.calc_sliders()

        self.draw_tracks()

    def calc_sliders(self):
        canvasw = int(700 / self.drw_zoom)
        canvash = int(350 / self.drw_zoom)
        if canvasw > self.drw_xrange[1] - self.drw_xrange[0]:
            self.ui.scrlHCanvas.setEnabled(False)
            self.ui.scrlHCanvas.setMinimum(self.drw_xrange[0])
            self.ui.scrlHCanvas.setMaximum(self.drw_xrange[0])
        else:
            self.ui.scrlHCanvas.setEnabled(True)
            self.ui.scrlHCanvas.setMinimum(self.drw_xrange[0])
            self.ui.scrlHCanvas.setMaximum(self.drw_xrange[1] - canvasw)
        if canvash > self.drw_yrange[1] - self.drw_yrange[0]:
            self.ui.scrlVCanvas.setEnabled(False)
            self.ui.scrlVCanvas.setMinimum(self.drw_yrange[0])
            self.ui.scrlVCanvas.setMaximum(self.drw_yrange[0])
        else:
            self.ui.scrlVCanvas.setEnabled(True)
            self.ui.scrlVCanvas.setMinimum(self.drw_yrange[0])
            self.ui.scrlVCanvas.setMaximum(self.drw_yrange[1] - canvash)

    def draw_tracks(self, xoffset=None, yoffset=None):
        if xoffset is None:
            xoffset = self.drw_xrange[0]
        if yoffset is None:
            yoffset = self.drw_yrange[0]

        offset = np.array([xoffset, yoffset, 0, 0, 0])
        # print('offset: ' + repr(offset))
        colors = ["#FF0000", "#00FF00", "#0000FF",
                  "#FFFF00", "#FF00FF", "#00FFFF",
                  "#FF8080", "#80FF80", "#8080FF",
                  "#FFFF80", "#FF80FF", "#80FFFF",
                  "#000000"]
        canvas = QtGui.QPixmap(700, 350)
        canvas.fill(Qt.white)
        self.ui.lblCanvas.setPixmap(canvas)
        painter = QtGui.QPainter(self.ui.lblCanvas.pixmap())
        pen = QtGui.QPen()
        pen.setWidth(1)
        brush = QtGui.QBrush()
        brush.setStyle(Qt.SolidPattern)
        for track in self.drw_tracks:
            color = colors[int(track[4])]
            # color = random.choice(colors)
            pen.setColor(QtGui.QColor(color))
            brush.setColor(QtGui.QColor(color))
            painter.setPen(pen)
            painter.setBrush(brush)
            drawtrack = (track - offset) * self.drw_zoom
            painter.drawRect(int(drawtrack[0]),
                             int(drawtrack[1]),
                             int(drawtrack[2]), int(drawtrack[3]))
        painter.end()
        self.ui.update()

    def sliderchanged(self, value):
        # print('x: ' + str(self.ui.scrlHCanvas.value()))
        # print('y: ' + str(self.ui.scrlVCanvas.value()))
        self.draw_tracks(self.ui.scrlHCanvas.value(),
                         self.ui.scrlVCanvas.value())

    def zoom_changed(self):
        self.drw_zoom = float(self.ui.ledZoom.text())
        self.calc_sliders()
        self.draw_tracks()

    def autogen(self):
        print('biep')
        project = self.ui.ledProject.text()
        netname = self.ui.ledNet.text()
        filename = self.starprop.autogen(project, netname)
        self.ui.lblWarning.setText('Autogenfile saved to: ' + filename)
        print('Autogenfile saved to: ' + filename)


def gui(filename, outfile):
    app = QtWidgets.QApplication(sys.argv)
    ui = MainUI(filename, outfile)
    app.exec_()


def cli(filename, outfile):
    print('NOT YET FUNCTIONAL.  Try the gui instead.  \n\nThx\n')


def argparse_setup(subparsers):
    parser_sr_gui = subparsers.add_parser(
            'gui', help='Use the gui to set and run the starrouting app')
    parser_sr_gui.add_argument(
            '-f', '--filename', default=None, help='the srd-file to be loaded')
    parser_sr_gui.add_argument(
            '-o', '--outfile', default=None,
            help=('the csv report file name, default: <cellname>_drc.csv in ' +
                  r'the drc result file location'))
    parser_sr_cli = subparsers.add_parser(
            'cli', help=('Use the command-line interface to set and run the ' +
                         'starrouting app !! NOT YET IN PLACE !!'))
    parser_sr_cli.add_argument(
            '-f', '--filename', default=None, help='the srd-file to be loaded')
    parser_sr_cli.add_argument(
            '-o', '--outfile', default=None,
            help=('the csv report file name, default: <cellname>_drc.csv in ' +
                  r'the drc result file location'))


def argparse_eval(args):
    # make a dict of args
    dictargs = vars(args)
    funcdict = {'gui': (gui,
                        [dictargs.get('filename'),
                         dictargs.get('outfile')]),
                'cli': (cli,
                        [dictargs.get('filename'),
                         dictargs.get('outfile')])
                }
    return funcdict


if __name__ == '__main__':
    general.logsetup()
    general.myargparse(argparse_setup, argparse_eval, 'v20221005')
