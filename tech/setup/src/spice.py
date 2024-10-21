import os
import sys
import re
import timestamp

import logging      # in case you want to add extra logging
import general
import LTBfunctions
import LTBsettings
import laygen
import settings


class SpiceError(general.LTBError):
    pass


class UndefSubcktError(SpiceError):
    pass


class PortMismatchError(SpiceError):
    pass


class IncompleteNetlist(SpiceError):
    pass


class ParameterMismatchError(SpiceError):
    pass


class AddressError(SpiceError):
    pass


class NetnameError(SpiceError):
    pass


USERset = settings.USERsettings()
PROJset = settings.PROJECTsettings()

# obsolete
# STD_SUBCKT = ['depletion', 'log_Cnwnmos', 'log_ndio', 'log_nmos',
#               'log_nmos_lowVth', 'log_pdio', 'log_pmos',
#               'log_pmos_lowVth', 'poly_diode', 'PPD', 'std_C_param',
#               'std_CMiM', 'std_CMiMH', 'std_Cnpod', 'std_Cnwnmos',
#               'std_ndio', 'std_nmos', 'std_nmos_lowVth', 'std_pdio',
#               'std_pmos', 'std_pmos_lowVth', 'std_rnwell', 'std_rpoly', 'TG',
#               'std_CMiM2', 'bondpad', 'std_TG', 'C_param']
DEF_SUBCKT = []
MOS_NAMES = ['std_pmos', 'std_nmos', 'log_pmos', 'log_nmos', 'std_nmos_lowVth',
             'log_nmos_lowVth', 'log_pmos_lowVth']
DIO_NAMES = ['std_pdio', 'std_ndio']
INTCON_NAMES = ['interconnect', 'interconnect_WL']
INTCON_NOPARAMS = {'interconnect': 2, 'interconnect_WL': 4}
RES_SHORT = ['Rshort', 'bondpadmodel', 'STDCELL_VERSION_1_0']
PREFIX = {'a': -18, 'f': -15, 'p': -12, 'n': -9, 'u': -6, 'm': -3,
          'k': 3, 'Meg': 6, 'G': 9, 'T': 12,
          }


def layoutfilepath(project):
    path = 'T:\\' + project + '\\layout\\'
    print('*****************************************************')
    print('* OBSOLETE, use LTBsettings.layoutfilepath(...) instead *')
    print('*****************************************************')
    return path


class Params(dict):
    def __init__(self, newparams={}):
        # self.params = {}
        # self = {}
        # Why is this paramorder?  Just use dict keys functionality, no?
        #  for exporting in the same order as in original netlist...
        self.paramorder = []
        self.add(newparams)

    def __lt__(self, other):
        # if one of those is not Params, the result is False (as if equal)
        if not isinstance(self, Params) or not isinstance(other, Params):
            return False
        # if the number of params is not the same, evaluate on length
        if len(self) != len(other):
            return len(self) < len(other)
        # check the parameter names in 'paramorder' and check alphabetically
        for i in range(len(self.paramorder)):
            if self.paramorder[i] != other.paramorder[i]:
                return self.paramorder[i] < other.paramorder[i]
        # still here? check values in paramorder
        for i in range(len(self.paramorder)):
            if self[self.paramorder[i]] != other[self.paramorder[i]]:
                # if they are not equal, they should both be strings, otherwise
                # string is higher
                selfval = isinstance(self[self.paramorder[i]], str)
                otherval = isinstance(other[self.paramorder[i]], str)
                if selfval != otherval:
                    return selfval < otherval
                # if both not strings, result False (as if equal)
                if not selfval:
                    return False
                # values that are not 'floatable' are 0
                try:
                    selfval = float(self[self.paramorder[i]])
                except ValueError:
                    selfval = 0
                try:
                    otherval = float(other[self.paramorder[i]])
                except ValueError:
                    otherval = 0
                # both strings? string comparison
                if selfval == 0 and otherval == 0:
                    return self[self.paramorder[i]] < other[self.paramorder[i]]
                # otherwise valuecomparison (unevaluatable string = 0)
                return selfval < otherval
        # still here, they are equal, check my statement with assert
        assert self == other
        return False

    def add(self, newparams):
        if newparams.__class__ == str:
            # better do this with re
            for m in re.finditer(r"(\S+)\s*=\s*[']?" +
                                 r"([^ \t\n\r\f\v']+)[']?\s*", newparams):
                if m.groups()[0] not in self:
                    self[m.groups()[0]] = m.groups()[1]
                    # self.paramorder.append(m.groups()[0])
                else:
                    raise SpiceError('Double definition of a parameter')
        elif newparams.__class__ == list:
            for el in newparams:
                if el.__class__ == str:
                    for m in re.finditer(r"(\S+)\s*=\s*[']?" +
                                         r"([^ \t\n\r\f\v']+)[']?\s*", el):
                        if m.groups()[0] not in self:
                            self[m.groups()[0]] = m.groups()[1]
                            # self.paramorder.append(m.groups()[0])
                        else:
                            raise SpiceError('Double definition of param: ' +
                                             m.groups()[0])
                elif el.__class__ == dict:
                    for [k, v] in el.items():
                        if k not in self:
                            self[k] = v
                            # self.paramorder.append(k)
                        else:
                            raise SpiceError('Double definition of param: ' +
                                             k)
        elif newparams.__class__ == dict:
            for [k, v] in newparams.items():
                if k not in self:
                    self[k] = v
                    # self.paramorder.append(k)
                else:
                    raise SpiceError('Double definition of param: ' + k)
        elif newparams.__class__ == Params:
            for k in newparams.paramorder:
                if k not in self:
                    self[k] = newparams[k]
                    # self.paramorder.append(k)
                else:
                    raise SpiceError('Double definition of param: ' + k)

    def __setitem__(self, key, value):
        # self[key] = val
        if isinstance(value, tuple):
            valtype = value[1]
            val = value[0]
        elif value is None:
            # The case where a default subckt param does not render a number
            # in any way
            valtype = None.__class__
            val = value
        else:
            valtype = str
            val = value

        if not isinstance(val, valtype):
            raise Exception('Should not happen')
        if isinstance(val, str):
            if val.count('9') > 6:
                if val.find('999999') != -1:
                    raise Exception('TO DO fix once this happens (1)')
                # else val.find('090909090909') != -1:
                    # see what happens
            if val[0] == '[':
                raise Exception('Should not happen')

        dict.__setitem__(self, key, val)
        if key not in self.paramorder:
            self.paramorder.append(key)

    def __delitem__(self, key):
        dict.__delitem__(self, key)
        if key in self.paramorder:
            self.paramorder.remove(key)

    def pop(self, key, *default):
        if key in self.paramorder:
            self.paramorder.remove(key)
        return dict.pop(self, key, default)

    def __repr__(self):
        paramsrepr = '{'
        n = 0
        for paramname in self.paramorder:
            n += 1
            if n > 10:
                paramsrepr += '... (' + str(len(self)-10) + ' Params more) '
                break
            if paramsrepr[-1] != '{':
                paramsrepr += ', '
            paramsrepr += '%r' % paramname + ': ' + '%r' % self[paramname]
        return 'Params(%s})' % (paramsrepr)

    def isNumValue(self, paramname):
        logging.warning("Obsoleting function 'isNumValue'", stack_info=True)
        return self.isNumValUnit(paramname)

    def isNumeric(self, paramname):
        return self.isNumValExp(paramname) or self.isNumValUnit(paramname) or self.isNumVal(paramname)

    def isNumValExp(self, paramname):
        if isinstance(self[paramname], str):
            m = re.match(r'(?P<value>\d*[.]?\d+)e(?P<exp>[-+]?\d+)$',
                         self[paramname])
            return m is not None
        else:
            return False

    def numValExp(self, paramname):
        if isinstance(self[paramname], str):
            m = re.match(r'(?P<value>\d*[.]?\d+)e(?P<exp>[-+]?\d+)$',
                         self[paramname])
            if m is not None:
                value = m.groupdict()['value']
                exp = m.groupdict()['exp']
                value = float(value)*10**int(exp)
                return (value, '')
            else:
                return (None, None)
        else:
            return (None, None)

    def isNumVal(self, paramname):
        if isinstance(self[paramname], str):
            m = re.match(r'(?P<value>\d*[.]?\d+)$',
                         self[paramname])
            try:
                float(m.groupdict()['value'])
            except:
                return False
            return True
        else:
            return False

    def isNumValUnit(self, paramname):
        if isinstance(self[paramname], str):
            m = re.match(r'(?P<value>\d*[.]?\d+)(?P<unit>\w*)$',
                         self[paramname])
            try:
                float(m.groupdict()['value'])
            except:
                return False
            if m.groupdict()['unit'].lower() in [x.lower() for x in PREFIX.keys()]:
                return True
            else:
                return False
            
        else:
            return False

    def numValUnit(self, paramname):
        if isinstance(self[paramname], str):
            m = re.match(r'(?P<value>\d*[.]?\d+)(?P<unit>\w*)$',
                         self[paramname])
            if m is not None:
                value = m.groupdict()['value']
                unit = m.groupdict()['unit']
                longestoverwrites = max([len(x) for x in PREFIX.keys()])
                unitmagnitude = 0
                unitscale = unit
                for x in range(longestoverwrites+1):
                    for prefix in PREFIX:
                        if len(prefix) == x:
                            if unit.lower().startswith(prefix.lower()):
                                unitmagnitude = PREFIX[prefix]
                                unitscale = unit[len(prefix):]

                value = float(value)*10**unitmagnitude
                return (value, unitscale)
            else:
                return (None, None)
        else:
            return (None, None)

    def strValUnit(self, paramname):
        if isinstance(self[paramname], str):
            m = re.match(r'(?P<value>\d*[.]?\d+)(?P<unit>\w*)',
                         self[paramname])
            if m is not None:
                value = m.groupdict()['value']
                unit = m.groupdict()['unit']
                longestoverwrites = max([len(x) for x in PREFIX.keys()])
                unitmagnitude = 0
                unitscale = unit
                for x in range(longestoverwrites+1):
                    for prefix in PREFIX:
                        if len(prefix) == x:
                            if unit.lower().startswith(prefix.lower()):
                                unitmagnitude = PREFIX[prefix]
                                unitscale = unit[len(prefix):]

                value = value + 'e' + str(unitmagnitude)
                return (value, unitscale)
            else:
                return (None, None)
        else:
            return (None, None)

    def strValUnit_nodot(self, paramname):
        XIFERP = dict((v, k) for k, v in PREFIX.items())
        XIFERP[0] = ''

        if isinstance(self[paramname], str):
            # m =re.match('(?P<value>\d*[.]?\d+)(?P<unit>\w*)',self[paramname])
            # catch also '###e-06'
            m = re.match(r'(?P<value>\d*[.]?\d+)(?P<unit>\S*)',
                         self[paramname])
            if m is not None:
                value = m.groupdict()['value']
                unit = m.groupdict()['unit']
                longestoverwrites = max([len(x) for x in PREFIX.keys()])
                if unit.startswith('e'):
                    unitmagnitude = int(unit[1:])
                    unitscale = ''
                else:
                    unitmagnitude = 0
                    unitscale = unit
                    for x in range(longestoverwrites+1):
                        for prefix in PREFIX:
                            if len(prefix) == x:
                                if unit.lower().startswith(prefix.lower()):
                                    unitmagnitude = PREFIX[prefix]
                                    unitscale = unit[len(prefix):]
                while unitmagnitude % 3 != 0:
                    value = str(float(value)*10)
                    unitmagnitude -= 1
                while unitmagnitude < min(PREFIX.values()):
                    value = str(float(value)/1000)
                    unitmagnitude += 3
                while unitmagnitude > max(PREFIX.values()):
                    value = str(float(value)*1000)
                    unitmagnitude -= 3

                while True:
                    # tidy up floats that represent integer values
                    if value.endswith('.0'):
                        value = value[:-2]
                    # tidy up floats that are almost integer values <0.1%
                    # inaccuracy
                    #   but do not touch 0.000... !!!
                    #   1.000456 can become 1 iso 1000456u
                    if '.' in value:
                        # check for 0.(000) first
                        if value.startswith('0.'):
                            if unitmagnitude > min(PREFIX.values()):
                                value = str(float(value)*1000)
                                unitmagnitude -= 3
                                continue
                            elif unitmagnitude == min(PREFIX.values()):
                                # lowest possible unitmagnitude reached
                                for digit in range(2, len(value)):
                                    if value[digit] != '0':
                                        if len(value) > digit + 3:
                                            tmpvalue = (value[digit:digit+3] +
                                                        '.' + value[digit+4])
                                            print('tmp:' + tmpvalue)
                                            value = (value[:digit] +
                                                     str(int(round(float(
                                                             tmpvalue)))))
                                            print('val:' + value)

                                        break
                                break
                        # check for x.000 or x.999
                        elif (value.find('.000') != -1 or
                              value.find('.999') != -1):
                            value = str(round(float(value)))
                            continue
                        else:
                            # too little accuracy
                            if value.find('.') < 3:
                                if unitmagnitude > min(PREFIX.values()):
                                    value = str(float(value)*1000)
                                    unitmagnitude -= 3
                                    continue
                                else:
                                    value = str(round(float(value),
                                                      3-value.find('.')))
                                    break
                            # too high accuracy
                            elif value.find('.') > 5 and unitmagnitude < max(PREFIX.values()):
                                value = str(float(value)/1000)
                                unitmagnitude += 3
                                continue
                            else:
                                value = str(round(float(value)))
                                break
                    else:
                        # are we done, let's check?
                        # cut trailing 000
                        if value.endswith('000'):
                            if unitmagnitude < max(PREFIX.values()):
                                value = str(int(value)/1000)
                                unitmagnitude += 3
                                continue
                            else:
                                # highest possible unitmagnitude reached
                                break
                        if len(value) > 5:
                            value = str(float(value)/1000)
                            unitmagnitude += 3
                        else:
                            break
                unit = XIFERP[unitmagnitude]+unitscale
                value_unit = str(value)+unit
                if len(value) > 6:
                    # if '.' in value and value.endswith('99'):
                    #     value = value[:-1]
                    warning = ('len(value) > 5:\n' + self[paramname] +
                               ' becomes: ' + value_unit)
                    logging.error('TO DO fix once this happens:\n' + warning)
                if value == '0':
                    warning = ("value == '0':\n" + self[paramname] +
                               ' becomes: ' + value_unit)
                    logging.error('TO DO fix once this happens:\n' + warning)
                    pass
                    # it is not unusual for interconnect to have a C or R equal
                    # to 0
                    # raise Exception('TO DO fix once this happens (4)')
                if value.endswith('.0'):
                    raise Exception('TO DO fix once this happens (5)')
                return value_unit
            else:
                return None
        else:
            return None

    def export_spice(self):
        netlist = ''
        for k in self.paramorder:
            netlist += k + "=" + self[k] + ' '
            # netlist += k + "=" + self.strValUnit_nodot(k) + ' '
        netlist.rstrip()
        return netlist

    def export_autogen(self):
        if len(self) > 0:
            suffix = '_'
            paramlist = self.paramorder
            paramlist.sort(key=str.upper)
            for key in paramlist:
                if not isinstance(self[key], str):
                    raise SpiceError("parameter value should be of the " +
                                     "string type")
                #if self.isNumValUnit(key) or self.isNumValExp(key):
                if self.isNumeric(key):
                    value = self.strValUnit_nodot(key)
                else:
                    value = self[key]

                if value is None:
                    continue
                if value[0] == value[-1] == "'":
                    raise SpiceError(" ['] should not appear as " +
                                     "opening/closing of parameter value")
                    value = value[1:-1]

                if value.find('.') != -1:
                    # a dot is a forbidden character in a gds file,
                    # so avoid it in a cell name as well.
                    value = re.sub('[.]([0-9])', r'_\1', value)

                suffix += '_' + key[0].upper() + value
            return suffix
        return ''


class LocalParams(Params):
    def export_spice(self):
        netlist = ''
        for k in self.paramorder:
            netlist += '.param ' + k + "=" + self[k] + '\n'
            # netlist += k + "=" + self.strValUnit_nodot(k) + ' '
        netlist.rstrip()
        return netlist


# class Size():
#     def __init__(self, name, value, custom = False):
#         self.name = name      # string
#         self.value = value    # string
#         self.custom = custom  # bool


class Spiceitem():
    def __init__(self, definition):
        self.definition = SpiceLine(definition)
        self.name = definition.split()[0]
        pass    # empty container

    def __lt__(self, other):
        # first check the names:
        #    if they are not equal, decide on the name

        if self.name != other.name:
            if self.name.find('<') == -1 or other.name.find('<') == -1:
                return self.name < other.name
            else:
                # take special care for cardinality, supported up to 99999999
                # (almost 100 million) between the brackets
                tempselfname = self.name
                bs = tempselfname.find('<')
                be = tempselfname.find('>')
                while bs != -1 and bs < be:
                    before = tempselfname[0:bs+1]
                    number = tempselfname[bs+1:be].zfill(8)
                    after = tempselfname[be:]
                    tempselfname = before + number + after
                    bs = tempselfname.find('<', len(before) + len(number))
                    be = tempselfname.find('<', bs)
                tempothername = other.name
                bs = tempothername.find('<')
                be = tempothername.find('>')
                while bs != -1 and bs < be:
                    before = tempothername[0:bs+1]
                    number = tempothername[bs+1:be].zfill(8)
                    after = tempothername[be:]
                    tempothername = before + number + after
                    bs = tempothername.find('<', len(before) + len(number))
                    be = tempothername.find('<', bs)

                return tempselfname < tempothername

        #    if the names are equal, decide on their parameters
        else:
            if hasattr(self, 'params') and hasattr(other, 'params'):
                return self.params < other.params
            else:
                return False

    def hasname(self, name):
        return self.name == name

    def setname(self, name):
        self.name = name

    def getname(self):
        return self.name

    def isSubckt(self):
        return isinstance(self, Subckt)
        # return type(self) == Subckt

    def isInstance(self):
        return isinstance(self, Instance)
        # return type(self) is Instance

    def isMosInstance(self):
        return isinstance(self, MosInstance)
        # return type(self) == MosInstance

    def isRes_short(self):
        return isinstance(self, Res_short)
        # return type(self) == Res_short

    def isCap_parasitic(self):
        return isinstance(self, Cap_parasitic)
        # return type(self) == Res_short

    def isInterconnectInstance(self):
        return isinstance(self, InterconnectInstance)
        # return type(self) == InterconnectInstance

    def isDevice(self):
        return isinstance(self, Device)

    def isDeviceExcl(self):
        return type(self) is Device

    def export_spice(self):
        netlist = self.definition + '\n'
        return netlist

    def export_autogen(self, listofdefinedautogenfunctions,
                       instparams=None, project=None):
        batchtext = '\t// ' + self.definition + '\n\n'
        return batchtext

    def export_wrl(self):
        return '\n'


class Device(Spiceitem):
    pass


