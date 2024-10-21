import re
import general
import LTBsettings


def laygenreset(outfilename=None, backup=True):
    cleartext = """
/*
* Macro name:
* Creator:
*
* Revision history:
*
*/

void laygen(){}

"""
    if outfilename is None:
        outfilename = LTBsettings.laygenfilename()
    general.write(outfilename, cleartext, backup)


def laygenstandalone2bound(standalonefilename, outfilename=None, backup=True):
    with open(standalonefilename, 'r') as sofile:
        oldCcode = sofile.read()
    # comment out module 'modulename' and opening curly bracket
    # (should be the first, not checked)
    newCcode = re.sub(r'(.*\n\s*)(module\s+\S+\s*)[{](.*)',
                      '\\1\n//\\2//{\n\\3', oldCcode, 0, re.DOTALL)
    # comment out last closing curly bracket and wrap all what is after it
    # in a laygen function wrap
    newCcode = re.sub('(.*)[}](.*)', '\\1\n//}\nvoid laygen() {\\2\n}\n',
                      newCcode, 0, re.DOTALL)
    # comment out all #/whatever/
    newCcode = re.sub('^(#.*)', '//\\1', newCcode, 0, re.M)

    if outfilename is None:
        outfilename = LTBsettings.laygenfilename()
    general.write(outfilename, newCcode, backup)


