from __future__ import print_function
import os
import re
import ast
import inspect
import logging      # in case you want to add extra logging
import general
import LTBsettings

NAME = -1
TYPE = 0
DFLT = 1
VALUE = 2

class SettingsError(general.LTBError):
    pass

class Settings():
    '''Masterclass for LTB USERsettings and PROJECTsettings.
    
    standard properties: 
        inifilename: string pointing to the file location of the settings
        settings: dictionary with for each settingname (key) containing a list
                  of type, defaultvalue, and the actual value
        defaultorder: order in which the settingnames are output by default,
                      should contain each key of settings.
        status: status of the settings class: (OBSOLETING)
            'empty': actual values are not set
            'default': actual values are equal to the default
            'modified': actual values are set and not equal to the default
            'ok': unclear, so obsoleting and replacing with is... methods
    standard methods:
        __init__()
        __repr__()
        showall(output)
        load()
        default()
        save()
        saveas(inifilename)
        savecopy(inifilename)
        get(settingname) OBSOLETING
        get_str(settingname)
        get_type(settingname)
        get_dflt_str(settingname)
        get_dflt_type(settingname)
        set_str(settingname, value[str])
        set_type(settingname, value)
        set_dflt_str(settingname, value[str])
        set_dflt_type(settingname, value)
    '''
    def __init__(self):
        self.inifilename = ''
        self.settings = {}
        self.defaultorder = []
        #self.status = ''

    def __repr__(self):
        if self.islegal():
            text = str('<' + str(self.__class__) + ' instance> with following ' +
                    'content:\n' + self.content(False))
        else:
            text = str('<' + str(self.__class__) + ' instance> with illegal ' +
                    'content:\n' + repr(self.settings))
        return text

    def content(self, verbose=True):
        '''returns inifile locations and settings content.'''
        global NAME, TYPE, DFLT, VALUE

        text = self.inifilename + '\n'
        text += '=' * len(self.inifilename) + '\n'
        text += 'settingname: VALUE   [DFLT] (TYPE)\n\n'
        for settingname in self.defaultorder:
            text += settingname + ': '
            text += self.get_str(settingname) + '   ['
            text += self.get_dflt_str(settingname) + '] ('
            text += self.settings[settingname][TYPE] + ')\n'
        
        if verbose:
            print(text)
        return text

    def islegal(self):
        '''checks whether
        - defaultorder equals all keys in settings.
        - all content for [TYPE] are classes
        - all content for [VALUE] and [DFLT] are of type [TYPE] or NoneType
        '''
        if len(self.defaultorder) != len(self.settings):
            logging.debug('len(self.defaultorder) != len(self.settings)')
            logging.debug('str(self.defaultorder)')
            logging.debug(str(self.defaultorder))
            logging.debug('str(self.settings)')
            logging.debug(str(self.settings))
            return False
        if not all([x in self.settings for x in self.defaultorder]):
            logging.debug('not all([x in self.settings for x in self.defaultorder])')
            logging.debug('str(x for x in self.settings)')
            logging.debug(str(x for x in self.settings))
            logging.debug('str(x for x in self.defaultorder)')
            logging.debug(str(x for x in self.defaultorder))
            return False
        global NAME, TYPE, DFLT, VALUE
        if not all([inspect.isclass(eval(self.settings[x][TYPE])) for x
                    in self.defaultorder]):
            logging.debug('not all([inspect.isclass(eval(self.settings[x][TYPE]))' +
                        ' for x in self.defaultorder])')
            logging.debug('not all(' + 
                          str([inspect.isclass(eval(self.settings[x][TYPE])) 
                               for x in self.defaultorder]) +
                          ')')
                        
            return False
        if not all([isinstance(self.settings[x][VALUE], 
                               (eval(self.settings[x][TYPE]), None.__class__) ) for
                    x in self.defaultorder]):
            logging.debug('not all([isinstance(self.settings[x][VALUE], ' +
                        '(eval(self.settings[x][TYPE]), None.__class__) ) for ' +
                        'x in self.defaultorder])')
            logging.debug('not all(' + 
                          str([isinstance(self.settings[x][VALUE], 
                                          (eval(self.settings[x][TYPE]),
                                           None.__class__) )
                               for x in self.defaultorder]) +
                          ')')
            for x in self.defaultorder:
                logging.debug(str(isinstance(self.settings[x][VALUE], 
                                          (eval(self.settings[x][TYPE]),
                                           None.__class__) ) ) + 
                              ': ' + repr(self.settings[x][VALUE]) )
            return False
        return True

    def load(self):
        '''(re-)load settings from inifile'''
        global NAME, TYPE, DFLT, VALUE
        if not self.islegal():
            raise SettingsError('Illegal state of settings instance.')
        
        # load with default values first
        self.default()
        
        if os.path.isfile(self.inifilename):
            with open(self.inifilename, 'r') as inifile:
                inifiletext = inifile.read()
        else:
            
            return

        for settingname in self.defaultorder:
            pattern = (r'^\s*' + settingname + r'\s*=[ \t\v]*(.+)\s*?$')
            m = re.search(pattern, inifiletext, re.M)
            # only if the value is defined in the inifile according the
            # pattern, the value will be overwritten, the other ones stay
            # default.
            if m is not None:
                self.set_str(settingname, m.groups()[0])
        if self.loadcheck() != 0:
            errno = self.loadcheck() 
            if errno == -1:
                raise Exception("Settings.loadcheck() not passed. project " + 
                                "does not match project names in settings.  " +
                                "Most probably, you have a local project.ini" +
                                "that does not match with the actual project. "+
                                "Check " + LTBsettings.settingspath())
            if errno == -2:
                raise Exception("Settings.loadcheck() not passed.  Project " + 
                                "settings are all empty.  Check " +
                                LTBsettings.settingspath() + " or " +
                                LTBsettings.defaultprojectsettings() + '.')
            else:
                raise Exception("Settings.loadcheck() not passed. loadcheck(): " +
                                str(self.loadcheck()))

    def loadcheck(self):
        return 0   # Ok

    def default(self):
        '''set setting values to default settings.'''
        global NAME, TYPE, DFLT, VALUE
        if not self.islegal():
            raise SettingsError('Illegal state of settings instance.')
        for settingname in self.defaultorder:
            self.settings[settingname][VALUE] = self.settings[settingname][DFLT]

    def save(self):
        '''save actual settings to inifile.
        
        Note: Saving makes implicit default settings from original inifile explicit
        '''
        global NAME, TYPE, DFLT, VALUE
        if not self.islegal():
            raise SettingsError('Illegal state of settings instance.')

        initext = ''
        for settingname in self.defaultorder:
            if self.get_type(settingname) is not None:
                initext += settingname + ' = ' + self.get_str(settingname) + '\n'
        
        with open(self.inifilename, 'w') as inifile:
            inifile.write(initext)

    def saveas(self, inifilename):
        '''save actual settings to new inifile.
        
        Note: Saving makes implicit default settings from original inifile explicit,
        but original inifile is not changed.
        inifilename changes to new inifilename
        '''
        self.inifilename = inifilename
        self.save()

    def savecopy(self, copyfilename):
        '''save actual settings to new inifile.
        
        Note: Saving makes implicit default settings from original inifile explicit,
        but original inifile is not changed.
        inifilename will not have changed after successful operation
        '''
        keepinifilename = self.inifilename
        self.inifilename = copyfilename
        self.save()
        self.inifilename = keepinifilename

    def get(self, settingname):
        '''obsolete function, replaced by get_str and get_type.'''
        global NAME, TYPE, DFLT, VALUE
        logging.warning('obsolete function Settings.get()', stack_info=True)
        return self.settings[settingname][VALUE]

    def get_str(self, settingname):
        '''get_str(self, settingname)
        returns string-representation of the value of setting[settingname]
        '''
        return str(self.get_type(settingname))

    def get_type(self, settingname):
        '''get_type(self, settingname)
        returns the value of setting[settingname] in the type it is.
        '''
        global NAME, TYPE, DFLT, VALUE
        return self.settings[settingname][VALUE]

    def get_dflt_str(self, settingname):
        '''get_dflt_str(self, settingname)
        returns string-representation of the default value of setting[settingname]
        '''
        return str(self.get_dflt_type(settingname))

    def get_dflt_type(self, settingname):
        '''get_dflt_type(self, settingname)
        returns the default value of setting[settingname] in the type it is.
        '''
        global NAME, TYPE, DFLT, VALUE
        return self.settings[settingname][DFLT]

    def set_str(self, settingname, value):
        '''set_str(self, settingname, value)
        sets the value of setting[settingname] as string representation.
        '''
        if settingname not in self.settings:
            raise SettingsError('unknown settingname: ' + settingname)
        if not isinstance(value, str):
            raise TypeError('value must be of type str')
        global NAME, TYPE, DFLT, VALUE

        if self.settings[settingname][TYPE] == 'str':
            self.set_type(settingname, value)
        elif self.settings[settingname][TYPE] == 'bool':
            if not isinstance(ast.literal_eval(value), bool):
                raise TypeError('ast.literal_eval(value) must be of type bool')
            self.set_type(settingname, ast.literal_eval(value))
        else:
            raise SettingsError('unsupported type in settings')

    def set_type(self, settingname, value):
        '''set_type(self, settingname, value)
        sets the value of setting[settingname] in the type it is
        '''
        global NAME, TYPE, DFLT, VALUE
        if settingname not in self.settings:
            raise SettingsError('unknown settingname: ' + settingname)
        if not isinstance(value, eval(self.settings[settingname][TYPE])):
            raise TypeError('value must be of type ' +
                            self.settings[settingname][TYPE])

        self.settings[settingname][VALUE] = value

    def set_dflt_str(self, settingname, value):
        '''set_dflt_str(self, settingname, value)
        sets the DFLT of setting[settingname] where value is given in string representation.
        '''
        if settingname not in self.settings:
            raise SettingsError('unknown settingname: ' + settingname)
        if not isinstance(value, str):
            raise TypeError('value must be of type str')
        global NAME, TYPE, DFLT, VALUE

        if self.settings[settingname][TYPE] == 'str':
            self.set_dflt_type(settingname, value)
        elif self.settings[settingname][TYPE] == 'bool':
            if not isinstance(ast.literal_eval(value), bool):
                raise TypeError('ast.literal_eval(value) must be of type bool')
            self.set_dflt_type(settingname, ast.literal_eval(value))
        else:
            raise SettingsError('unsupported type in settings')

    def set_dflt_type(self, settingname, value):
        '''set_dflt_type(self, settingname, value)
        sets the DFLT of setting[settingname] where value is given in the type it is
        '''
        global NAME, TYPE, DFLT, VALUE
        if settingname not in self.settings:
            raise SettingsError('unknown settingname: ' + settingname)
        if not isinstance(value, eval(self.settings[settingname][TYPE])):
            raise TypeError('value must be of type ' +
                            self.settings[settingname][TYPE])

        self.settings[settingname][DFLT] = value


