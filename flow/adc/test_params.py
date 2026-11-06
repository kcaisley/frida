"""The ADC's parameters: a testbench's default sequencer rows are the default recipe's."""

from . import sim
from .params import TbParams


def test_the_default_rows_are_the_default_recipe():
    recipe = sim.symbol256_init8_samp16_comp11110000_logic00001111
    assert sim.AdcSequence.from_tb_params(TbParams()) == recipe
    # written out exactly, with no whitespace for the sequence to strip
    assert {name: getattr(TbParams(), name) for name in recipe.as_tb_fields()} == recipe.as_tb_fields()
