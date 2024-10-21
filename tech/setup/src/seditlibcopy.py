import datetime
import logging      # in case you want to add extra logging
import general
import shutil
import pathlib
import re
import os
import time
import glob
import subprocess
import filecmp
import settings
import LTBsettings
import sedit


class checkcopybutok(general.LTBError):
    pass


class Lib2copy():
    def __init__(self, src, dst):
        self.src = sedit.Design(src)
        self.dst = sedit.Design(dst)
        self.equalnames = self.src.name.lower() == self.dst.name.lower()
        self.equalparents = (str(self.src.path.parents[0]).lower() ==
                             str(self.dst.path.parents[0]).lower())

    def __repr__(self):
        return ("Lib2copy(" + repr(str(self.src.path)) + ", " +
                repr(str(self.dst.path)) + ")")

    def checkbeforecopy(self):
        # # check if all source and destination name is equal
        # if not self.equalnames:
        #     general.error_log('Destination name is not equal to source name,
        #                        is that no issue?')

        # check if all (requiredfiles) necessary source files exist
        for i in self.src.requiredfiles:
            if not i.exists():
                raise Exception('Lib2copy.checkbeforecopy: Source library ' +
                                'file/path "' + str(i) + '" does not exist.')
        # check if destination folder does not exist, Yes, you'll have to
        # start copying into a virgin directory
        if self.dst.path.exists():
            raise checkcopybutok('Lib2copy.checkbeforecopy: Destination ' +
                                 'library path "' + str(self.dst.path) +
                                 '" already exists, overwriting is not ' +
                                 'recommended because of possible data-loss.')

    def copy(self, timestamp):
        logslc = logging.getLogger('seditlibcopy')
        # copy design files, that's easy
        self.dst.path.mkdir(parents=True)
        for i in range(len(self.src.allfiles)):
            logslc.info(str(self.src.allfiles[i]) + ' -> ' +
                        str(self.dst.allfiles[i]))
            try:
                shutil.copy2(str(self.src.allfiles[i]),
                             str(self.dst.allfiles[i]))
            except FileNotFoundError:
                if self.src.allfiles[i] in self.src.requiredfiles:
                    raise

        # copy folders
        for i in range(len(self.src.allfolders)):
            try:
                shutil.copytree(str(self.src.allfolders[i]),
                                str(self.dst.allfolders[i]))
            except FileNotFoundError:
                # setup is not so important, just skip if it does not exist
                break

            # print dirtree (2 levels)
            for child in self.dst.allfolders[i].iterdir():
                logslc.info(str(child))
                if child.is_dir():
                    for grandchild in child.iterdir():
                        logslc.info(str(grandchild))
                        if grandchild.is_dir():
                            logslc.info(str(grandchild) + r'\*.*')

    def delsource(self):
        for i in range(len(self.src.allfolders)):
            try:
                shutil.rmtree(self.src.allfolders[i])
            except FileNotFoundError:
                pass

        for i in range(len(self.src.allfiles)):
            try:
                os.remove(self.src.allfiles[i])
            except FileNotFoundError:
                pass

        try:
            os.rmdir(self.src.path)
        except Exception:
            pass

    def repairrelativesrclinksindst(self):
        lllines = self.src.get_liblinks()
        changed = False
        for ll in lllines:
            if '..' in ll:
                abslink = str(self.src.path / ll)
                abslink = sedit.resolve2dots(abslink)
                self.dst.replace_liblink(ll, abslink)
                changed = True
            if changed:
                print(str(self.src.path) + ': ' + ll[:-1])
                print(str(self.dst.path) + ': ' + abslink[:-1])


def copylibs(libs2copylist, timestamp, move=False):
    logslc = logging.getLogger('seditlibcopy')
    # copy (relevant) files for each lib
    # first check all and only continue when they all pass
    for l2c in libs2copylist:
        try:
            l2c.checkbeforecopy()
        except checkcopybutok:
            print('already exist: ' + str(l2c))
            logslc.info('already exist, skip copy: ' + str(l2c))

    for l2c in libs2copylist:
        try:
            l2c.checkbeforecopy()
        except checkcopybutok:
            break
        l2c.copy(timestamp)
        if not l2c.equalparents:
            l2c.repairrelativesrclinksindst()
        if not l2c.equalnames:
            l2c.dst.replace_designname(l2c.src.name, l2c.dst.name)

    logslc.info('All folders have been copied.  Their libraries still link' +
                'absolute to the schematics on the old location.')


def findnetlistsin(netlistfolder):
    subpdf = [sedit.Design(netlistfolder)]
    i = 0
    while i < len(subpdf):
        unfold = [sedit.Design(x) for x in subpdf[i].path.iterdir() if
                  x.is_dir()]

        i += 1
        if len(unfold) > 0:
            subpdf[i:i] = unfold
        if i % 250 == 0:
            print(str(i) + ' / ' + str(len(subpdf)) + '   (' +
                  str(subpdf[i-1].path) + ')')
    # #for x in subpdf:
    # #    print(x.path)
    print('unfolded structure size: ' + str(len(subpdf)))
    # what it will return are folders contain netlists
    return subpdf


def subfolderlist(folder):
    subpdf = [pathlib.Path(folder)]
    i = 0
    while i < len(subpdf):
        unfold = [x for x in subpdf[i].iterdir() if x.is_dir()]

        i += 1
        if len(unfold) > 0:
            subpdf[i:i] = unfold
        if i % 250 == 0:
            print(str(i) + ' / ' + str(len(subpdf)) + '   (' +
                  str(subpdf[i-1]) + ')')

    print('unfolded structure size: ' + str(len(subpdf)))
    # what it will return are all subfolders of folder
    return subpdf


def modifynetlist(moved_sch_libs, timestamp, beforeafter):
    netlistfolderbeforeafter = ('T:\\libcopylog' + timestamp + '\\export' +
                                beforeafter)
    allnetlists = findnetlistsin(netlistfolderbeforeafter)

    cmpcount = len(allnetlists)
    print(str(cmpcount) + ' folders to modify.')
    if cmpcount > 99:
        print('|---------' * 10 + '|')
    else:
        print('|' + '-' * (cmpcount-2) + '|')
    pct = 0
    pct1 = cmpcount / 100
    counttotal = 0
    for net in allnetlists:
        counttotal += 1
        if counttotal // pct1 != pct:
            pct = counttotal // pct1
            print('.', end='')

        path = str(net.path)+'\\*.sp'
        files = glob.glob(path)
        for filename in files:
            with open(filename, "r") as input:
                # lines = input.readlines()
                # del lines[1]
                # for i in range(len(lines)):
                #     lines[i] = re.sub('devices_generic_', 'devices_',
                #                       lines[i], 0, re.I)
                #     lines[i] = re.sub('IO_generic_', 'io_', lines[i],
                #                       0, re.I)
                #     lines[i] = re.sub('logic_generic_', 'logic_', lines[i],
                #                       0, re.I)
                #     lines[i] = re.sub('monitors_generic_', 'monitors_',
                #                       lines[i], 0, re.I)
                #     lines[i] = re.sub('stdcell_generic_', 'stdcells_',
                #                       lines[i], 0, re.I)
                # input.writelines(lines)
                alltext = input.read()
            # remove date and design name (S-Edit export comment)
            newtext = re.sub('\n.+\n.+\n', '\n', alltext, 1)
            # remove date and design name (S-Edit export comment)
            # newtext = re.sub('\n.+.subckt stdcells_PAGEFRAME  \n.+\n', '\n',
            #                  alltext, 1)

            # if beforeafter == 'before':
            #    newtext = re.sub('devices_generic_', 'devices_', newtext,
            #                     0, re.I)
            #    newtext = re.sub('IO_generic_', 'io_', newtext, 0, re.I)
            #    newtext = re.sub('logic_generic_', 'logic_', newtext, 0,
            #                     re.I)
            #    newtext = re.sub('monitors_generic_', 'monitors_', newtext,
            #                     0, re.I)
            #    newtext = re.sub('stdcell_generic_', 'stdcells_', newtext,
            #                     0, re.I)

            if beforeafter == 'before':
                # move outputs from libraries themselves from old location to
                # new location for comparison
                logfolder = ('T:\\libcopylog' + timestamp + '\\export' +
                             beforeafter + '\\')
                for sch, l2c in moved_sch_libs:
                    strsrcpath = str(l2c.src.path)
                    r2d_strsrcpath = sedit.resolve2dots(strsrcpath)
                    beforeexportpath = (logfolder +
                                        r2d_strsrcpath.replace(':', ''))

                    if beforeexportpath in filename:
                        strdstpath = str(l2c.dst.path)
                        r2d_strdstpath = sedit.resolve2dots(strdstpath)
                        beforeexportpath_cmp = (logfolder +
                                                r2d_strdstpath.replace(':', '')
                                                )
                        # otherwise the io becomes io_local_local_local...
                        # for as many times as there are libraries calling
                        # io_local or something
                        if beforeexportpath_cmp not in filename:
                            filename = filename.replace(beforeexportpath,
                                                        beforeexportpath_cmp)
                # replace all 'libname_' by 'newlibname_'
                for sch, l2c in moved_sch_libs:
                    # if file part of sch (path)
                    beforeexportpath = (logfolder +
                                        str(sch.path).replace(':', ''))
                    if beforeexportpath in filename:
                        if not l2c.equalnames:
                            # newtext = re.sub(l2c.src.name + '_',
                            #                  l2c.dst.name + '_', newtext, 0,
                            #                  re.I)
                            # > line above not good, it also changes parameter
                            # names and so on (try with adding space in the
                            # pattern)
                            if l2c.src.name.lower() == 'io':
                                # special case: since there are so many cells
                                # with name io_*, we only replace io_io_ in to
                                # IO_local_io_
                                newtext = re.sub(' ' + l2c.src.name + '_io_',
                                                 ' ' + l2c.dst.name + '_io_',
                                                 newtext, 0, re.I)
                            else:
                                newtext = re.sub(' ' + l2c.src.name + '_',
                                                 ' ' + l2c.dst.name + '_',
                                                 newtext, 0, re.I)

            outfilename = filename.replace('export' + beforeafter,
                                           'export' + beforeafter + '_cmp')

            general.write(outfilename, newtext, False)