class Subckt(Spiceitem):
    def __init__(self, name, ports, paramstring):
        self.definition = ('Subckt(' + repr(name) + ', ' + repr(ports) + ', ' +
                           repr(paramstring) + ')')
        self.name = name        # string
        self.realname = name        # string
        self.content = set()    # instances and devices, empty at init
        self.ports = ports     # list of strings
        self.params = Params(paramstring)    # dict string : value
        self.localparams = LocalParams()    # dict string : value
        self.design = None
        self.nets = set()

    def __lt__(self, other):
        # first check the names:
        #    if they are not equal, decide on the name

        if self.realname != other.realname:
            return self.realname < other.realname
        else:
            return self.name < other.name

    def __repr__(self):
        reprstr = (('Subckt(name = %r, content = set([%d items]), ports ... ' +
                    ', params ... ) ') % (self.name, len(self.content)))
        return reprstr

    def add(self, instdev):
        self.content.add(instdev)

    def hasContent(self, instdevname):
        for instdev in self.content:
            if instdev.hasname(instdevname):
                return True
        return False

    def addports(self, newports):
        self.ports.extend(newports)

    def setrealname(self, cellname):
        self.realname = cellname

    def getrealname(self):
        return self.realname

    def setdesign(self, designname):
        self.design = designname

    def getdesign(self):
        return self.design

    def getparams(self):
        return self.params

    def addparams(self, params):
        return self.params.add(params)

    def addlocalparams(self, params):
        # TODO there cannot be normal (defined in subckt def) and local params
        #      with the same name, this is not checked now
        print('localparam' + str(params))

        return self.localparams.add(params)

    def getcontent(self, itemname):
        for item in self.content:
            if item.getname() == itemname:
                return item

    def incontent(self, itemname):
        for item in self.content:
            if item.getname() == itemname:
                return True
        return False

    def export_spice(self):
        if self.name is not None:
            netlist = '.subckt ' + self.name
            for port in self.ports:
                netlist += ' ' + port
            netlist += ' ' + self.params.export_spice()
            netlist += '\n'
            if self.design is not None:
                netlist += ('* Cell: ' + self.getrealname() + ' | Design: ' +
                            self.design + '\n')
            netlist += self.localparams.export_spice()
            contentl = list(self.content)
            contentl.sort()
            for item in contentl:
                netlist += item.export_spice()
            netlist += '.ends\n\n'
            return netlist
        return '\n'

    def export_autogen_header(self, layoutcellname, design, radhard, force=False):
        newfunction = 'autogen_' + layoutcellname.replace('-', '_') + '_'
        if force:
            newfunction = 'autogen_force_' + layoutcellname.replace('-', '_') + '_'
        if design is not None:
            newfunction += design
        batchtext = '\nLCell ' + newfunction + '() {\n'
        batchtext += '\tLFile activefile;\n'
        batchtext += '\tLCell newCell;\n'
        batchtext += '\tLCell instCell;\n'
        batchtext += '\tLInstance instance;\n'
        batchtext += '\tLCell activeCell;\n'
        batchtext += '\tLPoint coord;\n'
        batchtext += '\tcoord = LPoint_Set(0,0);\n'
        batchtext += '\tLTransform_Ex99 nulTrans;\n'
        batchtext += '\tnulTrans = LTransform_Zero_Ex99();\n'
        batchtext += '\tLTransform_Ex99 shiftTrans;\n'
        batchtext += '\tLPort newPort;\n'
        batchtext += '\tLRect instRect;\n'
        batchtext += '\tLWindow activeWindow;\n'
        batchtext += '\tactivefile = LFile_GetVisible();\n'
        batchtext += '\tchar cellname2[MAX_CELL_NAME] = "";\n'
        batchtext += '\tchar cellname3[MAX_CELL_NAME] = "";\n'
        batchtext += '\tchar cellname4[MAX_CELL_NAME] = "";\n\n'
        
        if not force:    # not force = default
            if design is not None:
                # depending on the radhard setting, try firts in rh_-libs, but
                # also try as a 2nd option in rh_-libs for non-rh designs
                order = ['rh_', ''] if radhard else ['rh_', '']
                for prefix in order:
                    batchtext += ('\tnewCell = LCell_FindEx2_newcell(activefile, "' +
                                  layoutcellname + '", "layout", "' + prefix +
                                  design + '", 0);\n')
                    batchtext += '\tif (newCell == NULL)\n\t'
            batchtext += ('\tnewCell = LCell_FindEx2_newcell(activefile, "' +
                          layoutcellname + '","","", 0);\n\n')

            batchtext += '\tif (newCell == NULL) {\n'

            batchtext += ('\t\tnewCell  = LCell_New(activefile, "' +
                          layoutcellname + '");\n')
            batchtext += ('\t\tLFile_OpenCell(activefile, "' +
                          layoutcellname + '");\n\n')

        else:     # if force
            batchtext += ('\tnewCell = LCell_FindEx2_newcell(activefile, "' +
                                  layoutcellname + '", "layout", "' + 
                                  ('rh_' if radhard else '') +
                                  design + '", 0);\n')
            forcename = layoutcellname + '___force' + timestamp.now()
            batchtext += ('\tif (newCell != NULL) {\n')
            batchtext += ('\t\tnewCell  = LCell_New(activefile, "' + 
                                forcename + '");\n')
            batchtext += ('\t\tLFile_OpenCell(activefile, "' + 
                                forcename + '");\n')
            batchtext += ('\t\tif (newCell == NULL) {\n')
            batchtext += ('\t\t\tLDialog_MsgBox("newcell failed\\n This forcef' +
                                'ul cell might already once be generated, reg' +
                                'enerate using LTBgui for new timestamp.\\n");\n')
            batchtext += ('\t\t\tLUpi_LogMessage("newcell failed. This forcef' +
                                'ul cell might already once be generated, reg' +
                                'enerate using LTBgui for new timestamp.\\n");\n')
            batchtext += ('\t\t}\n')
            batchtext += ('\t}\n')
            batchtext += ('\telse {\n')
            batchtext += ('\t\tnewCell  = LCell_New(activefile, "' +
                                layoutcellname + '");\n')
            batchtext += ('\t\tif (newCell != NULL) {\n')
            batchtext += ('\t\t\tLFile_OpenCell(activefile, "' +
                                layoutcellname + '");\n')
            batchtext += ('\t\t}\n')
            batchtext += ('\t\telse {\n')
            batchtext += ('\t\t\tLDialog_MsgBox("newcell failed\\n This can be' +
                                " caused because in some library cell '" +
                                layoutcellname + "' exists.\\nI will retry with" +
                                ' forceful name\\n");\n')
            batchtext += ('\t\t\tLUpi_LogMessage("newcell failed. This can be' +
                                " caused because in some library cell '" +
                                layoutcellname + "'" + ' exists.\\n");\n')
            batchtext += ('\t\t\tLUpi_LogMessage("Retry with forceful name: ' + 
                                forcename + '\\n");\n')
            batchtext += ('\t\t\tnewCell  = LCell_New(activefile, "' + 
                                forcename + '");\n')
            batchtext += ('\t\t\tif (newCell != NULL) {\n')
            batchtext += ('\t\t\t\tLFile_OpenCell(activefile, "' + 
                                forcename + '");\n')
            batchtext += ('\t\t\t}\n')
            batchtext += ('\t\t\telse {\n')
            batchtext += ('\t\t\t\tLDialog_MsgBox("newcell failed\\n This forc' +
                                'eful cell might already once be generated, r' +
                                'egenerate using LTBgui.\\n");\n')
            batchtext += ('\t\t\t\tLUpi_LogMessage("newcell failed. This forc' +
                                'eful cell might already once be generated, r' +
                                'egenerate using LTBgui.\\n");\n')
            batchtext += ('\t\t\t}\n')
            batchtext += ('\t\t}\n')
            batchtext += ('\t}\n')
            batchtext += ('\tif (newCell != NULL) {\n')
                                  
        batchtext += ('\t\tLUpi_LogMessage(LFormat("autogenerating newCell = %s*%s:%s\\n",\n')
        batchtext += ('\t\t\tLCell_GetCellName( newCell, cellname2, MAX_CELL_NAME ),\n')
        batchtext += ('\t\t\tLCell_GetViewName( newCell, cellname3, MAX_CELL_NAME ),\n')
        batchtext += ('\t\t\tLCell_GetLibName( newCell, cellname4, MAX_CELL_NAME ) ));\n\n')
        return batchtext, newfunction

    def export_autogen_footer(self):
        batchtext = '\t\tactiveWindow = LWindow_GetVisible();\n'
        batchtext += '\t\tif (Assigned(activeWindow)) {\n'
        batchtext += '\t\t\tactiveCell = LWindow_GetCell(activeWindow);\n'
        # Check if activeCell equals newCell. (should be)
        batchtext += '\t\t\tif (activeCell == newCell)\n'
        # Closes activeCell window (except if it is the last one).
        batchtext += '\t\t\t\tif (LWindow_IsLast(activeWindow) == 0)\n'
        batchtext += '\t\t\t\t\tLWindow_Close(activeWindow);\n'
        batchtext += '\t\t}\n'
        batchtext += '\t}\n'
        batchtext += '\treturn newCell;\n}\n'
        return batchtext

    def export_autogen(self, trimPySch, listofdefinedautogenfunctions,
                       project=None, force=False):
        """export_autogen(trimPySch) of Subckt checks in what parameter
        settings the subckt is used in the full 'trimPySch' and generates one
        for every flavour.
        """
        #global PROJset
        # print('export_autogen (Subckt): getParamsUsedSubckt(' +
        # str(self.getname()) + ')')
        print('getParamsUsedSubckt ' + str(self.getname()))

        parameterlist = trimPySch.getParamsUsedSubckt(self.getname())
        parameterlist.sort()
        print('export_autogen of Subckt: ' + str(self))
        print('with so many param sets: ' + str(len(parameterlist)))
        batchtext = ''
        newfunctions = []
        for parameters in parameterlist:
            layoutcellname = self.getrealname() + parameters.export_autogen()

            batchtext_, newfunction = self.export_autogen_header(
                    layoutcellname, self.getdesign(),
                    PROJset.get_str('radhard').lower() == 'true',
                    force=force)
            batchtext += batchtext_
            newfunctions.append(newfunction)

            coordy = 0
            coordx = 0
            batchtext += '\t// PORTS\n'
            for port in self.ports:
                if port == 'gnd':
                    continue
                batchtext += ('\t\tcoord = LPoint_Set(' + str(coordx) + ', ' +
                              str(coordy) + ');\n')
                batchtext += ('\t\tnewPort = LPort_New(newCell, ' +
                              'tech2layer("defaultlabellayer"), "' + port +
                              '", coord.x, coord.y, coord.x, coord.y);\n')
                batchtext += ('\t\tLPort_SetTextAlignment(newPort, ' +
                              'PORT_TEXT_MIDDLE | PORT_TEXT_CENTER);\n')
                batchtext += '\t\tLPort_SetTextSize(newPort, 250);\n\n'
                coordx += 5000

            # # old:
            # contentl = list(self.content)
            # contentl.sort()
            # coordy = 0
            # coordx = -5000
            # for item in contentl:
                # coordx += 5000
                # batchtext += ('\tcoord = LPoint_Set(' + str(coordx) + ', ' +
                #               str(coordy) + ');\n')
                # batchtext += item.export_autogen()

            # new:
            contentl = list(self.content)
            contentl.sort()
            batchtext += '\t// INSTANCES\n'
            batchtext += '\t\tcoord = LPoint_Set(0, 0);\n\n'
            for item in contentl:
                # if instance:
                instparams = Params()
                if item.isInstance():
                    # check the parameter set here!
                    # parameters of instance: define values:
                    for paramname in item.getparams():
                        expression = item.getparams()[paramname]
                        valuefound = False
                        calcinfo = {}
                        while not valuefound:
                            try:
                                valuefound = True
                                calcresult = general.calc(
                                        expression, namevaluedict=calcinfo,
                                        verbose=0)
                            except general.CalcError as e:
                                valuefound = False
                                eargs = e.args[0]
                                # print(eargs[1])
                                assert eargs[0] == '?'
                                # is it just a value?
                                if Params({'tmp': eargs[1]}).isNumValUnit(
                                        'tmp'):
                                    (val, unit) = Params(
                                            {'tmp': eargs[1]}).strValUnit(
                                                    'tmp')
                                    calcinfo[eargs[1]] = str(val)
                                # unknown name found in subckt params?
                                elif eargs[1] in parameters:
                                    calcinfo[eargs[1]] = parameters[eargs[1]]
                                # unknown name found in local subckt params?
                                elif eargs[1] in self.localparams:
                                    calcinfo[eargs[1]] = (
                                            self.localparams[eargs[1]])
                                # in top-level params?
                                elif eargs[1] in (
                                        trimPySch.toplevel.getparams()):
                                    calcinfo[eargs[1]] = (
                                            trimPySch.toplevel.getparams(
                                                    )[eargs[1]])
                                else:
                                    raise SpiceError(
                                            'Parameter ' + eargs[1] + ' from' +
                                            ' ' + item.getparams()[paramname] +
                                            ' not found')
                            except Exception:
                                raise
                        if len(calcresult) > 1:
                            raise Exception('Should not happen')
                        result = calcresult[0]
                        # print(paramname + ': ' + str(result))
                        instparams.add({paramname: str(result)})

                batchtext += item.export_autogen(listofdefinedautogenfunctions,
                                                 instparams,
                                                 project=project)

            batchtext += self.export_autogen_footer()

        return batchtext, newfunctions

    def export_wrl(self, wholeSchematic, removeparasitics=True):
        wrltext = ''
        for port in self.ports:
            wrltext += port + '\t\t\t' + port + '\n'

        contentl = list(self.content)
        contentl.sort()

        shortlist = {}
        # output debug info depending on cell name
        if self.name in ['thiswonthappen']:
            debug = True
        else:
            debug = False

        if removeparasitics:
            sl_tmp = {}
            for item in contentl:
                if item.isRes_short() or item.isInterconnectInstance():
                    portnames2short = item.getshortports()
                    # print('item: ' + str(item))
                    # print('portnames2short: ' + str(portnames2short))

                    assert len(portnames2short) == 2
                    net0 = portnames2short[0]
                    net1 = portnames2short[1]
                    # temporarily have a full exhaustive shortlist (dict)
                    # they contains a sets of connected nets through Rshorts
                    # nets connect to one another
                    sl_tmp[net0] = sl_tmp.get(net0, set()).union((net1,))
                    sl_tmp[net1] = sl_tmp.get(net1, set()).union((net0,))

            if debug:
                print('0. self.ports = ' + str(self.ports))
                print('0. sl_tmp = ' + str(sl_tmp))

            while len(sl_tmp) > 0:
                if debug:
                    print('1. sl_tmp = ' + str(sl_tmp))

                # start finding groups of nets that are shorted
                # pick a random net
                for initnet in sl_tmp:
                    if debug:
                        print('1. initnet = ' + str(initnet))
                    break
                # add both sides of the short to the group
                netgroup = sl_tmp[initnet].union((initnet,))
                prev_ngsize = 0
                # loop over all other nets and repeat as long as the set grows
                while len(netgroup) != prev_ngsize:
                    prev_ngsize = len(netgroup)
                    for net in sl_tmp:
                        # add net if it collides with the existing netgroup
                        if len(sl_tmp[net].intersection(netgroup)) > 0:
                            netgroup.update((net,))
                # netgroup is defined now
                if debug:
                    print('1. netgroup = ' + str(netgroup))
                assert len(netgroup) > 0

                # prioritize port names
                prioritylist = list(filter(
                        lambda x: x in self.ports, netgroup))
                # if there's none, prioritize named nets
                if len(prioritylist) == 0:
                    prioritylist = list(filter(
                        lambda x: not x.startswith('N_'), netgroup))
                # if there's none, prioritize lowest numbered net
                if len(prioritylist) == 0:
                    prioritylist_tmp = list(filter(
                        lambda x: x.startswith('N_'), netgroup))
                    prioritylist = [x for x in prioritylist_tmp
                                    if int(x[2:]) ==
                                    min(int(x[2:]) for x in
                                        prioritylist_tmp)]
                assert len(prioritylist) > 0

                # if there is multiple, shortest name wins,
                prioritylist = [x for x in prioritylist if len(x) ==
                                min(len(x) for x in prioritylist)]
                # if there is still multiple, alphabetically lower wins
                prioritylist = [x for x in prioritylist if x.lower() ==
                                min(x.lower() for x in prioritylist)]
                assert len(prioritylist) == 1

                finalname = prioritylist[0]
                if debug:
                    print('2. finalname = ' + str(finalname))
                for net in netgroup:
                    assert net not in shortlist
                    if net != finalname:
                        shortlist[net] = finalname
                if debug:
                    print('3. shortlist = ' + str(shortlist))
                for net in netgroup:
                    sl_tmp.pop(net)
            if debug:
                print('4. shortlist = ' + str(shortlist))

        for item in contentl:
            if item.isMosInstance():
                wrltext += item.export_wrl(shortlist)
            elif item.isInstance():
                subckt = wholeSchematic.getSubckt(item.subcktname)
                if subckt is not None:
                    wrltext += item.export_wrl(subckt, shortlist)
        return wrltext


class MosSubckt(Subckt):
    def export_autogen(self, trimPySch, listofdefinedautogenfunctions,
                       project=None, force=False):
        """export_autogen(trimPySch) of MosSubckt checks in what parameter
        settings the subckt is used in the full 'trimPySch' and generates one
        for every flavour.
        """
        #global PROJset
        # print('export_autogen (MosSubckt): getParamsUsedSubckt(' +
        # str(self.getname()) + ')')
        print('getParamsUsedSubckt ' + str(self.getname()))

        parameterlist = trimPySch.getParamsUsedSubckt(self.getname())
        parameterlist.sort()
        print('export_autogen of Subckt: ' + str(self))
        print('with so many param sets: ' + str(len(parameterlist)))
        batchtext = ''

        newfunctions = []
        for parameters in parameterlist:
            layoutcellname = self.getrealname() + parameters.export_autogen()

            batchtext_, newfunction = self.export_autogen_header(
                    layoutcellname, self.design,
                    PROJset.get_str('radhard').lower() == 'true')
            batchtext += batchtext_
            newfunctions.append(newfunction)

            moswidth = float(parameters['W_'])
            moslength = float(parameters['L_'])
            mosmult = float(parameters['M_'])
            gateoverlap = 0.3e-6
            diffoverlap = 0.5e-6
            thickext = 0.5e-6
            wellext = 0.5e-6
            dopext = 0.2e-6
            dopgateext = 0.35e-6
            lowVthgateoverlap = 0.2e-6

#            //         B
#            //       +---+
#            //       |   |
#            // +-----+---+-----+
#            // |     |   |     |
#            // |  D  |   |  S  |
#            // |     |   |     |
#            // +-----0---+-----+
#            //       | G |
#            //       +---+

            batchtext += '\t// BOXES\n'
            if self.name.find('std') != -1:
                batchtext += ('\t\tLBox_New(newCell, tech2layer("thickox"), ' +
                              str(int(round((0 - diffoverlap - thickext) *
                                            1e9))) + ', ' +
                              str(int(round((0 - thickext) * 1e9))) + ', ' +
                              str(int(round((moslength + diffoverlap +
                                             thickext) * 1e9))) + ', ' +
                              str(int(round((moswidth + thickext)*1e9))) +
                              ');\n')

            if self.name.find('nmos') != -1:
                batchtext += ('\t\tLBox_New(newCell, tech2layer("nplus"), ' +
                              str(int(round((0 - diffoverlap - dopext) *
                                            1e9))) + ', ' +
                              str(int(round((0 - dopext) * 1e9))) + ', ' +
                              str(int(round((moslength + diffoverlap +
                                             dopext) * 1e9))) + ', ' +
                              str(int(round((moswidth + dopext) * 1e9))) +
                              ');\n')
                if self.name.find('lowVth') != -1:
                    batchtext += ('\t\tLBox_New(newCell, ' +
                                  'tech2layer("lowVth"), ' +
                                  str(int(round((0 - lowVthgateoverlap) *
                                                1e9))) + ', ' +
                                  str(int(round((0 - lowVthgateoverlap) *
                                                1e9))) + ', ' +
                                  str(int(round((moslength +
                                                 lowVthgateoverlap) *
                                                1e9))) + ', ' +
                                  str(int(round((moswidth +
                                                 lowVthgateoverlap) *
                                                1e9))) + ');\n')

            elif self.name.find('pmos') != -1:
                batchtext += ('\t\tLBox_New(newCell, tech2layer("pplus"), ' +
                              str(int(round((0-diffoverlap-dopext)*1e9))) +
                              ', ' + str(int(round((0-dopgateext)*1e9))) +
                              ', ' + str(int(round((
                                      moslength+diffoverlap+dopext)*1e9))) +
                              ', ' + str(int(round((
                                      moswidth+dopgateext)*1e9))) + ');\n')
                batchtext += ('\t\tLBox_New(newCell, tech2layer("nwell"), ' +
                              str(int(round((0-diffoverlap-wellext)*1e9))) +
                              ', ' + str(int(round((0-wellext)*1e9))) +
                              ', ' + str(int(round((moslength + diffoverlap +
                                                    wellext)*1e9))) +
                              ', ' + str(int(round((
                                      moswidth+wellext)*1e9))) + ');\n')
                if self.name.find('lowVth') != -1:
                    batchtext += ('\t\tLBox_New(newCell, ' +
                                  'tech2layer("lowVth"), ' +
                                  str(int(round((0 - lowVthgateoverlap) *
                                                1e9))) + ', ' +
                                  str(int(round((0 - lowVthgateoverlap) *
                                                1e9))) + ', ' +
                                  str(int(round((moslength +
                                                 lowVthgateoverlap) *
                                                1e9))) + ', ' +
                                  str(int(round((moswidth +
                                                 lowVthgateoverlap) *
                                                1e9))) + ');\n')

            batchtext += ('\t\tLBox_New(newCell, tech2layer("active"), ' +
                          str(int(round((0-diffoverlap)*1e9))) + ', ' +
                          str(int(round((0)*1e9))) + ', ' +
                          str(int(round((moslength+diffoverlap)*1e9))) +
                          ', ' + str(int(round((moswidth)*1e9))) + ');\n')

            batchtext += ('\t\tLBox_New(newCell, tech2layer("poly"), ' +
                          str(int(round((0)*1e9))) + ', ' +
                          str(int(round((0-gateoverlap)*1e9))) + ', ' +
                          str(int(round((moslength)*1e9))) + ', ' +
                          str(int(round((moswidth+gateoverlap)*1e9))) + ');\n')

            batchtext += '\n\t// PORTS\n'
            batchtext += ('\t\tnewPort = LPort_New(newCell, tech2layer("' +
                          'M1text"), "D", ' +
                          str(int(round((0-diffoverlap/2)*1e9))) + ', ' +
                          str(int(round((moswidth/2)*1e9))) + ', ' +
                          str(int(round((0-diffoverlap/2)*1e9))) + ', ' +
                          str(int(round((moswidth/2)*1e9))) + ');\n')
            batchtext += ('\t\tLPort_SetTextAlignment(newPort, ' +
                          'PORT_TEXT_MIDDLE | PORT_TEXT_CENTER);\n')
            batchtext += '\t\tLPort_SetTextSize(newPort, 250);\n\n'

            batchtext += ('\t\tnewPort = LPort_New(newCell, tech2layer("' +
                          'M1text"), "S", ' +
                          str(int(round((moslength+diffoverlap/2)*1e9))) +
                          ', ' + str(int(round((moswidth/2)*1e9))) + ', ' +
                          str(int(round((moslength+diffoverlap/2)*1e9))) +
                          ', ' + str(int(round((moswidth/2)*1e9))) + ');\n')
            batchtext += ('\t\tLPort_SetTextAlignment(newPort, ' +
                          'PORT_TEXT_MIDDLE | PORT_TEXT_CENTER);\n')
            batchtext += '\t\tLPort_SetTextSize(newPort, 250);\n\n'

            batchtext += ('\t\tnewPort = LPort_New(newCell, tech2layer("' +
                          'M1text"), "G", ' +
                          str(int(round((moslength/2)*1e9))) + ', ' +
                          str(int(round((0-gateoverlap/2)*1e9))) + ', ' +
                          str(int(round((moslength/2)*1e9))) + ', ' +
                          str(int(round((0-gateoverlap/2)*1e9))) + ');\n')
            batchtext += ('\t\tLPort_SetTextAlignment(newPort, ' +
                          'PORT_TEXT_MIDDLE | PORT_TEXT_CENTER);\n')
            batchtext += '\t\tLPort_SetTextSize(newPort, 250);\n\n'

            batchtext += ('\t\tnewPort = LPort_New(newCell, tech2layer("' +
                          'M1text"), "B", ' +
                          str(int(round((moslength/2)*1e9))) + ', ' +
                          str(int(round((moswidth+gateoverlap+(
                                  wellext-gateoverlap)/2)*1e9))) + ', ' +
                          str(int(round((moslength/2)*1e9))) + ', ' +
                          str(int(round((moswidth+gateoverlap+(
                                  wellext-gateoverlap)/2)*1e9))) + ');\n')
            batchtext += ('\t\tLPort_SetTextAlignment(newPort, ' +
                          'PORT_TEXT_MIDDLE | PORT_TEXT_CENTER);\n')
            batchtext += '\t\tLPort_SetTextSize(newPort, 250);\n\n'

            # let's not make a port saying M, just duplicate all

            # tchtext += ('\tnewPort = LPort_New(newCell, tech2layer("TEXT")' +
            #               ', "M = ' + str(int(round(mosmult))) + '", ' +
            #               str(int(round((moslength/2)*1e9))) + ', ' +
            #               str(int(round((moswidth+gateoverlap+(
            #                       wellext-gateoverlap)/2)*1e9))) + ', ' +
            #               str(int(round((moslength/2)*1e9))) + ', ' +
            #               str(int(round((moswidth+gateoverlap+(
            #                       wellext-gateoverlap)/2)*1e9))) + ');\n')
            # tchtext += ('\tLPort_SetTextAlignment(newPort, ' +
            #               'PORT_TEXT_MIDDLE | PORT_TEXT_CENTER);\n')
            # tchtext += '\tLPort_SetTextSize(newPort, 250);\n'
            # tchtext += '\t\n'
            if mosmult > 1:
                batchtext += '\tLSelection_SelectAll();\n'
                for m in range(int(mosmult)-1):
                    batchtext += '\tLSelection_Duplicate();\n'
                    pitch = moslength + .6e-6
                    batchtext += ('\tLSelection_Move(' +
                                  str(int(pitch*1e9))) + ', 0);\n'

            batchtext += self.export_autogen_footer()
        return batchtext, newfunctions


