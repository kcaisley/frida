"""The drives a CDAC's plates call for, on a synthetic driver model (no characterization read)."""

from types import SimpleNamespace

from flow.caparray.subckt import CapArrayConfig
from flow.capdriver import model


def test_the_drivers_scale_with_their_plates(monkeypatch):
    """Each stage takes the weakest drive whose RC estimate settles it in the target: stronger for a
    larger plate, the strongest where none does; FRIDA-1's fabricated bands stay as set."""

    def driver(pdk, strength, *, load_f, simulate):
        return SimpleNamespace(resistance_ohm=2000.0 / strength, intrinsic_delay_s=50e-12)

    monkeypatch.setattr(model.CapDriverModel, "of", staticmethod(driver))
    monkeypatch.setattr(model, "_supply_v", lambda pdk: 1.2)
    main = (4e-12, 2e-12, 1e-12, 30e-15, 1e-15)
    diff = (0.0, 0.0, 0.0, 20e-15, 0.5e-15)
    strengths = model.derive_strengths("any", main, diff, 0.5e-12, 14)
    assert list(strengths) == sorted(strengths, reverse=True) and strengths[-1] == 1
    assert all(strength in model.STRENGTHS for strength in strengths)
    load = sum(main) + sum(diff) + 0.5e-12
    tolerance = 1.2 * (sum(main) - sum(diff)) / load / 2**14
    for strength, plate_main, plate_diff in zip(strengths, main, diff, strict=True):
        settle = model.settling_estimate_s(
            "any", strength, plate_main, plate_diff, load, 1.2, tolerance, simulate=False
        )
        assert settle <= model.SETTLING_TARGET_S
        weaker = [s for s in model.STRENGTHS if s < strength]
        if weaker:  # the weakest that does
            assert (
                model.settling_estimate_s(
                    "any", weaker[-1], plate_main, plate_diff, load, 1.2, tolerance, simulate=False
                )
                > model.SETTLING_TARGET_S
            )
    # a plate no drive settles in time takes the strongest
    assert model.derive_strengths("any", (1e-9, 1e-9), (0.0, 0.0), 0.0, 14)[0] == model.STRENGTHS[-1]
    fabricated = CapArrayConfig(driver_strengths=(4, 4, 2, 2) + (1,) * 12)
    assert model.driver_strengths("any", fabricated) == fabricated.driver_strengths
