# -*- coding: utf-8 -*-

# import pytest
import spice


def test_Params_strValUnit_nodot():
    """Check round params in autogen files"""
    param = spice.Params({'testval': '16'})
    assert param.strValUnit_nodot('testval') == '16'
    param['testval'] = '16.666666666666668'
    assert param.strValUnit_nodot('testval') == '16667m'
    param['testval'] = '33.333333333333336'
    assert param.strValUnit_nodot('testval') == '33333m'
    param['testval'] = '24.09090909090909'
    assert param.strValUnit_nodot('testval') == '24091m'
    param['testval'] = '108.33333333333333'
    assert param.strValUnit_nodot('testval') == '108'
    param['testval'] = '333.33333333333337'
    assert param.strValUnit_nodot('testval') == '333'
    param['testval'] = '391850e-9'
    assert param.strValUnit_nodot('testval') == '392u'
    param['testval'] = '391.85e-6'
    assert param.strValUnit_nodot('testval') == '392u'
    param['testval'] = '0.00039185'
    assert param.strValUnit_nodot('testval') == '392u'
    param['testval'] = '0.00000039185'
    assert param.strValUnit_nodot('testval') == '392n'
    param['testval'] = '392000000'
    assert param.strValUnit_nodot('testval') == '392Meg'
    param['testval'] = '392000000000'
    assert param.strValUnit_nodot('testval') == '392G'

    param['testval'] = '0.039185e-15'
    assert param.strValUnit_nodot('testval') == '39.2a'
    param['testval'] = '0.00039185e-15'
    assert param.strValUnit_nodot('testval') == '0.392a'
    param['testval'] = '0.0000039185e-15'
    assert param.strValUnit_nodot('testval') == '0.00392a'

    param['testval'] = '0.039185e-18'
    assert param.strValUnit_nodot('testval') == '0.0392a'
    param['testval'] = '0.00039185e-18'
    assert param.strValUnit_nodot('testval') == '0.000392a'
    param['testval'] = '0.0000039185e-18'
    assert param.strValUnit_nodot('testval') == '0.00000392a'

    param['testval'] = '1.0230039185e-15'
    assert param.strValUnit_nodot('testval') == '1023a'
    param['testval'] = '1.0280039185e-15'
    assert param.strValUnit_nodot('testval') == '1028a'

    param['testval'] = '1.0230039185e-18'
    assert param.strValUnit_nodot('testval') == '1.02a'
    param['testval'] = '1.0280039185e-18'
    assert param.strValUnit_nodot('testval') == '1.03a'

    param['testval'] = '1.02888039185e15'
    assert param.strValUnit_nodot('testval') == '1029T'
    param['testval'] = '1.02888039185e16'
    assert param.strValUnit_nodot('testval') == '10289T'
    param['testval'] = '4.0'
    assert param.strValUnit_nodot('testval') == '4'
    param['S'] = '4.0'
    assert param.strValUnit_nodot('S') == '4'


def test_Params_strValUnit_milli_case():
    """Check param evaluation in netlist files"""
    param = spice.Params({'testval': '16'})
    assert param.strValUnit_nodot('testval') == '16'
    param['testval'] = '16667m'
    assert param.strValUnit_nodot('testval') == '16667m'
    param['testval'] = '16667M'
    assert param.strValUnit_nodot('testval') == '16667m'


def test_Params_strValUnit_femto_case():
    """Check param evaluation in netlist files"""
    param = spice.Params({'testval': '16'})
    assert param.strValUnit_nodot('testval') == '16'
    param['testval'] = '16667f'
    assert param.strValUnit_nodot('testval') == '16667f'
    param['testval'] = '16667F'
    assert param.strValUnit_nodot('testval') == '16667f'


def test_Params_strValUnit_pico_case():
    """Check param evaluation in netlist files"""
    param = spice.Params({'testval': '16'})
    assert param.strValUnit_nodot('testval') == '16'
    param['testval'] = '16667p'
    assert param.strValUnit_nodot('testval') == '16667p'
    param['testval'] = '16667P'
    assert param.strValUnit_nodot('testval') == '16667p'


def test_Params_strValUnit_meg_case():
    """Check param evaluation in netlist files"""
    param = spice.Params({'testval': '16'})
    assert param.strValUnit_nodot('testval') == '16'
    param['testval'] = '16667Meg'
    assert param.strValUnit_nodot('testval') == '16667Meg'
    param['testval'] = '16667MEG'
    assert param.strValUnit_nodot('testval') == '16667Meg'