# class ResDevice(Spiceitem):
#    def __init__(self, resname, ports):
#        self.definition = ('ResDevice(' + repr(resname) + ', ' +
#                           repr(resmodel) + ', ' + repr(ports) + ', ' +
#                           repr(paramstring) + ', ' + repr(location) + ')')
#        self.name = resname            # string
#        # model is not always present
#        # self.resmodel = resmodel
#        # ports: list of strings
#        # (future: dict, key = port of subckt, value = higher level net name)
#        self.ports = ports
#        # params is not always present
#        # self.params = Params(paramstring)            # dict string : value
#        # location is not always present
#        # self.location = location        # string?
#
#    def getparams(self):
#        return self.params
#
#    def getshortports(self):
#        return self.ports
#
#    def export_spice(self):
#        netlist = self.name
#        for port in self.ports:
#            netlist += ' ' + port
#        netlist += ' ' + self.resmodel
#        netlist += ' ' + self.params.export_spice()
#        netlist += '\n'
#        return netlist
#

class Res_short(Spiceitem):
    def __init__(self, resname, resmodel, ports, paramstring,
                 location=None):
        self.definition = ('Res_short(' + repr(resname) + ', ' +
                           repr(resmodel) + ', ' + repr(ports) + ', ' +
                           repr(paramstring) + ', ' + repr(location) + ')')
        self.name = resname            # string
        self.resmodel = resmodel    # string
        # ports: list of strings
        # (future: dict, key = port of subckt, value = higher level net name)
        self.ports = ports
        self.params = Params(paramstring)            # dict string : value
        self.location = location        # string?

    def getparams(self):
        return self.params

    def getshortports(self):
        return self.ports

    def export_spice(self):
        netlist = self.name
        for port in self.ports:
            netlist += ' ' + port
        netlist += ' ' + self.resmodel
        netlist += ' ' + self.params.export_spice()
        netlist += '\n'
        return netlist


class Cap_parasitic(Spiceitem):
    def __init__(self, capname, capmodel, ports, paramstring,
                 location=None):
        self.definition = ('Cap_parasitic(' + repr(capname) + ', ' +
                           repr(capmodel) + ', ' + repr(ports) + ', ' +
                           repr(paramstring) + ', ' + repr(location) + ')')
        self.name = capname            # string
        self.capmodel = capmodel    # string
        # ports: list of strings
        # (future: dict, key = port of subckt, value = higher level net name)
        self.ports = ports
        self.params = Params(paramstring)            # dict string : value
        self.location = location        # string?

    def getparams(self):
        return self.params

    def export_spice(self):
        netlist = self.name
        for port in self.ports:
            netlist += ' ' + port
        netlist += ' ' + self.capmodel
        netlist += ' ' + self.params.export_spice()
        netlist += '\n'
        return netlist


class Instance(Spiceitem):
    def __init__(self, instname, subcktname, ports, paramstring,
                 location=None):
        self.definition = ('Instance(' + repr(instname) + ', ' +
                           repr(subcktname) + ', ' + repr(ports) + ', ' +
                           repr(paramstring) + ', ' + repr(location) + ')')
        self.name = instname            # string
        self.subcktname = subcktname    # string
        self.realsubcktname = subcktname    # string
        self.subcktdesign = None
        # ports: list of strings
        # (future: dict, key = port of subckt, value = higher level net name)
        self.ports = ports
        self.params = Params(paramstring)            # dict string : value
        self.location = location        # string?

    def duplicate(self):
        other = Instance(self.name, self.subcktname, self.ports, self.params,
                         self.location)
        other.realsubcktname = self.realsubcktname
        other.subcktdesign = self.subcktdesign
        return other

    def getsubcktname(self):
        return self.subcktname

    def getrealsubcktname(self):
        return self.realsubcktname

    def setrealsubcktname(self, realsubcktname):
        self.realsubcktname = realsubcktname

    def setsubcktdesign(self, subcktdesign):
        self.subcktdesign = subcktdesign

    def getparams(self):
        return self.params

    def export_spice(self):
        netlist = self.name
        for port in self.ports:
            netlist += ' ' + port
        netlist += ' ' + self.subcktname
        netlist += ' ' + self.params.export_spice()
        netlist += '\n'
        return netlist

    def export_autogen(self, listofdefinedautogenfunctions,
                       instparams=Params(), project=None):
        layoutcellname = self.realsubcktname + instparams.export_autogen()

        functionname = 'autogen_' + layoutcellname.replace('-', '_') + '_'
        if self.subcktdesign is not None:
            functionname += self.subcktdesign

        if functionname not in listofdefinedautogenfunctions:
            batchtext = ('//\t\tinstCell = ' + functionname + '();\n')
            batchtext += ('// The function "' + functionname + '" seems not ' +
                          'to exist. Check for ghost parameters (= Instance ' +
                          'parameters that are not cell parameters, mostly ' +
                          'these are the remnants of previously existing cell ' +
                          'parameters).\n')
            logging.warning('Instance parameters suggest the layout cell: ' +
                            layoutcellname + '.  Probably does not match ' +
                            'cell parameters.')
            return batchtext
        # else:
        batchtext = ('\t\tinstCell = ' + functionname + '();\n')

        batchtext += '\t\tinstRect =  LCell_GetMbb(instCell);\n'
        batchtext += ('\t\tshiftTrans = LTransform_Set_Ex99(coord.x - ' +
                      'instRect.x0, coord.y - instRect.y0, ' +
                      'nulTrans.orientation, nulTrans.magnification);\n')
        batchtext += ('\t\tinstance = LInstance_New_Ex99(newCell, instCell, ' +
                      'shiftTrans, LPoint_Set(1, 1), LPoint_Set(1, 1));\n')
        batchtext += ('\t\tLInstance_SetName(newCell, instance, "' +
                      self.name + '");\n')
        batchtext += ('\t\tcoord = LPoint_Set(coord.x + instRect.x1 -' +
                      ' instRect.x0, 0);\n')
        if self.subcktdesign in ['stdcells', 'logic']:
            batchtext += '\t\tif (strcmp(LCell_GetLibName( instCell, cellname4, MAX_CELL_NAME ), "' + self.subcktdesign + '") != 0 &&\n'
            batchtext += '\t\t\tstrcmp(LCell_GetLibName( instCell, cellname4, MAX_CELL_NAME ), "rh_' + self.subcktdesign + '") != 0) {\n'
            batchtext += '\t\t\tnewPort = LPort_New(newCell, tech2layer("Error Layer"), "stdcells/logic cell from wrong library", '
            batchtext += 'coord.x - (instRect.x1+instRect.x0)/2, coord.y - (instRect.y1+instRect.y0)/2, '
            batchtext += 'coord.x - (instRect.x1+instRect.x0)/2, coord.y - (instRect.y1+instRect.y0)/2);\n'
            batchtext += '\t\t\tLPort_SetTextAlignment(newPort, PORT_TEXT_MIDDLE | PORT_TEXT_CENTER | PORT_TEXT_VERTICAL);\n'
            batchtext += '\t\t\tLPort_SetTextSize(newPort, 2500);\n\t\t}\n'
        batchtext += ('\n')
        return batchtext

    def export_wrl(self, instancedSubckt, shortlist={}):
        wrltext = ''
        lenportslist = len(self.ports)
        lensubcktportslist = len(instancedSubckt.ports)
        if lenportslist != lensubcktportslist:
            spiceErrortext = ("Port mismatch: subckt '" +
                              instancedSubckt.name +
                              "' (" +
                              ', '.join(instancedSubckt.ports) + ')' +
                              " vs. instance '" + self.name + "' (" +
                              ', '.join(self.ports) + ')')
            raise SpiceError(spiceErrortext)
        infloopprot = 0
        for i in range(lenportslist):
            netname = self.ports[i]
            while netname in shortlist:
                infloopprot += 1
                if infloopprot > 1000:
                    break
                netname = shortlist[netname]

            wrltext += (netname + '\t' + self.subcktname + '\t' +
                        self.name + '\t' + instancedSubckt.ports[i] + '\n')
        return wrltext


class InterconnectInstance(Instance):
    def __init__(self, instname, subcktname, ports, paramstring,
                 location=None):
        self.definition = ('InterconnectInstance(' + repr(instname) + ', ' +
                           repr(subcktname) + ', ' + repr(ports) + ', ' +
                           repr(paramstring) + ', ' + repr(location) + ')')
        self.name = instname            # string
        self.subcktname = subcktname    # string
        self.realsubcktname = subcktname    # string
        self.subcktdesign = None
        # ports: list of strings
        # (future: dict, key = port of subckt, value = higher level net name)
        self.ports = ports
        self.params = Params(paramstring)            # dict string : value
        self.location = location        # string?

    def getparams(self):
        return self.params

    def getshortports(self):
        return self.ports[0:2]

    def export_spice(self):
        netlist = self.name
        for port in self.ports:
            netlist += ' ' + port
        netlist += ' ' + self.subcktname
        netlist += ' ' + self.params.export_spice()
        netlist += '\n'
        return netlist


class MosInstance(Instance):
    """MosInstance(self, name, model, d, g, s, b, w, l, m, subcktparams=None,
        location=None):
            self.definition = 'Subckt(' + repr(name) + ', ' + repr(model) +
            ', ' + repr(d) + ', ' + repr(g) + ', ' + repr(s) + ', ' + repr(b) +
            ', ' + repr(w) + ', ' + repr(l) + ', ' + repr(m) + ', ' +
            repr(subcktparams) + ', ' + repr(location) + ')'
        """
    def __init__(self, name, model, d, g, s, b, w, l, m, location=None):
        self.definition = ('MosInstance(' + repr(name) + ', ' + repr(model) +
                           ', ' + repr(d) + ', ' + repr(g) + ', ' + repr(s) +
                           ', ' + repr(b) + ', ' + repr(w) + ', ' + repr(l) +
                           ', ' + repr(m) + ', ' + ', ' + repr(location) + ')')
        self.name = name            # string

        self.subcktname = model    # string
        self.realsubcktname = model    # string
        # undo definition of design for a mos, should not be filtered (Rev.174)
        self.subcktdesign = None
        # if other issues pop up, consider to use the following if-tree
        # if model.startswith('std_'):
        #     self.subcktdesign = 'stdcells'
        # elif model.startswith('log_'):
        #     self.subcktdesign = 'logic'
        # else:
        #     self.subcktdesign = None

        # Params dict string : value
        self.params = Params('W_=' + w + ' L_=' + l + ' M_=' + m)

        self.model = model          # string
        self.d = d                  # string, net name
        self.g = g                  # string, net name
        self.s = s                  # string, net name
        self.b = b                  # string, net name
        self.ports = [self.d, self.g, self.s, self.b]
        self.w = w                  # string
        self.l = l                  # string
        self.m = m                  # string
#        self.inheritedparams = subcktparams     # dict string : value
        self.location = location

#    def setinheritedparams(self, params):
#        self.inheritedparams = params     # dict string : value

    def export_spice(self):
        netlist = self.name
        for port in self.ports:
            netlist += ' ' + port
        netlist += ' ' + self.model
        netlist += " W_=" + self.w + " L_=" + self.l + " M_=" + self.m
        netlist += '\n'
        return netlist

#    def export_autogen(self, instparams = Params(), project = None):
#        """Instance the mosinstance as if it are instances, in the subckt,
#        it will be changed into a collection of boxes and ports."""
#
#        batchtext = ''
#        return batchtext

    def export_wrl(self, shortlist={}):
        instancedMosports = ['D', 'G', 'S', 'B']
        wrltext = ''
        lenportslist = len(self.ports)
        lensubcktportslist = len(instancedMosports)
        assert lenportslist == lensubcktportslist
        for i in range(lenportslist):
            netname = self.ports[i]
            while netname in shortlist:
                netname = shortlist[netname]

            wrltext += (netname + '\tmos\t' + self.name + '\t' +
                        instancedMosports[i] + '\n')
        return wrltext


class Netname():
    def __init__(self, netname, PWR=['vdd', 'vcc'], GND=['vss', 'vee'],
                 NONAME='N_', BUSDEF='<>', warnsortcase=True):
        self.netname = netname
        self.PWR = PWR
        self.GND = GND
        self.NONAME = NONAME
        self.BUSDEF = BUSDEF
        self.warnsortcase = warnsortcase
        (self.corenetname, self.order) = self.analyzenet()

    def analyzenet(self):
        if self.isunnamed():
            return [self.NONAME, int(self.netname[len(self.NONAME):])]
        elif self.isbus():
            return self.analyzebus()
        else:
            return (self.netname, [])

    def analyzebus(self, end=None):
        if self.isbus(end):
            start = self.netname[:end].rfind(self.BUSDEF[0])
            thisdim = int(self.netname[
                    start+1:len(self.netname[:end])-1])
            (corenetname, higherdim) = self.analyzebus(start)
            return (corenetname, higherdim + [thisdim])
        else:
            return (self.netname[:end], [])

    # Sorting netnames goes like this:
    # Generally:
    #    case insensitive, but if only the case is different:
    #       Capitals first
    #       raises NetnameError if warnsortcase == True (in self OR other)
    #         checked in __eq__, which is always ran
    # named nets first
    # bus nets LSB first
    # unnamed nets:
    #   lowest number first

    def __eq__(self, other):
        # equality can only be the case if both are an instance of Netname
        if not isinstance(other, Netname):
            return False
        if self.netname == other.netname:
            return True
        if ((self.warnsortcase or other.warnsortcase) and
                self.order == other.order and
                self.corenetname.lower() == other.corenetname.lower() and
                self.corenetname != other.corenetname):
            raise NetnameError('Netnames compared with only case ' +
                               'differences.  High probability of a ' +
                               'mixed use in schematic, which is confusing.')
        return False

    def __lt__(self, other):
        # Netname is uncomparable with other types
        if not isinstance(other, Netname):
            raise TypeError("'<' not supported between instances of '" +
                            str(type(self).__name__) + "' and '" +
                            str(type(other).__name__) + "'")
        # if equal, not lower than
        if self == other:
            return False
        # IT IS NOT EQUAL

        # one unnamed net
        if self.isunnamed() ^ other.isunnamed():
            return other.isunnamed()
        else:
            # both unnamed nets
            if self.isunnamed():  # and thus also other isunnamed
                if self.corenetname != other.corenetname:
                    # means self.NONAME != other.NONAME
                    return self.corenetname < other.corenetname
                else:
                    # typical situation
                    return self.order < other.order
            # both named nets
            else:
                # different corenetname (case-insensitive)
                if self.corenetname.lower() != other.corenetname.lower():
                    return self.corenetname.lower() < other.corenetname.lower()
                # equal corenetname, but different case:
                elif self.corenetname != other.corenetname:
                    return self.corenetname < other.corenetname
                # only order difference, so it is a bus
                elif self.order != other.order:
                    return self.order < other.order
                # can only be the case if self.BUSDEF != other.BUSDEF
                else:
                    return self.netname < other.netname

    def __ne__(self, other):
        return not self == other

    def __gt__(self, other):
        return other < self

    def __ge__(self, other):
        return not self < other

    def __le__(self, other):
        return not other < self

    def __str__(self):
        return self.netname

    def __repr__(self):
        return (type(self).__module__ + '.' + type(self).__name__ + "('" +
                self.netname + "')")

    def __format__(self, formatstring):
        return self.netname.__format__(formatstring)  # as string

    def __len__(self):
        return len(self.netname)

    def __hash__(self):
        return hash(self.netname)

    def isunnamed(self):
        """ returns True if self.netname starts with self.NONAME, followed by
        decimals [0-9 ]exclusively, False otherwise."""
        if self.netname.startswith(self.NONAME):
            return self.netname[len(self.NONAME):].isdecimal()
        return False

    def ispower(self):
        """returns 1/-1 if the netname suggest being a power/gnd, 0 otherwise.
        return -1:
            Case insensitive, contains self.GND in self.netname.
        return 1:
            Case insensitive, contains self.PWR in self.netname.
        returns 0:
            contains none of the above or
            some of both groups.

        Both 1 and -1 act as True in if x.ispower()
        """
        result = 0  # default
        for gnd in self.GND:
            if gnd.lower() in self.netname.lower():
                result = -1  # keep temporarily and check no PWR to be found
                break

        for pwr in self.PWR:
            if pwr.lower() in self.netname.lower():
                if result == 0:  # no GND found yet
                    return 1
                else:            # GND already found
                    return 0

        return result  # result == default or tmp

    def isbus(self, end=None):
        """only returns True if the self.netname[:end] format is like this:
            'whatever<#>', with '<>' being self.BUSDEF and
                           # being a positive integer.
            whatever can be a bus itself, making self being a part of a
            multidimensional bus.
        """
        if self.netname[:end].endswith(self.BUSDEF[1]):
            start = self.netname[:end].rfind(self.BUSDEF[0])
            if start == -1:
                return False
            return self.netname[start+1:len(self.netname[:end])-1].isdecimal()
        return False


class Address():
    """an address in chematic is defined as a string of the following format:
    <topsubcktname>/
    [ [<Instancename>/]
      [<Instancename>/]
      [<Instancename>/]]
    <netname> (can be empty '' for instance definition)
    Addressing other than instance or net in instance is not supported now."""
    def __init__(self, definition):
        if not isinstance(definition, str):
            raise AddressError("Address definition should be string")
        self.definition = str(definition)
        self.hierarchy = self.definition.split('/')
        if len(self.hierarchy) < 2:
            raise AddressError("Address should at least contain one '/'")
        for instcall in self.hierarchy[1:-1]:
            if instcall[0].lower() != 'x':
                raise AddressError("Instance calls should start with X.")

        self.top = self.hierarchy[0]
        self.netname = Netname(self.hierarchy[-1])

    def __str__(self):
        return self.definition

    def __repr__(self):
        return (type(self).__module__ + '.' + type(self).__name__ + "('" +
                self.definition + "')")

    def __format__(self, formatstring):
        return self.definition.__format__(formatstring)

    def __add__(self, other):
        if not isinstance(other, str):
            raise AddressError("Address definition should be string")

        return Address(self.definition + other)

    def __sub__(self, other):
        if not isinstance(other, int):
            raise AddressError('Substraction removes int amount of hierarchy' +
                               ' levels')
        if other < 0:
            raise AddressError('Substraction removes int amount of hierarchy' +
                               ' levels, should be a positive number')
        if other > len(self.hierarchy):
            raise AddressError('Substraction removes int amount of hierarchy' +
                               ' levels, should be less than hierarchy depth')
        if other == 0:
            return Address(self.definition)
        if (self.definition[-1] == '/'):
            # no net defined in this address
            return Address('/'.join(self.hierarchy[:-other] + '/'))
        else:
            # address is net
            newhier = self.hierarchy[:-1]
            newhier.append('')
            if other == 1:
                return Address('/'.join(newhier))
            else:
                return Address('/'.join(self.hierarchy[:-(other-1)] + '/'))

    def __eq__(self, other):
        # equality can only be the case if both are an instance of Address
        if not isinstance(other, Address):
            return False
        return self.definition == other.definition

    def __lt__(self, other):
        # Address is not comparable with other types
        if not isinstance(other, Address):
            raise TypeError("'<' not supported between instances of '" +
                            str(type(self).__name__) + "' and '" +
                            str(type(other).__name__) + "'")
        # if equal, not lower than
        if self == other:
            return False
        # IT IS NOT EQUAL

        if len(self.hierarchy) != len(other.hierarchy):
            return len(self.hierarchy) < len(other.hierarchy)
        else:
            return self.definition < other.definition

    def __ne__(self, other):
        return not self == other

    def __gt__(self, other):
        return other < self

    def __ge__(self, other):
        return not self < other

    def __le__(self, other):
        return not other < self

    def __hash__(self):
        return hash(self.definition)

    def _subcktname_core(self, pysch):
        # TODO: is more a method for PySchematic than for Address
        pass

    def isnet(self):
        return len(self.netname) > 0

    def isvalid(self, pysch):
        # TODO: is more a method for PySchematic than for Address
        subcktnames = []
        for x in pysch.subckts:
            subcktnames.append(x.name)
        if self.top not in subcktnames:
            print('nv1')
            return False

        subcktname = self.top

        for instcall in self.hierarchy[1:-1]:
            subckt = pysch.getSubckt(subcktname)
            if not(subckt.hasContent(instcall)):
                print('nv2')
                return False

            item = subckt.getcontent(instcall)
            subcktname = item.getsubcktname()

        if self.isnet():
            subckt = pysch.getSubckt(subcktname)

            # print('self.netname: ' + self.netname)
            # print('subckt: ' + str(subckt))
            # print('subckt.ports: ' + str(subckt.ports))
            if str(self.netname) in subckt.ports:
                return True
            for item in subckt.content:
                # print('item.name: ' + str(item.name))
                # print('item.ports: ' + str(item.ports))
                if str(self.netname) in item.ports:
                    return True
            print('nv3')
            return False

        return True

    def subcktname(self, pysch):
        # TODO: is more a method for PySchematic than for Address
        if not self.isvalid(pysch):
            print('scn: not Valid')
            return None

        subcktname = self.top

        for instcall in self.hierarchy[1:-1]:
            subckt = pysch.getSubckt(subcktname)
            if not(subckt.hasContent(instcall)):
                return False

            item = subckt.getcontent(instcall)
            subcktname = item.getsubcktname()
        return subcktname

    def expandnetname(self, pysch, short=False):
        prevsize = 0
        tmpset = set([self])
        tmpset |= set([self.highestnetname(pysch)])

        size = len(tmpset)
        while prevsize != size:
            prevsize = size
            # print('size: ' + str(size))
            tmplist = list(tmpset)
            # print('tmplist:' + '\n        '.join([str(x) for x in tmplist]))

            for i, addr in enumerate(tmplist):
                # print('for: ' + str(i) + ' of ' + str(size))
                if short:
                    tmpset |= set([addr.highestnetname(pysch)])
                # print('  addr: ' + str(addr))
                fanout = addr.fanout(pysch, short)
                # print('    fanout: ' + '\n            '.join([str(x) for x in
                #                                              fanout]))
                tmpset |= set(fanout)
                # print('    tmpset: ' + '\n            '.join([str(x) for x in
                #                                              tmpset]))
            size = len(tmpset)

        tmplist = list(tmpset)
        tmplist.sort()
        return tmplist

    def highestnetname(self, pysch):
        if not (self.isvalid(pysch) and self.isnet()):
            print('hnn: not Valid')
            return None

        # highestnetname cannot be higher than subckt/net
        if len(self.hierarchy) == 2:
            return self

        subckt = pysch.getSubckt(self.subcktname(pysch))
        if str(self.netname) not in subckt.ports:
            return Address(self.definition)
        portnr = subckt.ports.index(str(self.netname))
        # print(self.netname + ' = port n° ' + str(portnr) + ' of ' +
        #       self.subcktname(pysch))
        tmp = Address('/'.join(self.hierarchy[:-2])+'/')
        highersubckt = pysch.getSubckt(tmp.subcktname(pysch))
        # print('highersubckt: ' + str(highersubckt))
        # print('highersubckt.content:')
        # print ('self.hierarchy[-2]: ' + self.hierarchy[-2])
        for x in highersubckt.content:
            if x.name == self.hierarchy[-2]:
                # print('>>> ' + x.name + ' <<<')
                break
        else:
            raise AddressError('instance not Found.???')
            # print('    ' + x.name)
        # print('y.ports: ' + str(y.ports))
        # print(x.name + '.ports[portnr]: ' + str(x.ports[portnr]))
        newhier = self.hierarchy[:-2]
        newhier.append(x.ports[portnr])
        # print('/'.join(newhier))
        return Address('/'.join(newhier)).highestnetname(pysch)

    def fanout(self, pysch, short=False):
        if not (self.isvalid(pysch) and self.isnet()):
            print('fo: not Valid')
            return None

        # print('self.netname: ' + self.netname)
        subckt = pysch.getSubckt(self.subcktname(pysch))
        # print('fanout: ')

        fanout = []
        for x in subckt.content:
            assert isinstance(x, Spiceitem)