class USERsettings(Settings):
    '''class for LTB USERsettings.'''
    def __init__(self, inifilename=None):
        if inifilename is None:
            inifilename = LTBsettings.usersettings()
        self.inifilename = inifilename
        self.settings = {
                 'simserver': ['str', 'clsim.clst', ''],
                 'linuxusername': ['str', os.getlogin().lower(), ''],
                 'caelestefolder': ['str', r'\\dsn.silo.clst\caeleste_S', ''],
                 'CSVseparator': ['str', getListSeparator(), ''],
                 'CSVheadersep': ['bool', True, True]
                }
        self.defaultorder = ['simserver', 'linuxusername', 'caelestefolder',
                             'CSVseparator', 'CSVheadersep']
        self.default()

    def load(self):
        '''(re-)load the values with the content of the file set in the inifile
        property. In the case for user settings, it is rare that one can 
        continue without local LTB user settings, so this deserves a warning.
        '''
        if not os.path.isfile(self.inifilename):
            logging.info('Local user inifile does not exist: ' + self.inifilename)
        super().load()


class PROJECTsettings(Settings):
    '''class for LTB PROJECTsettings.
    
    extra properties: 
        defaultfilename: string pointing to the file location of the default 
            settings
        project: project name 
        
    extra methods:    
        isempty_alldefaults()
        isempty_allvalues()
        isnondefault_anyvalue()
        isempty_anyvalue_for_nonempty_default()
    '''
    def __init__(self, project=None, inifilename=None, defaultfilename=None):
        if inifilename is None:
            inifilename = LTBsettings.projectsettings()
        if defaultfilename is None:
            defaultfilename = LTBsettings.defaultprojectsettings()
        self.inifilename = inifilename
        self.defaultfilename = defaultfilename
        self.project = project
        self.settings = {'projectname': ['str', project, None],
                         'technologyname': ['str', None, None],
                         'schematicsfolder': ['str', None, None],
                         'Sedit_exportpath': ['str', None, None],
                         'sourceincludetech': ['str', None, None],
                         'sourceincludeproject': ['str', None, None],
                         'calibreEnvironment': ['str', None, None],
                         'LVSrulefile': ['str', None, None],
                         'LVSincludefile': ['str', None, None],
                         'DRCrulefile': ['str', None, None],
                         'DRCTOPrulefile': ['str', None, None],
                         'DRCstitchrulefile': ['str', None, None],
                         'YLDrulefile': ['str', None, None],
                         'ANTrulefile': ['str', None, None],
                         'PEXrulefile': ['str', None, None],
                         'radhard': ['bool', None, None],
                         'stdcellLayoutLib': ['str', None, None]
                        }
        self.defaultorder = ['projectname', 'technologyname',
                             'schematicsfolder', 'Sedit_exportpath',
                             'sourceincludetech', 'sourceincludeproject',
                             'calibreEnvironment',
                             'LVSrulefile', 'LVSincludefile', 'DRCrulefile', 
                             'DRCTOPrulefile', 'DRCstitchrulefile', 
                             'YLDrulefile', 'ANTrulefile', 'PEXrulefile', 
                             'radhard', 'stdcellLayoutLib']
        if project is not None:
            if os.path.isfile(self.defaultfilename):
                self.loaddefault(project)
            self.default()

    def loaddefault(self, project):
        '''loaddefault(self, project)
        loads the project-dependent default values from the defaultfilename with 
        'project.settingname = '
        that resides in the file.
        '''
        if not self.islegal():
            raise SettingsError('Illegal state of settings instance.')
        self.project = project
        global NAME, TYPE, DFLT, VALUE
        try:
            with open(self.defaultfilename, 'r') as defaultfile:
                defaultfiletext = defaultfile.read()
        except FileNotFoundError:
            logging.error('defaultfile does not exist: ' +
                          self.defaultfilename)
            raise
        allset = True
        anyset = False
        for settingname in self.defaultorder:
            oneset = False
            pattern = (r'^\s*' + self.project + '[.]' +
                       settingname + r'\s*=\s*(.+)\s*?$')
            m = re.search(pattern, defaultfiletext, re.M)
            if m is not None:
                #self.settings[settingname][DFLT] = m.groups()[0]
                self.set_dflt_str(settingname, m.groups()[0])
                oneset = True
            allset = allset and oneset
            anyset = anyset or oneset
        if anyset and not allset:
            logging.info('Not all settings have been loaded with a ' +
                         'default value. project:' + project)
        if not anyset:
            logging.info('No default settings have been loaded, is it a' +
                         'correct project name (' + project + ')?')

    def loadcheck(self):
        '''If this fails, the settings of another project are to be used for the
        actual project.
        This is a showstopper, too risky
        '''
        if not self.islegal():
            raise SettingsError('Illegal state of settings instance.')
        if self.project != self.get_type('projectname'):
            return -1
        if self.isempty_allvalues():
            return -2

        return 0  # all ok

    def load(self):
        '''(re-)load the values with the content of the file set in the inifile
        property. In the case for project settings, this deserves a warning and
        a check whether self.project and settings.projectname are equal.
        '''
        if os.path.isfile(self.inifilename):
            logging.warning('Local project inifile used: ' + self.inifilename)
        super().load()
        if self.loadcheck() != 0:
            if self.loadcheck() == -1:
                raise SettingsError("project name doesn't match project name in project.ini file.")
            elif self.loadcheck() == -2:
                raise SettingsError("project.ini file is empty for current project.")
            else:
                raise SettingsError("Settings.loadcheck() not passed.")

        self.savecopy(self.inifilename + '.lastused')

    def isempty_alldefaults(self):
        '''Are all settings defaults None? (Note: projectname is not checked)
        '''
        if not self.islegal():
            raise SettingsError('Illegal state of settings instance.')

        for settingname in self.defaultorder:
            if settingname != 'projectname':
                if self.get_dflt_type(settingname) is not None:
                    return False
        return True

    def isempty_allvalues(self):
        '''Are all settings values None? (Note: projectname is not checked)
        '''
        if not self.islegal():
            raise SettingsError('Illegal state of settings instance.')

        for settingname in self.defaultorder:
            if settingname != 'projectname':
                if self.get_type(settingname) is not None:
                    return False
        return True

    def isnondefault_anyvalue(self):
        '''Is there any setting with a nondefault value?
        '''
        if not self.islegal():
            raise SettingsError('Illegal state of settings instance.')

        for settingname in self.defaultorder:
            if self.get_type(settingname) != self.get_dflt_type(settingname):
                return True
        return False

    def isempty_anyvalue_for_nonempty_default(self):
        '''Is there any empty value for a non-empty default value?
        '''
        if not self.islegal():
            raise SettingsError('Illegal state of settings instance.')
        global NAME, TYPE, DFLT, VALUE
        for settingname in self.defaultorder:
            if settingname == 'projectname':
                continue   # for settingname
            if (self.get_type(settingname) is None and
                    self.get_type(settingname) is not None):
                return True
        return False


def getListSeparator():
    '''Retrieves the Windows list separator character from the registry'''
    import winreg
    aReg = winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER)
    aKey = winreg.OpenKey(aReg, r"Control Panel\International")
    val = winreg.QueryValueEx(aKey, "sList")[0]
    return val

