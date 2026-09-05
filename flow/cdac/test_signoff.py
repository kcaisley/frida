"""Source-structure checks for the replaced layout flow."""

from pathlib import Path


def test_removed_workflow_globals_and_pin_adapters_do_not_return() -> None:
    repository = Path(__file__).resolve().parents[2]
    sources = "\n".join(
        (repository / path).read_text(encoding="utf-8")
        for path in (
            "flow/adc/layout.py",
            "flow/adc/laygen.py",
            "flow/cdac/layout.py",
            "flow/cdac/laygen.py",
        )
    )
    for removed in (
        "REPOSITORY_ROOT",
        "FRIDA_2_TOP_CELL",
        "FRIDA_2_CDAC_PLACEHOLDER",
        "ADC_BLOCK_DRC_UNSELECT",
        "_OLD_MAIN_PIN",
        "_OLD_DIFF_PIN",
        "_NEW_MAIN_PIN",
        "_NEW_DIFF_PIN",
        "LAYOUT_TARGETS",
        "PROFILES",
        "_calc_lvs_source",
        "_calc_mom_lvs_source",
    ):
        assert removed not in sources