#            if x.isMosInstance():
#                if str(self.netname) in x.ports:
#                    portnr = x.ports.index(str(self.netname))
#                    thisone = x.name + '/' + ['D', 'G', 'S' 'B'][portnr]
#                    fanout.append(Address('/'.join(self.hierarchy[:-1]) +
#                                          '/' + thisone))
#            el
            if x.isInstance():
                if str(self.netname) in x.ports:
                    portnr = x.ports.index(str(self.netname))
                    # print('vars(x) :' + str(vars(x)))
                    subckt = pysch.getSubckt(x.subcktname)
                    if subckt is not None:
                        thisone = x.name + '/' + subckt.ports[portnr]
                        # print(thisone)
                        fanout.append(Address('/'.join(self.hierarchy[:-1]) +
                                              '/' + thisone))
            elif x.isRes_short():
                if short and str(self.netname) in x.ports:
                    # print('Res_short:')
                    for p in x.ports:
                        thisone = (self - 1) + p
                        # print(thisone)
                        fanout.append(thisone)
            elif x.isDevice():
                # more depth is not needed
                pass
            elif x.isCap_parasitic():
                # more depth is not needed
                pass
            else:
                logging.warning('unsupported content type: ' + x.definition)
                #raise AddressError('unsupported content type')
        return fanout


class PySchematic():
    """class PySchematic keeps all accessible subckts in it.
     New subckts can be added or removed in a similar syntax as working with
     python sets."""

    def __init__(self, source=None):
        """Upon creation you can add the source of the spice definition"""
        self.setsource(source)
        self.subckts = set()
        self.toplevel = Subckt(None, [], [])
        self.cache_paramsubckt = {}
        self.cache_countsubckt = {}

    def __repr__(self):
        subsrepr = 'set('
        if len(self.subckts) < 11:
            for i in self.subckts:
                subsrepr += '\n' + str(i)
        else:
            n = 0
            for i in self.subckts:
                n += 1
                if n > 10:
                    break
                subsrepr += '\n' + str(i)
            subsrepr += ('\n... (' + str(len(self.subckts)-10) +
                         ' Subckts more)   )   ')
        return 'PySchematic(source = %r, subckts = %s)' % (self.source,
                                                           subsrepr)

    def __len__(self):
        return len(self.subckts)

    def setsource(self, source):
        if source is None:
            self.source = ''
        else:
            self.source = source

    # def addsource(self, source):
    #     self.source += ';' + source

    def getsource(self):
        return self.source

    def add(self, subckt):
        self.subckts.add(subckt)

    def addinstdev2top(self, instdev):
        self.toplevel.add(instdev)

    def addparams2top(self, newparams):
        self.toplevel.addparams(newparams)

    def remove(self, subckt):
        self.subckts.remove(subckt)

    def hasSubckt(self, subcktname):
        for subckt in self.subckts:
            if subckt.hasname(subcktname):
                return True
        return False

    def getSubckt(self, subcktname):
        for subckt in self.subckts:
            if subckt.hasname(subcktname):
                return subckt

    def check(self, cellname=None, allow_std_subckt_notfound=False, fullcheck=True):
        errors = ''
        skipportcheck = []
        # TODO: check for ghost parameters (both ways)
        
        # trim of all subckts we are not interested in because they are not
        # instanced at any level down from cellname

        if cellname is None:
            PySch2check = self
        else:
            PySch2check = self.trim(cellname)
        # check for existence of all subckts as they are expected in LTB
        # S-Edit probably never makes this mistake, but after tweaking...
        # For simulation it might be ok, but it would overcomplicate LTB.
        allsubcktnames = []
        for subckt in PySch2check.subckts:
            allsubcktnames.append(subckt.name)

        notfound = []
        for subckt in PySch2check.subckts:
            if subckt.name in DEF_SUBCKT:
                # Do not crawl deeper than the device level, even if in
                # v2.0 file a deeper subckt exists, skip this subckt and ...
                continue
                # ... with the next
            for content in subckt.content:
                if content.isInstance():
                    instancedsubcktname = content.getsubcktname()
                    if instancedsubcktname not in allsubcktnames:
                        if not allow_std_subckt_notfound:
                            notfound.append(instancedsubcktname)
                        else:
                            if instancedsubcktname not in DEF_SUBCKT:
                                notfound.append(instancedsubcktname)
        if len(notfound) > 0:
            error = 'undefined subckt(s): ' + ', '.join(notfound) + '\n'
            note = 'Take note of the fact that LTB is case-sensitive.\n'
            hint = ("Hint: Check for the cell definition in the project's " +
                    "'sourceincludetech' or 'sourceincludeproject' file.\n" +
                    'Workaround hint: May the FORCE be with you. (Keep in ' +
                    'mind that doing so might postpone your problems to later.\n')
            if fullcheck:
                errors += error
            else: 
                raise UndefSubcktError( error + note + hint )
        print(errors)
        print('Continuing')
        # check that ports match between instance and subcktdef.
        # S-Edit probably never makes this mistake, but after tweaking...
        portnotok = []
        for subckt in PySch2check.subckts:
            if subckt.name not in notfound:
                if subckt.name in DEF_SUBCKT:
                    # Do not crawl deeper than the device level, even if in
                    # v2.0 file a deeper subckt exists, skip this subckt and ...
                    continue
                    # ... with the next
                for content in subckt.content:
                    if content.isInstance():
                        if content.getsubcktname() in notfound:
                            continue
                        instancedsubckt = PySch2check.getSubckt(
                                content.getsubcktname())
                        if (instancedsubckt is None and
                                allow_std_subckt_notfound and
                                content.getsubcktname() in DEF_SUBCKT):
                            continue
                        if len(instancedsubckt.ports) != len(content.ports):
                            error = (subckt.name + '.' + content.name + '(' +
                                     ', '.join(content.ports) + ')\n\t' +
                                     instancedsubckt.name + '(' +
                                     ', '.join(instancedsubckt.ports) + ')\n')
                            portnotok.append(error)
                            # assert False
        if len(portnotok) > 0:
            error = 'port mismatch: \n' + ', '.join(portnotok)
            if fullcheck:
                errors += error
            else:
                raise PortMismatchError(error)
            
        if len(errors) == 0:
            return None
        else:
            return errors
        

    def evalParam(self, expression, subcktparams=None):
        if subcktparams is None:
            subcktparams = Params()
        toplevelparams = self.toplevel.getparams()
        valuefound = False
        calcinfo = {}
        while not valuefound:
            try:
                valuefound = True
                calcresult = general.calc(expression, namevaluedict=calcinfo,
                                          verbose=0)
                assert len(calcresult) == 1
                result = calcresult[0]
            except general.CalcError as e:
                valuefound = False
                eargs = e.args[0]
                # print(eargs[1])
                assert eargs[0] == '?'
                # is it just a value?
                if Params({'tmp': eargs[1]}).isNumValUnit('tmp'):
                    (val, unit) = Params({'tmp': eargs[1]}).strValUnit('tmp')
                    calcinfo[eargs[1]] = str(val)
                # unknown name found in subckt params?
                elif eargs[1] in subcktparams:
                    calcinfo[eargs[1]] = subcktparams[eargs[1]]
                    if eargs[1] == subcktparams[eargs[1]]:
                        valuefound = True
                        result = expression
                # in top-level params?
                elif eargs[1] in toplevelparams:
                    calcinfo[eargs[1]] = toplevelparams[eargs[1]]
                else:
                    # raise SpiceError('Parameter ' + eargs[1] +
                    #                  ' not found as parameter for ' +
                    #                  subcktname +
                    #                  ' nor as toplevel parameter')
                    warning = ('Given parameter not a numerical value or a ' +
                               'toplevel parameter.')
                    warning += ('\nevalParam(' + repr(expression) + ', ' +
                                repr(subcktparams)+'), eargs[1]=' + repr(eargs[1]))
                    raise SpiceError(warning)
            except Exception:
                print('self.evalParam('+repr(expression)+', '+repr(subcktparams)+')')
                raise
        return result

    def countSubcktParamsInCell(self, subckt, params, mastercellname,
                                mastercellparams, tab='', path=None):
        verbose = 0
        
        if path is None:
            path = mastercellname
            

        ##TODO: fix nested parameters                         
        number = 0
        subcktname = subckt.getname()
        
        
        if verbose >0:
            print(tab, end='')
            print('countSubcktParamsInCell(self, ', end='')
            print(subckt.getname(), end=', ')
            print(params, end=', ')
            print(mastercellname, end=', ')
            print(mastercellparams, end=", '")
            print(tab, end="')\n")

        if params is not None:
            paramsAGstr = params.export_autogen()
            # print('paramsAGstr:' + paramsAGstr)
            mastercellparamsAGstr = mastercellparams.export_autogen()
            allparams = Params(self.toplevel.getparams())
            # print('allparams', end=': ')
            # print(allparams)
            # print(allparams['S'])
            # print('mastercellparams', end=': ')
            # print(mastercellparams)
            allparams.add(mastercellparams)
        else:
            paramsAGstr = None
            mastercellparamsAGstr = None
            
        if (subcktname, paramsAGstr, mastercellname, mastercellparamsAGstr) in self.cache_countsubckt:
            if (verbose > 1):
                print('cache')
            return self.cache_countsubckt[(subcktname, paramsAGstr, mastercellname, mastercellparamsAGstr)]

        for mastercell in self.subckts:
            if mastercell.hasname(mastercellname):
                # print(mastercellname)
                break
        else:
            raise SpiceError("Subcircuit '" + mastercellname + "' not found.")

        # design = subckt.getdesign()
        for content in mastercell.content:
            if content.isInstance():
                subcell = content.getsubcktname()
                if (verbose > 1):
                    print(tab + ' ' + content.name, end='')
                if params is not None:
                    subcellparams = Params(content.getparams())

                    for param in subcellparams:

                        if subcellparams.isNumeric(param):
                            pass
                            if (verbose > 1):
                                print('numeric')
                        else:
                            if (verbose > 1):
                                print(' --is cell--', end=' ')
                                print(param, end=': ')
                                print(subcellparams[param], end='  ')
                                print('X', end=' ')
                                print ('(mastercellparams: ', end='')
                                print(mastercellparams)

                            try:
                                calcresult = self.evalParam(subcellparams[param], mastercellparams)
                            except:
                                print(path)
                                raise
                            if (verbose > 1):
                                print(calcresult)
                            #assert len(calcresult) == 1
                            subcellparams[param] = str(calcresult)
                            if (verbose > 1):
                                print(param, end=': ')
                                print(subcellparams[param], end='  ')
                                print('ok?')
                else:
                    subcellparams = None
                
                if subcell == subcktname:
                    if params is not None:
                        subcellparamsAGstr = subcellparams.export_autogen()
                    else:
                        subcellparamsAGstr = None
                    # print('paramsAGstr: ' + str(paramsAGstr))
                    #print('subcellparamsAGstr:  ' + str(subcellparamsAGstr))
                    if subcellparamsAGstr == paramsAGstr:
                        number += 1
                        #print(tab + '.')
                    else:
                        pass
                        #print(tab + paramsAGstr + '!=' + subcellparamsAGstr)
                else:
                    #print(tab + content.name)
                    try:
                        number += self.countSubcktParamsInCell(
                                subckt, params, subcell, subcellparams,
                                tab + '  ', path + '\\' + content.name)
                    except SpiceError as e:
                        print(e)
                        number += 0

        self.cache_countsubckt[(subcktname, paramsAGstr, mastercellname, mastercellparamsAGstr)] = number
        return number

    def getParamsUsedSubckt(self, subcktname):
        # print('getParamsUsedSubckt ' + str(subcktname))

        # first look in cache
        if subcktname in self.cache_paramsubckt:
            # print('cache')
            return self.cache_paramsubckt[subcktname]

        for subckt in self.subckts:
            if subckt.hasname(subcktname):
                break
        else:
            raise SpiceError("Subcircuit '" + subcktname + "' not found.")
        initsubckt = subckt

        initsubcktparams = initsubckt.getparams()

        paramnames = list(initsubcktparams.keys())

        if len(paramnames) == 0:
            self.cache_paramsubckt[subcktname] = [Params()]
            return [Params()]
        else:
            listofparams = []

        toplevelparams = self.toplevel.getparams()
        dfltparams = Params()

        # nonvalueparamnames = []
        origundefinedparamnames = paramnames
        # FIRST: define what is the default parameter value for the subckt,
        # in case it is somewhere (at whatever level) not defined.
        for paramname in paramnames:
            expression = paramname
            valuefound = False
            calcinfo = {}
            while not valuefound:
                try:
                    valuefound = True
                    # print('1st: general.calc('  +expression + ',' +
                    #       str(calcinfo) + ')')
                    calcresult = general.calc(expression,
                                              namevaluedict=calcinfo,
                                              verbose=0)
                    assert len(calcresult) == 1
                    result = calcresult[0]
                except general.CalcError as e:
                    valuefound = False
                    eargs = e.args[0]
                    # print(eargs[1])
                    assert eargs[0] == '?'
                    # is eargs[1] just a string representation of a value?
                    if Params({'tmp': eargs[1]}).isNumValUnit('tmp'):
                        (val, unit) = Params(
                                {'tmp': eargs[1]}).strValUnit('tmp')
                        calcinfo[eargs[1]] = str(val)
                    # is eargs[1] a name found in subckt params?
                    elif eargs[1] in initsubcktparams:
                        calcinfo[eargs[1]] = initsubcktparams[eargs[1]]
                        if eargs[1] == initsubcktparams[eargs[1]]:
                            logging.debug('Investigate when this happens.')
                            valuefound = True
                            result = expression
                    # in eargs[1] one of the top-level params?
                    elif eargs[1] in toplevelparams:
                        calcinfo[eargs[1]] = toplevelparams[eargs[1]]
                    else:
                        # raise SpiceError('Parameter ' + eargs[1] +
                        #                  ' not found as parameter for ' +
                        #                  subcktname +
                        #                  ' nor as toplevel parameter')
                        warning = ("Subcircuit '" + subcktname +
                                   "' has parameter '" + paramname +
                                   "' with not-so-sweet default value (" +
                                   eargs[1] + "). This causes issues when " +
                                   "this cell is instanced without specify" +
                                   "ing this parameter value.")
                        print(warning)
                        logging.warning(warning)
                        result = None
                        valuefound = True
                except Exception:
                    raise
            # print(paramname + ': ' + str(result))
            if result is None:
                dfltparams[paramname] = (None, None.__class__)
            else:
                dfltparams[paramname] = str(result)
                if result == 0:
                    pass  # param with value is so far no problem, I guess

            # following code covered in try loop above, I think
            #
            # if not dfltparams.isNumeric(paramname):
            #    # is the parameter value a parameter name at top level?
            #    if dfltparams[paramname] in toplevelparams:
            #        dfltparams[paramname] = (
            #                toplevelparams[dfltparams[paramname]])
            #    else:
            #        warning = ("Subcircuit '" + subcktname +
            #                   "' has parameter '" + paramname +
            #                   "' with not-so-sweet default value (" +
            #                   dfltparams[paramname] + "). This causes " +
            #                   "issues when this cell is instanced without " +
            #                   "specifying this parameter value.")
            #        print(warning)
            #        #dfltparams[paramname] = None
            #        #raise SpiceError(warning)
            #        #nonvalueparamnames.append(paramname)
            #        #break

        # SECOND: deep into all subckts, look for instances of this initsubckt
        for subckt in self.subckts:
            if subckt.name in DEF_SUBCKT:
                # Do not crawl deeper than the device level, even if in
                # v2.0 file a deeper subckt exists, skip this subckt and ...
                continue
                # ... with the next
            for inst in subckt.content:
                if inst.isInstance() and (
                        inst.getsubcktname() == initsubckt.getname()):
                    subcktparams = subckt.getparams()
                    # deeperparamnamestranslate = []
                    # deeperparamnames = []
                    # print('>')
                    deeperparamvalues = self.getParamsUsedSubckt(
                            subckt.getname())
                    # print('<')
                    for pv in deeperparamvalues:
                        undefinedparamnames = list(origundefinedparamnames)
                        newparams = Params(dfltparams)
                        # print("We just immediately dive deeper for this to" +
                        #       " catch all possible params for this instance")
                        for paramname in paramnames:
                            instparams = inst.getparams()
                            # print('instparams: ' + str(instparams))
                            if paramname not in instparams:
                                for k in instparams:
                                    if k.upper() == paramname.upper():
                                        error = ("Subcircuit '" + subcktname +
                                                 "' has parameter '" +
                                                 paramname +
                                                 "' and is used by '" +
                                                 subckt.name + "' using a " +
                                                 "different case for that " +
                                                 "parameter. Please fix " +
                                                 "netlist.")
                                        raise SpiceError(error)
                                # this will be the default value (simple)
                                undefinedparamnames.remove(paramname)
                                # but then it has to be a numeric value!!
                                if not newparams.isNumeric(paramname):
                                    error = ("Subcircuit '" + subcktname +
                                             "' has parameter '" + paramname +
                                             "' with not-so-sweet default " +
                                             "value (" +
                                             str(dfltparams[paramname]) +
                                             "). This causes issues when " +
                                             "this cell is instanced " +
                                             "without specifying this " +
                                             "parameter value. Like now in " +
                                             subckt.name + '.' + inst.name +
                                             '.')
                                    raise SpiceError(error)
                                # but encapsulate it in a list
                                newparams[paramname] = (
                                        [newparams[paramname]], list)
                            else:
                                # is it defined in the calling of the instace
                                expression = instparams[paramname]
                                valuefound = False
                                calcinfo = {}
                                while not valuefound:
                                    try:
                                        valuefound = True
                                        # print('2nd: general.calc(' +
                                        #       expression + ',' +
                                        #       str(calcinfo) + ')')
                                        calcresult = general.calc(
                                                expression,
                                                namevaluedict=calcinfo,
                                                verbose=0)
                                    except general.CalcError as e:
                                        valuefound = False
                                        eargs = e.args[0]
                                        # print(eargs[1])
                                        assert eargs[0] == '?'
                                        # is it just a value?
                                        if Params({'tmp': eargs[1]}
                                                  ).isNumValExp('tmp'):
                                            (val, unit) = Params(
                                                    {'tmp': eargs[1]}
                                                    ).numValExp('tmp')
                                            calcinfo[eargs[1]] = str(val)
                                        elif Params({'tmp': eargs[1]}
                                                    ).isNumValUnit('tmp'):
                                            (val, unit) = Params(
                                                    {'tmp': eargs[1]}
                                                    ).strValUnit('tmp')
                                            calcinfo[eargs[1]] = str(val)
                                        # unknown name found in subckt params?
                                        elif eargs[1] in subcktparams:
                                            calcinfo[eargs[1]] = pv[eargs[1]]
                                        # in top-level params?
                                        elif eargs[1] in toplevelparams:
                                            calcinfo[eargs[1]] = (
                                                    toplevelparams[eargs[1]])
                                        else:
                                            raise SpiceError(
                                                    'Parameter ' + eargs[1] +
                                                    ' not found as parameter' +
                                                    ' for ' + subcktname +
                                                    ' nor as toplevel ' +
                                                    'parameter')
                                    except Exception:
                                        raise
                                newparams[paramname] = calcresult, list
                                undefinedparamnames.remove(paramname)
                        assert len(undefinedparamnames) == 0
                        arraysize = []
                        product = [1]
                        paramnames = list(newparams.keys())
                        for paramname in paramnames:
                            arraysize.append(len(newparams[paramname]))
                            product.append(product[-1] * len(
                                    newparams[paramname]))

                        for element in range(product[-1]):
                            singlesetofparams = Params(dfltparams)
                            for pointer in range(len(paramnames)):
                                paramname = paramnames[pointer]
                                index = (int(element / product[pointer]) %
                                         arraysize[pointer])
                                singlesetofparams[paramname] = str(
                                        newparams[paramname][index])
                            if singlesetofparams not in listofparams:
                                listofparams.append(singlesetofparams)

        if len(listofparams) == 0:
            listofparams.append(dfltparams)
        for p in listofparams:
            if '0' in p.values():
                pass  # no problem, I guess
            if None in p.values():
                warning = ("Subcircuit '" + subcktname + "' has parameter '" +
                           paramname + "' with not-so-sweet default value " +
                           "and not a better defined value (not instanced " +
                           "somewhere else) Hint: check case of subcktdef " +
                           "with case of instance.")
                print(warning)
                raise SpiceError(warning)
        self.cache_paramsubckt[subcktname] = sorted(listofparams)
        return sorted(listofparams)

    def subcktdepth(self, subcktname=None):
        """subcktdepth([subcktname = None]) returns the lowest level subckt
     depth for all subckts listed in this class (PySchematic.subckts) or for
     the specified subckt with name subcktname and all lower-level instances
     that are listed in PySchematic.subckts.
     returns a dictionary
        dict[subckt]:level
        level 0 means top level
        a negative level number reflects the (lowest) instance depth
        a positive number should not exist in the dictionary values() list
     """
        # temporarily:
        # all levels with a positive number reflect subckts that are
        # instanciated in another cell in depth somewhere.
        # those that are not instanciated somewhere else stay at level 0 and
        # are being considered (one of the) top levels.
        # all cells that receive a positive value temporarily will be
        # overwritten later with a negative value because they exist as an
        # instance of at least one of the other cells.

        depth = {}
        if subcktname is None:
            # in this case, return dict containing all subckts, before
            # finalize, all cells will be in depth, containing 0 or more.
            for subckt in self.subckts:
                level = -1
                depth[subckt] = depth.get(subckt, level) + 1
        else:
            # in this case, return dict with subckt 'subcktname' and all
            # lower-level cells, before finalize, depth contains only subckt
            # 'subcktname'
            for subckt in self.subckts:
                if subckt.hasname(subcktname):
                    level = -1
                    depth[subckt] = depth.get(subckt, level) + 1
        if len(depth) == 0:
            raise SpiceError('Subckt ' + subcktname + ' not found in ' +
                             self.source)

        # selected cell with subcktname (or all) are mentioned in depth
        # dictionary and receive value 0.

        namesofsubcktsdepth = set(
                [subckt.getname() for subckt in depth.keys()])
        if (len(depth) != len(namesofsubcktsdepth)):
            raise SpiceError('Double definition of subckt(s)')

        # find out what the top-level cells are in the design, those stay at
        # level 0.  cells that exist in depth and are instanced in another
        # cell get positive values
        for subckt in depth:
            for item in subckt.content:
                if item.isInstance() and (
                        item.getsubcktname() in namesofsubcktsdepth):
                    addone = [subckt for subckt in depth.keys()
                              if subckt.getname() == item.getsubcktname()]
                    assert len(addone) == 1, ("addone should contain a " +
                                              "single subckt")
                    depth[addone[0]] += 1

        # finalize:
        # now all levels will get their final value.  start at level 0 (1-1)
        level = 1

        while True:
            level -= 1
            # investigate all subckts that are on the actual level
            investigationlist = [subckt for subckt in depth.keys()
                                 if depth[subckt] == level]
            if len(investigationlist) == 0:
                break
            for subckt in investigationlist:
                for item in subckt.content:
                    if item.isInstance():
                        for asubckt in self.subckts:
                            if item.getsubcktname() == asubckt.getname():
                                # children of the actual subckt get the level
                                # number of actual -1, that cell will of course
                                # be investigated in the next round
                                depth[asubckt] = level - 1
        if max(depth.values()) > 0:
            raise SpiceError('Something wrong with the subckt nesting.')
        return depth

