# -*- coding: utf-8 -*-

import pytest
import general as general


def list_of_float(calcretval):
    assert isinstance(calcretval, list)
    for x in calcretval:
        assert isinstance(x, float)
    return True


def test_calc_operators():
    """Check proper calculation of expressions"""
    expr = '14-14+5'
    calcretval = general.calc(expr)
    assert calcretval[0] == eval(expr)
    assert list_of_float(calcretval)
    expr = '14-14*5'
    calcretval = general.calc(expr)
    assert calcretval[0] == eval(expr)
    assert list_of_float(calcretval)
    expr = '14-14+5-5+6'
    calcretval = general.calc(expr)
    assert calcretval[0] == eval(expr)
    assert list_of_float(calcretval)
    expr = '14-14+5-5+6-6'
    calcretval = general.calc(expr)
    assert calcretval[0] == eval(expr)
    assert list_of_float(calcretval)
    expr = '14/14+5/5+6/6'
    calcretval = general.calc(expr)
    assert calcretval[0] == eval(expr)
    assert list_of_float(calcretval)
    expr = '14*14'
    calcretval = general.calc(expr)
    assert calcretval[0] == eval(expr)
    assert list_of_float(calcretval)
    expr = '14**2'
    calcretval = general.calc(expr)
    assert calcretval[0] == eval(expr)
    assert list_of_float(calcretval)
    expr = '14*2'
    calcretval = general.calc(expr)
    assert calcretval[0] == eval(expr)
    assert list_of_float(calcretval)
    expr = '14*2/7'
    calcretval = general.calc(expr)
    assert calcretval[0] == eval(expr)
    assert list_of_float(calcretval)
    expr = '14**2/7'
    calcretval = general.calc(expr)
    assert calcretval[0] == eval(expr)
    assert list_of_float(calcretval)
    expr = '2*7**2/7'
    calcretval = general.calc(expr)
    assert calcretval[0] == eval(expr)
    assert list_of_float(calcretval)
    expr = '2*49/7'
    calcretval = general.calc(expr)
    assert calcretval[0] == eval(expr)
    assert list_of_float(calcretval)
    expr = '(2*7)**2/7'
    calcretval = general.calc(expr)
    assert calcretval[0] == eval(expr)
    assert list_of_float(calcretval)
    expr = '5**2'
    calcretval = general.calc(expr)
    assert calcretval[0] == eval(expr)
    assert list_of_float(calcretval)
    expr = '5**2*2'
    calcretval = general.calc(expr)
    assert calcretval[0] == eval(expr)
    assert list_of_float(calcretval)
    expr = '5**2**2'
    calcretval = general.calc(expr)
    assert calcretval[0] == eval(expr)
    assert list_of_float(calcretval)
    expr = '5**4'
    calcretval = general.calc(expr)
    assert calcretval[0] == eval(expr)
    assert list_of_float(calcretval)
    expr = '25**2'
    calcretval = general.calc(expr)
    assert calcretval[0] == eval(expr)
    assert list_of_float(calcretval)
    expr = '5**2**3'
    calcretval = general.calc(expr)
    assert calcretval[0] == eval(expr)
    assert list_of_float(calcretval)
    expr = '25**3'
    calcretval = general.calc(expr)
    assert calcretval[0] == eval(expr)
    assert list_of_float(calcretval)
    expr = '2**3'
    calcretval = general.calc(expr)
    assert calcretval[0] == eval(expr)
    assert list_of_float(calcretval)
    expr = '5**8'
    calcretval = general.calc(expr)
    assert calcretval[0] == eval(expr)
    assert list_of_float(calcretval)
    expr = '9++5'
    calcretval = general.calc(expr)
    assert calcretval[0] == eval(expr)
    assert list_of_float(calcretval)
    expr = '9+-5'
    calcretval = general.calc(expr)
    assert calcretval[0] == eval(expr)
    assert list_of_float(calcretval)


def test_calc_orig_wrong_division():
    expr = '14*14/5*5'
    calcretval = general.calc(expr)
    assert calcretval[0] == eval(expr)
    assert list_of_float(calcretval)


