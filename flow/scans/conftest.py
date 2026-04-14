"""Pytest configuration for flow/scans tests."""


def pytest_collection_modifyitems(items):
    """Remove non-cocotb tests incorrectly collected by the cocotb Testbench.

    The cocotb pytest plugin's Testbench collector (extends Module) picks up
    all test_* functions from the test module, including hw tests that aren't
    cocotb tests. This creates duplicates that fail with TCP timeouts.
    Keep only sim_* functions under Testbench nodes.
    """
    items[:] = [item for item in items if type(item.parent).__name__ != "Testbench" or item.name.startswith("sim_")]