#    def cache_getParamsUsedSubckt(self):
#        sd = self.subcktdepth()
#        mindepth = min(sd.values())
#        # from top to bottom
#        depth = 0
#        while depth >= mindepth:
#            for subckt in sd:
#                if sd[subckt] == depth:
#                    self.cache_paramsubckt[(subckt.name, None)] = (
#                            self.getParamsUsedSubckt(subckt.name))
#            depth -= 1

    def trim(self, subcktname):
        """returns a new PySchematic only containing the specified subckt and
        its infants"""
        newPySch = PySchematic(self.source)
        newPySch.toplevel = self.toplevel
        depth = self.subcktdepth(subcktname)
        for subckt in depth:
            newPySch.add(subckt)

        return newPySch

    def prepare_spicenetlist(self, subcktname=None):
        netlist = ''

        # top level parameters
        if len(self.toplevel.getparams()) > 0:
            netlist += ('.param ' + self.toplevel.getparams().export_spice() +
                        '\n\n')

        # all subckts (bottom-up)
        depth = self.subcktdepth(subcktname)
        # for k,v in depth.items():
        #     print(str(v) + ': ' + str(k))

        level = min(depth.values())
        while level < 1:
            subcktlist = [subckt for subckt in depth.keys()
                          if depth[subckt] == level]
            subcktlist.sort()

            for subckt in subcktlist:
                netlist += subckt.export_spice()
            level += 1

        # top-level instances and devices
        contentl = list(self.toplevel.content)
        contentl.sort()
        for item in contentl:
            netlist += item.export_spice()

        spicenetlist = SpiceNetlist()
        spicenetlist.setsource(('From PySchematic.export_spicefile() with ' +
                                'PySchematic(source = %s, ...) ') % (
                                        self.source))
        spicenetlist.importNetlistFromStr(netlist)
        return spicenetlist

    def export_spicefile(self, filename, subcktname=None, backup=True):
        spicenetlist = self.prepare_spicenetlist(subcktname)
        spicenetlist.write(filename, backup)

    def prepare_autogen(self, subcktname=None, project=None, force=False):
        batchtext = '// From PySchematic.export_autogen(' + str(subcktname)
        batchtext += ') with PySchematic(source = %r, ...) \n' % (self.source)
        batchtext += 'module batch_module\n'
        batchtext += '{\n'
        batchtext += '#include <stdlib.h>\n'
        batchtext += '#include <stdarg.h>\n'
        batchtext += '#include <stdio.h>\n'
        batchtext += '#include <string.h>\n'
        batchtext += '#include <ctype.h>\n'
        batchtext += '#include <math.h>\n'
        batchtext += '\n'
        batchtext += '#define EXCLUDE_LEDIT_LEGACY_UPI\n'
        batchtext += '#include <ldata.h>\n'
        batchtext += r'#include "X:\LEdit\general\globals.c"' + '\n'
        batchtext += r'#include "X:\LEdit\general\update2newcell.c"' + '\n'
        batchtext += r'#include "X:\LEdit\technology\project.c"' + '\n'
        batchtext += (r'#include "S:\technologies\setup\tech2layoutparams' +
                      r'\tech2layoutparams.c"' + '\n')

        batchtext += '\n'

        # trim all subckts that are not in the hierarchy to be exported
        #  bugfix: do not do so, because you miss the parameters of the cells
        #  where it is used

        # trimPySch = self

        #  Do trim, but first check all possible parameter values for the
        #  subckt.  And question which to autogenerate.
        parameterlist = self.getParamsUsedSubckt(subcktname)
        assert len(parameterlist) > 0

        ltbgui = False
        import traceback
        for x in traceback.format_stack():
            if 'LTBgui' in x:
                ltbgui |= True

        if not ltbgui:
            if len(parameterlist) == 1 and len(parameterlist[0].keys()) == 0:
                print('No parameters for this subckt')
                defined = True
            else:
                defined = False
                print('With which set of parameters you would like to have ' +
                      subcktname + ' generated?\n')

            while not defined:
                newparameterlist = []
                for i, plist in enumerate(parameterlist):
                    print(str(i) + ') ' + plist.export_spice())

                print("\nDefine your choice as follows: \n" +
                      " - 1-2,4 (as you would define printed pages)\n" +
                      " - [A]ll\n" +
                      " - Add [N]ew set\n")
                ans = input('Your choice: ')
                print('\n\n')
                if ans in ['', 'a', 'A']:
                    defined = True
                elif ans in ['n', 'N']:
                    print('Give numeric value for parameter(s):')
                    newparams = Params()
                    for paramname in parameterlist[0].keys():
                        val = input(paramname + ' = ')
                        newparams.add(paramname + ' = ' + val)
                    # evaluate parameters if necessary
                    for paramname in newparams:
                        result = self.evalParam(newparams[paramname])
                        newparams[paramname] = str(result)
                    parameterlist.append(newparams)
                    parameterlist.sort()
                else:
                    ok = True
                    for char in ans:
                        if char not in ' ,-0123456789':
                            print('Sorry, not understood\n')
                            ok &= False
                        else:
                            ok &= True
                    if ok:
                        stripans = ans.replace(' ', '')
                        for sub in stripans.split(','):
                            if len(sub.split('-')) > 2:
                                print('Sorry, not understood\n')
                                ok &= False
                            elif len(sub.split('-')) == 1:
                                try:
                                    newparameterlist.append(
                                            parameterlist[int(sub)])
                                except IndexError:
                                    print('IndexError: list index out of ' +
                                          'range. Sorry, not understood\n')
                                    ok &= False

                                # print(sub)
                                # print(newparameterlist)
                            elif '' in sub.split('-'):
                                print('Sorry, not understood\n')
                                ok &= False
                            else:
                                for x in range(int(sub.split('-')[0]),
                                               int(sub.split('-')[1]) + 1):
                                    try:
                                        newparameterlist.append(
                                                parameterlist[x])
                                    except IndexError:
                                        print('IndexError: list index out of' +
                                              ' range. Sorry, not understood' +
                                              '\n')
                                        ok &= False
                                    # print(x)
                                    # print(newparameterlist)
                    if ok:
                        parameterlist = newparameterlist
                if not defined:
                    print('Confirm with which set of parameters you would ' +
                          'like to have ' + subcktname + ' generated?\n')

        trimPySch = self.trim(subcktname)
        trimPySch.cache_paramsubckt = {subcktname: parameterlist}

        # generate from deepest level upwards
        depth = trimPySch.subcktdepth(subcktname)
        # for k,v in depth.items():
        #     print(str(v) + ': ' + str(k))

        # check Spice lib
        allsubcktnames = []
        for subckt in depth.keys():
            allsubcktnames.append(subckt.name)

        notfound = []
        for subckt in depth.keys():
            if subckt.name in DEF_SUBCKT:
                # Do not crawl deeper than the device level, even if in
                # v2.0 file a deeper subckt exists, skip this subckt and ...
                continue
                # ... with the next
            for content in subckt.content:
                if content.isInstance():
                    instancedsubcktname = content.getsubcktname()
                    if instancedsubcktname not in allsubcktnames:
                        notfound.append(instancedsubcktname)
        if len(notfound) > 0:
            spiceErrortext = ('undefined subckt(s): ' + ', '.join(notfound) +
                              '\nTake note of the fact that LTB is case-' +
                              'sensitive.')
            if force:
                logging.warning(spiceErrortext)
            else:
                raise SpiceError(spiceErrortext)

        level = min(depth.values())
        listofdefinedautogenfunctions = []
        while level < 1:
            # sort alphabetically iso random order -> same netlist is same
            # output .c file (allows file-by-file comparison)
            subcktlist = [subckt for subckt in depth.keys()
                          if depth[subckt] == level]
            subcktlist.sort()

            for subckt in subcktlist:
                batchtext_, newfunctions = subckt.export_autogen(
                        trimPySch, listofdefinedautogenfunctions,
                        project=project, force=force and level==0)
                listofdefinedautogenfunctions.extend(newfunctions)
                batchtext += batchtext_
            level += 1

        batchtext += '\nvoid layoutbatch()\n'
        batchtext += '{\n'

        # batchtext += '\tautogen_' + subcktname.replace('-', '_') + '();\n'
        batchtext += '\tLFile activefile;\n'
        batchtext += '\tLCell newCell;\n'
        batchtext += '\tchar cellname[MAX_CELL_NAME] = "";\n\n'
        batchtext += '\tactivefile = LFile_GetVisible();\n\n'
        batchtext += ('\tLUpi_LogMessage("You are about to ' +
                      '{!s}autogen '.format('FORCE ' if force else '') +
                      'cell {!r}.\\nContinue?\\n");\n'.format(subcktname))
        batchtext += ('\tif (!LDialog_YesNoBox("You are about to ' +
                      '{!s}autogen '.format('FORCE ' if force else '') +
                      'cell {!r}.\\n\\nContinue?")){{\n'.format(subcktname))
        batchtext += '\t\tLUpi_LogMessage("You: No.\\n");\n'
        batchtext += '\t\treturn 0;\n\t}\n\tLUpi_LogMessage("You: Yes.\\n");\n\n'

        for newfunction in newfunctions:
            batchtext += '\tnewCell = ' + newfunction + '();\n'

        batchtext += '\n'

        for newfunction in newfunctions:
            newcell = newfunction[8:]
            batchtext += ('\tLFile_OpenCell(activefile, LCell_GetFullName(' +
                            'newCell, cellname, MAX_CELL_NAME ));\n')

        batchtext += '}\n\n'
        batchtext += '}  // module\n\n'
        batchtext += 'layoutbatch();\n'

        return batchtext

    def export_autogen(self, filename, subcktname=None, backup=True,
                       project=None, force=False):
        batchtext = self.prepare_autogen(subcktname, project=project,
                                         force=force)
        general.write(filename, batchtext, backup)
        print('autogenfile of subckt "' + subcktname +
              '" exported to ' + filename)
        laygen.laygenstandalone2bound(filename)

    def export_wrl(self, subcktname, hierarchy, project=None, backup=True):
        if hierarchy:
            depth = self.subcktdepth(subcktname)
            # for k,v in depth.items():
            #     print(str(v) + ': ' + str(k))

            if True:
                # using realnames, there are sometimes duplicates
                duplicate_realnames = set()
                realnames = set()
                for subckt in depth.keys():
                    if subckt.realname not in realnames:
                        realnames.add(subckt.realname)
                    else:
                        duplicate_realnames.add(subckt.realname)
                # logging.debug('duplicate_realnames: ' +
                #               ', '.join(duplicate_realnames))

                # check there are no duplicate wrlnames
                duplicate_wrlnames = set()
                wrlnames = set()
                for subckt in depth.keys():
                    wrlname = subckt.realname
                    if wrlname in duplicate_realnames:
                        wrlname += '__' + str(subckt.design)
                    if wrlname not in wrlnames:
                        wrlnames.add(wrlname)
                    else:
                        duplicate_wrlnames.add(wrlname)
                assert(len(duplicate_wrlnames) == 0)

            level = min(depth.values())
            while level < 1:
                subcktlist = [subckt for subckt in depth.keys()
                              if depth[subckt] == level]
                subcktlist.sort()

                for subckt in subcktlist:
                    wrlname = subckt.realname
                    if wrlname in duplicate_realnames:
                        wrlname += '__' + str(subckt.design)
                        # logging.debug(subckt.realname + ' --> ' +
                        #               wrlname)

                    fullwrl = subckt.export_wrl(self)

                    if project is None:
                        fullwrlfilename = 'T:\\_full_' + wrlname + '.wrl'
                        wrlfilename = 'T:\\' + wrlname + '.wrl'
                    else:
                        fullwrlfilename = (LTBsettings.wrlfilepath(project) +
                                           '_full_' + wrlname + '.wrl')
                        wrlfilename = (LTBsettings.wrlfilepath(project) +
                                       wrlname + '.wrl')
                    general.write(fullwrlfilename, fullwrl, backup)
                    # strip from gnd and 0
                    pattern = '^gnd.*gnd\n'
                    nogndwrl = re.sub(pattern, '', fullwrl, 0, re.M)
                    pattern = '^0\tPAGEFRAME\tXstd_versioncheck\tgnd\n'
                    wrl = re.sub(pattern, '', nogndwrl, 0, re.M)
                    general.write(wrlfilename, wrl, backup)

                    print('wrlfile of subckt "' + subckt.name +
                          '" exported to ' + wrlfilename)

                level += 1

        else:
            for subckt in self.subckts:
                if subckt.hasname(subcktname):
                    wrl = subckt.export_wrl(self)
                    if project is None:
                        wrlfilename = 'T:\\' + subckt.name + '.wrl'
                    else:
                        wrlfilename = (LTBsettings.wrlfilepath(project) +
                                       subckt.name + '.wrl')
                    general.write(wrlfilename, wrl, backup)
                    print('wrlfile of subckt "' + subckt.name +
                          '" exported to ' + wrlfilename)

    def export_autolabel(self, filename, cellname, backup=True):
        batchtext = ('// From PySchematic.export_autolabel(%r, %r, %r) with ' +
                     'PySchematic(source = %r, ...) \n\n') % (
                             filename, cellname, backup, self.source)
        batchtext += 'module autolabel_module\n'
        batchtext += '{\n'
        batchtext += '#include <stdlib.h>\n'
        batchtext += '#include <stdarg.h>\n'
        batchtext += '#include <stdio.h>\n'
        batchtext += '#include <string.h>\n'
        batchtext += '#include <ctype.h>\n'
        batchtext += '#include <math.h>\n'
        batchtext += '\n'
        batchtext += '#define EXCLUDE_LEDIT_LEGACY_UPI\n'
        batchtext += '#include <ldata.h>\n'
        # batchtext += r'#include "X:\LEdit\technology\settings.c"' + '\n'
        batchtext += '\n'

        batchtext += 'LLabel LLabel_Find(LCell cell, const char* name) {\n'
        batchtext += '\tLLabel findLabel;\n'
        batchtext += '\tchar labelname[128];\n\n'
        batchtext += '\tfindLabel = LLabel_GetList(cell);\n'
        batchtext += '\tif (findLabel != NULL) {\n'
        batchtext += '\t\tLLabel_GetName(findLabel, labelname, 127);\n'
        batchtext += '\t\twhile (strcmp(labelname, name) != 0) {\n'
        batchtext += '\t\t\tfindLabel = LLabel_GetNext(findLabel);\n'
        batchtext += '\t\t\tLLabel_GetName(findLabel, labelname, 127);\n'
        batchtext += '\t\t\tif (findLabel == NULL)\n'
        batchtext += '\t\t\t\tbreak;\n'
        batchtext += '\t\t}\n'
        batchtext += '\t}\n'
        batchtext += '\treturn findLabel;\n'
        batchtext += '}\n\n'

        batchtext += ('LRect calcoffset(LTransform_Ex99 instTrans, ' +
                      'LRect offsetportRect){\n')
        batchtext += '\tLRect portRect;\n'
        batchtext += '\t\n'
        batchtext += '\tswitch ((int) instTrans.orientation){\n'
        batchtext += '\tcase 0: \n'
        batchtext += ('\t\tportRect = LRect_Set(instTrans.translation.x+' +
                      'offsetportRect.x0 ,instTrans.translation.y+' +
                      'offsetportRect.y0 , \n')
        batchtext += ('\t\t\t\t\t\t\tinstTrans.translation.x+' +
                      'offsetportRect.x1 ,instTrans.translation.y+' +
                      'offsetportRect.y1);\n')
        batchtext += '\t\tbreak;\n'
        batchtext += '\tcase 90:\n'
        batchtext += ('\t\tportRect = LRect_Set(instTrans.translation.x-' +
                      'offsetportRect.y1 ,instTrans.translation.y+' +
                      'offsetportRect.x0 , \n')
        batchtext += ('\t\t\t\t\t\t\tinstTrans.translation.x-' +
                      'offsetportRect.y0 ,instTrans.translation.y+' +
                      'offsetportRect.x1);\n')
        batchtext += '\t\tbreak;\n'
        batchtext += '\tcase 180:\n'
        batchtext += ('\t\tportRect = LRect_Set(instTrans.translation.x-' +
                      'offsetportRect.x1 ,instTrans.translation.y-' +
                      'offsetportRect.y1 , \n')
        batchtext += ('\t\t\t\t\t\t\tinstTrans.translation.x-' +
                      'offsetportRect.x0 ,instTrans.translation.y-' +
                      'offsetportRect.y0);\n')
        batchtext += '\t\tbreak;\n'
        batchtext += '\tcase 270:\n'
        batchtext += ('\t\tportRect = LRect_Set(instTrans.translation.x+' +
                      'offsetportRect.y0 ,instTrans.translation.y-' +
                      'offsetportRect.x1 , \n')
        batchtext += ('\t\t\t\t\t\t\tinstTrans.translation.x+' +
                      'offsetportRect.y1 ,instTrans.translation.y-' +
                      'offsetportRect.x0);\n')
        batchtext += '\t\tbreak;\n'
        batchtext += '\tcase -360:\n'
        batchtext += ('\t\tportRect = LRect_Set(instTrans.translation.x-' +
                      'offsetportRect.x1 ,instTrans.translation.y+' +
                      'offsetportRect.y0 , \n')
        batchtext += ('\t\t\t\t\t\t\tinstTrans.translation.x-' +
                      'offsetportRect.x0 ,instTrans.translation.y+' +
                      'offsetportRect.y1);\n')
        batchtext += '\t\tbreak;\n'
        batchtext += '\tcase -90:\n'
        batchtext += ('\t\tportRect = LRect_Set(instTrans.translation.x-' +
                      'offsetportRect.y1 ,instTrans.translation.y-' +
                      'offsetportRect.x1 , \n')
        batchtext += ('\t\t\t\t\t\t\tinstTrans.translation.x-' +
                      'offsetportRect.y0 ,instTrans.translation.y-' +
                      'offsetportRect.x0);\n')
        batchtext += '\t\tbreak;\n'
        batchtext += '\tcase -180:\n'
        batchtext += ('\t\tportRect = LRect_Set(instTrans.translation.x+' +
                      'offsetportRect.x0 ,instTrans.translation.y-' +
                      'offsetportRect.y1 , \n')
        batchtext += ('\t\t\t\t\t\t\tinstTrans.translation.x+' +
                      'offsetportRect.x1 ,instTrans.translation.y-' +
                      'offsetportRect.y0);\n')
        batchtext += '\t\tbreak;\n'
        batchtext += '\tcase -270:\n'
        batchtext += ('\t\tportRect = LRect_Set(instTrans.translation.x+' +
                      'offsetportRect.y0 ,instTrans.translation.y+' +
                      'offsetportRect.x0 , \n')
        batchtext += ('\t\t\t\t\t\t\tinstTrans.translation.x+' +
                      'offsetportRect.y1 ,instTrans.translation.y+' +
                      'offsetportRect.x1);\n')
        batchtext += '\t\tbreak;\n'
        batchtext += '\tdefault:\n'
        batchtext += '\t\tLDialog_MsgBox("Orientation not found");\n'
        batchtext += '\t}\n'
        batchtext += '\treturn portRect;\n'
        batchtext += '}\n\n'

        batchtext += 'void autolabel()\n'
        batchtext += '{\n'
        batchtext += 'int notfoundPorts;\n'
        batchtext += 'int foundPorts;\n'
        batchtext += 'int totalPorts;\n'
        batchtext += 'LFile activefile;\n'
        batchtext += 'LCell editCell;\n'
        batchtext += 'LCell instCell;\n'
        batchtext += 'LPort movePort;\n'
        batchtext += 'LPort deepPort;\n'
        batchtext += 'LLayer deepPortLayer;\n'
        batchtext += 'LLayer labelLayer;\n'
        batchtext += 'LLayerParamEx830 LayerParameters;\n'
        batchtext += 'LLabel findLabel;\n'
        batchtext += 'LPoint labelPoint;\n'
        batchtext += 'LRect portRect;\n'
        batchtext += 'LRect offsetportRect;\n'
        batchtext += 'LInstance instance;\n'
        batchtext += 'LTransform_Ex99 instTrans;\n'

        batchtext += 'activefile = LFile_GetVisible();\n\n'
        subckt = self.getSubckt(cellname)
        if subckt is None:
            SpiceError(('cellname %r not found in PySchematic(source = %r, ' +
                        '...)') % (cellname, self.source))
        batchtext += ('editCell = LCell_Find(activefile, "' + cellname +
                      '");\n\n')
        batchtext += 'notfoundPorts = 0;\n'
        batchtext += 'foundPorts = 0;\n'
        batchtext += 'totalPorts = 0;\n'

        batchtext += ('if (!LDialog_YesNoBox("You are about to autolabel ' +
                      'cell {!r}.\\n\\nContinue?")){{\n'.format(cellname))
        batchtext += '\treturn 0;\n}\n\n'

        dangling = 0
        numberofports = len(subckt.ports)
        portcount = 0
        debugDoOnce = True
        for port in subckt.ports:
            portcount += 1
            progresstext = str(portcount) + '/' + str(numberofports)
            print(progresstext)
            batchtext += '// ' + progresstext + '\n'
            contentl = list(subckt.content)
            contentl.sort()

            portconn = {}   # dict{instname: its portname}

            for item in contentl:
                if item.isInstance():
                    if port in item.ports:
                        itemsubcktdefinition = self.getSubckt(item.subcktname)
                        if itemsubcktdefinition is not None:
                            portindex = item.ports.index(port)
                            if debugDoOnce:
                                print(port)
                                print(repr(item))
                                print(item.ports)
                                print(portindex)
                                print(itemsubcktdefinition.ports)
                                debugDoOnce = False

                            portconn[item] = (
                                itemsubcktdefinition.ports[portindex])
                elif item.isMosInstance():
                    if port in item.ports:
                        portindex = item.ports.index(port)
                        portconn[item] = ['D', 'G', 'S', 'B'][portindex]

            batchtext += 'movePort = LPort_Find(editCell, "' + port + '");\n'

            # commented because missing ports are created
            # batchtext += 'if (movePort == NULL) notfoundPorts++;\n'
            batchtext += 'if (movePort == NULL) {\n'
            batchtext += ('\tmovePort = LPort_New(editCell, tech2layer(' +
                          '"defaultlabellayer"), "' + port +
                          '", 0, 0, 0, 0);\n')
            batchtext += '}\n'

            # commented because missing ports are created
            # batchtext += 'else {\n'
            batchtext += ('\tfindLabel = LLabel_Find(editCell, "' + port +
                          '");\n')
            # You can use labels to force the port to be on the label location
            batchtext += '\tif (findLabel != NULL) {\n'
            batchtext += '\t\tlabelPoint = LLabel_GetPosition(findLabel);\n'
            batchtext += ('\t\tportRect = LRect_Set(labelPoint.x, ' +
                          'labelPoint.y, labelPoint.x, labelPoint.y);\n')
            batchtext += '\t\tlabelLayer = LLabel_GetLayer(findLabel);\n'
            batchtext += ('\t\tLObject_ChangeLayer(editCell, movePort, ' +
                          'labelLayer);\n')
            batchtext += ('\t\tLLayer_GetParametersEx830(labelLayer, ' +
                          '&LayerParameters);\n')
            batchtext += ('\t\tLObject_SetGDSIIDataType(movePort, ' +
                          'LayerParameters.GDSDataType);\n')
            batchtext += '\t\tLPort_Set(editCell, movePort, portRect);\n'
            batchtext += '\t}\n'
            # yet, most of the time you want it on the location of the deeper
            # subckt
            batchtext += '\telse {\n'

            dontknow = False
            # if the port has no connections in the cell
            if len(portconn) == 0:
                batchtext += ('\t\tportRect = LRect_Set(' +
                              str(dangling * 5000) + ', 0, ' +
                              str(dangling * 5000) + ', 0);\n')
                batchtext += '\t\tLPort_Set(editCell, movePort, portRect);\n'
                batchtext += '\t}\n'
                dangling += 1
            else:
                # if the port has only one connection in the cell
                if len(portconn) == 1:
                    item, portname = portconn.popitem()
                    if not(item.isInstance() or item.isMosInstance()):
                        batchtext += '\t}\n'
                        dontknow = True
                # if the port has more than one connection in the cell
                else:
                    # find a connected subckt's portname that is 'out'
                    if 'out' in portconn.values():
                        for item, portname in portconn.items():
                            if item.isInstance() and portname == 'out':
                                break
                    # find a connected subckt's portname that has 'out' in
                    # the name
                    elif True in ['out' in x for x in portconn.values()]:
                        for item, portname in portconn.items():
                            if item.isInstance() and 'out' in portname:
                                break
                    # find a connected subckt's portname that has any name
                    elif True in [x.isInstance() for x in portconn.keys()]:
                        # prioritize <0> in the instancename
                        if True in ['<0>' in x.getname() for x in
                                    portconn.keys() if x.isInstance()]:
                            for item, portname in portconn.items():
                                if (item.isInstance() and
                                        '<0>' in item.getname()):
                                    break
                        # prioritize <1> in the instancename
                        elif True in ['<1>' in x.getname() for x in
                                      portconn.keys() if x.isInstance()]:
                            for item, portname in portconn.items():
                                if (item.isInstance() and
                                        '<1>' in item.getname()):
                                    break
                        # otherwise take any other
                        else:
                            for item, portname in portconn.items():
                                if item.isInstance():
                                    break
                    # find a connected mos's portname that has any name
                    elif True in [x.isMosInstance() for x in portconn.keys()]:
                        for item, portname in portconn.items():
                            if item.isMosInstance():
                                break
                    # anything else
                    else:
                        item, portname = portconn.popitem()
                        dontknow = True
                if dontknow:
                    print("Don't know: " + str(item) + " : " + str(portname))
                    batchtext += '\t}\n'
                else:
                    batchtext += ('\t\tinstance = LInstance_Find(editCell, "' +
                                  item.name + '");\n')
                    batchtext += ('\t\tinstCell = ' +
                                  'LInstance_GetCell(instance);\n')
                    batchtext += ('\t\tdeepPort = LPort_Find(instCell, "' +
                                  portname + '");\n')
                    batchtext += ('\t\toffsetportRect = ' +
                                  'LPort_GetRect(deepPort);\n')
                    batchtext += ('\t\tdeepPortLayer = ' +
                                  'LPort_GetLayer(deepPort);\n')
                    batchtext += ('\t\tLObject_ChangeLayer(editCell, ' +
                                  'movePort, deepPortLayer);\n')
                    batchtext += ('\t\tLLayer_GetParametersEx830(' +
                                  'deepPortLayer, &LayerParameters);\n')
                    batchtext += ('\t\tLObject_SetGDSIIDataType(movePort, ' +
                                  'LayerParameters.GDSDataType);\n')
                    batchtext += ('\t\tinstTrans = ' +
                                  'LInstance_GetTransform_Ex99(instance);\n')
                    batchtext += ('\t\tportRect = calcoffset(instTrans, ' +
                                  'offsetportRect);\n')
                    batchtext += ('\t\tLPort_Set(editCell, movePort, ' +
                                  'portRect);\n')
                    batchtext += '\t}\n'
            batchtext += 'LPort_SetTextSize( movePort, 250 );\n'
            batchtext += ('LPort_SetTextAlignment( movePort, ' +
                          'PORT_TEXT_MIDDLE | PORT_TEXT_CENTER );\n')

            # commented because missing ports are created
            # batchtext += '}\n\n'

        batchtext += '}\n}\n'
        batchtext += 'autolabel();\n'

        general.write(filename, batchtext, backup)
        print('autolabel of subckt "' + subckt.name +
              '" exported to ' + filename)
        laygen.laygenstandalone2bound(filename)

    def export_autoplace(self, filename, cellname, instname, rangebegin,
                         rangeend, startx, starty, pitch, backup=True,
                         radhard=False):
        batchtext = (('// From PySchematic.export_autoplace(%r, %r, %r, %r, ' +
                      '%r, %r, %r, %r, %r) with PySchematic(source = %r, ...' +
                      ') \n\n') % (filename, cellname, instname, rangebegin,
                                   rangeend, startx, starty, pitch, backup,
                                   self.source))
        batchtext += 'module autoplace_module\n'
        batchtext += '{\n'
        batchtext += '#include <stdlib.h>\n'
        batchtext += '#include <stdarg.h>\n'
        batchtext += '#include <stdio.h>\n'
        batchtext += '#include <string.h>\n'
        batchtext += '#include <ctype.h>\n'
        batchtext += '#include <math.h>\n'
        batchtext += '\n'
        batchtext += '#define EXCLUDE_LEDIT_LEGACY_UPI\n'
        batchtext += '#include <ldata.h>\n'
        batchtext += '\n'

        batchtext += 'void autoplace()\n'
        batchtext += '{\n'
        batchtext += 'LFile activefile;\n'
        batchtext += 'activefile = LFile_GetVisible();\n'
        batchtext += 'LCell editCell;\n'
        batchtext += 'LInstance moveInstance;\n'
        batchtext += 'LTransform_Ex99 instTrans;\n'
        batchtext += 'LPoint coord;\n\n'

        subckt = self.getSubckt(cellname)
        if subckt is None:
            SpiceError(('cellname %r not found in PySchematic(source = %r, ' +
                        '...)') % (cellname, self.source))
        batchtext += ('editCell = LCell_Find(activefile, "' + cellname +
                      '");\n\n')

        if radhard:
            batchtext += 'LCell westCell, eastCell;\n'
            batchtext += 'LRect instRect, westRect, eastRect;\n'
            batchtext += 'LTransform_Ex99 westTrans, eastTrans, nulTrans;\n'
            batchtext += 'LInstance westInstance, eastInstance;\n'
            batchtext += 'nulTrans = LTransform_Zero_Ex99();\n'
            batchtext += 'westCell = LCell_Find(activefile, "__westend");\n'
            batchtext += 'eastCell = LCell_Find(activefile, "__eastend");\n'
            batchtext += 'westRect =  LCell_GetMbb(westCell);\n'
            batchtext += 'eastRect =  LCell_GetMbb(eastCell);\n\n'

        batchtext += ('if (!LDialog_YesNoBox("You are about to autoplace ' +
                      'cell {!r}.\\n\\nContinue?")){{\n'.format(cellname))
        batchtext += '\treturn 0;\n}\n\n'

        assert len(pitch) % 3 == 0
        dimensions = int(len(pitch)/3)
        arraylocation = [0] * dimensions
        startcoord = [startx, starty]

        for instancenumber in range(int(rangebegin), int(rangeend+1)):
            coordx = startcoord[0]
            coordy = startcoord[1]
            for dim in range(dimensions):
                coordx += pitch[0 + dim * 3] * arraylocation[dim]
                coordy += pitch[1 + dim * 3] * arraylocation[dim]

            fullinstname = instname + '<' + str(instancenumber) + '>'
            if not(subckt.incontent(fullinstname)):
                warning = 'Warning: %s not in %s' % (fullinstname,
                                                     subckt.getname())
                print(warning)
                logging.warning(warning)
            batchtext += ('moveInstance = LInstance_Find(editCell, "' +
                          fullinstname + '");\n')
            batchtext += ('instTrans = LInstance_GetTransform_Ex99(' +
                          'moveInstance);\n')
            batchtext += ('coord = LPoint_Set(' + str(int(coordx*1000)) +
                          ', ' + str(int(coordy*1000)) + ');\n')

            batchtext += ('instTrans = LTransform_Set_Ex99(coord.x, ' +
                          'coord.y, instTrans.orientation, ' +
                          'instTrans.magnification);\n')
            batchtext += ('LInstance_Set_Ex99(editCell, moveInstance, ' +
                          'instTrans, LPoint_Set(1, 1), LPoint_Set(1, 1));' +
                          '\n\n')

            if radhard:
                batchtext += 'instRect =  LInstance_GetMbb(moveInstance);\n'
                # westTrans = LTransform_Set_Ex99(instRect.x0 - westRect.x1,
                #                               coord.y, nulTrans.orientation,
                #                               nulTrans.magnification);
                #    instRect.x0 should be equal to coord.x =>
                #        if not: lvs/drc will report errors
                #    all y should be aligned =>
                #        if not: lvs/drc will report errors
                batchtext += ('westTrans = LTransform_Set_Ex99(coord.x - ' +
                              'westRect.x1, coord.y, nulTrans.orientation, ' +
                              'nulTrans.magnification);\n')
                # eastTrans = LTransform_Set_Ex99(instRect.x1 + eastRect.x0,
                #                               coord.y, nulTrans.orientation,
                #                               nulTrans.magnification);
                #   eastRect.x0 should be 0
                #        if not: lvs/drc will report errors
                #   RALP of stdcells is thus guaranteed for cells in
                #        'all_stdcells_used_in...'
                batchtext += ('eastTrans = LTransform_Set_Ex99(instRect.x1, ' +
                              'coord.y, nulTrans.orientation, ' +
                              'nulTrans.magnification);\n')
                batchtext += ('westInstance = LInstance_New_Ex99(editCell, ' +
                              'westCell, westTrans, LPoint_Set(1, 1), ' +
                              'LPoint_Set(1, 1));\n')
                batchtext += ('LInstance_SetName(editCell, westInstance, "' +
                              fullinstname + '_west");\n')
                batchtext += ('eastInstance = LInstance_New_Ex99(editCell, ' +
                              'eastCell, eastTrans, LPoint_Set(1, 1), ' +
                              'LPoint_Set(1, 1));\n')
                batchtext += ('LInstance_SetName(editCell, eastInstance, "' +
                              fullinstname + '_east");\n\n\n')

            # update arraylocation
            for dim in range(dimensions):
                arraylocation[dim] += 1
                if arraylocation[dim] % pitch[2 + dim * 3] == 0:
                    arraylocation[dim] = 0
                    continue
                break

        batchtext += '}\n'
        batchtext += '}\n\n'
        batchtext += 'autoplace();\n'

        general.write(filename, batchtext, backup)
        print('autoplace of subckt "' + subckt.name +
              '" exported to ' + filename)
        laygen.laygenstandalone2bound(filename)