def test_calc_orig_wrong_negative():
    expr = '9--5'
    calcretval = general.calc(expr)
    assert calcretval[0] == eval(expr)
    assert list_of_float(calcretval)
    expr = '9*-5'
    calcretval = general.calc(expr)
    assert calcretval[0] == eval(expr)
    assert list_of_float(calcretval)


def test_calc_names_unknown_exctype():
    expr = 'koen*2'
    with pytest.raises(general.CalcError):
        general.calc(expr)
    expr = 'log_Cacc_1pF_W*5/14'
    with pytest.raises(general.CalcError):
        general.calc(expr)


def test_calc_names_unknown_excargs():
    expr = 'koen*2'
    with pytest.raises(general.CalcError) as excinfo:
        general.calc(expr)
    print(dir(excinfo))
    print(excinfo.type)
    print(excinfo.value)
    print(excinfo.value.__class__)
    print(dir(excinfo.value))
    print(excinfo.value.args)
    assert excinfo.value.args == (['?', 'koen'],)
    assert excinfo.value.args[0] == ['?', 'koen']
    assert excinfo.value.args[0][0] == '?'
    assert excinfo.value.args[0][1] == 'koen'

    expr = 'log_Cacc_1pF_W*5/14'
    with pytest.raises(general.CalcError) as excinfo:
        general.calc(expr)
    assert excinfo.value.args == (['?', 'log_Cacc_1pF_W'],)


def test_calc_valunit_exctype():
    expr = '10n'
    with pytest.raises(general.CalcError):
        general.calc(expr)
    expr = '10+20n'
    with pytest.raises(general.CalcError):
        general.calc(expr)


def test_calc_valunit_excargs():
    expr = '10n'
    with pytest.raises(general.CalcError) as excinfo:
        general.calc(expr)
    assert excinfo.value.args == (['?', '10n'],)
    assert excinfo.value.args[0] == ['?', '10n']
    assert excinfo.value.args[0][0] == '?'
    assert excinfo.value.args[0][1] == '10n'

    expr = '10+20n'
    with pytest.raises(general.CalcError) as excinfo:
        general.calc(expr)
    assert excinfo.value.args == (['?', '20n'],)

    expr = '14 +46+ 15Meg + 15'
    with pytest.raises(general.CalcError) as excinfo:
        general.calc(expr)
    assert excinfo.value.args == (['?', '15Meg'],)

    expr = '14 +46+15Meg+ 15'
    with pytest.raises(general.CalcError) as excinfo:
        general.calc(expr)
    assert excinfo.value.args == (['?', '15Meg'],)


def test_calc_synterr_find_operand():
    assert general.calc_synterr_find_operand('10n', 3) == '10n'
    assert general.calc_synterr_find_operand('10+20n', 6) == '20n'


def test_calc_with_namevaluedict_str():
    expr = 'log_Cacc_1pF_W*5/14'
    namevaluedict = {'log_Cacc_1pF_W': '24.7u', '24.7u': '24.7e-6'}

    calcretval = general.calc(expr, namevaluedict, verbose=1)
    assert calcretval[0] == eval('24.7e-6*5/14')
    assert list_of_float(calcretval)


def test_calc_with_namevaluedict_num():
    expr = 'log_Cacc_1pF_W*5/14'
    namevaluedict = {'log_Cacc_1pF_W': '24.7u', '24.7u': 24.7e-6}

    calcretval = general.calc(expr, namevaluedict, verbose=1)
    assert calcretval[0] == eval('24.7e-6*5/14')
    assert list_of_float(calcretval)


def test_calc_with_namevaluedict_liststr():
    expr = 'log_Cacc_1pF_W*5/14'
    namevaluedict = {'log_Cacc_1pF_W': '24.7u', '24.7u': ['24.7e-6']}

    calcretval = general.calc(expr, namevaluedict, verbose=1)
    assert calcretval[0] == eval('24.7e-6*5/14')
    assert list_of_float(calcretval)


