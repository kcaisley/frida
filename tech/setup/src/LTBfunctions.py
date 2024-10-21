# Some functions that are used in different modules of the LayoutToolbox
import os
import logging      # in case you want to add extra logging
import general
import LTBsettings

import settings

PROJset = settings.PROJECTsettings()


def copy_dotsp_inpath_rec(project, path, backup):
    import shutil
    for fileordir in os.listdir(path):
        fullfileordir = path + os.sep + fileordir
        if os.path.isdir(fullfileordir):
            copy_dotsp_inpath_rec(project, fullfileordir, backup)
        elif os.path.isfile(fullfileordir):
            if fileordir.endswith('.sp'):
                src = fullfileordir
                dst = LTBsettings.seditfilepath(project) + fileordir
                copy = False
                if os.path.isfile(dst):
                    srctime = os.path.getmtime(src)
                    dsttime = os.path.getmtime(dst)
                    if srctime > dsttime:
                        general.prepare_write(dst, backup)
                        print(fullfileordir + ':\n OVERWRITE: older version ' +
                              'in LTB seditfilepath')
                        logging.info(fullfileordir + ':\n OVERWRITE: ' +
                                     'older version in LTB seditfilepath')
                        copy = True
                    else:
                        print(fullfileordir + ':\n NO copy   :newer/equally ' +
                              'old version in LTB seditfilepath')
                else:
                    print(fullfileordir + ':\n COPY:      did not exist in ' +
                          'LTB seditfilepath')
                    copy = True

                if copy:
                    shutil.copy2(src, dst)


def copynetlist_proj2ltb(project, backup=True):
    global PROJset
    PROJset.loaddefault(project)
    PROJset.load()

    projectcheck = PROJset.get_str('projectname')
    if projectcheck != project:
        warning = ('WARNING!! \nSelected project (' + project +
                   ') does not match the projectname defined in ' +
                   LTBsettings.projectsettings() + ' (' + projectcheck + ').')
        raise Exception(warning)
    else:
        Sedit_exportpath = PROJset.get_type('Sedit_exportpath')
        if Sedit_exportpath is not None:
            if os.path.exists(LTBsettings.seditfilepath(project) +
                          '_BLOCK_AUTOCOPY'):
                logging.info('Auto-copy from default netlist to LTB blocked.')
            else:
                if os.path.isdir(Sedit_exportpath):
                    copy_dotsp_inpath_rec(project, Sedit_exportpath, backup)


def prepare_lvs_dir(project, cellname):
    general.prepare_dirs(LTBsettings.lvspaths(project, cellname))


def prepare_drc_dir(project, cellname):
    general.prepare_dirs(LTBsettings.drcpaths(project, cellname))


def prepare_yld_dir(project, cellname):
    general.prepare_dirs(LTBsettings.yldpaths(project, cellname))


def prepare_xor_dir(project, cellname):
    general.prepare_dirs(LTBsettings.xorpaths(project, cellname))


def prepare_project_dir(project):
    general.prepare_dirs(LTBsettings.allpaths(project))


def isprepared_project_dir(project):
    return general.isprepared_dirs(LTBsettings.allpaths(project))