class SpiceLine(str):
    """class SpiceLine contains a single line in a full netlist.
     Added class for more testability and generalization."""

    #    def __init__(self, text):
    #        self.text = text

    def __add__(self, other):
        return SpiceLine(str(self) + str(other))

    def isComment(self):
        """isComment() returns True if the SpiceLine is a full line comment,
        False otherwise."""
        if re.match(r'\s*[*]+', self):
            return True
        return False

    def isCellDesignPAGEFRAMEComment(self):
        """isCellDesignPAGEFRAMEComment() returns True if the SpiceLine is the
        cell-design information of a PAGEFRAME header, False otherwise."""
        if re.match(r'\s*[*] Cell: \w+ [|] Design: \w+', self):
            return True
        return False

    def analyzeCDPFC(self):
        """analyzeCDPFC() tries to match a CellDesignPAGEFRAMEComment, get
        cell and design name.
         returns tuple of 2 strings: ('cell', 'design')."""
        match = re.match(r'\s*[*] Cell: (?P<cell>\w+) [|] Design: ' +
                         r'(?P<design>\w+)', self, re.I)
        if not match:
            raise SpiceError('SpiceLine does not match ' +
                             'DesignCellPAGEFRAMEComment. ' +
                             '(line content: "' + self + ')')

        cell = match.groupdict()['cell']
        design = match.groupdict()['design']
        # print('Cell: ' + cell + ' | design: ' + design)
        return (cell, design)

    def isSeditCellComment(self):
        """isSeditCellComment() returns True if the SpiceLine is the cell name
        information that S-Edit automatically puts as comment at the start of
        the subckt, False otherwise."""
        if re.match(r'\s*[*] Cell name: \w+', self):
            return True
        return False

    def analyzeSCC(self):
        """analyzeSCC() tries to match a SeditCellComment, get the cell name.
        returns a string."""
        match = re.match(r'\s*[*] Cell name: (?P<cell>\w+)', self, re.I)
        if not match:
            raise SpiceError('SpiceLine does not match ' +
                             'SeditCellComment. ' +
                             '(line content: "' + self + ')')

        cell = match.groupdict()['cell']
        return cell

    def isSeditDesignComment(self):
        """isSeditCellComment() returns True if the SpiceLine is the design name
        information that S-Edit automatically puts as comment at the start of
        the subckt, False otherwise."""
        if re.match(r'\s*[*] Library name: \w+', self):
            return True
        return False

    def analyzeSDC(self):
        """analyzeSDC() tries to match a SeditDesignComment, get the design name.
        returns a string."""
        match = re.match(r'\s*[*] Library name: (?P<design>\w+)', self, re.I)
        if not match:
            raise SpiceError('SpiceLine does not match ' +
                             'SeditDesignComment. ' +
                             '(line content: "' + self + ')')

        design = match.groupdict()['design']
        return design

    def isSeditPortComment(self):
        """isSeditPortComment() returns True if the SpiceLine is the part of the
        Port listing that S-Edit automatically puts as comment at the start of
        the subckt, False otherwise."""
        if re.match(r'\s*[*] PORT=\S+ TYPE=\S+', self):
            return True
        return False

    def isBlankline(self):
        """isBlankline() returns True if the SpiceLine is a blankline,
        False otherwise."""
        if re.match(r'\s*$', self):
            return True
        return False

    def isInclude(self):
        """isInclude() returns True if the SpiceLine is a blankline,
        False otherwise."""
        if re.match(r'\s*[.]include\s', self):
            return True
        return False

    def analyzeInclude(self):
        """analyzeInclude() tries to match a .include statement line,
        get filename string out
         returns string."""
        match = re.match(r"[.]include\s+['\"]?" +
                         r"(?P<include>[^ \t\n\r\f\v'\"]+)['\"]?", self, re.I)
        if not match:
            raise SpiceError('SpiceLine does not match include statement. ' +
                             '(line content: "' + self + ')')

        includefile = match.groupdict()['include']
        return includefile

    def isParam(self):
        """isParam() returns True if the SpiceLine is a parameter definition,
        False otherwise."""
        if re.match(r'\s*[.]param\s', self):
            return True
        return False

    def analyzeParam(self):
        """analyzeParam() tries to match a parameter definition line,
        get parameter string out
         returns Params element."""
        match = re.match(r'\s*[.]param(?P<params>(\s+\S+\s*[=]\s*\S+)*)',
                         self, re.I)
        if not match:
            raise SpiceError('SpiceLine does not match parameter definition. ' +
                             '(line content: "' + self + ')')

        params = Params(match.groupdict()['params'])
        return params

    def isBeginSubckt(self):
        """isBeginSubckt() returns True if the SpiceLine is the beginning of
        a subckt, False otherwise."""
        if re.match(r'\s*[.]subckt\s', self, re.I):
            return True
        return False

    def analyzeBS(self):
        """analyzeBS() tries to match a 'beginning subckt' line, get ports
        and params out and create a Subckt element.
         returns Subckt element."""

        # remove inline comment
        analyzestring = self[0:self.find('$') if self.find('$') !=-1 else None]
        match = re.match(r'\s*[.]subckt\s+(?P<name>\S+)' +
                         r'(?P<ports>(\s+[^ =\t\n\r\f\v]+(?!\S))*)' +
                         r'(?P<params>(\s+\S+\s*[=]\s*\S+)*)', analyzestring, re.I)
        if not match:
            raise SpiceError('SpiceLine does not match begin of subckt. ' +
                             '(line content: "' + self + ')')

        subcktname = match.groupdict()['name']
        if subcktname in MOS_NAMES:
            if match.groupdict()['params'].count('=') > 3:
                raise ParameterMismatchError('Mos ' + subcktname + ' should ' +
                                             'have no more than 3 parameters ' +
                                             'in definition, check and fix ' +
                                             'v2.0_LVS.sp file.')
            subckt = MosSubckt(subcktname, match.groupdict()['ports'].split(),
                               match.groupdict()['params'])
            # Mosses should not be part of stdcells or logic library
            # causes troubles when filtering stdcells
            # if subcktname.startswith('std_'):
            #     subckt.setdesign('stdcells')
            # elif subcktname.startswith('log_'):
            #     subckt.setdesign('logic')
        else:
            subckt = Subckt(subcktname, match.groupdict()['ports'].split(),
                            match.groupdict()['params'])
        # print('in  ' + subcktname)
        return subckt

    def isEndSubckt(self):
        """isEndSubckt() returns True if the SpiceLine is the closing of a
        subckt definition, False otherwise."""
        if re.match(r'\s*[.]ends\s*', self, re.I):
            return True
        return False

    def isEnd(self):
        """isEnd() returns True if the SpiceLine is the closing of a spice
        definition, False otherwise."""
        if re.match(r'\s*[.]end\s*', self, re.I):
            return True
        return False

    def isInstance(self):
        """isInstance() returns True if the SpiceLine is the instantiation of a
        subckt (not if it is a MOS transistor), False otherwise."""
        if re.match(r'\s*(?P<name>X\S+)', self, re.I):
            # if not (self.isMosInstance() or self.isInterconnectInstance() or
            #         self.isDiodeInstance())
            if not (self.isMosInstance() or self.isInterconnectInstance()):
                return True
        return False

    def analyzeInst(self):
        """analyzeInst() tries to match a the instantiation of the subckt line,
        get ports and params out and create a Instance element.
         returns Instance element."""
        match = re.match(r'\s*(?P<name>X\S+)' +
                         r'(?P<ports>(\s+[^ =\t\n\r\f\v]+(?!\S))*)' +
                         r'(?P<subcktname>\s+[^ =\t\n\r\f\v$]+(?!\S| =))' +
                         r'(?P<params>(\s+\S+\s*[=]\s*\S+)*)\s+[$]' +
                         r'(?P<location>(\s+[$]\S+\s*[=]\s*\S+)+)', self, re.I)
        if match is None:
            match = re.match(r'\s*(?P<name>X\S+)' +
                             r'(?P<ports>(\s+[^ =\t\n\r\f\v]+(?!\S))*)' +
                             r'(?P<subcktname>\s+[^ =\t\n\r\f\v$]+(?!\S| =))' +
                             r'(?P<params>(\s+\S+\s*[=]\s*\S+)*)', self, re.I)
        if match is None:
            raise SpiceError('Instance definition in spice file is not ' +
                             'according to my expectations (line content: "' +
                             self + ')')
        location = match.groupdict().get('location', None)
        inst = Instance(match.groupdict()['name'],
                        match.groupdict()['subcktname'].strip(),
                        match.groupdict()['ports'].split(),
                        match.groupdict()['params'], location)
        # print('  + ' + match.groupdict()['name'])
        return inst

    def isMosInstance(self):
        match = re.match(r'\s*(?P<name>X\S+)' +
                         r'(?P<ports>(\s+[^ =\t\n\r\f\v]+(?!\S))+)' +
                         r'(?P<subcktname>\s+[^ =\t\n\r\f\v]+(?!\S))' +
                         r'(?P<params>(\s+\S+\s*[=]\s*\S+)*)', self, re.I)
        if not match:
            return False
        subcktname = match.groupdict()['subcktname'].strip()
        if subcktname in MOS_NAMES:
            return True
        return False

    def isDiodeInstance(self):
        match = re.match(r'\s*(?P<name>X\S+)' +
                         r'(?P<ports>(\s+[^ =\t\n\r\f\v]+(?!\S))+)' +
                         r'(?P<subcktname>\s+[^ =\t\n\r\f\v]+(?!\S))' +
                         r'(?P<params>(\s+\S+\s*[=]\s*\S+)*)', self, re.I)
        if not match:
            return False
        subcktname = match.groupdict()['subcktname'].strip()
        if subcktname in DIO_NAMES:
            return True
        return False

    def analyzeMosInstance(self):
        """analyzeMosInstance() tries to match a the instantiation of the mos
         device, get ports and params out and create a MosInstance element.
         returns MosInstance element."""
        match = re.match(r'\s*(?P<name>X\S+)' +
                         r'(?P<ports>(\s+[^ =\t\n\r\f\v]+(?!\S))+)' +
                         r'(?P<subcktname>\s+[^ =\t\n\r\f\v]+(?!\S))' +
                         r'(?P<params>(\s+\S+\s*[=]\s*\S+)*)', self, re.I)
        subcktname = match.groupdict()['subcktname'].strip()
        location = match.groupdict().get('location', None)
        if subcktname in MOS_NAMES:
            ports = match.groupdict()['ports'].split()
            assert len(ports) == 4
            noparams = match.groupdict()['params'].count('=')
            assert noparams > 1  # at least W_ and L_
            if noparams > 3:  # but no more than also M_ (default 1)
                raise ParameterMismatchError('Mos should have no more than 3' +
                                             ' parameters in definition, ' +
                                             'check and fix v2.0_LVS.sp file.')
            mosmult = '1'
            params = match.groupdict()['params']
            widthpatt = r'W_\s*[=]\s*(\S+)'
            lenghthpatt = r'L_\s*[=]\s*(\S+)'
            multpatt = r'M_\s*[=]\s*(\S+)'

            moswidth = re.search(widthpatt, params).groups()[0]
            moslength = re.search(lenghthpatt, params).groups()[0]
            mosmult = re.search(multpatt, params).groups()[0]

            mosinstance = MosInstance(match.groupdict()['name'], subcktname,
                                      ports[0], ports[1], ports[2], ports[3],
                                      moswidth, moslength, mosmult, location)
        return mosinstance

    def isDevice(self):
        """isDevice() returns True if the SpiceLine is the definition for
        a Resistor (but not Res_short), capacitor (but not Cap_parasitic),
        MOS transistor, or a Diode.
        False otherwise."""
        if re.match(r'\s*(?P<name>R\S+)', self, re.I):
            if not (self.isRes_short()):
                return True
        if re.match(r'\s*(?P<name>C\S+)', self, re.I):
            if not (self.isCap_parasitic()):
                return True
        if re.match(r'\s*(?P<name>M\S+)', self, re.I):
            return True
        if re.match(r'\s*(?P<name>D\S+)', self, re.I):
            return True
        return False

    def isRes_short(self):
        # match = re.match(r'\s*(?P<name>R\S+)' +
        #                  r'(?P<ports>(\s+[^ =\t\n\r\f\v]+(?!\S))+)' +
        #                  r'(?P<resmodel>\s+[^ =\t\n\r\f\v]+(?!\S))' +
        #                  r'(?P<params>(\s+\S+[=]\S+)*)', self, re.I)
        # circuitreducer strips away R= from R=<value>
        match = re.match(r'\s*(?P<name>R\S+)' +
                         r'(?P<ports>(\s+[^ =\t\n\r\f\v]+(?!\S))+)' +
                         r'(?P<resmodel>\s+[^ =\t\n\r\f\v]+(?!\S))' +
                         r'(?P<param>\s+(\S+\s*[=]\s*)?\S+)', self, re.I)
        if not match:
            return False
        resmodel = match.groupdict()['resmodel'].strip()
        if resmodel in RES_SHORT:
            # print('RES_SHORT: ' + self)
            return True
        return False

    def analyzeRes_short(self):
        """analyzeRes_short() tries to match a the instantiation of the
        RES_SHORT line, get ports and params out and create a Res_short
        element.
        returns Res_short element."""
        # match = re.match(r'\s*(?P<name>R\S+)' +
        #                  r'(?P<ports>(\s+[^ =\t\n\r\f\v]+(?!\S))*)' +
        #                  r'(?P<resmodel>\s+[^ =\t\n\r\f\v$]+(?!\S))' +
        #                  r'(?P<params>((\s+\S+[=])?\S+)*)\s+[$]' +
        #                  r'(?P<location>(\s+[$]\S+[=]\S+)+)', self, re.I)
        match = re.match(r'\s*(?P<name>R\S+)' +
                         r'(?P<ports>(\s+[^ =\t\n\r\f\v]+(?!\S))*)' +
                         r'(?P<resmodel>\s+[^ =\t\n\r\f\v$]+(?!\S))' +
                         r'(?P<param>\s+(\S+\s*[=]\s*)?\S+)\s+[$]' +
                         r'(?P<location>(\s+[$]\S+\s*[=]\s*\S+)+)', self, re.I)
        if match is None:
            # match = re.match(r'\s*(?P<name>R\S+)' +
            #                  r'(?P<ports>(\s+[^ =\t\n\r\f\v]+(?!\S))*)' +
            #                  r'(?P<resmodel>\s+[^ =\t\n\r\f\v$]+(?!\S))' +
            #                  r'(?P<params>(\s+\S+[=]\S+)*)', self, re.I)
            match = re.match(r'\s*(?P<name>R\S+)' +
                             r'(?P<ports>(\s+[^ =\t\n\r\f\v]+(?!\S))*)' +
                             r'(?P<resmodel>\s+[^ =\t\n\r\f\v$]+(?!\S))' +
                             r'(?P<param>\s+(\S+\s*[=]\s*)?\S+)', self, re.I)
        if match is None:
            raise SpiceError('Res_short definition in spice file is not ' +
                             'according to my expectations (line content: "' +
                             self + ')')
        assert len(match.groupdict()['ports'].split()) == 2

        location = match.groupdict().get('location', None)
        resparam = match.groupdict()['param'].split()
        assert len(resparam) == 1
        if resparam[0].find('=') == -1:
            resparam[0] = 'R=' + resparam[0]

        res = Res_short(match.groupdict()['name'],
                        match.groupdict()['resmodel'].strip(),
                        match.groupdict()['ports'].split(),
                        resparam, location)
        # print('  + ' + match.groupdict()['name'])
        return res

    def isCap_parasitic(self):
        match = re.match(r'\s*(?P<name>C\S+)' +
                         r'(?P<ports>(\s+[^ =\t\n\r\f\v]+(?!\S))+)' +
                         r'(?P<capmodel>\s+[^ =\t\n\r\f\v]+(?!\S))' +
                         r'(?P<param>\s+(\S+\s*[=]\s*)?\S+)', self, re.I)
        if not match:
            return False
        capmodel = match.groupdict()['capmodel'].strip()
        if capmodel in ['Cparasitic']:
            # print('Cparasitic: ' + self)
            return True
        return False

    def analyzeCap_parasitic(self):
        """analyzeCap_parasitic() tries to match a the instantiation of the
        Cparasitic line, get ports and params out and create a Cap_parasitic
        element.
        returns Cap_parasitic element."""
        match = re.match(r'\s*(?P<name>C\S+)' +
                         r'(?P<ports>(\s+[^ =\t\n\r\f\v]+(?!\S))*)' +
                         r'(?P<capmodel>\s+[^ =\t\n\r\f\v$]+(?!\S))' +
                         r'(?P<param>\s+(\S+\s*[=]\s*)?\S+)\s+[$]' +
                         r'(?P<location>(\s+[$]\S+\s*[=]\s*\S+)+)', self, re.I)
        if match is None:
            match = re.match(r'\s*(?P<name>C\S+)' +
                             r'(?P<ports>(\s+[^ =\t\n\r\f\v]+(?!\S))*)' +
                             r'(?P<capmodel>\s+[^ =\t\n\r\f\v$]+(?!\S))' +
                             r'(?P<param>\s+(\S+\s*[=]\s*)?\S+)', self, re.I)
        if match is None:
            raise SpiceError('Cap_parasitic definition in spice file is not ' +
                             'according to my expectations (line content: "' +
                             self + ')')
        assert len(match.groupdict()['ports'].split()) == 2

        location = match.groupdict().get('location', None)
        capparam = match.groupdict()['param'].split()
        assert len(capparam) == 1
        if capparam[0].find('=') == -1:
            capparam[0] = 'C=' + capparam[0]

        cap = Cap_parasitic(match.groupdict()['name'],
                            match.groupdict()['capmodel'].strip(),
                            match.groupdict()['ports'].split(),
                            capparam, location)
        # print('  + ' + match.groupdict()['name'])
        return cap

    def isInterconnectInstance(self):
        match = re.match(r'\s*(?P<name>X\S+)' +
                         r'(?P<ports>(\s+[^ =\t\n\r\f\v]+(?!\S))*)' +
                         r'(?P<subcktname>\s+[^ =\t\n\r\f\v$]+(?!\S))' +
                         r'(?P<params>(\s+\S+\s*[=]\s*\S+)*)', self, re.I)
        if not match:
            return False
        subcktname = match.groupdict()['subcktname'].strip()
        if subcktname in INTCON_NAMES:
            # print('InterconnectInstance: ' + self)
            return True
        return False

    def analyzeInterconnect(self):
        """analyzeInterconnect() tries to match a the instantiation of the
        InterconnectInstance line, get ports and params out and create a
        InterconnectInstance element.
        returns InterconnectInstance element."""
        match = re.match(r'\s*(?P<name>X\S+)' +
                         r'(?P<ports>(\s+[^ =\t\n\r\f\v]+(?!\S))*)' +
                         r'(?P<subcktname>\s+[^ =\t\n\r\f\v$]+(?!\S))' +
                         r'(?P<params>(\s+\S+\s*[=]\s*\S+)*)\s+[$]' +
                         r'(?P<location>(\s+[$]\S+\s*[=]\s*\S+)+)', self, re.I)
        if match is None:
            match = re.match(r'\s*(?P<name>X\S+)' +
                             r'(?P<ports>(\s+[^ =\t\n\r\f\v]+(?!\S))+)' +
                             r'(?P<subcktname>\s+[^ =\t\n\r\f\v]+(?!\S))' +
                             r'(?P<params>(\s+\S+\s*[=]\s*\S+)*)', self, re.I)
        if match is None:
            raise SpiceError('interconnect definition in spice file is not ' +
                             'according to my expectations (line content: "' +
                             self + ')')
        # ports: in, out, sub (and gnd since March 2023 PAGEFRAME was added)
        assert len(match.groupdict()['ports'].split()) in [3, 4]
        subcktname = match.groupdict()['subcktname'].strip()
        location = match.groupdict().get('location', None)

        params = match.groupdict()['params']
        noparams = params.count('=')
        assert noparams == INTCON_NOPARAMS[subcktname]
        # if subcktname == 'interconnect_WL':
        #     assert len(intparam) == INTCON_NOPARAMS[subcktname]
        # if subcktname == 'interconnect':
        #     assert len(intparam) == 2

        intcon = InterconnectInstance(match.groupdict()['name'],
                                      subcktname,
                                      match.groupdict()['ports'].split(),
                                      params, location)
        # print('  + ' + match.groupdict()['name'])
        return intcon