def ltbresetkeys(outfilename=None, backup=True):
    header = "\nchar* shortcut(char* function)\n{\n"

    shortcuts = []
    shortcuts.append(
            ('"texteditor"',
             '"\\"C:\\\\Program Files\\\\Notepad++\\\\notepad++.exe\\""'))
    shortcuts.append(('"macro_release_fix"', '"Ctrl+F7"'))
    shortcuts.append(('"laygenreset"', '"Shift+F7"'))
    shortcuts.append(('"shortkeyreset"', 'NULL'))

    shortcuts.append(('"export_instances"', '"F5"'))
    #shortcuts.append(('"extract_lvs_active_Calibre"', 'NULL'))
    shortcuts.append(('"extract_preprunlvs_active_Calibre1"', '"F3"'))
    shortcuts.append(('"lvs_active_Calibre_dialog"', '"Shift+F3"'))
    shortcuts.append(('"open_lvs_report_active"', '"Ctrl+F3"'))
    shortcuts.append(('"parse_open_lvs_report_active"', '"Ctrl+Shift+F3"'))
    shortcuts.append(('"add_verification_cell_lvs"', '"Alt+F3"'))
    #shortcuts.append(('"extract_drc_active_Calibre"', 'NULL'))
    shortcuts.append(('"extract_preprundrc_active_Calibre1"', '"F2"'))
    shortcuts.append(('"drc_active_Calibre_dialog"', '"Shift+F2"'))
    shortcuts.append(('"open_drc_report_active"', '"Ctrl+F2"'))
    shortcuts.append(('"add_verification_cell_drc"', '"Alt+F2"'))
    shortcuts.append(('"xor_Calibre_dialog"', 'NULL'))
    shortcuts.append(('"toggle_calibrebutton"', '"Shift+F4"'))
    shortcuts.append(('"run_cal1"', '"F4"'))
    shortcuts.append(('"extract_pex_active_Calibre"', 'NULL'))
    shortcuts.append(('"extract_preprunpex_active_Calibre1"', '"F6"'))
    shortcuts.append(('"pex_active_Calibre_dialog"', '"Shift+F6"'))
    shortcuts.append(('"snap_to_design_grid"', '"G"'))
    shortcuts.append(('"snap_to_nudge_grid"', '"Alt+G"'))
    shortcuts.append(('"laygen"', '"F7"'))
    shortcuts.append(('"ltb_options"', '"F8"'))
    shortcuts.append(('"update2newcell"', '"Ctrl+F8"'))
    shortcuts.append(('"csv2poly"', 'NULL'))
    shortcuts.append(('"csv2portbox"', 'NULL'))
    shortcuts.append(('"bp_locations"', 'NULL'))
    shortcuts.append(('"label2port"', 'NULL'))

    shortcuts.append(('"toggle_active"', '"Alt+Num 0"'))
    shortcuts.append(('"toggle_all"', '"Alt+Num Del"'))
    shortcuts.append(('"select_metal1"', '"Num 1"'))
    shortcuts.append(('"change_metal1"', '"Ctrl+Num 1"'))
    shortcuts.append(('"toggle_metal1"', '"Alt+Num 1"'))
    shortcuts.append(('"select_metal2"', '"Num 2"'))
    shortcuts.append(('"change_metal2"', '"Ctrl+Num 2"'))
    shortcuts.append(('"toggle_metal2"', '"Alt+Num 2"'))
    shortcuts.append(('"select_metal3"', '"Num 3"'))
    shortcuts.append(('"change_metal3"', '"Ctrl+Num 3"'))
    shortcuts.append(('"toggle_metal3"', '"Alt+Num 3"'))
    shortcuts.append(('"select_metal4"', '"Num 4"'))
    shortcuts.append(('"change_metal4"', '"Ctrl+Num 4"'))
    shortcuts.append(('"toggle_metal4"', '"Alt+Num 4"'))
    shortcuts.append(('"select_metal5"', '"Num 5"'))
    shortcuts.append(('"change_metal5"', '"Ctrl+Num 5"'))
    shortcuts.append(('"toggle_metal5"', '"Alt+Num 5"'))
    shortcuts.append(('"select_metal6"', '"Num 6"'))
    shortcuts.append(('"change_metal6"', '"Ctrl+Num 6"'))
    shortcuts.append(('"toggle_metal6"', '"Alt+Num 6"'))
    shortcuts.append(('"select_metal7"', '"Num 7"'))
    shortcuts.append(('"change_metal7"', '"Ctrl+Num 7"'))
    shortcuts.append(('"toggle_metal7"', '"Alt+Num 7"'))
    shortcuts.append(('"select_metal8"', '"Num 8"'))
    shortcuts.append(('"change_metal8"', '"Ctrl+Num 8"'))
    shortcuts.append(('"toggle_metal8"', '"Alt+Num 8"'))
    shortcuts.append(('"select_metal9"', '"Num 9"'))
    shortcuts.append(('"change_metal9"', '"Ctrl+Num 9"'))
    shortcuts.append(('"toggle_metal9"', '"Alt+Num 9"'))
    shortcuts.append(('"select_layeractive"', '"Num Del"'))

    shortcuts.append(('"viaIntersection"', '"Ctrl+Alt+X"'))
    shortcuts.append(('"viaDialog"', '"Ctrl+Alt+V"'))
    shortcuts.append(('"viaChangeDim"', '"Ctrl+Alt+D"'))
    shortcuts.append(('"viaChangeToSquare"', '"Ctrl+Alt+S"'))
    shortcuts.append(('"viaChangeToLine"', '"Ctrl+Alt+L"'))
    shortcuts.append(('"viaChangeToCross"', '"Ctrl+Alt+C"'))
    shortcuts.append(('"viaChangeToBig"', '"Ctrl+Alt+B"'))
    shortcuts.append(('"viaStretchUp"', '"Ctrl+Alt+U"'))
    shortcuts.append(('"viaStretchDown"', '"Ctrl+Alt+J"'))
    shortcuts.append(('"viaReduceUpwards"', '"Ctrl+Alt+I"'))
    shortcuts.append(('"viaReduceDownwards"', '"Ctrl+Alt+K"'))
    shortcuts.append(('"rotateOnOrigin"', '"Ctrl+Alt+R"'))
    shortcuts.append(('"cellCursorOnGrid"', '"Ctrl+Alt+G"'))
    shortcuts.append(('"viaResetPitch"', '"Ctrl+Alt+P"'))
    shortcuts.append(('"flipOnOrigin"', '"Ctrl+Alt+F"'))
    shortcuts.append(('"zigzagDialog"', '"Ctrl+Alt+Z"'))
    shortcuts.append(('"holes"', '"Ctrl+Alt+H"'))
    shortcuts.append(('"holesDialog"', '"Shift+Ctrl+Alt+H"'))

    shortcuts.append(('"setup_export_color_layerrender"', 'NULL'))
    shortcuts.append(('"setup_import_color_layerrender"', 'NULL'))
    shortcuts.append(('"setup_export_colorpalette_csv"', 'NULL'))
    shortcuts.append(('"setup_import_colorpalette_csv"', 'NULL'))
    shortcuts.append(('"setup_export_layerrender_csv"', 'NULL'))
    shortcuts.append(('"setup_import_layerrender_csv"', 'NULL'))
    shortcuts.append(('"setup_export_layerparams"', 'NULL'))
    shortcuts.append(('"setup_import_layerparams"', 'NULL'))
    shortcuts.append(('"setup_export_layerorder"', 'NULL'))
    shortcuts.append(('"setup_import_layerorder"', 'NULL'))
    shortcuts.append(('"setup_lib_list"', 'NULL'))
    shortcuts.append(('"setup_lib_xreflist"', 'NULL'))
    shortcuts.append(('"setup_lib_listcheck"', 'NULL'))
    shortcuts.append(('"setup_lib_listsummary"', 'NULL'))
    shortcuts.append(('"setup_lib_layersummary"', 'NULL'))
    shortcuts.append(('"setup_lib_consolidatetop"', 'NULL'))
    shortcuts.append(('"polygons2wire"', '"Shift+W"'))
    shortcuts.append(('"wireLeftDwnN"', 'NULL'))
    shortcuts.append(('"wireLeftDwnNE"', 'NULL'))
    shortcuts.append(('"wireLeftDwnE"', 'NULL'))
    shortcuts.append(('"wireLeftDwnSE"', 'NULL'))
    shortcuts.append(('"wireLeftDwnS"', 'NULL'))
    shortcuts.append(('"wireLeftDwnSW"', 'NULL'))
    shortcuts.append(('"wireLeftDwnW"', 'NULL'))
    shortcuts.append(('"wireLeftDwnNW"', 'NULL'))
    shortcuts.append(('"wireRightUpN"', 'NULL'))
    shortcuts.append(('"wireRightUpNE"', 'NULL'))
    shortcuts.append(('"wireRightUpE"', 'NULL'))
    shortcuts.append(('"wireRightUpSE"', 'NULL'))
    shortcuts.append(('"wireRightUpS"', 'NULL'))
    shortcuts.append(('"wireRightUpSW"', 'NULL'))
    shortcuts.append(('"wireRightUpW"', 'NULL'))
    shortcuts.append(('"wireRightUpNW"', 'NULL'))
    shortcuts.append(('"splitwires"', 'NULL'))
    shortcuts.append(('"wires2polygon"', 'NULL'))
    shortcuts.append(('"find_AA_Wire_from_selection"', 'NULL'))

    settingtext = header
    for (function, key) in shortcuts:
        settingtext += ("\tif (strcmp(function, " + function +
                        ") == 0)\n\t\treturn " + key + ";\n")
    settingtext += "\telse\n\t\treturn NULL;\n}\n"

    if outfilename is None:
        outfilename = LTBsettings.leditsettings()
    general.write(outfilename, settingtext, backup)