def test_Params_isNumValExp():
    """Check param evaluation in netlist files"""
    param = spice.Params({'testval': '16'})
    assert not param.isNumValExp('testval')
    param['testval'] = '16667e10'
    assert param.isNumValExp('testval')
    param['testval'] = '1.6667e10'
    assert param.isNumValExp('testval')
    param['testval'] = '1.6Meg'
    assert not param.isNumValExp('testval')


def test_Params_isNumValUnit():
    """Check param evaluation in netlist files"""
    param = spice.Params({'testval': '16'})
    assert not param.isNumValUnit('testval')
    param['testval'] = '16667e10'
    assert not param.isNumValUnit('testval')
    param['testval'] = '1.6667e10'
    assert not param.isNumValUnit('testval')
    param['testval'] = '1.6f'
    assert param.isNumValUnit('testval')
    param['testval'] = '1.6p'
    assert param.isNumValUnit('testval')
    param['testval'] = '1.6n'
    assert param.isNumValUnit('testval')
    param['testval'] = '1.6u'
    assert param.isNumValUnit('testval')
    param['testval'] = '1.6m'
    assert param.isNumValUnit('testval')
    param['testval'] = '1.6k'
    assert param.isNumValUnit('testval')
    param['testval'] = '1.6G'
    assert param.isNumValUnit('testval')
    param['testval'] = '1.6T'
    assert param.isNumValUnit('testval')
    param['testval'] = '1.6F'
    assert param.isNumValUnit('testval')
    param['testval'] = '1.6P'
    assert param.isNumValUnit('testval')
    param['testval'] = '1.6N'
    assert param.isNumValUnit('testval')
    param['testval'] = '1.6U'
    assert param.isNumValUnit('testval')
    param['testval'] = '1.6M'
    assert param.isNumValUnit('testval')
    param['testval'] = '1.6K'
    assert param.isNumValUnit('testval')
    param['testval'] = '1.6g'
    assert param.isNumValUnit('testval')
    param['testval'] = '1.6t'
    assert param.isNumValUnit('testval')
    param['testval'] = '1.6Meg'
    assert param.isNumValUnit('testval')
    param['testval'] = '1.6MEG'
    assert param.isNumValUnit('testval')
    param['testval'] = '2u'
    assert param.isNumValUnit('testval')


def test_Params_numValUnit():
    """Check param evaluation in netlist files"""
    param = spice.Params({'testval': '1.6f'})
    assert param.numValUnit('testval') == (float(1.6) * 10 ** -15, '')
    param = spice.Params({'testval': '1.6fV'})
    assert param.numValUnit('testval') == (float(1.6) * 10 ** -15, 'V')
    param = spice.Params({'testval': '1.6F'})
    assert param.numValUnit('testval') == (float(1.6) * 10 ** -15, '')
    param = spice.Params({'testval': '1.6FV'})
    assert param.numValUnit('testval') == (float(1.6) * 10 ** -15, 'V')
    param = spice.Params({'testval': '1.6m'})
    assert param.numValUnit('testval') == (float(1.6) * 10 ** -3, '')
    param = spice.Params({'testval': '1.6mV'})
    assert param.numValUnit('testval') == (float(1.6) * 10 ** -3, 'V')
    param = spice.Params({'testval': '1.6M'})
    assert param.numValUnit('testval') == (float(1.6) * 10 ** -3, '')
    param = spice.Params({'testval': '1.6MV'})
    assert param.numValUnit('testval') == (float(1.6) * 10 ** -3, 'V')
    param = spice.Params({'testval': '1.6Meg'})
    assert param.numValUnit('testval') == (float(1.6) * 10 ** 6, '')
    param = spice.Params({'testval': '1.6MegV'})
    assert param.numValUnit('testval') == (float(1.6) * 10 ** 6, 'V')
    param = spice.Params({'testval': '1.6MEG'})
    assert param.numValUnit('testval') == (float(1.6) * 10 ** 6, '')
    param = spice.Params({'testval': '1.6MEGV'})
    assert param.numValUnit('testval') == (float(1.6) * 10 ** 6, 'V')
    param = spice.Params({'testval': '2u'})
    assert param.numValUnit('testval') == (float(2) * 10 ** -6, '')