class SpiceNetlist():
    """class SpiceNetlist contains a full netlist, and remembers where it had
    the file from.

     Initializes with:
     >>> net = SpiceNetlist()
      or
     >>> net = SpiceNetlist(spicefilename)

     attributes:
       source  : original file location,  <class 'str'>
       netlist : line-by-line list from the source, list of SpiceLine elements

     available methods:
       read(spicefilename),
         reads spicefilename (if valid file) and stores in .text,
         updates .source accordingly
         returns None
       write(filename, [backup = True])
         writes netlist to filename and adds netlist source in comment at
         beginning of the file.
         returns None
       export2py()
         analyzes netlist,
         returns <class 'spice.PySchematic'>
       checkvalidspice()
         checks netlist for correctness to be used by export method
         returns True if valid or raises SpiceError"""

    def __init__(self, spicefilename=None, evalinclude=False,
                 caelestefolder=''):
        """Initializes with:
     >>> net = SpiceNetlist()
     or
     >>> net = SpiceNetlist(spicefilename)"""
        if spicefilename is None:
            self.netlist = []
            self.setsource(spicefilename)
        else:
            self.read(spicefilename, evalinclude=evalinclude,
                      caelestefolder=caelestefolder)
        # elif os.path.isfile(spicefilename):
        #     self.read(spicefilename)
        # else:
        #     raise()

    def __repr__(self):
        if len(self.netlist) < 5:
            return ('SpiceNetlist(netlist = %r, source = %r)' %
                    (self.netlist, self.source))
        else:
            return ('SpiceNetlist(netlist = %r, source = %r)' %
                    (self.netlist[0:4] + [' ...'], self.source))

    def importNetlistFromStr(self, inputtext, overwrite=True,
                             afterNotbefore=True, evalinclude=False,
                             caelestefolder='', path=''):
        if overwrite:
            # print('OVERWRITE!!!')
            self.netlist = []

        insertSpicelines = []
        for line in inputtext.splitlines():
            newspiceline = SpiceLine(line)
            if evalinclude and newspiceline.isInclude():
                includefilename = newspiceline.analyzeInclude()
                if os.path.split(includefilename)[0] == '':
                    includefilename = os.path.join(path, includefilename)

                includefilename = includefilename.replace('/caeleste',
                                                          caelestefolder)
                # print('actual source:' + self.getsource() + '\n')
                # print('add:' + includefilename + '\n')
                includeNetlistSpiceLines = SpiceNetlist(
                        includefilename, evalinclude, caelestefolder)
                insertSpicelines.append(SpiceLine('** begin ' + line))
                insertSpicelines += includeNetlistSpiceLines.netlist
                insertSpicelines.append(SpiceLine('**  end  ' + line))
                self.addsource(includeNetlistSpiceLines.getsource())
                # print('new source:' + self.getsource() + '\n\n')

            else:
                insertSpicelines.append(newspiceline)

        if afterNotbefore:
            # print('insertafter')
            self.netlist.extend(insertSpicelines)
        else:
            # insert after first non-comment line
            # should have no impact on PySchematic
            # print ('insertbefore')
            for i in range(len(self.netlist)):
                if not self.netlist[i].isComment():
                    # print('i: ' + str(i))
                    self.netlist[i:i] = insertSpicelines
                    break
            else:
                raise SpiceError('unexpected')

    def setsource(self, source):
        if source is None:
            self.source = ''
        else:
            self.source = source

    def addsource(self, source=''):
        self.source += ';\n**' + source

    def getsource(self):
        return self.source

    def read(self, spicefilename, overwrite=True, afterNotbefore=True,
             evalinclude=False, caelestefolder=''):
        """read(spicefilename)
     reads spicefilename (if valid file) and stores in .spicelines,
     updates .source accordingly
     returns None"""
        if overwrite:
            self.setsource(spicefilename)
        else:
            self.addsource(spicefilename)
        trylocal = False
        try:
            with open(spicefilename, 'r') as spicefile:
                inputtext = spicefile.read()
        except OSError:
            # TODO: replace hardcoded path with a setting
            #       general.trylocal() or so
            trylocal = True
            localspicefilename = spicefilename.replace(
                    r'\\dsn.silo.clst\caeleste_S', 'S:', 1)
        except FileNotFoundError:
            # TODO: replace hardcoded path with a setting
            #       general.trylocal() or so
            trylocal = True
            localspicefilename = spicefilename.replace(
                    r'\\dsn.silo.clst\caeleste_S', 'S:', 1)

        if trylocal:
            try:
                with open(localspicefilename, 'r') as spicefile:
                    inputtext = spicefile.read()
                logging.critical('Continued with local version (' +
                                 localspicefilename + ') of the ' +
                                 'following file: ' + spicefilename)
            except FileNotFoundError:
                msg = ('File ' + spicefilename + ' and ' + localspicefilename +
                       ' not found.')
                ans = input(msg + '  Continue without this file? Y/[N] : ')
                if ans not in ['y', 'Y']:
                    raise
                logging.critical('Continued with part of netlist missing ' +
                                 'because of following error: ' + msg)
                raise IncompleteNetlist

        path = os.path.split(spicefilename)[0]
        self.importNetlistFromStr(inputtext, overwrite=overwrite,
                                  afterNotbefore=afterNotbefore,
                                  evalinclude=evalinclude,
                                  caelestefolder=caelestefolder, path=path)

    def write(self, spicefilename, backup=True):
        """write(spicefilename, [backup=True])
     writes netlist to filename and adds netlist source in comment at beginning
     of the file.
     returns None"""
        general.prepare_write(spicefilename, backup)
        with open(spicefilename, 'w') as spicefile:
            spicefile.write('** Python spice.SpiceNetlist() export from ' +
                            'source: ' + self.source + '\n\n')
            for line in self.netlist:
                spicefile.write(line + '\n')

    def stripportcomment(self):
        striplines= []
        for lnum, line in enumerate(self.netlist):
            if line.isComment() and line.isSeditPortComment():
                striplines.append(lnum)
        for x in range(len(striplines)-1,-1,-1):
            self.netlist.pop(striplines[x])

    def export2py(self, nodefsubckt=False):
        """export()
     analyzes netlist,
     returns <class 'spice.PySchematic'>"""

        if (len(DEF_SUBCKT) == 0 and nodefsubckt is False):
            logging.warning('DEF_SUBCKT = [], maybe your project set-up is ' +
                            'incomplete or a bug in the software exists')
        progressend = len(self.netlist)
        pyschematic = PySchematic(self.source)
        subckt = None
        thisline = None
        lineno = 0
        # the netlist should contain one extra line to make sure all are
        # evaluated, there is a bit of a funky for loop down here (for nextline
        # in self.netlist)
        self.netlist.append(SpiceLine(''))
        print(self.netlist[-1])
        if self.checkvalidspice():
            FoundUninterpretedLineNumber = False
            warning1 = ('\nThe following spice line(s) is not interpreted,\n' +
                        'it will be ignored on autogen, wrl or autolabel.\n')
            FoundDevicesOutsideSubckt = False
            warning2 = ('\nFound devices outside of subckt, they are always ' +
                        'on top level.\n')
            FoundParamsInsideSubckt = False
            warning3 = ('\nFound parameters inside of subckt. no longer a ' +
                        'problem.\n')
            FoundNotEvaluatedInclude = False
            warning4 = ('\nThe following spice line(s) is not evaluated, ' +
                        "because the function\nsetting 'evalinclude' while " +
                        'reading the netlist was set to False.\n')

            for nextline in self.netlist:
                if lineno % 1000 == 0:
                    print('progress: ' + str(lineno) + '/' + str(progressend))
                lineno += 1
                # add support for wrapped lines (next line starting with a '+')
                if thisline is None:
                    # this happens only the very first line of the file
                    # linespan = 1
                    thisline = nextline
                    continue
                if len(nextline) > 0 and nextline[0] == '+':
                    # linespan += 1
                    thisline += SpiceLine(' ') + nextline[1:]
                    continue
                else:
                    # linestart = lineno - linespan
                    # linespan = 1
                    line = thisline
                    thisline = nextline
                if line.isBlankline():
                    # blankline: SKIP and go to next line
                    continue
                    # pass    # should work too, no?
                elif line.isComment():
                    # comment: check for proper cell/design name
                    if subckt is not None:
                        if line.isCellDesignPAGEFRAMEComment():
                            (cell, design) = line.analyzeCDPFC()
                            subckt.setrealname(cell)
                            subckt.setdesign(design)
                        elif line.isSeditCellComment():
                            cell = line.analyzeSCC()
                            subckt.setrealname(cell)
                        elif line.isSeditDesignComment():
                            design = line.analyzeSDC()
                            subckt.setdesign(design)
                elif line.isBeginSubckt():
                    subckt = line.analyzeBS()
                    # print('in ' + subckt.getname())
                elif line.isEndSubckt():
                    pyschematic.add(subckt)
                    if subckt.design is None:
                        base_elements = ['PAGEFRAME']
                        base_elements.extend(DEF_SUBCKT)
                        if subckt.getname() not in base_elements:
                            pageframewarning = (subckt.getname() +
                                                ' has no PAGEFRAME')
                            # print(pageframewarning)
                            logging.info(pageframewarning)
#                    if subckt.hasname(subckt.getrealname()):
#                        print('out ' + subckt.getname())
#                    else:
#                        print('out ' + subckt.getname() + ' [' +
#                              subckt.getrealname() + ']')
                    subckt = None
                elif line.isInstance():
                    inst = line.analyzeInst()
                    instsubcktname = inst.getsubcktname()
                    instancedsubckt = pyschematic.getSubckt(instsubcktname)
                    if instancedsubckt is not None:
                        inst.setrealsubcktname(instancedsubckt.getrealname())
                        inst.setsubcktdesign(instancedsubckt.getdesign())
                    # expand multiple instances if multiplication is 'hidden'
                    # as a parameter
                    multparams = list(filter(lambda x: x in inst.getparams(),
                                             ['M', 'm']))
                    assert len(multparams) < 2
                    # of course we can only expand in this stage if the m
                    # parameter is a hard number.  otherwise, we will keep
                    # the m parameter and do duplication during autogen.
                    if (len(multparams) == 1 and
                            inst.getparams()[multparams[0]].isnumeric()):
                        multfactor = int(inst.getparams().pop(multparams[0]))
                        allinst = []
                        for x in range(multfactor):
                            kard = '<' + str(x+1) + '>'
                            newinst = inst.duplicate()
                            newinst.setname(inst.getname() + kard)
                            allinst.append(newinst)
                    else:
                        allinst = [inst]
                    for inst in allinst:
                        if subckt is not None:
                            subckt.add(inst)
                        else:
                            pyschematic.addinstdev2top(inst)
                            FoundDevicesOutsideSubckt = True
                            warning2 += '- line ' + str(lineno) + ':\n'
                            warning2 += '{:.60}'.format(line) + '\n'
                elif line.isMosInstance():
                    try:
                        mos = line.analyzeMosInstance()
                    except:
                        errormsg = ("error in line: " + str(lineno) + ": " +
                                    line)
                        print(errormsg)
                        logging.error(errormsg)
                        raise
                    if subckt is not None:
                        # mos.setinheritedparams(subckt.params)
                        subckt.add(mos)
                    else:
                        pyschematic.addinstdev2top(mos)
                        FoundDevicesOutsideSubckt = True
                        warning2 += '- line ' + str(lineno) + ':\n'
                        warning2 += '{:.60}'.format(line) + '\n'
                elif line.isRes_short():
                    res = line.analyzeRes_short()
                    if subckt is not None:
                        # mos.setinheritedparams(subckt.params)
                        subckt.add(res)
                    else:
                        pyschematic.addinstdev2top(res)
                        FoundDevicesOutsideSubckt = True
                        warning2 += '- line ' + str(lineno) + ':\n'
                        warning2 += '{:.60}'.format(line) + '\n'
                elif line.isInterconnectInstance():
                    intcon = line.analyzeInterconnect()
                    if subckt is not None:
                        # mos.setinheritedparams(subckt.params)
                        subckt.add(intcon)
                    else:
                        pyschematic.addinstdev2top(intcon)
                        FoundDevicesOutsideSubckt = True
                        warning2 += '- line ' + str(lineno) + ':\n'
                        warning2 += '{:.60}'.format(line) + '\n'
