import os
import re

import logging
# import general
import LTBsettings
import LTBfunctions
import spice
import stdcells

# LayoutGen tab


def projectslist(inifilename=None):
    pl = []
    if inifilename is None:
        inifilename = LTBsettings.defaultprojectsettings()
    if os.path.isfile(inifilename):
        with open(inifilename, 'r') as inifile:
            for line in inifile:
                pattern = r'(?P<name>\w+)[.]projectname\s*=\s*(?P=name)'
                m = re.search(pattern, line)
                if m is not None:
                    # projects added later come higher in the list
                    pl.insert(0, m.groups()[0])
        return pl
    else:
        raise Exception('Projects ini file does not exist')
        return []


def createprojectdir(project):
    LTBfunctions.prepare_project_dir(project)


def iscreatedprojectdir(project):
    return LTBfunctions.isprepared_project_dir(project)


def copynetlist_proj2ltb(project, backup=True):
    # copy .sp files from project netlist directory to LTB
    try:
        LTBfunctions.copynetlist_proj2ltb(project, backup)
    except Exception:
        logging.exception("LTBfunctions.copynetlist_proj2ltb('" +
                          str(project) + "', " + str(backup) + ") failed.")
        raise


def dictcells(project):
    # print('read cells from: ' + project)

    allcellsdict = {}

    # search first for cells in project.sp
    seditfilepath = LTBsettings.seditfilepath(project)
    filename = seditfilepath + project + '.sp'
    if os.path.exists(seditfilepath):
        if os.path.isfile(filename):
            modifiedtime = os.path.getmtime(filename)
            with open(filename, 'r') as spfile:
                for line in spfile:
                    if len(line) > 9 and line[0] == '.':
                        m = re.match(r'^.subckt\s+(\w+)', line, re.I)
                        if m is not None:
                            allcellsdict[m.groups()[0]] = (filename,
                                                           modifiedtime)
        for file in os.listdir(seditfilepath):
            if file.endswith('.sp'):
                filename = os.path.join(seditfilepath, file)
                cellname = file[:-3]
                # print(cellname)
                modifiedtime = os.path.getmtime(filename)
                with open(filename, 'r') as spfile:
                    for line in spfile:
                        if len(line) > 9 and line[0] == '.':
                            m = re.match(r'^.subckt\s+('+cellname+')\s+', line,
                                         re.I)
                            if m is not None:
                                allcellsdict[m.groups()[0]] = (filename,
                                                               modifiedtime)
    return allcellsdict

    # for key in allcellsdict:
    #     print('{:32} {:<30} {:>30}'.format(key, allcellsdict[key][0],
    #                                        time.ctime(allcellsdict[key][1])))


def cellslist(project):
    # print(project)
    allcellsdict = dictcells(project)
    allcellslist = list(allcellsdict.keys())
    allcellslist.sort()

    return allcellslist


def cellinfo(project, cellname):
    # print(project)
    allcellsdict = dictcells(project)
    if cellname in allcellsdict:
        return allcellsdict[cellname]

    return None


