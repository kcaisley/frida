import logging      # in case you want to add extra logging
import general
import os
import settings
import LTBsettings
import pathlib  # not LEdit/Py2.6 compatible
import re
import time

USERset = settings.USERsettings()
PROJset = settings.PROJECTsettings()

class Leditdesign():
    def __init__(self, tannerfile):
        """create a link to an L-Edit design using its file path.
        The design does not have to exist."""
        self.tannerfile = pathlib.Path(tannerfile)
        self.path = self.tannerfile.parent
        self.name = self.tannerfile.name.split('.')[0]
        #self.liblist = self.path / 'libraries.list'
        self.liblistsummary = pathlib.Path(r'T:\LayoutToolbox\laygen\alllibs.csv')
        #self.design = self.path / 'design.edif'
        #self.xmlfile = self.path / 'dockinglayout.xml'
        self.allfiles = [self.tannerfile]
        self.requiredfiles = [self.tannerfile]
        #self.setup = self.path / 'setup'
        self.allfolders = []
        self.allfilesfolders = self.allfiles + self.allfolders

    def __repr__(self):
        return "Leditdesign(" + repr(str(self.tannerfile)) + ")"

    def exists(self):
        if not self.tannerfile.is_file():
            return False
        for x in self.requiredfiles:
            if not x.exists():
                return False
        for x in self.allfilesfolders:
            if not x.exists():
                # print(str(x) + ' missing in Seditfolder.')
                pass
        return True

    def get_liblinks(self):
        listofrefs = []
        if self.exists():
            with open(self.liblistsummary) as lls:
                for line in lls:
                    if line.startswith(str(self.tannerfile)+';'):
                        m = re.match('(?P<tdb>[^;\n]+);(?P<libname>[^;\n]+);(?P<libpath>[^;\n]*);(?P<liblink>[^;\n]*);(?P<comment>[^;\n]*)',line)
                        listofrefs.append([m.groupdict()['libname'], m.groupdict()['liblink']])
        else:
            raise Exception('non-existing library')
        return listofrefs

    def get_liblinkdict(self, nest = 20, tree = None):
        liblinkdict = {}
        if self.exists():
            # do not forget to add itself!! (bad example: consolidated from CASPAR2 @ 20170420)
            # for L-Edit, add itself is already done by get_liblinks
            # yet, for speed, we will change '..' in its name as default value
            if tree is None:
                tree = [self.name]
            #print('\ntree : ' + repr(tree))
            #print('self : ' + repr(self))
            for llname, ll in self.get_liblinks():
                if ll=='':
                    continue
                if ':' not in ll:
                    llpath = self.path / ll
                    #print('self.path : ' + repr(self.path))
                    #print('ll : ' + repr(ll))
                    #print('llpath : ' + repr(llpath))
                else:
                    llpath = pathlib.Path(ll)
                    #print('llpath : ' + repr(llpath))

                llpathname = llname
                llpathlink = resolve2dots(str(llpath))
                #print('llpathlink : ' + repr(llpathlink))
                liblinkdict[llpathname] = [  [ tree, llpathlink] ]

            if nest>0:
                for llname, ll in self.get_liblinks():
                    if ':' not in ll:
                        llpath = self.path / ll
                    else:
                        llpath = pathlib.Path(ll)

                    llpathname = llname
                    llpathlink = resolve2dots(str(llpath))

                    if llpathname not in tree:
                        #print('deeper: ' + repr(llpathname))
                        deeptree = tree + [llpathname]
                        subliblinkdict = Leditdesign(llpathlink).get_liblinkdict(nest - 1, deeptree)
                        for key in subliblinkdict:
                            if key not in liblinkdict.keys():
                                liblinkdict[key] = []
                            for finaltree, link in subliblinkdict[key]:
                                liblinkdict[key].append([finaltree, link])

            else:
                print('maybe make nest longer: ' + repr(llpathname) + 'not in ' + str(tree))

        return liblinkdict

    def check_liblinkdict(self):
        liblinkdict = self.get_liblinkdict()

        text = ''

        for lib in liblinkdict:
            links = set()
            for tree, link in liblinkdict[lib]:
                links.add(link.lower())
            linkslist = list(links)
            linkslist.sort()
            if len(links)>1:
                for liblink in linkslist:
                    if len(text) == 0:
                        text = 'Multiple links for same library in design: ' + str(self.tannerfile) + '\n'
                        print(text[:-1])
                    text += '\t' + liblink + ':\n'
                    for tree, link in liblinkdict[lib]:
                        if link.lower() == liblink:
                            text += '\t\t' + '>'.join(tree) + ':\n'

        return text

    def get_nhlpath(self):
        """ works only correctly in 20% of the cases"""
        if self.exists():
            with open(self.tannerfile,'rb') as tdbfile:
                tdbfilestr = tdbfile.read()
                tech1 = tdbfilestr.find(b'Technology')
                if tech1 != -1:
                    tech2 = tdbfilestr.find(b'Technology', tech1 + 1)
                    if tech2 != -1:
                        tdbfile.seek(tech2 - 200)
                        nhlpathstr = tdbfile.read(200)
                        colon = nhlpathstr.find(b':\\')
                        if colon != -1:
                            null = nhlpathstr.find(0,colon)
                            if null != -1:
                                return nhlpathstr[colon-1:null].decode()
        return ''