def argparse_setup(subparsers):
    parser_lay_rst = subparsers.add_parser(
            'laygenreset', help='creates an empty macro file for L-Edit to ' +
            'make sure include statements cause no failure')
    parser_lay_rst.add_argument(
            '-o', '--outfile', default=None, help='the path to the output ' +
            'file (default: ' + LTBsettings.laygenfilename() + ')')
    parser_lay_rst.add_argument(
            '--nobackup', dest='backup', default=True, action='store_false',
            help='Avoids creation of backup files of previous output files.')

    parser_lay_keys = subparsers.add_parser(
            'ltbresetkeys', help='creates a standard shortkeys file for ' +
            'L-Edit to load the default shortkeys for LTB in L-Edit')
    parser_lay_keys.add_argument(
            '-o', '--outfile', default=None, help='the path to the output ' +
            'file (default: ' + LTBsettings.leditsettings() + ')')
    parser_lay_keys.add_argument(
            '--nobackup', dest='backup', default=True, action='store_false',
            help='Avoids creation of backup files of previous output files.')

    parser_lay_s2b = subparsers.add_parser(
            'laygenstandalone2bound', help='Creates a laygen.c bound to the ' +
            'Ledit_Toolbox from the given stand-alone c code')
    parser_lay_s2b.add_argument(
            '-f', '--filename', required=True,
            help='the standalone C filename name')
    parser_lay_s2b.add_argument(
            '-o', '--outfile', default=None, help='the path to the output ' +
            'file (default: ' + LTBsettings.laygenfilename() + ')')
    parser_lay_s2b.add_argument(
            '--nobackup', dest='backup', default=True, action='store_false',
            help='Avoids creation of backup files of previous output files.')


def argparse_eval(args):
    # make a dict of args
    dictargs = vars(args)
    funcdict = {'laygenreset': (laygenreset,
                                [dictargs.get('outfile'),
                                 dictargs.get('backup')]),
                'ltbresetkeys': (ltbresetkeys,
                                 [dictargs.get('outfile'),
                                  dictargs.get('backup')]),
                'laygenstandalone2bound': (laygenstandalone2bound,
                                           [dictargs.get('filename'),
                                            dictargs.get('outfile'),
                                            dictargs.get('backup')])
                }
    return funcdict


if __name__ == "__main__":
    general.myargparse(argparse_setup, argparse_eval, 'v20231211')
