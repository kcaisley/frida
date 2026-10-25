"""The layout compiler's netlist check (``flow/layout/lint.py``), on a made-up PDK."""

from __future__ import annotations

import pytest

from flow.layout import lint

MANIFEST = {
    "models": {"n": "nfet_row", "p": "pfet_row"},
    "cells": {"inv_1": ["y", "a", "vdd", "vss"]},
}


def messages(text: str, severity: str | None = None) -> list[tuple[int | None, str, str]]:
    result = lint.check(text, MANIFEST)
    return [
        (item.get("line"), item["rule"], item["message"])
        for item in result.diagnostics
        if severity is None or item["severity"] == severity
    ]


def test_the_example_is_clean_and_normalizes_to_nanometres() -> None:
    result = lint.check(lint.example(MANIFEST), MANIFEST)
    assert result.ok and result.diagnostics == [] and result.top == "ota5t"
    stats = {item["label"]: item["value"] for item in result.stats}
    assert (stats["NMOS"], stats["PMOS"], stats["Internal nets"]) == (3, 2, 2)
    assert stats["Gate area"] == pytest.approx(4 * 1 + 4 * 0.5 * 4)
    normalized = lint.normalize(result)
    assert "Mtail tail vbn vss vss nfet_row w=4000n l=1000n nf=2" in normalized
    assert normalized.startswith(".subckt ota5t inp inn out vbn vdd vss\n")


def test_continuations_comments_and_ng_are_read() -> None:
    text = """* a comment
.subckt inv a y vdd vss ; inline comment
Mn y a vss vss nfet_row w=1u
+ l=150n ng=2 $ fingers
Mp y a vdd vdd pfet_row w=2u l=150n
.ends
.end
"""
    result = lint.check(text, MANIFEST)
    assert result.ok, result.diagnostics
    assert result.devices[0].params == {"w": pytest.approx(1e-6), "l": pytest.approx(150e-9), "nf": 2}


def test_what_the_flow_cannot_lay_out_is_an_error_on_its_line() -> None:
    text = """.subckt bad a y vdd vss
.include models.sp
R1 a y 1k
Mn y a vss vss nch w=1u l=1u
Mp y a vdd vdd pfet_row l=1u
Mn y a vdd vdd pfet_row w=1u l=1u
X1 y a vdd inv_1
X2 y a vdd vss nand9
.ends
"""
    errors = {(line, rule) for line, rule, _ in messages(text, "error")}
    assert errors == {
        (2, "statement"),
        (3, "element"),
        (4, "model"),
        (5, "size"),
        (6, "duplicate"),
        (7, "pins"),
        (8, "cell"),
    }


def test_supplies_and_hierarchy_are_required_as_the_rows_need_them() -> None:
    rules = {rule for _, rule, _ in messages(".subckt a x y\nMn x y gnd gnd nfet_row w=1u l=1u\n.ends\n", "error")}
    assert rules == {"supplies"}
    two = ".subckt a x vdd vss\n.ends\n.subckt b x vdd vss\nMn x x vss vss nfet_row w=1u l=1u\n.ends\n"
    assert any(rule == "hierarchy" for _, rule, _ in messages(two, "error"))
    assert any(rule == "empty" for _, rule, _ in messages(".subckt a x vdd vss\n.ends\n", "error"))
    assert any(rule == "syntax" for _, rule, _ in messages("Mn x x vss vss nfet_row w=1u l=1u\n"))


def test_connectivity_warnings_name_the_net_and_the_device() -> None:
    text = """.subckt c a out unused vdd vss
Mn out a vss gnd nfet_row w=1u l=1u
Mp out a vdd vdd pfet_row w=1u l=1u
Mg x float vss vss nfet_row w=1u l=1u
Mcap a out a vss nfet_row w=1u l=1u
.ends
"""
    warnings = messages(text, "warning")
    assert any(rule == "port" and "port unused" in message for _, rule, message in warnings)
    assert any(rule == "bulk" and "gnd" in message for _, rule, message in warnings)
    assert any(rule == "floating" and "net float connects only to Mg's g" in message for _, rule, message in warnings)
    assert any(rule == "shorted" for _, rule, _ in messages(text, "info"))
    assert lint.check(text, MANIFEST).ok  # warnings do not stop the flow


def test_numbers_take_spice_scales() -> None:
    assert lint.number("2meg") == pytest.approx(2e6)
    assert lint.number("0.5u") == pytest.approx(5e-7)
    assert lint.number("4e-6") == pytest.approx(4e-6)
    assert lint.number("{w}") is None


def test_statistics_read_w_per_finger_where_the_pdk_writes_it() -> None:
    per_finger = {**MANIFEST, "w_per_finger": True}
    example = lint.example(per_finger)
    assert "w=2u l=1u nf=2" in example and "one finger's width" in example
    stats = {item["label"]: item["value"] for item in lint.check(example, per_finger).stats}
    # the same devices as the total-width example: 2 fingers of 2 um each
    assert stats["Gate area"] == pytest.approx(4 * 1 + 4 * 0.5 * 4)
    assert stats["Total width"] == pytest.approx(5 * 4)