def resolve2dots(path):
    #print('resolve2dots:')
    #print('path: ' + path)
    resolvedpath = path
    while '\\..\\' in resolvedpath:
        #print('temp resolvedpath: ' + resolvedpath)
        y = re.sub(r'\\[^\\]+\\[.][.]\\', r'\\',resolvedpath,1)
        #print('y: ' + str(y))
        resolvedpath = y
    #print('resolvedpath: ' + resolvedpath)
    return resolvedpath


def findlayoutsin(projectdesignfolder):
    if projectdesignfolder is None:
        projectdesignfolder = ('S:\\')
    print(projectdesignfolder)
    layoutlist = []
    i = 0
    for root, dirs, files in os.walk(projectdesignfolder):
        for file in files:
            if file.endswith('.tdb') and not file.startswith('~$'):
                i += 1
                fullpath = os.path.join(root,file)
                print(str(i) + '  : ' + fullpath)
                layoutlist.append(Leditdesign(fullpath))
    return layoutlist

def exportlayoutfiles(project=None, projectsdrive=None, outfile=None):
    global USERset
    USERset.load()
    sep = USERset.get_type('CSVseparator')
    CSVheader = USERset.get_type('CSVheadersep')

    if projectsdrive is None:
        projectsdrive = 'N'
    projectsdrive += ':\\'
    tic = time.time()

    if project is not None:
        startdrive = os.path.join(projectsdrive, 'projects', project)
    else:
        startdrive = os.path.join(projectsdrive, 'projects')
    if outfile is None:
        outfile = LTBsettings.alltdbfilename()

    if CSVheader:
        txt = sep.join(['sep=', '\n'])
    else:
        txt = ''

    for lay in findlayoutsin(startdrive):
        txt += str(lay.tannerfile) + '\n'
    toc = time.time()
    general.write(outfile, txt, True)

    print('elapsed time: '+ str(toc-tic) + ' seconds')

def exporttechrefs(projectdesignfolder = None, outfile = None):
    if outfile is None:
        outfile = LTBsettings.tdbtechreffilename()
    layouttxt = ''

    i = 0
    for lay in findlayoutsin(projectdesignfolder):
        print(str(lay.tannerfile))
        with open(lay.tannerfile,'rb') as tdbfile:
            tdbfilestr = tdbfile.read()
            techrefpoint = tdbfilestr.find(b'TechnologyTdb')
            if techrefpoint != -1:
                tdbfile.seek(techrefpoint + 21)
                techrefraw = tdbfile.read(200)
                techref = techrefraw[:techrefraw.find(b'\x00')].decode('utf-8')
                if not os.path.exists(techref):
                    layouttxt += '*** Broken link *** '
                if techref.find('internal projects') != -1:
                    layouttxt += '*** internal projects is obsoleting *** '
                layouttxt += lay.tannerfile + '   ==> ' + techref + '\n'

    general.write(outfile, layouttxt, True)