def comparenetlistfolders(timestamp, ignorepaths=[], genCopy=False):
    logslc = logging.getLogger('seditlibcopy')
    netlistfolderbefore = ('T:\\libcopylog' + timestamp + '\\export' +
                           'before' + '_cmp')
    netlistfolderafter = ('T:\\libcopylog' + timestamp + '\\export' +
                          'after' + '_cmp')
    subfolderlistbefore = subfolderlist(netlistfolderbefore)
    subfolderlistafter = subfolderlist(netlistfolderafter)

    # compare folder structure and file content of each identical folder
    poplistbefore = [str(x) for x in subfolderlistbefore]
    poplistafter = [str(x) for x in subfolderlistafter]
    if (not glob.glob('T:\\libcopylog' + timestamp + '\\export' + 'before' +
                      '_cmp' + '\\*.*') and
            not glob.glob('T:\\libcopylog' + timestamp + '\\export' + 'after' +
                          '_cmp' + '\\*.*')):
        poplistbefore.remove('T:\\libcopylog' + timestamp + '\\export' +
                             'before' + '_cmp')
        poplistafter.remove('T:\\libcopylog' + timestamp + '\\export' +
                            'after' + '_cmp')
    else:
        raise Exception('A file in the main exportbefore_folder or ' +
                        'exportafter_folder was found... Was not expected')

    tocompare = []
    beforeonly = []
    afteronly = []

    # while len(poplistbefore) > 0:
    #    folderbefore = poplistbefore.pop(0)
    for folderbefore in poplistbefore:
        if not genCopy:
            folderafter = folderbefore.replace('exportbefore', 'exportafter')
        else:
            # we are copying generation-style - folderhierarchy might have
            # changed. Frind for each original design the new design
            # Now, each folder that is no SEDIT-design is actually not
            # important to compare anyway. This way we use the sedit design
            # name to mach folders
            folderafter = ""
            orig_name = folderbefore[folderbefore.rfind('\\')+1:]

            for copyfolder in poplistafter:
                copy_name = copyfolder[copyfolder.rfind('\\')+1:]
                if orig_name == copy_name:
                    folderafter = copyfolder
                    break  # for copyfolder in poplistafter:
            # I think the following 3 lines are to be removed (KL 20220111):
            # else:
            #     if not folderafter:
            #         continue

        if folderafter in poplistafter:
            poplistafter.remove(folderafter)

            filesbefore = glob.glob(folderbefore + '\\*.*')

            filesafter = glob.glob(folderafter + '\\*.*')

            # while len(filesbefore) > 0:
            #    filebefore = filesbefore.pop(0)
            for filebefore in filesbefore:
                if not genCopy:
                    fileafter = filebefore.replace('exportbefore',
                                                   'exportafter')
                else:
                    orig_filename = filebefore[filebefore.rfind('\\')+1:]
                    expected_copy = folderafter + '\\' + orig_filename
                    if expected_copy in filesafter:
                        fileafter = expected_copy
                    else:
                        raise Exception('An expected copyfile (' +
                                        expected_copy + ') was not found!')
                if fileafter in filesafter:
                    filesafter.remove(fileafter)
                    if os.path.isfile(filebefore):
                        tocompare.append([filebefore, fileafter])
                    else:
                        # some dirs have a dot in the folder name, that comes
                        # unintenionally with glob in the list
                        print('not to compare:')
                        print("filecmp.cmp(r'" + filebefore + "', r'" +
                              fileafter + "')")
                else:
                    beforeonly.append(filebefore)
            afteronly.extend(filesafter)
        else:
            beforeonly.append(folderbefore)
    afteronly.extend(poplistafter)

    if len(beforeonly) + len(afteronly) != 0:
        print('\n\nDifferences in folder structure:')
        logslc.info('\n\nDifferences in folder structure:')
        print('Before only:')
        logslc.info('Before only:')
        for x in beforeonly:
            print('\t' + x)
            logslc.info('\t' + x)
        print('After only:')
        logslc.info('After only:')
        for x in afteronly:
            print('\t' + x)
            logslc.info('\t' + x)

    # compare files identical

    cmpcount = len(tocompare)
    print(str(cmpcount) + ' files to compare.')
    if cmpcount > 99:
        print('|---------' * 10 + '|')
    else:
        print('|' + '-' * (cmpcount-2) + '|')
    pct = 0
    pct1 = cmpcount / 100
    checkagain = []
    countequal = 0
    countnonequal = 0
    counttotal = 0
    for filebefore, fileafter in tocompare:
        if not filecmp.cmp(filebefore, fileafter):
            checkagain.append([filebefore, fileafter])
            countnonequal += 1
        else:
            countequal += 1
        counttotal += 1
        if counttotal // pct1 != pct:
            pct = counttotal // pct1
            print('.', end='')

    print('\n\nNumber of equal files:' + str(countequal))
    logslc.info('\n\nNumber of equal files:' + str(countequal))
    print('Number of non-equal files:' + str(countnonequal))
    logslc.info('Number of non-equal files:' + str(countnonequal))

    # if not identical, compare identical number of subcircuits, identical
    # list of names of subcircuits and identical definition for each subcircuit
    cmpcount = len(checkagain)
    print(str(cmpcount) + ' files to check better.')
    if cmpcount > 99:
        print('|---------' * 10 + '|')
    else:
        print('|' + '-' * (cmpcount-2) + '|')
    pct = 0
    pct1 = cmpcount / 100

    reallynotidentical = []
    counttotal = 0
    for filebefore, fileafter in checkagain:
        counttotal += 1
        if counttotal // pct1 != pct:
            pct = counttotal // pct1
            print('.', end='')
        beforesubcktdict = {}
        aftersubcktdict = {}
        # open binary, otherwise f.tell() does not work well.
        with open(filebefore, 'rb') as fbefore, \
                open(fileafter, 'rb') as fafter:
            # linenr = 0
            insubckt = False
            # for line in fbefore:  <-- this uses the file as iterator,
            #                           but it screws because of a kind of
            #                           readahead buffer the file position,
            #                           tell() is not usable.
            line = fbefore.readline()
            filepos_tmp = 0
            while line != b'':
                # linenr += 1
                if line.startswith(b'.subckt'):
                    assert not insubckt
                    insubckt = True
                    start = line.find(b' ')
                    end = line.find(b' ', start+1)
                    subcktname = line[start+1:end]
                    subcktstartpos = filepos_tmp
                elif line.startswith(b'.ends'):
                    assert insubckt
                    insubckt = False
                    subcktendpos = fbefore.tell()
                    beforesubcktdict[subcktname] = [subcktstartpos,
                                                    subcktendpos]
                filepos_tmp = fbefore.tell()
                line = fbefore.readline()

            insubckt = False
            # for line in fafter:
            line = fafter.readline()
            while line != b'':
                # linenr += 1
                if line.startswith(b'.subckt'):
                    assert not insubckt
                    insubckt = True
                    start = line.find(b' ')
                    end = line.find(b' ', start+1)
                    subcktname = line[start+1:end]
                    subcktstartpos = filepos_tmp
                elif line.startswith(b'.ends'):
                    assert insubckt
                    insubckt = False
                    subcktendpos = fafter.tell()
                    assert subcktendpos < 1000000000
                    aftersubcktdict[subcktname] = [subcktstartpos,
                                                   subcktendpos]
                filepos_tmp = fafter.tell()
                line = fafter.readline()

            # check if all subcktnames are equal
            if len(beforesubcktdict) != len(aftersubcktdict):
                reallynotidentical.append([filebefore, fileafter])
                continue
            tmp = True
            for key in beforesubcktdict.keys():
                if key not in aftersubcktdict:
                    tmp = False
                    break
            if not tmp:
                reallynotidentical.append([filebefore, fileafter])
                continue

            # check if subcktcontent is equal
            tmp = True  # still True
            for key in beforesubcktdict.keys():
                beforestart = beforesubcktdict[key][0]
                beforeend = beforesubcktdict[key][1]
                fbefore.seek(beforestart)
                beforetext = fbefore.read(beforeend - beforestart)

                afterstart = aftersubcktdict[key][0]
                afterend = aftersubcktdict[key][1]
                fafter.seek(afterstart)
                aftertext = fafter.read(afterend - afterstart)
                if beforetext != aftertext:
                    tmp = False
                    break

            if not tmp:
                reallynotidentical.append([filebefore, fileafter])
                continue
    print('\nNumber of non-equal netlists: ' + str(len(reallynotidentical)))
    logslc.info('\nNumber of non-equal netlists: ' +
                str(len(reallynotidentical)))
    runyourself = "Run yourself:\n\n"
    runyourself += ('reallynotidentical = {0}\n'.format(repr(reallynotidentical)))
    runyourself += 'from seditlibcopy import *\n'
    runyourself += 'for filebefore, fileafter in reallynotidentical:\n'
    runyourself += (r"""    subprocess.run(r'"c:\Program Files\WinMerge""" +
                    r"""\WinMergeU.exe" "' + filebefore + '" "' + fileafter + '"')""")
    logslc.info(runyourself)

    manualcheck = []
    for filebefore, fileafter in reallynotidentical:
        for ignorepath in ignorepaths:
            if ignorepath[2:] in filebefore:
                break
        else:
            manualcheck.append([filebefore, fileafter])

    print('\nNumber of netlists ignored: ' +
          str(len(reallynotidentical) - len(manualcheck)))

    print('\nNumber of netlists to check manually: ' + str(len(manualcheck)))
    logslc.info('\nNumber of netlists to check manually: ' +
                str(len(manualcheck)))
    for filebefore, fileafter in manualcheck:
        print(filebefore + ' <--> ' + fileafter)
    runyourself = "Run yourself:\n\n"
    runyourself += ('manualcheck = {0}\n'.format(repr(manualcheck)))
    runyourself += 'from seditlibcopy import *\n'
    runyourself += 'for filebefore, fileafter in manualcheck:\n'
    runyourself += (r"""    subprocess.run(r'"c:\Program Files\WinMerge""" +
                    r"""\WinMergeU.exe" "' + filebefore + '" "' + fileafter + '"')""")
    logslc.info(runyourself)