def dictinstances(project, cellname):
    celldict = cellinfo(project, cellname)
    if celldict is None:
        return {}

    # print('read instances from: ' + project + ' / ' + cellname)

    filename = celldict[0]

    # if os.path.isfile(filename):  <= should always be True

    insubckt = False
    instdict = {}
    # print(filename)
    with open(filename, 'r') as spfile:
        for line in spfile:
            if not insubckt:
                if len(line) > 9 and line[0] == '.':
                    m = re.match(r'^.subckt\s+('+cellname+')\s+', line, re.I)
                    if m is not None:
                        insubckt = True
                        # print('in')
            else:
                if len(line) > 4 and line[0] == '.':
                    m = re.match(r'^.ends\s?', line, re.I)
                    if m is not None:
                        # print('out')
                        break
                if len(line) > 5 and line[0] in 'xX':
                    m = re.match(r'^(X\w+)(?:<(\d+)>)?\s+', line, re.I)
                    if m is not None:
                        inst = m.groups()[0]
                        cardinality = m.groups()[1]
                        # print(inst + ' ' + repr(cardinality))
                        if cardinality is not None:
                            if inst in instdict:
                                instdict[inst].append(int(cardinality))
                            else:
                                instdict[inst] = [int(cardinality)]

    cardwarn = ''
    for key in instdict:
        cardlist = instdict[key]
        mincard = min(cardlist)
        maxcard = max(cardlist)
        for c in range(mincard, maxcard+1):
            if c not in cardlist:
                cardwarn += (key + '<' + str(c) + '> does not exist in ' +
                             cellname + '\n')
        instdict[key] = (mincard, maxcard)

    if cardwarn != '':
        print(cardwarn)
        logging.warning(cardwarn)

    return instdict

    # for key in allcellsdict:
    #     print('{:32} {:<30} {:>30}'.format(key, allcellsdict[key][0],
    #                                        time.ctime(allcellsdict[key][1])))


def netlist2autogen(project, cellname, force=False):
    logging.info(">>> import spice;spice.netlist2autogen('" + str(project) +
                 "', '" + str(cellname) + "', force=" + str(force) + ")")
    try:
        spice.netlist2autogen(project, cellname, force=force)
    except Exception:
        logging.exception("spice.netlist2autogen('" + str(project) + "', '" +
                          str(cellname) + "', force=" + str(force) +
                          ") failed.")
        raise


def netlist2wrl(project, cellname, force=False):
    logging.info(">>> import spice;spice.netlist2wrl('" + str(project) +
                 "', '" + str(cellname) + "', force=" + str(force) + ")")
    try:
        spice.netlist2wrl(project, cellname, force=force)
    except Exception:
        logging.exception("spice.netlist2wrl('" + str(project) + "', '" +
                          str(cellname) + "', force=" + str(force) +
                          ") failed.")
        raise


def netlist2autolabel(project, cellname, force=False):
    logging.info(">>> import spice;spice.netlist2autolabel('" + str(project) +
                 "', '" + str(cellname) + "', force=" + str(force) + ")")
    try:
        spice.netlist2autolabel(project, cellname, force=force)
    except Exception:
        logging.exception("spice.netlist2autolabel('" + str(project) + "', '" +
                          str(cellname) + "', force=" + str(force) +
                          ") failed.")
        raise


def netlist2stdcells(project, cellname=None, lib=None, force=False):
    logging.info(">>> import stdcells;stdcells.filter('" + str(project) +
                 "', '" + str(cellname) + "', '" + str(lib) + "', force=" +
                 str(force) + ")")
    try:
        stdcells.filter(project, cellname, lib, force=force)
    except Exception:
        logging.exception("stdcells.filter('" + str(project) + "', '" +
                          str(cellname) + "', '" + str(lib) + "', force=" +
                          str(force) + ") failed.")
        raise


def netlist2autoplace(project, cellname, instnamerange, startx, starty, pitch,
                      force=False):
    listpitch = pitch.split()
    logging.info(">>> import spice;spice.netlist2autoplace('" + str(project) +
                 "', '" + str(cellname) + "', '" + str(instnamerange) + "', " +
                 str(startx) + ", " + str(starty) + ", " + str(listpitch) +
                 ", force=" + str(force) + ")")
    try:
        spice.netlist2autoplace(project, cellname, instnamerange, startx,
                                starty, listpitch, force=force)
    except Exception:
        logging.exception("spice.netlist2autoplace('" + str(project) + "', '" +
                          str(cellname) + "', '" + str(instnamerange) + "', " +
                          str(startx) + ", " + str(starty) + ", " +
                          str(listpitch) + ", force=" + str(force) +
                          ") failed.")
        raise

# Verification tab


# Licensing tab


# User Settings tab