def libcheck(projectfolder=None, autoclick=True):
    # The logger of this module is called 'seditlibcheck'
    # The Filehandler's filename will be dependent on the initial function
    logllc = logging.getLogger('seditlibcopy')
    hndl = logging.FileHandler(r'T:\leditlibcheck.log')
    hndl.setFormatter(logging.Formatter('%(asctime)s: %(message)s'))
    logllc.addHandler(hndl)

    if projectfolder is None:
        projectfolder = r'S:\projects'

    logllc.info('===========================================')
    logllc.info('Run libcheck in: ' + projectfolder)
    logllc.info('===========================================')
    # exportlayoutfiles(projectfolder)
    # exporttechrefs(projectfolder)

    alllayouts = findlayoutsin(projectfolder)

    print('run LibrariesSummary in L-Edit.')
    print('Make sure all files in alltdb.txt are openable, comment with **' +
          'if not (make filename unexistent).')

    input('Done so?')

    # while autoclick and not complete:
    #     subprocess.Popen(r"X:\LEdit\external\libcheckContinue.exe")
    #     time.sleep(2)

    # find all problems in allschematics:
    # broken links (Ow ow, that is gonna be a lot....)
    logllc.info('===========================================')
    logllc.info('Find broken links in: ' + projectfolder)
    logllc.info('-------------------------------------------')

    for lay in alllayouts:
        # make lay as sch, so we can reuse algorithm. :-)
        # continue here #####################
        lllines = lay.get_liblinks()
        for llname, ll in lllines:
            if ll == '':
                print('broken library link: ' + str(lay.tannerfile) + ' / ' +
                      llname)
                logllc.warning('broken library link: ' + str(lay.tannerfile) +
                               ' / ' + llname)

    logllc.info('===========================================\n\n\n')

    # Library nesting with different location for equal library name
    logllc.info('===========================================')
    logllc.info('Inconsistent library nesting in: ' + projectfolder)
    logllc.info('-------------------------------------------')
    textsum = 'Summary of designs with multiple links for same library:\n'
    for lay in alllayouts:
        print('checking: ' + repr(lay))
        text = lay.check_liblinkdict()
        if len(text) > 0:
            logllc.info(text, r'T:\laylibcheck.log', False)
            textsum += str(lay.path) + '\n'

    logllc.info('\n\n-------------------------------------------\n')
    logllc.info(textsum + '\n', r'T:\laylibcheck.log', False)
    logllc.info('===========================================\n\n\n')


def nhlpathcheck(projectfolder=None, outfile=r'T:\nhlpathcheck.csv'):
    if projectfolder is None:
        projectfolder = r'S:\projects'

    alllayouts = findlayoutsin(projectfolder)

    nhlpaths = ''
    with open(r'T:\nhlpathcheck1.log', 'w') as nhllistfile:
        for x in alllayouts:
            path = x.get_nhlpath()
            print(str(x.tannerfile) + '    :    ' + path)
            nhlpaths += str(x.tannerfile) + ';' + path + '\n'
            nhllistfile.write(str(x.tannerfile) + ';' + path + '\n')
    general.write(outfile, nhlpaths, True)


def argparse_setup(subparsers):
    parser_led_elf = subparsers.add_parser('exportlayoutfiles',
                                           help=('export all tdb layout files' +
                                                 ' for a given project'))
    parser_led_elf.add_argument('-p', '--project', required=False,
                                default=None, help='project name ' +
                                '(default: None (=all))')
    parser_led_elf.add_argument('-d', '--projectsdrive', required=False,
                                default=None, help='projects disk drive ' +
                                '(default: N)')
    parser_led_elf.add_argument('-o', '--outfile', default=None, help=('the ' + 
                                'csv report file name, default: "' + 
                                LTBsettings.alltdbfilename() + '"'))


    parser_led_etr = subparsers.add_parser('exporttechrefs',
                                           help=('export technology ' +
                                                 'references for a given ' +
                                                 'project'))
    parser_led_etr.add_argument(
            '-p', '--project', required=True, help='the PROJECT name')

    parser_led_lc = subparsers.add_parser('libcheck',
                                          help=('do library check for a ' +
                                                'given project'))
    parser_led_lc.add_argument(
            '-p', '--project', required=True, help='the PROJECT name')


def argparse_eval(args):
    # make a dict of args
    dictargs = vars(args)
    funcdict = {'exportlayoutfiles': (exportlayoutfiles,
                                      [dictargs.get('project'),
                                       dictargs.get('projectsdrive'),
                                       dictargs.get('outfile')]),
                'exporttechrefs': (exporttechrefs,
                                   [dictargs.get('project')]),
                'libcheck': (libcheck,
                             [dictargs.get('project')])
                }
    return funcdict


if __name__ == "__main__":
    general.logsetup()
    general.myargparse(argparse_setup, argparse_eval, 'v20230901')