def uniquename_and_thislib_in_liblinkdict(liblinkdict, absliblink):
    # liblinkdict = self.get_liblinkdict()

    libname = pathlib.Path(absliblink).name

    if libname in liblinkdict:
        links = set()
        for tree, link in liblinkdict[libname]:
            links.add(link.lower())
        if len(links) > 1:
            return False
        else:
            the_one_link = links.pop()
            if the_one_link == absliblink.lower():
                return True
            else:
                return False
    else:
        return False


# def resolve2dots(path):
#    #print('resolve2dots:')
#    #print('path: ' + path)
#    resolvedpath = path
#    while '\\..\\' in resolvedpath:
#        #print('temp resolvedpath: ' + resolvedpath)
#        y = re.sub(r'\\[^\\]+\\[.][.]\\', r'\\',resolvedpath,1)
#        #print('y: ' + str(y))
#        resolvedpath = y
#    #print('resolvedpath: ' + resolvedpath)
#    return resolvedpath


def exportspice(timestamp, allschematics, beforeafter, autoclick):
    logslc = logging.getLogger('seditlibcopy')

    if len(allschematics) == 0:
        raise Exception('Number of schematics is 0. Hint: check on typos of' +
                        ' schematicsfolder in projects.xls for your project.')
    logslc.info('CREATE EXPORT' + beforeafter.upper() + ' TCL SCRIPT\n')

    # do export of all potentially affected spice outputs
    logtclfilename = ('T:\\libcopylog' + timestamp + '\\export' + beforeafter +
                      '.tcllog')
    tclfilename = os.path.expanduser(r'~\AppData\Roaming\Tanner EDA\scripts' +
                                     r'\startup\export' + beforeafter + '.tcl')
    general.prepare_dir_for(tclfilename)
    general.prepare_dir_for(logtclfilename)
    try:
        with open(tclfilename, 'w') as tclfile, \
                open(logtclfilename, 'w') as logtclfile:
            txt = "source {X:\\SEdit\\spiceexport.tcl} -encoding utf-8\n\n"
            tclfile.write(txt)
            logtclfile.write(txt)
            waitalittlelongerfirsttime = True
            for sch in allschematics:
                logfolder = ('T:\\libcopylog' + timestamp + '\\export' +
                             beforeafter + '\\')
                folder = logfolder + str(sch.path).replace(':', '')
                print(folder)
                general.prepare_dir_for(folder)
                os.mkdir(folder)
                # A.C. added line below:
                # 23/05/2018: If I give SEDIT no time in between the exports,
                # there is an 80% possibility of an SEDIT-crash!
                txt = 'after 500 '+'\n'
                if waitalittlelongerfirsttime:
                    txt = 'after 4000 '+'\n'
                    waitalittlelongerfirsttime = False

                txt += ('puts "OPEN : design open ' +
                        re.sub(r'[\\]', r'\\\\', str(sch.path)) + '\\\\' +
                        sch.name + '.tanner\"\n')
                txt += ('design open "' +
                        re.sub(r'[\\]', r'\\\\', str(sch.path)) + '\\\\' +
                        sch.name + '.tanner"\n')
                txt += ('topcellviewexport "' +
                        re.sub(r'[\\]', r'\\\\', folder) + r'\\" "' +
                        sch.name + '"\n')
                txt += ('design close -design "' + sch.name + '"\n\n')
                tclfile.write(txt)
                logtclfile.write(txt)

            txt = 'exit -now\n\n'
            tclfile.write(txt)
            logtclfile.write(txt)

        print("!!!!!!!!!!!!!!!!!!!!!!!")
        print("!!! Time for action '''")
        print("!!!!!!!!!!!!!!!!!!!!!!!")
        print("")
        # print("Open S-Edit and execute the following in the command window:")
        # print("source {" + tclfilename + "} -encoding utf-8")
        print("Opens S-Edit automatically and executes the export batch:")
        print("")
        print("The library move and design fix continues (automatically) as " +
              "soon as the script has been succesfully finished.")
        print("")
        print("Waiting for the S-Edit to have closed.")
        Seditexec = [(r'C:\MentorGraphics\Tanner EDA\Tanner Tools v2016.1' +
                      r'\x64\sedit64.exe'),
                     (r'D:\MentorGraphics\Tanner EDA\Tanner Tools v2016.1' +
                      r'\x64\sedit64.exe')]
        for x in Seditexec:
            if os.path.exists(x):
                # Wait for it... tcl file maybe not fully closed yet?
                time.sleep(10)
                break
        else:
            raise Exception('No S-Edit executable found on known location')

        seditprocess = subprocess.Popen('"' + x + '"')
        tenseconds = 0
        while seditprocess.poll() is None:
            time.sleep(10)
            if autoclick:
                subprocess.Popen(r"X:\SEdit\omitActivate.exe")
            tenseconds += 1
            if tenseconds % 360 == 0:
                print('.')
            elif tenseconds % 60 == 0:
                print('X', end='')
            elif tenseconds % 6 == 0:
                print('.', end='')

        print("We are good to go...")

        print("Wait 10 seconds extra to assure the file is also fully " +
              "written, that will be enough, no?")
        time.sleep(10)
        logslc.info('This lasted about ' + str(tenseconds // 6) + ' minutes')

    finally:
        os.remove(tclfilename)


def movelibs(libs2copylist, timestamp, projectdesignfolder=None,
             move=False, dryrun=True, backup=True, copy=True, test=True,
             autoclick=False, dry_repattern=r'[sS](:\\proj)',
             wet_rerepl=r'T\1', generation_copy=False, destinationFolder='',
             exclude=[]):
    logslc = logging.getLogger('seditlibcopy')

    logslc.info('\tThe time is now: ' +
                datetime.datetime.now().strftime("%Y%m%d_%H%M"))
    logslc.info('MOVELIBS parameters:')
    logslc.info('\tlibs2copylist = ' + repr(libs2copylist))
    logslc.info('\ttimestamp = ' + repr(timestamp))
    logslc.info('\tprojectdesignfolder = ' + repr(projectdesignfolder))
    logslc.info('\tmove = ' + repr(move))
    logslc.info('\tdryrun = ' + repr(dryrun))
    logslc.info('\tbackup = ' + repr(backup))
    logslc.info('\tcopy = ' + repr(copy))
    logslc.info('\ttest = ' + repr(test))
    logslc.info('\tautoclick = ' + repr(autoclick))
    logslc.info('\tdry_repattern = ' + repr(dry_repattern))
    logslc.info('\twet_rerepl = ' + repr(wet_rerepl))
    # check the timestamp (only 1 subloop allowed)
    if timestamp.count('_') > 3:
        raise Exception('only 1 subloop allowed, checked by timestamp')
    # find S-Edit design folder structures
    if projectdesignfolder is None:
        pdf = r'S:\projects'
        # to be on the safe side during debugging
        dryrun = True
    elif projectdesignfolder == 'all':
        pdf = r'S:\projects'
    else:
        pdf = str(projectdesignfolder)

    if backup or dryrun:
        wetpdf = re.sub(dry_repattern, wet_rerepl, pdf, 0, re.I)

        logslc.info('\tThe time is now: ' +
                    datetime.datetime.now().strftime("%Y%m%d_%H%M"))
        logslc.info('\n\nBACKUP FIRST, ' + pdf + ' --> ' + wetpdf)
        allschematics = sedit.findschematicsin(pdf, exclude)
        allschematicsplus = list(allschematics)
        for l2c in libs2copylist:
            allschematicsplus.append(l2c.src)
        print(len(allschematicsplus))
        count = 0
        for sch in allschematicsplus:
            count += 1
            if count % 100 == 0:
                print('C')
            elif count % 50 == 0:
                print('L', end='')
            elif count % 10 == 0:
                print('X', end='')
            elif count % 5 == 0:
                print('V', end='')
            else:
                print('I', end='')
            wetpath = re.sub(dry_repattern, wet_rerepl, str(sch.path), 0, re.I)
            logslc.info(wetpath)
            if os.path.exists(wetpath):
                logslc.warning('The following was omitted and probably ' +
                               'already executed before because of a funky ' +
                               'design hierarchy:\n    ' + str(sch.path) +
                               ' -> ' + wetpath)
            else:
                shutil.copytree(str(sch.path), wetpath)
            logslc.info(str(sch.path) + ' -> ' + wetpath)

    if backup and dryrun:
        logslc.info('\tThe time is now: ' +
                    datetime.datetime.now().strftime("%Y%m%d_%H%M"))
        logslc.info('\n\nBACKUP BEFORE DRYRUNNING AS WELL, ' +
                    wetpdf + ' --> ' + wetpdf + '_backup')
        shutil.copytree(wetpdf, wetpdf + '_backup')

    if dryrun:
        logslc.info('\tThe time is now: ' +
                    datetime.datetime.now().strftime("%Y%m%d_%H%M"))
        logslc.info('DRYRUN PREPARATION\n')
        print('\n\nDRYRUN PREPARATION')

        # if dryrun, the copylist has to be changed as well from dry to wet
        # (s:\proj to t:\proj)
        pdf = re.sub(dry_repattern, wet_rerepl, pdf, 0, re.I)
        wetl2c = list(range(len(libs2copylist)))
        for i in range(len(libs2copylist)):
            wetl2c[i] = Lib2copy(re.sub(dry_repattern, wet_rerepl,
                                        str(libs2copylist[i].src.path)),
                                 re.sub(dry_repattern, wet_rerepl,
                                        str(libs2copylist[i].dst.path)))
        libs2copylist = wetl2c

        print('wetl2c: ' + str(wetl2c))

        logslc.info('DRYRUN RELINK ALL libraries.list PATHS\n')

        allschematics = sedit.findschematicsin(pdf, exclude)
        allschematicsplus = list(allschematics)
        for l2c in libs2copylist:
            allschematicsplus.append(l2c.src)
        for sch in allschematicsplus:
            logtxt = sch.replace_liblink_beginofpath(dry_repattern, wet_rerepl)
            logslc.info('lib list (' + str(sch.path) + '):')
            logslc.info(logtxt)

        logslc.info('\tThe time is now: ' +
                    datetime.datetime.now().strftime("%Y%m%d_%H%M"))
        logslc.info('\n\nDRYRUN PREPARATION FINISHED\n')
        print('\n\nDRYRUN PREPARATION FINISHED')

    if not dryrun and not backup:
        allschematics = sedit.findschematicsin(pdf, exclude)

    logslc.info('pdf: ' + pdf + ' (plus full deeper hierarchy!!)')
    logslc.info('l2c: ')
    for i in range(len(libs2copylist)):
        logslc.info('     ' + repr(libs2copylist[i]))

    # find all problems in allschematics:
    # broken links (Ow ow, that is gonna be a lot....)
    # For each of the design-folders in the source-path, this code will check
    # that all libraries linked to in the libraries.list are existing.
    logslc.info('\tThe time is now: ' +
                datetime.datetime.now().strftime("%Y%m%d_%H%M"))
    logslc.info('===========================================')
    logslc.info('Find broken links in: ' + pdf)
    logslc.info('-------------------------------------------')
    for sch in allschematics:
        lllines = sch.get_liblinks()
        for ll in lllines:
            lib = sch.path / ll[:-1]
            testlib = sedit.Design(lib)
            if not testlib.exists():
                print('broken library link: ' + str(sch.path) + ' / ' +
                      ll[:-1])
                logslc.info('broken library link: ' + str(sch.path) + ' / ' +
                            ll[:-1])

    logslc.info('===========================================\n\n\n')

    # Library nesting with different location for equal library name
    logslc.info('\tThe time is now: ' +
                datetime.datetime.now().strftime("%Y%m%d_%H%M"))
    logslc.info('===========================================')
    logslc.info('Inconsistent library nesting in: ' + pdf)
    if len(exclude) > 0:
        logslc.info('(excl: ' + '\n       '.join(exclude) + ')')
    logslc.info('-------------------------------------------')
    ignoreatcompare = []
    textsum = 'Summary of designs with multiple links for same library:\n'
    for sch in allschematics:
        text = sch.check_liblinkdict()
        if len(text) > 0:
            logslc.info(text)
            ignoreatcompare.append(str(sch.path))
            textsum += str(sch.path) + '\n'

    logslc.info('\n\n-------------------------------------------\n')
    logslc.info(textsum + '\n')
    logslc.info('\n\n-------------------------------------------\n')
    logslc.info('ignoreatcompare = ' + repr(ignoreatcompare) + '\n')
    logslc.info('===========================================\n\n\n')

    logslc.info('\tThe time is now: ' +
                datetime.datetime.now().strftime("%Y%m%d_%H%M"))
    logslc.info('===========================================')
    logslc.info('Library renaming (also nested and if consistent) in: ' + pdf)
    if len(exclude) > 0:
        logslc.info('(excl: ' + '\n       '.join(exclude) + ')')
    logslc.info('-------------------------------------------')
    # sch_copylibs_replacebeforecomparison is a list that holds all new
    # librarynames that are listed to hold a new name AND this new name does
    # not yet exists on one of the libraries.list of ANY of the schematics in
    # the current project folder. If not the new library-name we want to create
    # could collapese with the existing library!
    sch_copylibs_replacebeforecomparison = []
    for sch in allschematics:
        liblinkdict = sch.get_liblinkdict()
        for l2c in libs2copylist:
            if not l2c.equalnames:
                if uniquename_and_thislib_in_liblinkdict(
                        liblinkdict, sedit.resolve2dots(str(l2c.src.path))):
                    sch_copylibs_replacebeforecomparison.append([sch, l2c])

    logslc.info('\n\n-------------------------------------------\n')
    logslc.info('sch_copylibs_replacebeforecomparison = ' +
                repr(sch_copylibs_replacebeforecomparison) + '\n')
    logslc.info('===========================================\n\n\n')
    logslc.info('\tThe time is now: ' +
                datetime.datetime.now().strftime("%Y%m%d_%H%M"))

    if test:
        logslc.info('TEST EXPORT SPICE BEFORE: ')
        logslc.info('from seditlibcopy import *')
        logslc.info('if True:')
        logslc.info('    pdf = ' + repr(pdf))
        logslc.info('    exclude = ' + repr(exclude))
        logslc.info('    allschematics = sedit.findschematicsin(' +
                    repr(pdf) + ', ' + repr(exclude) + ')')
        logslc.info('    timestamp = ' + repr(timestamp))
        logslc.info('    autoclick = ' + repr(autoclick))
        logslc.info("    exportspice(timestamp, allschematics, 'before')\n\n")
        exportspice(timestamp, allschematics, 'before', autoclick)
    logslc.info('\tThe time is now: ' +
                datetime.datetime.now().strftime("%Y%m%d_%H%M"))

    if copy:
        # copy libraries to copy
        copylibs(libs2copylist, timestamp, move)

        # make sure there is not an already existing library that has the name
        # of a dst library name
        problemsolved = False
        subfolder = 0
        sch_lib2copy_allproblems = []
        while not problemsolved:
            problemsolved = True
            for l2c in libs2copylist:
                if not l2c.equalnames:
                    dstname = l2c.dst.name
                    logslc.info(dstname)
                    for sch in allschematics:
                        lllines = sch.get_liblinks()
                        for ll in lllines:
                            if (pathlib.Path(ll[:-1]).name.lower() ==
                                    dstname.lower()):
                                # and if so: rename to _local
                                oldlib = sch.path / ll[:-1]
                                testoldlib = sedit.Design(oldlib)
                                if not testoldlib.exists():
                                    # check first if oldlib exists, otherwise
                                    # we are trying to clean up things that are
                                    # already broken.
                                    warning = ('broken library link: ' +
                                               str(oldlib))
                                    print(warning)
                                    logslc.warning(warning)
                                    break

                                problemsolved = False
                                print("====================================" +
                                      "=================")
                                print("Existing lib with name: '" + dstname +
                                      "' in schematic: '" + str(sch.path) +
                                      "'")
                                logslc.info("Existing lib with name: '" +
                                            dstname + "' in schematic: '" +
                                            str(sch.path) + "'")
                                print(ll)
                                print(''.join(lllines))

                                newlib = str(oldlib) + '_local'
                                subfolder += 1
                                subbackup = False
                                submove = False
                                subdryrun = False
                                subtest = False
                                movelibs([Lib2copy(oldlib, newlib)],
                                         timestamp + '_' + str(subfolder),
                                         sch.path, submove, subdryrun,
                                         subbackup, copy, subtest)
                                sch_lib2copy_allproblems.append(
                                        [str(sch.path), Lib2copy(oldlib,
                                                                 newlib)])

        logslc.info('\tThe time is now: ' +
                    datetime.datetime.now().strftime("%Y%m%d_%H%M"))

        sch_lib2copy_init = []
        for l2c in libs2copylist:
            sch_lib2copy_init.append([str(pdf), l2c])

        sch_copylibs_2remove = sch_lib2copy_init + sch_lib2copy_allproblems

        # sch_copylibs_replacebeforecomparison += sch_lib2copy_allproblems
        # this is potentially incomplete do it with the following for loop
        count = 0

        # create set of unique changes (sch_copylibs_replacebeforecomparison)
        l2c_stringlist = []
        l2c_uniquelist = []
        for sch_ap, l2c in sch_lib2copy_allproblems:
            l2c_r2dsrc = sedit.resolve2dots(str(l2c.src.path))
            l2c_r2ddst = sedit.resolve2dots(str(l2c.dst.path))
            l2c_string = ('Lib2copy(' + repr(l2c_r2dsrc) + ', ' +
                          repr(l2c_r2ddst) + ')')
            if l2c_string not in l2c_stringlist:
                l2c_stringlist.append(l2c_string)
                l2c_uniquelist.append(Lib2copy(l2c_r2dsrc, l2c_r2ddst))
        logslc.info('l2c_uniquelist:' + repr(l2c_uniquelist))

        logslc.info('\tThe time is now: ' +
                    datetime.datetime.now().strftime("%Y%m%d_%H%M"))
        for sch in allschematics:
            liblinkdict = sch.get_liblinkdict()
            for l2c in l2c_uniquelist:
                if not l2c.equalnames:
                    if uniquename_and_thislib_in_liblinkdict(
                            liblinkdict, sedit.resolve2dots(
                                    str(l2c.dst.path))):
                        count += 1
                        sch_copylibs_replacebeforecomparison.insert(0,
                                                                    [sch, l2c])
                        logslc.info(str(count) + ") Also to replace before " +
                                    "comparison: '" + str(l2c.src) + ' --> ' +
                                    str(l2c.dst) + "' in schematic: '" +
                                    str(sch.path) + "'")
        logslc.info('sch_copylibs_replacebeforecomparison = ' +
                    repr(sch_copylibs_replacebeforecomparison))

        logslc.info('\tThe time is now: ' +
                    datetime.datetime.now().strftime("%Y%m%d_%H%M"))

        if move:
            # we do not have to remove doubles
            for sch, l2c in sch_copylibs_2remove:
                l2c.delsource()
            logslc.info('Source files/folders have been deleted.')
        if generation_copy:
            if destinationFolder == '':
                raise Exception('A destination library is required when ' +
                                'requesting a generationCopy')
            allschematics = sedit.findschematicsin(destinationFolder)
        else:
            # redo this because the folder structure changed after copying
            # and maybe deleting
            allschematics = sedit.findschematicsin(pdf, exclude)

        # replace all pseudo-relative links by their absolute counterpart
        # pseudo-relative links link to the internal projects library iso local
        # project's folder

        logslc.info('\tThe time is now: ' +
                    datetime.datetime.now().strftime("%Y%m%d_%H%M"))
        print("FIXING PSEUDO RELATIVE LINKS")
        logslc.info("FIXING PSEUDO RELATIVE LINKS")

        for sch in allschematics:
            lllines = sch.get_liblinks()
            for ll in lllines:
                # print("------------------")
                # print("ll: " + ll)
                if '..' in ll:
                    abslink = str(sch.path / ll[:-1])
                    abslink = sedit.resolve2dots(abslink)
                    # print('abslink: ' + abslink)
                    for l2c in libs2copylist:
                        if not l2c.equalparents:
                            # print('str(abslink).lower(): ' +
                            #       str(abslink).lower())
                            # print('str(l2c.src.path).lower(): ' +
                            #       str(l2c.src.path).lower())
                            if (str(abslink).lower() ==
                                    str(l2c.src.path).lower()):
                                logslc.info("pseudo relative fix of " +
                                            "sch.path: " + str(sch.path) +
                                            ': ' + ll[:-1] + ' --> ' +
                                            abslink)
                                sch.replace_liblink(ll, abslink)
                        else:
                            logslc.info('should NEVER be printed in the ' +
                                        'initial run, but will show up in ' +
                                        'subloops (timestamp_x)')
                            logslc.info('l2c: ' + str(l2c))

                    # else:
                    #    print(str(sch.path) + ': ' + ll[:-1])
                    #    what is left relative is only local

        # replace all links in all libraries.list and if necessary names in
        # design.edif

        # sch_copylibs = sch_lib2copy_allproblems

        logslc.info('\tThe time is now: ' +
                    datetime.datetime.now().strftime("%Y%m%d_%H%M"))
        print("Replacing links in libraries.list and design.edif")
        logslc.info("REPLACING LINKS IN LIBRARIES.LIST AND DESIGN EDIF")
        for sch in allschematics:
            for l2c in libs2copylist:
                lllines = sch.get_liblinks()
                for ll in lllines:
                    if (str(pathlib.Path(ll[:-1])).lower() ==
                            str(l2c.src.path).lower()):
                        logslc.info("replace links in ll of sch.path: " +
                                    str(sch.path) + ' for: ' +
                                    str(l2c.src.path.name) + ' --> ' +
                                    str(l2c.dst.path.name))
                        sch.replace_liblink(l2c.src.path, l2c.dst.path)
                        if not l2c.equalnames:
                            logslc.info("replace links in de of sch.path: " +
                                        str(sch.path) + ' for: ' +
                                        str(l2c.src.path.name) + ' --> ' +
                                        str(l2c.dst.path.name))
                            sch.replace_librarydesignname(l2c.src.name,
                                                          l2c.dst.name)
                            # sch_copylibs.append([str(sch.path), l2c])

                            # best effort add to in case of inconsistent libs
                            # sch_copylibs_replacebeforecomparison
                            found = False
                            _scrbc = sch_copylibs_replacebeforecomparison
                            for sch_cl_rb, l2c_cl_rb in _scrbc:
                                if str(sch_cl_rb.path) == str(sch.path):
                                    if (sedit.resolve2dots(str(l2c_cl_rb.src.path)) == sedit.resolve2dots(str(l2c.src.path))):
                                        if sedit.resolve2dots(str(l2c_cl_rb.dst.path)) == sedit.resolve2dots(str(l2c.dst.path)):
                                            found = True
                            if not found:
                                # sch should be in ignoreatcompare
                                if str(sch.path) not in ignoreatcompare:
                                    printtext = ('This should be a replaced ' +
                                                 'lib itself, since this sch' +
                                                 'is not in the sch_copylibs' +
                                                 '_replacebeforecomparison ' +
                                                 'with this l2c and not ' +
                                                 'found in ignoreatcompare? ' +
                                                 'sch: ' + str(sch.path) +
                                                 ' l2c: ' + str(l2c))
                                    print(printtext)
                                    logslc.info(printtext)
                                sch_copylibs_replacebeforecomparison.append(
                                        [sch, l2c])

                    elif (str(sch.path / pathlib.Path(ll[:-1])).lower() ==
                          str(l2c.src.path).lower()):
                        # in case of relative link in lib list (subloops)
                        relsrclink = str(l2c.src.path)[len(str(sch.path))+1:]
                        reldstlink = str(l2c.dst.path)[len(str(sch.path))+1:]
                        sch.replace_liblink(relsrclink, reldstlink)
                        if not l2c.equalnames:
                            sch.replace_librarydesignname(l2c.src.name,
                                                          l2c.dst.name)
                            # sch_copylibs.append([str(sch.path), l2c])
                if str(sch.path).lower() == str(l2c.dst.path).lower():
                    # also rename logic_generic_ into logic_ for the export
                    # of the library itself.
                    sch_copylibs_replacebeforecomparison.append([sch, l2c])
                    printtext = ('A replaced lib itself, added to the ' +
                                 'sch_copylibs_replacebeforecomparison with ' +
                                 'this same l2c. sch: ' + str(sch.path) +
                                 ' l2c: ' + str(l2c))
                    logslc.info(printtext)

        # sch_copylibs is not really complete for modifynetlist because some
        # renamings are inherited from deeper hierarchy, not part of
        # libraries.list itself
        # sch_copylibs_replacebeforecomparison solves this

    logslc.info('\tThe time is now: ' +
                datetime.datetime.now().strftime("%Y%m%d_%H%M"))

    if test:
        logslc.info('TEST EXPORT SPICE AFTER: ')
        logslc.info('from seditlibcopy import *')
        logslc.info('if True:')
        logslc.info('    pdf = ' + repr(pdf))
        logslc.info('    exclude = ' + repr(exclude))
        logslc.info('    allschematics = sedit.findschematicsin(' +
                    repr(pdf) + ', ' + repr(exclude) + ')')
        logslc.info('    timestamp = ' + repr(timestamp))
        logslc.info('    autoclick = ' + repr(autoclick))
        logslc.info("    exportspice(timestamp, allschematics, 'after', " +
                    "autoclick)\n\n")
        exportspice(timestamp, allschematics, 'after', autoclick)

    logslc.info('\tThe time is now: ' +
                datetime.datetime.now().strftime("%Y%m%d_%H%M"))
    if test:
        #    # # compare outputs
        #    list all netlists in exportbefore
        #    for each file:
        #        delete 2nd line (date/time)
        #        replace l2c.src.name + '_' into l2c.dst.name + '_'
        #        and store them where they are expected AFTER the move
        #            (if it is one of the moved libs itself)
        #        make new folder structure (_cmp)
        logslc.info('MODIFY NETLIST BEFORE: ')
        logslc.info('from seditlibcopy import *')
        logslc.info('if True:')
        logslc.info('    sch_copylibs_replacebeforecomparison = ' +
                    repr(sch_copylibs_replacebeforecomparison))
        logslc.info('    timestamp = ' + repr(timestamp))
        logslc.info("    modifynetlist(sch_copylibs_replacebeforecomparison," +
                    "timestamp, 'before')\n\n")
        # print(sch_copylibs_replacebeforecomparison)
        modifynetlist(sch_copylibs_replacebeforecomparison, timestamp,
                      'before')
        logslc.info('\tThe time is now: ' +
                    datetime.datetime.now().strftime("%Y%m%d_%H%M"))

        #    list all netlists in exportafter
        #    for each file:
        #        delete 2nd and 3rd line (date/time)
        #        make new folder structure (_cmp)

        logslc.info('MODIFY NETLIST AFTER: ')
        logslc.info('from seditlibcopy import *')
        logslc.info('if True:')
        logslc.info('    sch_copylibs_replacebeforecomparison = ' +
                    repr(sch_copylibs_replacebeforecomparison))
        logslc.info('    timestamp = ' + repr(timestamp))
        logslc.info("    modifynetlist(sch_copylibs_replacebeforecomparison," +
                    " timestamp, 'after')\n\n")
        modifynetlist(sch_copylibs_replacebeforecomparison, timestamp, 'after')
        logslc.info('\tThe time is now: ' +
                    datetime.datetime.now().strftime("%Y%m%d_%H%M"))

        #    compare files (winmerge /r )
        #        "c:\Program Files (x86)\WinMerge\WinMergeU.exe" /r
        #        T:\libcopylog_20170503_1455\exportbefore\T\projects\
        #            p_PHAEDRA\design\schematic\
        #        T:\libcopylog_20170503_1455\exportafter\T\projects\
        #            p_PHAEDRA\design\schematic\ c:\Users\Koen\Desktop\test.txt
        # subprocess.Popen(r'"c:\Program Files (x86)\WinMerge\WinMergeU.exe"' +
        #                  r' /r T:\libcopylog' + timestamp +
        #                  r'\exportbefore\T\projects\p_PHAEDRA\design\' +
        #                  r'schematic T:\libcopylog' + timestamp +
        #                  r'\exportafter\T\projects\p_PHAEDRA\design\' +
        #                  r'schematic')
        # subprocess.Popen(r'"c:\Program Files (x86)\WinMerge\WinMergeU.exe"' +
        #                  r' /r T:\libcopylog' + timestamp +' +
        #                  r'\exportbefore_cmp\T T:\libcopylog' + timestamp +
        #                  r'\exportafter_cmp\T')

        # we'll compare ourselves... Wat je zelf doet, doe je beter
        logslc.info('COMPARE NETLISTS: ')
        logslc.info('from seditlibcopy import *')
        logslc.info('if True:')
        logslc.info('    timestamp = ' + repr(timestamp))
        logslc.info('    ignoreatcompare = ' + repr(ignoreatcompare))
        logslc.info("    comparenetlistfolders(timestamp)\n\n")
        comparenetlistfolders(timestamp, ignoreatcompare, generation_copy)

        logslc.info('\tThe time is now: ' +
                    datetime.datetime.now().strftime("%Y%m%d_%H%M"))


def move2scib(dryrun=True, backup=True, autoclick=False):
    L2C = []

    srcfldr = r'S:\projects\internal projects\v2.0\schematic'
    dstfldr = r'S:\projects\scib\standard\schematic'
    L2C.append(Lib2copy(srcfldr + r'\Attributes',
                        dstfldr + r'\attributes'))
    L2C.append(Lib2copy(srcfldr + r'\generic\devices_generic',
                        dstfldr + r'\devices'))
    L2C.append(Lib2copy(srcfldr + r'\generic\IO_generic',
                        dstfldr + r'\io'))
    L2C.append(Lib2copy(srcfldr + r'\generic\logic_generic',
                        dstfldr + r'\logic'))
    L2C.append(Lib2copy(srcfldr + r'\generic\monitors_generic',
                        dstfldr + r'\monitors'))
    L2C.append(Lib2copy(srcfldr + r'\generic\SB',
                        dstfldr + r'\SB'))
    L2C.append(Lib2copy(srcfldr + r'\spice',
                        dstfldr + r'\spice'))
    L2C.append(Lib2copy(srcfldr + r'\generic\stdcell_generic',
                        dstfldr + r'\stdcells'))

    timestamp = datetime.datetime.now().strftime("_%Y%m%d_%H%M")

    # dryrun = True means the real changes happen on T:\proj*
    # dryrun = True
    # move = True means the source will be deleted
    move = True
    # backup = True means that the initial full copy will be done
    # backup = True
    # copy = True means it will do the copy and replacement of libraries
    # list/design.edif
    copy = True
    # test = True means that there is S-Edit export before and after copy and
    # verification
    test = True
    # autoclick = True means every 10 seconds a AutoHotkey tool will check
    # whether S-Edit is waiting for some specific input (not recommended if
    # you are working at the same time)
    # autoclick = True
    # dry_repattern = r'S:\\projects'
    # wet_rerepl = r'T:\\projects'

    # skip = True
    # if skip:
    #    timestamp = '_20170518_2355'

    movelibs(L2C, timestamp, 'all', move, dryrun, backup, copy, test,
             autoclick)


def updatedesign():
    # relink in all libraries.list files
    # (only the ones with an absolute link!)

    # rename in all design.edif files
    # (only those that had an absolute link)
    pass


def intexternallibs(schematicsfolder, exclude=[]):
    logslc = logging.getLogger('seditlibcopy')
    allschematics = sedit.findschematicsin(schematicsfolder, exclude)
    print(len(allschematics))
    count = 0
    dependencies = set()
    for sch in allschematics:
        lllines = sch.get_liblinks()
        for ll in lllines:
            lib = sch.path / ll[:-1]
            testlib = sedit.Design(lib)
            if not testlib.exists():
                print('broken library link: ' + str(sch.path) + ' / ' +
                      ll[:-1])
                logslc.warning('broken library link: ' + str(sch.path) +
                               ' / ' + ll[:-1])
        count += 1
        # print(str(count) + ' sch: ' + str(sch))
        dep = sch.get_dependencies()
        # print('dep: ' + str(dep))

        for justadep in dep:
            if pathlib.Path(justadep) in map(pathlib.Path, exclude):
                print('reincluded ' + str(justadep) +
                      ' because of library listed in ' + sch.name)

        dependencies = dependencies.union(dep)

    print('all libs in project: ')
    for l in dependencies:
        print(l)
    print('\n\n')
    extdepnames = set()
    alldepnames = set()
    externaldependencies = set()
    internallibs = set()
    sfpath = pathlib.Path(schematicsfolder)
    for dep in dependencies:
        name = sedit.Design(dep).name
        external = True
        dpath = pathlib.Path(dep)
        while dpath != dpath.parent:
            if dpath == sfpath:
                external = False
                break  # while
            dpath = dpath.parent
        if external:
            externaldependencies.add(dep)
            extdepnames.add(name)
            alldepnames.add(name)
        else:
            internallibs.add(dep)
            alldepnames.add(name)

    if len(extdepnames) != len(externaldependencies):
        warning = ('Warning: Multiple external libraries with same name in ' +
                   'design: ' + str(externaldependencies))
        print(warning)
        raise Exception(warning)

    if len(alldepnames) != len(externaldependencies) + len(internallibs):
        warning = ('Warning: Multiple libraries with same name in design: ' +
                   str(externaldependencies) + str(internallibs))
        print(warning)
        raise Exception(warning)

    extlibslist = list(externaldependencies)
    extlibslist.sort()
    intlibslist = list(internallibs)
    intlibslist.sort()
    return intlibslist, extlibslist


def casedpath(path):
    r = glob.glob(re.sub(r'([^:/\\])(?=[/\\]|$)', r'[\1]', path))
    return r and r[0] or path


def consolidate(project=None, schematicsfolder=None,
                consolidatefoldername=None, dryrun=True, backup=True,
                autoclick=False, test=True, exclude_arg=None):

    timestamp = datetime.datetime.now().strftime("_%Y%m%d_%H%M")
    timetext = 'The time is now: ' + timestamp + '\n\n'

    logslc = logging.getLogger('seditlibcopy')
    # First create file for logging, otherwise it crashes while making the
    # logging.fileHandler
    logfilename = r'T:\libcopylog' + timestamp + r'\consolidate.log'
    general.write(logfilename, '', False)
    hndl = logging.FileHandler(logfilename)
    hndl.setFormatter(logging.Formatter('%(asctime)s: %(message)s'))
    logslc.addHandler(hndl)

    defaultschematicsfolder = r'S:\projects'
    if project is not None:
        PROJset = settings.PROJECTsettings()
        PROJset.loaddefault(project)
        PROJset.load()
        projectcheck = PROJset.get_str('projectname')
        if projectcheck != project:
            warning = ('\nWARNING!! \nSelected project (' + project +
                       ') does not match the projectname defined in ' +
                       LTBsettings.projectsettings() + ' (' + projectcheck +
                       ').')
            # print(warning)
            # general.error_log(warning)
            raise Exception(warning)
        else:
            if PROJset.get_type('schematicsfolder') is not None:
                defaultschematicsfolder = PROJset.get_str('schematicsfolder')

    if schematicsfolder is None:
        schematicsfolder = defaultschematicsfolder
        if project is None:
            raise Exception('We do not want to consolidate the whole ' +
                            'S:\\projects, do we?')

    if exclude_arg is None:
        exclude = []
    else:
        exclude = exclude_arg

    if consolidatefoldername is None:
        dstfolder = schematicsfolder + r'\consolidate_' + timestamp
    else:
        dstfolder = consolidatefoldername

    intlibs, l2csrc = intexternallibs(schematicsfolder, exclude)
    # l2csrc = sedit.findschematicsin(srcfolder)
    # print('l2csrc: ' + str(l2csrc))

    # srcfolder_repattern = srcfolder.replace('\\', '\\\\')
    # dstfolder_repattern = dstfolder.replace('\\', '\\\\')
    L2C = []
    for x in l2csrc:
        x = pathlib.Path(casedpath(str(x)))
        xl2cdst = dstfolder + '\\' + pathlib.Path(x).name
        L2C.append(Lib2copy(x, xl2cdst))

    a = 0
    text = ''
    while a != '':
        print('---------------------------------------')
        print('Internal libs:')
        for x in intlibs:
            print(x)
        print('')
        count = 0
        print('External libs to be consolidated:')
        text = timetext
        for x in L2C:
            count += 1
            text += str(x.src.path) + ' --> ' + str(x.dst.path) + '\n'
            print(str(count) + ')  ' + str(x.src.path) + ' --> ' +
                  str(x.dst.path))
        inputstr = ("You want to change libname of some libraries " +
                    "(No, it's ok [Enter] / Edit [#] / Stop [0]) ?  ")
        a = input(inputstr)
        if a == '0':
            return  # exit()
        if a != '' and a.isdecimal() and 0 < int(a) <= count:
            print(str(L2C[int(a)-1].src.path) + ' --> ' +
                  str(L2C[int(a)-1].dst.path))
            print('\nEdit:')
            newname = input(str(L2C[int(a)-1].src.path) + ' --> ' +
                            str(L2C[int(a)-1].dst.path.parent) + '\\')
            L2C[int(a)-1] = (Lib2copy(L2C[int(a)-1].src.path,
                             str(L2C[int(a)-1].dst.path.parent) + '\\' +
                             newname))

    if dryrun:
        general.write('T' + dstfolder[1:] + r'\OnTheOriginOfSpecies.log', text,
                      True)
    else:
        general.write(dstfolder + r'\OnTheOriginOfSpecies.log', text, True)

    # dryrun = False
    # move = True means the source will be deleted
    move = False
    # backup = True means that the initial full copy will be done
    # backup = True
    # copy = True means it will do the copy and replacement of libraries
    # list/design.edif
    copy = True
    # test = True means that there is S-Edit export before and after copy and
    # verification
    # test = True

    movelibs(L2C, timestamp, schematicsfolder, move, dryrun, backup, copy,
             test, autoclick, exclude)


def unconsolidate(project=None, schematicsfolder=None,
                  dryrun=True, backup=True,
                  autoclick=False, test=True):
    pass


def generationCopy(schematicsfolder=None, destinationfoldername=None,
                   test=False, autoclick=False, exclude_arg=None):
    """Created by Arne at 23/05/2018 - Create a copy towards a new folder
    e.g. to start a new project based on a copy of an old project
    (e.g. for the scib, to go from a generation x to generation x+1-design)"""
    # The logger of this module is called 'seditlibcheck'
    # The Filehandler's filename will be dependent on the initial function
    logslc = logging.getLogger('seditlibcopy')
    hndl = logging.FileHandler(r'T:\seditlibcopy_generationcopy.log')
    hndl.setFormatter(logging.Formatter('%(asctime)s: %(message)s'))
    logslc.addHandler(hndl)

    if schematicsfolder is None:
        raise Exception('You do need to specify a source folder from where ' +
                        'you want to start the copy to build up a new ' +
                        'generation project!')

    timestamp = datetime.datetime.now().strftime("_%Y%m%d_%H%M")
    timetext = 'The time is now: ' + timestamp + '\n\n'

    if destinationfoldername is None:
        raise Exception('If you want to copy a certain project towards a new' +
                        'folder; you need to give the destinamtion folder!')

    if exclude_arg is None:
        exclude = []
    else:
        exclude = exclude_arg

    intlibs, extlibs = intexternallibs(schematicsfolder, exclude)
    # l2csrc = sedit.findschematicsin(srcfolder)
    # print('l2csrc: ' + str(l2csrc))

    # srcfolder_repattern = srcfolder.replace('\\', '\\\\')
    # dstfolder_repattern = dstfolder.replace('\\', '\\\\')
    L2C = []

    basefolder = str(pathlib.Path(casedpath(str(schematicsfolder).lower())))
    # print('basefolder: ' + basefolder)

    for x in intlibs:
        x = pathlib.Path(casedpath(str(x)))

        subfolder = ''
        if str(x).find(basefolder) == 0:
            lastslash = str(x).rfind('\\')
            subfolder = str(x)[len(basefolder):lastslash]
            # print('subfolder: ' + subfolder)

        xl2cdst = destinationfoldername + subfolder + '\\' + pathlib.Path(x).name
        L2C.append(Lib2copy(x, xl2cdst))

    a = 0
    while a != '':
        print('---------------------------------------')
        print('External libs:')
        for x in extlibs:
            print(x)
        print('')
        count = 0
        print('Internal libs to be copied:')
        text = timetext
        for x in L2C:
            count += 1
            text += str(x.src.path) + ' --> ' + str(x.dst.path) + '\n'
            print(str(count) + ')  ' + str(x.src.path) + ' --> ' +
                  str(x.dst.path))
        a = input("You want to change libname of some libraries " +
                  "(No, it's ok [Enter] / Edit [#] / Stop [0]) ?  ")
        if a == '0':
            return  # exit()
        if a != '' and a.isdecimal() and 0 < int(a) <= count:
            print(str(L2C[int(a)-1].src.path) + ' --> ' +
                  str(L2C[int(a)-1].dst.path))
            print('\nEdit:')
            newname = input(str(L2C[int(a)-1].src.path) + ' --> ' +
                            str(L2C[int(a)-1].dst.path.parent) + '\\')
            L2C[int(a)-1] = Lib2copy(L2C[int(a)-1].src.path,
                                     (str(L2C[int(a)-1].dst.path.parent) +
                                      '\\' + newname))

        general.write(destinationfoldername + r'\OnTheOriginOfSpecies.log',
                      text, True)

    # copy = True means it will do the copy and replacement of libraries
    # list/design.edif
    copy = True
    move = False
    dryrun = False
    backup = False
    # movelibs(libs2copylist, timestamp, projectdesignfolder=None, move=False,
    #          dryrun=True, backup=True, copy=True, test=True,
    #          autoclick=False, dry_repattern=r'[sS](:\\proj)',
    #          wet_rerepl=r'T\1', generation_copy=False,
    #          destinationFolder=''):
    movelibs(L2C, timestamp, schematicsfolder, move, dryrun, backup, copy,
             test, autoclick, r'', r'', True, destinationfoldername, exclude)


def reportcellsviews(project=None, schematicsfolder=None, outfile=None,
                     exclude_arg=None):
    """Created by Koen at 2022/01/20 - List all existing cell views for all cells
    e.g. to start a new project based on a copy of an old project
    (e.g. for the scib, to go from a generation x to generation x+1-design)"""
    # The logger of this module is called 'seditlibcheck'
    # The Filehandler's filename will be dependent on the initial function
    logslc = logging.getLogger('seditlibcopy')
    if outfile is None:
        hndl = logging.FileHandler(r'T:\reportcellsviews.log')
    else:
        hndl = logging.FileHandler(outfile)
    hndl.setFormatter(logging.Formatter('%(asctime)s: %(message)s'))
    logslc.addHandler(hndl)

    defaultschematicsfolder = r'S:\projects'
    if project is not None:
        PROJset = settings.PROJECTsettings()
        PROJset.loaddefault(project)
        PROJset.load()
        projectcheck = PROJset.get_str('projectname')
        if projectcheck != project:
            warning = ('\nWARNING!! \nSelected project (' + project +
                       ') does not match the projectname defined in ' +
                       LTBsettings.projectsettings() + ' (' + projectcheck +
                       ').')
            # print(warning)
            # general.error_log(warning)
            raise Exception(warning)
        else:
            if PROJset.get_type('schematicsfolder') is not None:
                defaultschematicsfolder = PROJset.get_str('schematicsfolder')

    if schematicsfolder is None:
        schematicsfolder = defaultschematicsfolder
        if project is None:
            raise Exception('We do not want to consolidate the whole ' +
                            'S:\\projects, do we?')

    if schematicsfolder is None:
        raise Exception('You do need to specify a source folder from where ' +
                        'you want to start the copy to build up a new ' +
                        'generation project!')

    timestamp = datetime.datetime.now().strftime("_%Y%m%d_%H%M")
    timetext = 'The time is now: ' + timestamp + '\n\n'

    if exclude_arg is None:
        exclude = []
    else:
        exclude = exclude_arg

    intlibs, extlibs = intexternallibs(schematicsfolder, exclude)
    # l2csrc = sedit.findschematicsin(srcfolder)
    # print('l2csrc: ' + str(l2csrc))

    # srcfolder_repattern = srcfolder.replace('\\', '\\\\')
    # dstfolder_repattern = dstfolder.replace('\\', '\\\\')
    logslc.info('internal libs')
    for lib in intlibs:
        logslc.info(lib)
    logslc.info('external libs')
    for lib in extlibs:
        logslc.info(lib)

    alllibs = []
    alllibs.extend(intlibs)
    alllibs.extend(extlibs)

    logslc.info('all libs')
    for lib in alllibs:
        logslc.info(lib)

    for lib in alllibs:
        file = pathlib.Path(casedpath(lib)) / 'design.edif'
        logslc.info(str(file))
        with open(file, 'r') as fp:
            for line in fp:
                if line.startswith('(edif '):
                    logslc.info(line[:-1])
                elif line.startswith('\t(external '):
                    logslc.info(line[:-1])
                elif line.startswith('\t(library '):
                    logslc.info(line[:-1])
                elif line.startswith('\t\t(cell '):
                    logslc.info(line[:-1])
                elif line.startswith('\t\t\t(cellType '):
                    logslc.info(line[:-1])
                elif line.startswith('\t\t\t(view '):
                    logslc.info(line[:-1])
                elif line.startswith('\t\t\t\t(viewType '):
                    logslc.info(line[:-1])

    return

    L2C = []

    basefolder = str(pathlib.Path(casedpath(str(schematicsfolder).lower())))
    # print('basefolder: ' + basefolder)

    for x in intlibs:
        x = pathlib.Path(casedpath(str(x)))

        subfolder = ''
        if str(x).find(basefolder) == 0:
            lastslash = str(x).rfind('\\')
            subfolder = str(x)[len(basefolder):lastslash]
            # print('subfolder: ' + subfolder)

        xl2cdst = destinationfoldername + subfolder + '\\' + pathlib.Path(x).name
        L2C.append(Lib2copy(x, xl2cdst))

    a = 0
    while a != '':
        print('---------------------------------------')
        print('External libs:')
        for x in extlibs:
            print(x)
        print('')
        count = 0
        print('Internal libs to be copied:')
        text = timetext
        for x in L2C:
            count += 1
            text += str(x.src.path) + ' --> ' + str(x.dst.path) + '\n'
            print(str(count) + ')  ' + str(x.src.path) + ' --> ' +
                  str(x.dst.path))
        a = input("You want to change libname of some libraries " +
                  "(No, it's ok [Enter] / Edit [#] / Stop [0]) ?  ")
        if a == '0':
            return  # exit()
        if a != '' and a.isdecimal() and 0 < int(a) <= count:
            print(str(L2C[int(a)-1].src.path) + ' --> ' +
                  str(L2C[int(a)-1].dst.path))
            print('\nEdit:')
            newname = input(str(L2C[int(a)-1].src.path) + ' --> ' +
                            str(L2C[int(a)-1].dst.path.parent) + '\\')
            L2C[int(a)-1] = Lib2copy(L2C[int(a)-1].src.path,
                                     (str(L2C[int(a)-1].dst.path.parent) +
                                      '\\' + newname))

        general.write(destinationfoldername + r'\OnTheOriginOfSpecies.log',
                      text, True)

    # copy = True means it will do the copy and replacement of libraries
    # list/design.edif
    copy = True
    move = False
    dryrun = False
    backup = False
    # movelibs(libs2copylist, timestamp, projectdesignfolder=None, move=False,
    #          dryrun=True, backup=True, copy=True, test=True,
    #          autoclick=False, dry_repattern=r'[sS](:\\proj)',
    #          wet_rerepl=r'T\1', generation_copy=False,
    #          destinationFolder=''):
    movelibs(L2C, timestamp, schematicsfolder, move, dryrun, backup, copy,
             test, autoclick, r'', r'', True, destinationfoldername, exclude)

def libcheck(project=None, schematicsfolder=None, exclude_arg=None):
    # The logger of this module is called 'seditlibcheck'
    # The Filehandler's filename will be dependent on the initial function
    logslc = logging.getLogger('seditlibcopy')
    if project is not None:
        logfile = LTBsettings.varfilepath(project) + 'seditlibcheck.log'
    else:
        logfile = r'T:\seditlibcheck.log'
    hndl = logging.FileHandler(logfile)
    hndl.setFormatter(logging.Formatter('%(asctime)s: %(message)s'))
    logslc.addHandler(hndl)

    defaultschematicsfolder = r'S:\projects'
    if project is not None:
        PROJset = settings.PROJECTsettings()
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
        else:
            if PROJset.get_type('schematicsfolder') is not None:
                defaultschematicsfolder = PROJset.get_str('schematicsfolder')

    if schematicsfolder is None:
        schematicsfolder = defaultschematicsfolder

    if exclude_arg is None:
        exclude = []
    else:
        exclude = exclude_arg

    allschematics = sedit.findschematicsin(schematicsfolder, exclude)

    count = 0
    # find all problems in allschematics:
    # broken links (Ow ow, that is gonna be a lot....)
    # general.error_log('===========================================',
    #                   r'T:\libcheck.log', False)
    # general.error_log('Find broken links in: ' + schematicsfolder,
    #                   r'T:\libcheck.log', False)
    # general.error_log('-------------------------------------------',
    #                   r'T:\libcheck.log', False)
    logslc.info('Try to find broken links in: %s', schematicsfolder)
    if len(exclude) > 0:
        logslc.info('(excl: ' + '\n       '.join(exclude) + ')')

    for sch in allschematics:
        lllines = sch.get_liblinks()
        for ll in lllines:
            # check if ll[-1] == '\n' (in case of manually edited
            # libraries.list files without last lines including \n)
            # get_lib_links modified as to make sure all list entries end with
            # '\n'
            lib = sch.path / ll[:-1]
            testlib = sedit.Design(lib)
            if not testlib.exists():
                print('broken library link: ' + str(sch.path) + ' / ' +
                      ll[:-1])
                count += 1
                # general.error_log('broken library link: ' + str(sch.path) +
                #                   ' / ' + ll[:-1], r'T:\libcheck.log', False)
                logslc.warning('broken library link: %s', str(sch.path) +
                               ' / ' + ll[:-1])

    # general.error_log('===========================================\n\n\n',
    #                   r'T:\libcheck.log', False)

    # Library nesting with different location for equal library name
    # general.error_log('===========================================',
    #                   r'T:\libcheck.log', False)
    # general.error_log('Inconsistent library nesting in: ' + schematicsfolder,
    #                   r'T:\libcheck.log', False)
    # general.error_log('-------------------------------------------',
    #                   r'T:\libcheck.log', False)
    logslc.info('Try to find inconsistent library nesting in: %s',
                schematicsfolder)
    if len(exclude) > 0:
        logslc.info('(excl: ' + '\n       '.join(exclude) + ')')

    textsum = 'Summary of designs with multiple links for same library:\n'
    for sch in allschematics:
        text = sch.check_liblinkdict()
        if len(text) > 0:
            # general.error_log(text, r'T:\libcheck.log', False)
            logslc.info('%s', text)
            count += 1
            textsum += str(sch.path) + '\n'

    # general.error_log('\n\n-------------------------------------------\n',
    #                   r'T:\libcheck.log', False)
    # general.error_log(textsum + '\n', r'T:\libcheck.log', False)
    # general.error_log('===========================================\n\n\n',
    #                   r'T:\libcheck.log', False)
    logslc.info('%s', textsum)

    if count == 0:
        print('No issues found')
    else:
        print(str(count) + ' issue(s) found, check (end of) ' + logfile +
              ' for more info.')


def argparse_setup(subparsers):
    parser_slc_move = subparsers.add_parser(
            'move2scib', help='move standard libraries to scib (one-time ' +
            'thing in May 2017)')
    parser_slc_move.add_argument(
            '-nobu', '--nobackup', dest='backup', default=True,
            action='store_false', help='makes no backup (anymore)')
    parser_slc_move.add_argument(
            '-nodry', '--nodryrun', dest='dryrun', default=True,
            action='store_false', help='does no dryrun first (anymore)')
    parser_slc_move.add_argument(
            '-ac', '--autoclick', dest='autoclick', default=False,
            action='store_true', help='does not autoclick on known S-Edit ' +
            'warnings to resume action')

    parser_slc_cons = subparsers.add_parser(
            'consolidate', help='consolidate schematics from outside project' +
            ' (scib, but also others)')
    parser_slc_cons.add_argument(
            '-p', '--project', required=False, help='the PROJECT name, if ' +
            'given schematicsfolder found in LTB project settings')
    parser_slc_cons.add_argument(
            '-sf', '--schematicsfolder', default=None,
            help='the schematics folder')
    parser_slc_cons.add_argument(
            '-cf', '--consolidatefoldername', default=None, help='the name ' +
            'of the folder containing the consolidated libraries, full path ' +
            'or subpath of project folder. Default: consolidate_<timestamp>')
    parser_slc_cons.add_argument(
            '-nobu', '--nobackup', dest='backup', default=True,
            action='store_false', help='makes no backup (anymore)')
    parser_slc_cons.add_argument(
            '-nodry', '--nodryrun', dest='dryrun', default=True,
            action='store_false', help='does no dryrun first (anymore)')
    parser_slc_cons.add_argument(
            '-ac', '--autoclick', dest='autoclick', default=False,
            action='store_true', help='does autoclick on known S-Edit ' +
            'warnings to resume action')
    parser_slc_cons.add_argument(
            '-notest', '--notest', dest='test', default=True,
            action='store_false', help='When added, no spice-to-spice ' +
            'testing of the original and newely copied project will occur.')

    parser_slc_chk = subparsers.add_parser(
            'libcheck', help='Check the libraries on consistency')
    parser_slc_chk.add_argument(
            '-p', '--project', required=False, help='the PROJECT name, if ' +
            'given schematicsfolder found in LTB project settings, if not ' +
            'given: full S:\\')
    parser_slc_chk.add_argument(
            '-sf', '--schematicsfolder', default=None, help='the schematics ' +
            'folder')
    parser_slc_chk.add_argument(
            '-x', '--exclude', dest='exclude', default=None, nargs = '+',
            help='excludes the listed paths (and subdirs) from the ' +
            'schematicsfolder')

    # (schematicsfolder = None, destinationfoldername = None, test = False,
    #  autoclick = False)
    parser_slc_cpy = subparsers.add_parser(
            'generationCopy', help='To fully copy one project a new folder ' +
            'to start a new generation of a project (libraries automatically' +
            ' updated)')
    parser_slc_cpy.add_argument(
            '-sf', '--schematicsfolder', dest='schematicsfolder', default=None,
            help='The source project its schematic folder')
    parser_slc_cpy.add_argument(
            '-df', '--destinationfoldername', dest='destinationfoldername',
            default=None, help='The new project its destination folder. ' +
            'Should be a new folder')
    parser_slc_cpy.add_argument(
            '-notest', '--notest', dest='test', default=True,
            action='store_false', help='When added, no spice-to-spice ' +
            'testing of the original and newely copied project will occur.')
    parser_slc_cpy.add_argument(
            '-ac', '--autoclick', dest='autoclick', default=False,
            action='store_true', help='does autoclick on known S-Edit ' +
            'warnings to resume action')
    parser_slc_cpy.add_argument(
            '-x', '--exclude', dest='exclude', default=None, nargs = '+',
            help='excludes the listed paths (and subdirs) from the ' +
            'schematicsfolder')

    parser_slc_unc = subparsers.add_parser(
            'unconsolidate', help='undo consolidation of schematics from ' +
            'outside project (scib, but also others)')
    parser_slc_unc.add_argument(
            '-p', '--project', required=False, help='the PROJECT name, if ' +
            'given schematicsfolder found in LTB project settings')
    parser_slc_unc.add_argument(
            '-sf', '--schematicsfolder', dest='schematicsfolder', default=None,
            help='The source project its schematic folder')
    parser_slc_unc.add_argument(
            '-nobu', '--nobackup', dest='backup', default=True,
            action='store_false', help='makes no backup (anymore)')
    parser_slc_unc.add_argument(
            '-nodry', '--nodryrun', dest='dryrun', default=True,
            action='store_false', help='does no dryrun first (anymore)')
    parser_slc_unc.add_argument(
            '-ac', '--autoclick', dest='autoclick', default=False,
            action='store_true', help='does autoclick on known S-Edit ' +
            'warnings to resume action')
    parser_slc_unc.add_argument(
            '-notest', '--notest', dest='test', default=True,
            action='store_false', help='When added, no spice-to-spice ' +
            'testing of the original and newely copied project will occur.')

    parser_slc_rcv = subparsers.add_parser(
            'reportcellsviews', help='generate report on all cells and views' +
            'in the schematic')
    parser_slc_rcv.add_argument(
            '-p', '--project', required=False, help='the PROJECT name, if ' +
            'given schematicsfolder found in LTB project settings')
    parser_slc_rcv.add_argument(
            '-sf', '--schematicsfolder', dest='schematicsfolder', default=None,
            help='The source project its schematic folder')
    parser_slc_rcv.add_argument(
            '-o', '--outfile', default=None,
            help=('location of the output file, default: T:\\' +
              'reportcellsviews.log'))
    parser_slc_rcv.add_argument(
            '-x', '--exclude', dest='exclude', default=None, nargs = '+',
            help='excludes the listed paths (and subdirs) from the ' +
            'schematicsfolder')


def argparse_eval(args):
    # make a dict of args
    dictargs = vars(args)
    funcdict = {'move2scib': (move2scib,
                              [dictargs.get('dryrun'),
                               dictargs.get('backup'),
                               dictargs.get('autoclick')]),
                'consolidate': (consolidate,
                                [dictargs.get('project'),
                                 dictargs.get('schematicsfolder'),
                                 dictargs.get('consolidatefoldername'),
                                 dictargs.get('dryrun'),
                                 dictargs.get('backup'),
                                 dictargs.get('autoclick'),
                                 dictargs.get('test'),
                                 dictargs.get('exclude')]),
                'libcheck': (libcheck,
                             [dictargs.get('project'),
                              dictargs.get('schematicsfolder'),
                              dictargs.get('exclude')]),
                'generationCopy': (generationCopy,
                                   [dictargs.get('schematicsfolder'),
                                    dictargs.get('destinationfoldername'),
                                    dictargs.get('test'),
                                    dictargs.get('autoclick'),
                                    dictargs.get('exclude')]),
                'unconsolidate': (unconsolidate,
                                  [dictargs.get('project'),
                                   dictargs.get('schematicsfolder'),
                                   dictargs.get('dryrun'),
                                   dictargs.get('backup'),
                                   dictargs.get('autoclick'),
                                   dictargs.get('test')]),
                'reportcellsviews': (reportcellsviews,
                                     [dictargs.get('project'),
                                      dictargs.get('schematicsfolder'),
                                      dictargs.get('outfile'),
                                      dictargs.get('exclude')])
                }
    return funcdict


if __name__ == "__main__":
    general.logsetup()
    general.myargparse(argparse_setup, argparse_eval, 'v20230926')