def test_Params_strValUnit():
    """Check param evaluation in netlist files"""
    param = spice.Params({'testval': '1.6f'})
    assert param.strValUnit('testval') == ('1.6e-15', '')
    param = spice.Params({'testval': '1.6fV'})
    assert param.strValUnit('testval') == ('1.6e-15', 'V')
    param = spice.Params({'testval': '1.6F'})
    assert param.strValUnit('testval') == ('1.6e-15', '')
    param = spice.Params({'testval': '1.6FV'})
    assert param.strValUnit('testval') == ('1.6e-15', 'V')
    param = spice.Params({'testval': '1.6m'})
    assert param.strValUnit('testval') == ('1.6e-3', '')
    param = spice.Params({'testval': '1.6mV'})
    assert param.strValUnit('testval') == ('1.6e-3', 'V')
    param = spice.Params({'testval': '1.6M'})
    assert param.strValUnit('testval') == ('1.6e-3', '')
    param = spice.Params({'testval': '1.6MV'})
    assert param.strValUnit('testval') == ('1.6e-3', 'V')
    param = spice.Params({'testval': '1.6Meg'})
    assert param.strValUnit('testval') == ('1.6e6', '')
    param = spice.Params({'testval': '1.6MegV'})
    assert param.strValUnit('testval') == ('1.6e6', 'V')
    param = spice.Params({'testval': '1.6MEG'})
    assert param.strValUnit('testval') == ('1.6e6', '')
    param = spice.Params({'testval': '1.6MEGV'})
    assert param.strValUnit('testval') == ('1.6e6', 'V')
    param = spice.Params({'testval': '2u'})
    assert param.strValUnit('testval') == ('2e-6', '')


def test_Params_isNumeric():
    param = spice.Params({'testval': '2*S'})
    assert not param.isNumeric('testval')
    param = spice.Params({'testval': 'S*2'})
    assert not param.isNumeric('testval')
    param = spice.Params({'testval': '2u'})
    assert param.isNumeric('testval')
    param = spice.Params({'testval': '6.75u'})
    assert param.isNumeric('testval')
    param = spice.Params({'testval': '4e-07'})
    assert param.isNumeric('testval')
    param = spice.Params({'testval': '1'})
    assert param.isNumeric('testval')


def test_Params_strValUnit_nodot_big():
    """Check round params in autogen files"""
    param = spice.Params({'testval': '16'})
    param['testval'] = '1.02888039185e17'
    assert param.strValUnit_nodot('testval') == '102888T'


def test_isInterconnect():
    line = spice.SpiceLine(
        'Xinterconnect_1 sh_ro N_1 sub interconnect C=4p R=4k')
    assert line.isInterconnectInstance()


def test_ports_subckt_without_dollar():
    line = spice.SpiceLine(
        '.subckt inv_balanced in out sub vdd vss gnd S=1')
    assert line.isBeginSubckt()
    subckt = line.analyzeBS()
    # print('ports: ' + str(subckt.ports))
    subcktports = ['in', 'out', 'sub', 'vdd', 'vss', 'gnd']
    assert len(subckt.ports) == len(subcktports)
    for x in range(len(subckt.ports)):
        assert subckt.ports[x] == subcktports[x]


def test_ports_subckt_with_dollar():
    line = spice.SpiceLine(
        '.subckt ASPIrdac10 reg<0> reg<1> reg<2> reg<3> reg<4> reg<5> reg<6> reg<7> reg<8> reg<9> reg<10> reg<11> ' +
        'reg<12> reg<13> reg<14> reg<15> reg<16> reg<17> $ Bondpad="name" Dac="reg" Strength="reg" Mode="reg"')
    assert line.isBeginSubckt()
    subckt = line.analyzeBS()
    # print('ports: ' + str(subckt.ports))
    subcktports = ['reg<0>', 'reg<1>', 'reg<2>', 'reg<3>', 'reg<4>', 'reg<5>', 'reg<6>', 'reg<7>', 'reg<8>', 'reg<9>',
                   'reg<10>', 'reg<11>', 'reg<12>', 'reg<13>', 'reg<14>', 'reg<15>', 'reg<16>', 'reg<17>']
    assert len(subckt.ports) == len(subcktports)
    for x in range(len(subckt.ports)):
        assert subckt.ports[x] == subcktports[x]


def test_params_subckt_no_params_without_dollar():
    line = spice.SpiceLine(
        '.subckt inv_balanced in out sub vdd vss gnd')
    assert line.isBeginSubckt()
    subckt = line.analyzeBS()
    # print('params: '+ str(subckt.params))
    assert len(subckt.params) == 0


def test_params_subckt_no_params_with_dollar():
    line = spice.SpiceLine(
        '.subckt ASPIrdac10 reg<0> reg<1> reg<2> reg<3> reg<4> reg<5> reg<6> reg<7> reg<8> reg<9> reg<10> reg<11> ' +
        'reg<12> reg<13> reg<14> reg<15> reg<16> reg<17> $ Bondpad="name" Dac="reg" Strength="reg" Mode="reg"')
    assert line.isBeginSubckt()
    subckt = line.analyzeBS()
    # print('params: '+ str(subckt.params))
    assert len(subckt.params) == 0