#                elif line.isMosDevice():
#                    pass
#                elif line.isResDevice():
#                    pass
#                elif line.isCapDevice():
#                    pass
#                elif line.isDioDevice():
#                    pass
                elif line.isParam():
                    # print('paramline: ' + line)
                    params = line.analyzeParam()
                    if subckt is not None:
                        subckt.addlocalparams(params)
                        FoundParamsInsideSubckt = True
                        warning3 += '- subckt ' + subckt.getname() + ':\n'
                        warning3 += '{:.60}'.format(line) + '\n'
                    else:
                        # print('param2top: ' + repr(params))
                        pyschematic.addparams2top(params)
                elif line.isEnd():
                    if subckt is not None:
                        raise SpiceError('.end statement in the middle of ' +
                                         'subckt definition @ line ' + str(lineno))
                    else:
                        print('this .end is ignored, there should be ' +
                              'nothing after this.')
                        print('- line ' + str(lineno) + ':\n' +
                              '{:.60}'.format(line) + '\n')
                elif line.isInclude():
                    FoundNotEvaluatedInclude = True
                    spitem = Spiceitem(line)
                    warning4 += '- line ' + str(lineno) + ':\n'
                    warning4 += '{:.60}'.format(line) + '\n'
                elif line.isCap_parasitic():
                    cap = line.analyzeCap_parasitic()
                    if subckt is not None:
                        # mos.setinheritedparams(subckt.params)
                        subckt.add(cap)
                    else:
                        pyschematic.addinstdev2top(cap)
                        FoundDevicesOutsideSubckt = True
                        warning2 += '- line ' + str(lineno) + ':\n'
                        warning2 += '{:.60}'.format(line) + '\n'
                elif line.isDevice():
                    dev = Device(line)
                    if subckt is not None:
                        subckt.add(dev)
                    else:
                        pyschematic.addinstdev2top(dev)
                        FoundDevicesOutsideSubckt = True
                        warning2 += '- line ' + str(lineno) + ':\n'
                        warning2 += '{:.60}'.format(line) + '\n'
                else:
                    FoundUninterpretedLineNumber = True
                    spitem = Spiceitem(line)
                    if subckt is not None:
                        subckt.add(spitem)
                        warning1 += '- subckt ' + subckt.getname() + ':\n'
                        warning1 += '{:.60}'.format(line) + '\n'
                    else:
                        pyschematic.addinstdev2top(spitem)
                        warning1 += '- line ' + str(lineno) + ':\n'
                        warning1 += '{:.60}'.format(line) + '\n'
                        FoundDevicesOutsideSubckt = True
                        warning2 += '- line ' + str(lineno) + ':\n'
                        warning2 += '{:.60}'.format(line) + '\n'
            print('total number of lines: ' + str(lineno))
            if not(nextline.isBlankline):
                print('\nThe last spice line is not evaluated properly, ' +
                      'consider adding a newline.')

            if FoundUninterpretedLineNumber:
                if True:
                    print(warning1)
                else:
                    print('FoundUninterpretedLineNumber')
            if FoundDevicesOutsideSubckt:
                if True:
                    print(warning2)
                else:
                    print('FoundDevicesOutsideSubckt')
            if FoundParamsInsideSubckt:
                if True:
                    print(warning3)
                else:
                    print('FoundParamsInsideSubckt')
            if FoundNotEvaluatedInclude:
                if True:
                    print(warning4)
                else:
                    print('FoundNotEvaluatedInclude')
            print('')
        else:
            raise SpiceError('Invalid spice netlist for use in this toolbox')

        return pyschematic

    def checkvalidspice(self):
        """checkvalidspice()
     checks netlist for correctness to be used by export method
     returns True if valid or raises SpiceError
     """
        subcktname = None
        subckt = None
        allsubcktnames = set()
        errorlist = []
        lineno = 0
        for line in self.netlist:
            lineno += 1
            if line.isBeginSubckt():
                # there are only subckt defs in the top-level of the netlist
                if subcktname is None:
                    subckt = line.analyzeBS()
                    subcktname = subckt.getname()
                else:
                    errorlist.append('Nested subckt definition found in "' +
                                     subcktname + '" in line ' + str(lineno))

                # there are no double definitions of a subckt
                if subcktname not in allsubcktnames:
                    allsubcktnames.add(subcktname)
                else:
                    errorlist.append('Double definition of subckt "' +
                                     subcktname + '" in line ' + str(lineno))
            elif line.isEndSubckt():
                subckt = None
                subcktname = None

        if len(errorlist) != 0:
            errortext = '\n'.join(errorlist)
            raise SpiceError(errortext)
            return False
        else:
            return True


def load_settings(project):
    global USERset
    USERset.load()
    global PROJset
    PROJset.loaddefault(project)
    PROJset.load()
    projectcheck = PROJset.get_str('projectname')
    if projectcheck != project:
        warning = ('\nWARNING!! \nSelected project (' + project +
                   ') does not match the projectname defined in ' +
                   LTBsettings.projectsettings() + ' (' + projectcheck + ').')
        raise Exception(warning)


def update_DEF_SUBCKT(project):
    global DEF_SUBCKT
    #global USERset
    #global PROJset
    load_settings(project)

    caelestefolder = USERset.get_str('caelestefolder')
    filenames = []
    if PROJset.get_type('sourceincludetech') is not None:
        if PROJset.get_str('sourceincludetech').startswith('/caeleste'):
            filenames.append(PROJset.get_str('sourceincludetech').replace(
            '/caeleste', caelestefolder))
        else:
            filenames.append(LTBsettings.seditfilepath(project) +
                             PROJset.get_str('sourceincludetech'))


    if PROJset.get_type('sourceincludeproject') is not None:
        if PROJset.get_str('sourceincludeproject').startswith('/caeleste'):
            filenames.append(PROJset.get_str('sourceincludeproject').replace(
            '/caeleste', caelestefolder))
        else:
            filenames.append(LTBsettings.seditfilepath(project) +
                             PROJset.get_str('sourceincludeproject'))


    DEF_SUBCKT = []

    for filename in filenames:
        netlist = SpiceNetlist(filename, True, caelestefolder)
        pysch = netlist.export2py(nodefsubckt=True)
        for subckt in pysch.subckts:
            DEF_SUBCKT.append(subckt.name)
    print('DEF_SUBCKT: ' + str(DEF_SUBCKT))


def netlistfile(project, cellname=None, libname=None, filepath=None):
    if filepath is None:
        LTBfunctions.copynetlist_proj2ltb(project, backup=True)
        filepath = LTBsettings.seditfilepath(project)

    if cellname is None:
        spicefilename = filepath + project + '.sp'
    else:
        if libname is not None:
            spicefilename = filepath + libname + '_' + cellname + '.sp'
            if os.path.isfile(spicefilename):
                # if libname is not None and the libname_cellname.sp exists,
                # return thet spicefilename immediately.
                return spicefilename
                # otherwise, do as if libname would not be defined.

        spicefilename = filepath + cellname + '.sp'
        if not os.path.isfile(spicefilename):
            spicefilename = filepath + project + '.sp'

    return spicefilename


def netlist(project, cellname=None, libname=None, filepath=None,
            evalinclude=False):
    spicefilename = netlistfile(project, cellname, libname, filepath)
    src = SpiceNetlist(spicefilename, evalinclude)

    return src


def netlist2py(project, cellname=None, libname=None, filepath=None,
               check=True, evalinclude=False):
    src = netlist(project, cellname, libname, filepath, evalinclude)
    update_DEF_SUBCKT(project)
    pyschematic = src.export2py()

    subcktdefname = None
    if check:
        if pyschematic.hasSubckt(cellname):
            subcktdefname = cellname
        else:
            if libname is not None:
                newlibcellname = cellname + '_' + libname
                libcellname = libname + '_' + cellname
                if pyschematic.hasSubckt(newlibcellname):
                    subcktdefname = newlibcellname
                elif pyschematic.hasSubckt(libcellname):
                    subcktdefname = libcellname
                else:
                    warnname = "', '".join([cellname, newlibcellname,
                                           libcellname])
            else:
                warnname = cellname
        if subcktdefname is None:
            raise Exception("subcktdef with name(s) '" + warnname +
                            "' not found.")
        pyschematic.check(subcktdefname, True)

    return pyschematic


def netlist2fullpy(project, cellname=None, libname=None, filepath=None,
                   check=True):
    #global USERset
    #global PROJset
    load_settings(project)

    src = netlist(project, cellname, libname, filepath)

    caelestefolder = USERset.get_str('caelestefolder')
    filenames = []
    if PROJset.get_type('sourceincludetech') is not None:
        filenames.append(PROJset.get_str('sourceincludetech').replace(
            '/caeleste', caelestefolder))

    if PROJset.get_type('sourceincludeproject') is not None:
        filenames.append(PROJset.get_str('sourceincludeproject').replace(
            '/caeleste', caelestefolder))

    for filename in filenames:
        try:
            src.read(filename, overwrite=False, afterNotbefore=False,
                     evalinclude=True, caelestefolder=caelestefolder)
        except IncompleteNetlist:
            msg = 'No longer full netlist.'
            ans = input(msg + '  Continue without checking? Y/[N] : ')
            if ans not in ['y', 'Y']:
                raise
            logging.critical('Continued without checking netlist: ' + msg)
            check = False

    update_DEF_SUBCKT(project)
    try:
        fullpysch = src.export2py()
    except SpiceError:
        filepath = LTBsettings.seditfilepath(project)
        dumpfilename = filepath + cellname + '_dump.sp'
        src.write(dumpfilename)
        logging.debug('dump file stored here: ' + str(dumpfilename))
        raise

    if check:
        if fullpysch.hasSubckt(cellname):
            subcktdefname = cellname
        elif libname is not None and fullpysch.hasSubckt(libname + '_' +
                                                         cellname):
            subcktdefname = libname + '_' + cellname
        else:
            if libname is not None:
                raise Exception("subcktdef with name '" + libname + '_' +
                                cellname + "' or '" + cellname +
                                "' not found.")
            else:
                raise Exception("subcktdef with name '" + cellname +
                                "' not found.")
        try:
            fullpysch.check(subcktdefname)
        except UndefSubcktError:
            info = ('!!! Check the following files: \n ' +
                    netlistfile(project, cellname, libname, filepath) + '\n ' +
                    includetechfilename + '\n ' + includeprojectfilename)
            print(info)
            logging.info(info)
            raise

    return fullpysch


def netlist2netlist(project, cellname=None, backup=True, filepath=None):
    pyschematic = netlist2py(project, cellname, None, filepath)

    if cellname is None:
        spicefilename = (LTBsettings.pyschematicfilepath(project) + project +
                         '.spy')
    else:
        spicefilename = (LTBsettings.pyschematicfilepath(project) + cellname +
                         '.spy')

    pyschematic.export_spicefile(spicefilename, cellname, backup=backup)
    print('netlist exported to ' + spicefilename)


def netlist2trimnetlist(project, cellname=None, backup=True, filepath=None):
    pyschematic = netlist2py(project, cellname, None, filepath)

    if cellname is None:
        spicefilename = (LTBsettings.pyschematicfilepath(project) + project +
                         '.spy')
    else:
        spicefilename = (LTBsettings.pyschematicfilepath(project) + cellname +
                         '.spy')

    trimpysch = pyschematic.trim(cellname)

    trimpysch.export_spicefile(spicefilename, cellname, backup=backup)
    print('netlist exported to ' + spicefilename)


def netlist2trimnetlist_realname(project, cellname=None, libname=None,
                                 backup=True, filepath=None, force=False,
                                 evalinclude=False):
    check = not force
    pyschematic = netlist2py(project, cellname, libname, filepath,
                             check=check, evalinclude=evalinclude)

    if cellname is None:
        spicefilename = (LTBsettings.pyschematicfilepath(project) + project +
                         '.spy')
        trimpysch = pyschematic.trim(cellname)
    else:
        subcktdefname = None
        if pyschematic.hasSubckt(cellname):
            subcktdefname = cellname
        else:
            if libname is not None:
                newlibcellname = cellname + '_' + libname
                libcellname = libname + '_' + cellname
                if pyschematic.hasSubckt(newlibcellname):
                    subcktdefname = newlibcellname
                elif pyschematic.hasSubckt(libcellname):
                    subcktdefname = libcellname
                else:
                    warnname = "', '".join([cellname, newlibcellname,
                                            libcellname])
            else:
                warnname = cellname
        if subcktdefname is None:
            raise Exception("subcktdef with name(s) '" + warnname +
                            "' not found.")

        trimpysch = pyschematic.trim(subcktdefname)
        if subcktdefname != cellname:
            subckt = trimpysch.getSubckt(subcktdefname)
            subckt.name = cellname

        count = 0
        for subckt in trimpysch.subckts:
            if subckt.name == cellname:
                count += 1
        assert count == 1

        spicefilename = (LTBsettings.pyschematicfilepath(project) + cellname +
                         '.spy')

    trimpysch.export_spicefile(spicefilename, cellname, backup=backup)
    print('netlist exported to ' + spicefilename)


def netlist2fullnetlist(project, cellname=None, backup=True, filepath=None):
    pyschematic = netlist2fullpy(project, cellname, filepath=filepath)

    if cellname is None:
        spicefilename = (LTBsettings.pyschematicfilepath(project) + project +
                         '.fspy')
    else:
        spicefilename = (LTBsettings.pyschematicfilepath(project) + cellname +
                         '.fspy')

    pyschematic.export_spicefile(spicefilename, cellname, backup=backup)
    print('netlist exported to ' + spicefilename)


def netlist2autogen(project, cellname=None, backup=True, filepath=None,
                    force=False):
    # netlist2fullpy is needed in order to know all possible parameter values,
    # they are in the project-defined LVSinclude
    check = not force
    pyschematic = netlist2fullpy(project, cellname, filepath=filepath,
                                 check=check)
    # pyschematic.cache_getParamsUsedSubckt()

    if cellname is None:
        batchfilename = LTBsettings.autogenfilepath(project) + project + '.c'
    else:
        batchfilename = LTBsettings.autogenfilepath(project) + cellname + '.c'

    pyschematic.export_autogen(batchfilename, cellname, backup=backup,
                               project=project, force=force)
    print('batchfile exported to ' + batchfilename)

def netlist2check(project, cellname=None, filepath=None,
                    force=False):
    # netlist2fullpy is needed in order to know all possible parameter values,
    # they are in the project-defined LVSinclude
    check = not force
    pyschematic = netlist2fullpy(project, cellname, filepath=filepath,
                                 check=check)
    # pyschematic.cache_getParamsUsedSubckt()

    if cellname is None:
        batchfilename = LTBsettings.autogenfilepath(project) + project + '.c'
    else:
        batchfilename = LTBsettings.autogenfilepath(project) + cellname + '.c'

    errors = pyschematic.check(fullcheck=True)
    
    if errors is None:
        print('No errors detected.')
    else:
        print('The following errors were detected:')
        print(errors)


def netlist2wrl(project, cellname=None, backup=True, filepath=None,
                force=False):
    check = not force
    pyschematic = netlist2fullpy(project, cellname, filepath=filepath,
                                 check=check)

    hierarchy = True

    pyschematic.export_wrl(cellname, hierarchy, project, backup=backup)


def netlist2autolabel(project, cellname=None, backup=True, filepath=None,
                      force=False):
    check = not force
    pyschematic = netlist2py(project, cellname, filepath=filepath, check=check)

    filename = (LTBsettings.autolabelfilepath(project) + cellname +
                '_autolabel.c')

    pyschematic.export_autolabel(filename, cellname, backup=backup)


def netlist2autoplace(project, cellname, instnamerange, startx, starty, pitch,
                      backup=True, filepath=None, force=False):
    #global PROJset
    load_settings(project)

    check = not force
    pyschematic = netlist2py(project, cellname, filepath=filepath, check=check)

    temp = re.findall(r'(\S+)[[](\d+):(\d+)[\]]', instnamerange)
    instname = temp[0][0]
    rangebegin = temp[0][1]
    rangeend = temp[0][2]
    filename = (LTBsettings.autoplacefilepath(project) + cellname + '_' +
                instname + '_' + rangebegin + '_' + rangeend + '_autoplace.c')

    if (cellname.startswith('_all') and '_used_in_' in cellname and
            PROJset.get_str('radhard').lower() == 'true'):
        radhard = True
    else:
        # print(cellname + ' | ' + repr(PROJset.get_str('radhard')))
        radhard = False

    try:
        intpitch = [float(number) for number in pitch]
    except ValueError:
        raise SpiceError('pitch must be a list of base10 numbers')

    pyschematic.export_autoplace(filename, cellname, instname, int(rangebegin),
                                 int(rangeend), float(startx), float(starty),
                                 intpitch, backup=backup, radhard=radhard)


def netlist2crprepare(project, cellname, backup=True):
    filepath = LTBsettings.seditfilepath(project)
    spicefilename = filepath + cellname + '.sp'
    src = SpiceNetlist(spicefilename)
    src.stripportcomment()
    src.write(spicefilename)


def argparse_setup(subparsers):
    parser_spc_chk = subparsers.add_parser('netlist2check',
                                           help=('Checks the netlist file on ' +
                                                 'errors that would stop LVS ' +
                                                 'or autogen from working as ' +
                                                 'they should.'))
    parser_spc_chk.add_argument(
            '-p', '--project', required=True, help='the PROJECT name')
    parser_spc_chk.add_argument(
            '-c', '--cellname', default=None,
            help='the CELL name (or all cells from project.sp)')
    parser_spc_chk.add_argument(
            '-fp', '--filepath', default=None,
            help=('location of the source netlist file, default: ' +
                  'LTBsettings.seditfilepath(project)'))

    parser_spc_ag = subparsers.add_parser('netlist2autogen',
                                          help=('Creates a macro file for ' +
                                                'L-Edit that will generate ' +
                                                "the cell 'cellname' and " +
                                                'hierarchy'))
    parser_spc_ag.add_argument(
            '-p', '--project', required=True, help='the PROJECT name')
    parser_spc_ag.add_argument(
            '-c', '--cellname', default=None,
            help='the CELL name (or all cells from project.sp)')
    parser_spc_ag.add_argument(
            '-fp', '--filepath', default=None,
            help=('location of the source netlist file, default: ' +
                  'LTBsettings.seditfilepath(project)'))
    parser_spc_ag.add_argument(
            '-nobu', '--nobackup', dest='backup', default=True,
            action='store_false', help='makes no backup (anymore)')

    parser_spc_wrl = subparsers.add_parser('netlist2wrl',
                                           help=('Creates wrl (wirelist) ' +
                                                 'files for SDL in L-Edit ' +
                                                 "for the cell 'cellname' " +
                                                 'and hierarchy'))
    parser_spc_wrl.add_argument(
            '-p', '--project', required=True, help='the PROJECT name')
    parser_spc_wrl.add_argument(
            '-c', '--cellname', default=None,
            help='the CELL name (or all cells from project.sp)')
    parser_spc_wrl.add_argument(
            '-fp', '--filepath', default=None,
            help=('location of the source netlist file, default: ' +
                  'LTBsettings.seditfilepath(project)'))
    parser_spc_wrl.add_argument(
            '-nobu', '--nobackup', dest='backup', default=True,
            action='store_false', help='makes no backup (anymore)')

    parser_spc_al = subparsers.add_parser('netlist2autolabel',
                                          help=('Creates a macro file for ' +
                                                'L-Edit that will autoplace ' +
                                                "the ports of the cell '" +
                                                "cellname' on the port " +
                                                'locations based on the ' +
                                                'ports found in lower level ' +
                                                'cells'))
    parser_spc_al.add_argument(
            '-p', '--project', required=True, help='the PROJECT name')
    parser_spc_al.add_argument(
            '-c', '--cellname', required=True,
            help='the CELL name')
    parser_spc_al.add_argument(
            '-fp', '--filepath', default=None,
            help=('location of the source netlist file, default: ' +
                  'LTBsettings.seditfilepath(project)'))
    parser_spc_al.add_argument(
            '-nobu', '--nobackup', dest='backup', default=True,
            action='store_false', help='makes no backup (anymore)')

    parser_spc_ap = subparsers.add_parser('netlist2autoplace',
                                          help=('Creates a macro file for ' +
                                                'L-Edit that will autoplace ' +
                                                "the instances 'instancename" +
                                                "' of the cell 'cellname' " +
                                                'in the range begin:end in ' +
                                                'an array'))
    parser_spc_ap.add_argument(
            '-p', '--project', required=True, help='the PROJECT name')
    parser_spc_ap.add_argument(
            '-c', '--cellname', required=True,
            help='the CELL name')
    parser_spc_ap.add_argument(
            '-i', '--instnamerange', required=True,
            help='instancename[begin:end]')
    parser_spc_ap.add_argument(
            '-x', '--startx', required=True,
            help='1st element origin X-position')
    parser_spc_ap.add_argument(
            '-y', '--starty', required=True,
            help='1st element origin Y-position')
    parser_spc_ap.add_argument(
            '--pitch', default=None, type=int, nargs='+',
            help=('pitch: xstep_1 ystep_1 #_of_instances_in_this_direction_1' +
                  '       xstep_2 ystep_2 #_of_instances_in_this_direction_2'))
    parser_spc_ap.add_argument(
            '-nobu', '--nobackup', dest='backup', default=True,
            action='store_false', help='makes no backup (anymore)')

    parser_spc_prep = subparsers.add_parser(
            'netlist2crprepare', help=("Strips netlist from '* PORT=...' for " +
                                       'a smoother circuitreducer experience'))
    parser_spc_prep.add_argument(
            '-p', '--project', required=True, help='the PROJECT name')
    parser_spc_prep.add_argument(
            '-c', '--cellname', required=True, help='the CELL name')
    parser_spc_prep.add_argument(
            '-nobu', '--nobackup', dest='backup', default=True,
            action='store_false', help='makes no backup (anymore)')


def argparse_eval(args):
    # make a dict of args
    dictargs = vars(args)
    funcdict = {'netlist2check': (netlist2check,
                          [dictargs.get('project'),
                           dictargs.get('cellname'),
                           dictargs.get('filepath')]),
                'netlist2autogen': (netlist2autogen,
                                    [dictargs.get('project'),
                                     dictargs.get('cellname'),
                                     dictargs.get('backup'),
                                     dictargs.get('filepath')]),
                'netlist2wrl': (netlist2wrl,
                                [dictargs.get('project'),
                                 dictargs.get('cellname'),
                                 dictargs.get('backup'),
                                 dictargs.get('filepath')]),
                'netlist2autolabel': (netlist2autolabel,
                                      [dictargs.get('project'),
                                       dictargs.get('cellname'),
                                       dictargs.get('backup'),
                                       dictargs.get('filepath')]),
                'netlist2autoplace': (netlist2autoplace,
                                      [dictargs.get('project'),
                                       dictargs.get('cellname'),
                                       dictargs.get('instnamerange'),
                                       dictargs.get('startx'),
                                       dictargs.get('starty'),
                                       dictargs.get('pitch'),
                                       dictargs.get('backup'),
                                       dictargs.get('filepath')]),
                'netlist2crprepare': (netlist2crprepare,
                                      [dictargs.get('project'),
                                       dictargs.get('cellname'),
                                       dictargs.get('backup')]),
                }
    return funcdict


if __name__ == "__main__":
    general.logsetup()
    general.myargparse(argparse_setup, argparse_eval, 'v20240909')