def test_calc_with_namevaluedict_listnum():
    expr = 'log_Cacc_1pF_W*5/14'
    namevaluedict = {'log_Cacc_1pF_W': '24.7u', '24.7u': [24.7e-6]}

    calcretval = general.calc(expr, namevaluedict, verbose=1)
    assert calcretval[0] == eval('24.7e-6*5/14')
    assert list_of_float(calcretval)


def test_calc_with_namevaluedict_multipleval():
    expr = 'log_Cacc_1pF_W*5/14'
    namevaluedict = {'log_Cacc_1pF_W': ['24.7u', '49.4u'],
                     '24.7u': '24.7e-6',
                     '49.4u': '49.4e-6'}

    calcretval = general.calc(expr, namevaluedict, verbose=1)
    assert eval('24.7e-6*5/14') in calcretval
    assert eval('49.4e-6*5/14') in calcretval
    assert list_of_float(calcretval)


def test_calc_with_namevaluedict_multipleval_sort():
    expr = 'log_Cacc_1pF_W*5/14'
    namevaluedict = {'log_Cacc_1pF_W': ['50u', '24.7u', '49.4u'],
                     '24.7u': 24.7e-6,
                     '49.4u': '49.4e-6',
                     '50u': ['50e-6']}

    calcretval = general.calc(expr, namevaluedict, verbose=1)
    assert eval('24.7e-6*5/14') == calcretval[0]
    assert eval('49.4e-6*5/14') == calcretval[1]
    assert eval('50e-6*5/14') == calcretval[2]
    assert list_of_float(calcretval)


def test_calc_with_namevaluedict_multipleval_sort_v2():
    expr = 'log_Cacc_1pF_W*5/14'
    namevaluedict = {'log_Cacc_1pF_W': ['50u', '24.7u', '49.4u'],
                     '24.7u': 24.7e-6,
                     '49.4u': '49.4e-6',
                     '50u': ['50e-6']}

    calcretval = general.calc(expr, namevaluedict, verbose=2)
    assert eval('24.7e-6*5/14') == calcretval[0]
    assert eval('49.4e-6*5/14') == calcretval[1]
    assert eval('50e-6*5/14') == calcretval[2]
    assert list_of_float(calcretval)


def test_calc_with_namevaluedict_2multipleval_sort():
    expr = 'log_Cacc_1pF_W/log_Cacc_1pF_L'
    namevaluedict = {'log_Cacc_1pF_W': ['50u', '24.7u', '49.4u'],
                     'log_Cacc_1pF_L': ['15u', '7u'],
                     '24.7u': 24.7e-6,
                     '49.4u': '49.4e-6',
                     '50u': ['50e-6'],
                     '7u': 7e-6,
                     '15u': 15e-6}

    calcretval = general.calc(expr, namevaluedict, verbose=2)
    assert len(calcretval) == 6
    assert list_of_float(calcretval)


def test_calc_with_namevaluedict_2mulitpleval_sort():
    expr = 'log_Cacc_1pF_W/log_Cacc_1pF_L'
    namevaluedict = {'log_Cacc_1pF_W': ['50u', '24.7u', '49.4u'],
                     'log_Cacc_1pF_L': ['14u', '7u'],
                     '24.7u': 24.7e-6,
                     '49.4u': '49.4e-6',
                     '50u': ['50e-6'],
                     '7u': 7e-6,
                     '14u': 14e-6}

    calcretval = general.calc(expr, namevaluedict, verbose=2)
    assert len(calcretval) == 5
    assert list_of_float(calcretval)


def test_fancy_float():
    expr = '10*1e-6'
    calcretval = general.calc(expr, verbose=2)
    assert eval('1e-5') == calcretval[0]
    assert list_of_float(calcretval)


def test_calc_with_brackets():
    expr = '(6.9u-0.9u)/2'
    namevaluedict = {'6.9u': 6.9e-6,
                     '0.9u': 0.9e-6}
    calcretval = general.calc(expr, namevaluedict, verbose=2)
    assert eval('3e-6') == calcretval[0]
    assert list_of_float(calcretval)