def test_params_subckt_with_params_without_dollar():
    line = spice.SpiceLine(
        '.subckt inv_balanced in out sub vdd vss gnd R=3 S=1 ')
    assert line.isBeginSubckt()
    subckt = line.analyzeBS()
    # print('params: '+ str(subckt.params))
    subcktparams = ['S', 'R']
    assert len(subckt.params) == len(subcktparams)
    for x in subckt.params:
        assert x in subcktparams


def test_params_subckt_with_params_without_dollar_2():
    line = spice.SpiceLine(
        '.subckt switch_np_cbalanced A B sub swN swP vcc vee gnd S=1')
    assert line.isBeginSubckt()
    subckt = line.analyzeBS()
    # print('params: '+ str(subckt.params))
    subcktparams = ['S']
    assert len(subckt.params) == len(subcktparams)
    for x in subckt.params:
        assert x in subcktparams


def test_params_subckt_with_params_with_dollar():
    line = spice.SpiceLine(
        '.subckt ASPIrdac10 reg<0> reg<1> reg<2> reg<3> reg<4> reg<5> reg<6> reg<7> reg<8> reg<9> reg<10> reg<11> ' +
        'reg<12> reg<13> reg<14> reg<15> reg<16> reg<17> S=1 R=3 $ Bondpad="name" Dac="reg" Strength="reg" Mode="reg"')
    assert line.isBeginSubckt()
    subckt = line.analyzeBS()
    # print('params: '+ str(subckt.params))
    subcktparams = ['S', 'R']
    assert len(subckt.params) == len(subcktparams)


def test_ports_instance_without_dollar():
    line = spice.SpiceLine('Xinv_balanced_1 N_2 N_3 sub vdd vss gnd inv_balanced S=Su')
    assert line.isInstance()
    instance = line.analyzeInst()
    instanceports = ['N_2', 'N_3', 'sub', 'vdd', 'vss', 'gnd']
    assert len(instance.ports) == len(instanceports)
    for x in range(len(instance.ports)):
        assert instance.ports[x] == instanceports[x]


def test_ports_instance_with_dollar():
    line = spice.SpiceLine(
        'XASPIrdac10_1 bit_ref_tia_dac<0> bit_ref_tia_dac<1> bit_ref_tia_dac<2> bit_ref_tia_dac<3> bit_ref_tia_dac<4>' +
        ' bit_ref_tia_dac<5> bit_ref_tia_dac<6> bit_ref_tia_dac<7> bit_ref_tia_dac<8> bit_ref_tia_dac<9> ' +
        'bit_ref_tia_str<0> bit_ref_tia_str<1> bit_ref_tia_str<2> bit_ref_tia_str<3> bit_ref_tia_str<4> ' +
        'bit_ref_tia_mode<0> bit_ref_tia_mode<1> bit_ref_tia_mode<2> ASPIrdac10 $ Bondpad="REF_TIA" ' +
        'Dac="bit_ref_tia_dac" Strength="bit_ref_tia_str" Mode="bit_ref_tia_mode"')
    assert line.isInstance()
    instance = line.analyzeInst()
    instanceports = [
        'bit_ref_tia_dac<0>', 'bit_ref_tia_dac<1>', 'bit_ref_tia_dac<2>', 'bit_ref_tia_dac<3>', 'bit_ref_tia_dac<4>',
        'bit_ref_tia_dac<5>', 'bit_ref_tia_dac<6>', 'bit_ref_tia_dac<7>', 'bit_ref_tia_dac<8>', 'bit_ref_tia_dac<9>',
        'bit_ref_tia_str<0>', 'bit_ref_tia_str<1>', 'bit_ref_tia_str<2>', 'bit_ref_tia_str<3>', 'bit_ref_tia_str<4>',
        'bit_ref_tia_mode<0>', 'bit_ref_tia_mode<1>', 'bit_ref_tia_mode<2>']
    assert len(instance.ports) == len(instanceports)
    for x in range(len(instance.ports)):
        assert instance.ports[x] == instanceports[x]

def test_analyze_inst_nospaceinparam():
    line = spice.SpiceLine('Xnmosfet_Rbalanced_3 reset_avg preset_videoin reference sub nmosfet_Rbalanced S=4')
    assert line.isInstance()
    instance = line.analyzeInst()
    assert instance.subcktname == 'nmosfet_Rbalanced'

def test_analyze_inst_spaceinparam():
    line = spice.SpiceLine('Xnmosfet_Rbalanced_3 reset_avg preset_videoin reference sub nmosfet_Rbalanced S =4')
    assert line.isInstance()
    instance = line.analyzeInst()
    assert instance.subcktname == 'nmosfet_Rbalanced'

