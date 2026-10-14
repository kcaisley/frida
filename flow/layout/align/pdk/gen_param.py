# ruff: noqa  -- adapted from ALIGN's Bulk65nm mock PDK (star imports, ALIGN style)
import json
import logging
import os
from collections import Counter
from copy import deepcopy
from math import ceil, floor, gcd, log, log10, sqrt

from align.compiler.util import get_generator

logger = logging.getLogger(__name__)
LOGIC = ("INV", "NAND2", "NOR2")  # user_template.sp gates drawn by logiccell.py


def limit_pairs(pairs):
    # Hack to limit aspect ratios when there are a lot of choices
    if len(pairs) > 12:
        new_pairs = []
        log10_aspect_ratios = [-0.3, 0, 0.3]
        for l in log10_aspect_ratios:
            best_pair = min((abs(log10(newy) - log10(newx) - l), (newx, newy)) for newx, newy in pairs)[1]
            new_pairs.append(best_pair)
        return new_pairs
    else:
        return pairs


def construct_sizes_from_exact_patterns(exact_patterns):

    legal_size_d = {}

    for pattern in exact_patterns:
        histo = Counter(c for row in pattern for c in row)
        num_devices = len(set(c.upper() for c in histo.keys()))
        if num_devices == 2:
            k = len(pattern[0]) // 2, len(pattern)
        else:
            k = len(pattern[0]), len(pattern)
        assert k not in legal_size_d
        legal_size_d[k] = pattern

    return legal_size_d


def check_legal(x, y, legal_sizes):
    assert legal_sizes is not None
    for d in legal_sizes:
        for tag, val in [("x", x), ("y", y)]:
            if tag in d and d[tag] != val:
                break
        else:
            return True

    return False


def fold_rows(block_name, mvalues):
    """Row counts a MOS primitive may take: one while its row is at most 1.5 times as wide as tall,
    else the even splits of its fingers from two rows up to the deepest that brings the folded
    block within 1.5 either way (the closest one if none does), so the placer chooses each
    block's shape. One row with a floorplan, whose rows are fixed, and for logic gates."""
    if os.environ.get("STEMS_STD_DENSE") or block_name.upper().startswith(LOGIC):
        return (1,)
    from pdk.mos import rowcell  # the stems engine, on the path through mos.py

    nm = lambda v: int(round(float(v) * 1e9 / 5)) * 5
    devs = [
        rowcell.Dev(name, nm(v["L"]), nm(v["W"]), int(v.get("NF", 1)) * int(v.get("M", 1)), f"d{i}", f"g{i}", "s")
        for i, (name, v) in enumerate(mvalues.items())
    ]
    nf = 0
    for v in devs:
        nf = gcd(nf, v.nf)
    aspect = {}
    for r in (r for r in range(1, nf + 1) if nf % r == 0):
        try:  # a fold too narrow for its straps (rowcell.mos_rows) is no variant
            aspect[r] = rowcell.mos_rows(block_name, "n", devs, r).width / (r * rowcell.H)
        except AssertionError:
            continue
    if aspect[1] <= 1.5:
        return (1,)
    within = [r for r, a in aspect.items() if 1 / 1.5 <= a <= 1.5]
    deepest = max(within) if within else min(aspect, key=lambda r: abs(log(aspect[r])))
    # and every shallower fold, so the placer can trade a block's width against its height
    return tuple(r for r in aspect if 2 <= r <= deepest) or (deepest,)


def add_primitive(primitives, block_name, block_args, generator_constraint, rows=(1,)):

    if block_name in primitives:
        block_args["abstract_template_name"] = block_name
        block_args["concrete_template_name"] = block_name
        if not primitives[block_name] == block_args:
            logger.warning(
                f"Distinct devices mapped to the same primitive {block_name}: \
                             existing: {primitives[block_name]}\
                             new: {block_args}"
            )
    else:
        logger.debug(f"Found primitive {block_name} with {block_args}")
        if "x_cells" in block_args and "y_cells" in block_args:
            x, y = block_args["x_cells"], block_args["y_cells"]
            pairs = set()
            m = x * y
            y_sqrt = floor(sqrt(x * y))
            # one row (a 9-track cell), or the fold_rows variants of a wide MOS primitive; a few
            # variants keep the placer's search small
            pairs.update((ceil(m / r), r) for r in rows)

            legal_size_set = None
            legal_sizes = None
            if generator_constraint is not None:
                generator_parameters = generator_constraint.parameters
                if generator_parameters is not None:
                    legal_sizes = generator_parameters.get("legal_sizes")
                    exact_patterns = generator_parameters.get("exact_patterns")
                    assert exact_patterns is None or legal_sizes is None
                    if exact_patterns is not None:
                        legal_size_set = set(construct_sizes_from_exact_patterns(exact_patterns).keys())

            if legal_size_set is None and legal_sizes is None:
                pairs = limit_pairs(pairs)  # call limit_pairs if there aren't constraints

            for newx, newy in pairs:
                if legal_sizes is not None:  # legal_sizes
                    ok = check_legal(newx, newy, legal_sizes)
                else:
                    ok = legal_size_set is None or (newx, newy) in legal_size_set

                if legal_sizes is not None or legal_size_set is not None:
                    if ok:
                        logger.debug(f"Adding matching primitive of size {newx} {newy} {generator_constraint}")
                    else:
                        logger.debug(
                            f"Not adding primitive of size {newx} {newy} because it doesn't match {generator_constraint}"
                        )

                if ok:
                    concrete_name = f"{block_name}_X{newx}_Y{newy}"
                    if concrete_name not in primitives:
                        primitives[concrete_name] = deepcopy(block_args)
                        primitives[concrete_name]["x_cells"] = newx
                        primitives[concrete_name]["y_cells"] = newy
                        primitives[concrete_name]["abstract_template_name"] = block_name
                        primitives[concrete_name]["concrete_template_name"] = concrete_name
        else:
            primitives[block_name] = block_args
            primitives[block_name]["abstract_template_name"] = block_name
            primitives[block_name]["concrete_template_name"] = block_name


def gen_param(subckt, primitives, pdk_dir):

    generator_constraint = None
    for const in subckt.constraints:
        if const.constraint == "Generator":
            assert generator_constraint is None
            generator_constraint = const

    block_name = subckt.name
    generator_name = subckt.generator["name"]
    if get_generator(generator_name, pdk_dir) and generator_name.upper() not in (
        "NMOS",
        "PMOS",
        "MOS",
        "CAP",
        "RES",
    ):  # a standard cell (stdcell.py)
        # routed through the guard-ring path, see stdcell.RingGenerator
        from pdk.stdcell import CELLS, INDEX_BASE
        from pdk.stdcell import generator_class as std_class

        cell = std_class(generator_name).cell
        primitives[block_name] = {
            "primitive": "guard_ring",
            "x_cells": INDEX_BASE + CELLS.index(cell),
            "y_cells": 1,
            "abstract_template_name": block_name,
            "concrete_template_name": block_name,
        }
        return True
    vt = subckt.elements[0].model
    values = subckt.elements[0].parameters
    generator_name = subckt.generator["name"]
    block_name = subckt.name
    logger.debug(f"Getting generator parameters for: {subckt.name}")
    generator_name = subckt.generator["name"]
    layers_json = pdk_dir / "layers.json"
    with open(layers_json, "rt") as fp:
        pdk_data = json.load(fp)
    design_config = pdk_data["design_info"]

    if len(subckt.elements) == 1:
        values = subckt.elements[0].parameters
    else:
        mvalues = {}
        for ele in subckt.elements:
            mvalues[ele.name] = ele.parameters

    if generator_name == "CAP":
        size = round(float(values["VALUE"]) * 1e15, 4)

        assert size <= design_config["max_size_cap"], (
            f"caps larger than {design_config['max_size_cap']}fF are not supported"
        )

        if "L" in values and "W" in values:
            length = round(float(values["L"]) * 1e9, 4)
            width = round(float(values["W"]) * 1e9, 4)
        else:
            # HACK for unit cap used in common centroid and support older SPICE
            length = int((sqrt(size / 2)) * 1000)
            width = int((sqrt(size / 2)) * 1000)

        # TODO: use float in name
        logger.debug(f"Generating capacitor for:{block_name}, {size}")
        block_args = {"primitive": generator_name, "value": [int(length), int(width)]}
        add_primitive(primitives, block_name, block_args, generator_constraint)

    elif generator_name == "RES":
        assert float(values["VALUE"]) or float(values["R"]), f"unidentified size {values['VALUE']} for {block_name}"
        if "R" in values:
            size = round(float(values["R"]), 2)
        elif "VALUE" in values:
            size = round(float(values["VALUE"]), 2)
        # TODO: use float in name
        if size.is_integer():
            size = int(size)
        height = ceil(sqrt(float(size) / design_config["unit_height_res"]))
        logger.debug(f"Generating resistor for: {block_name} {size}")
        block_args = {"primitive": generator_name, "value": (height, float(size))}
        add_primitive(primitives, block_name, block_args, generator_constraint)

    else:
        assert "MOS" == generator_name, f"{generator_name} is not recognized"
        if "vt_type" in design_config:
            vt = [vt.upper() for vt in design_config["vt_type"] if vt.upper() in subckt.elements[0].model]
        mvalues = {}
        for ele in subckt.elements:
            mvalues[ele.name] = ele.parameters
        device_name_all = [*mvalues.keys()]
        device_name = next(iter(mvalues))

        for key in mvalues:
            assert mvalues[key]["W"] != str, f"unrecognized size of device {key}:{mvalues[key]['W']} in {block_name}"
            width = int(float(mvalues[key]["W"]) * 1e9 / design_config["Fin_pitch"])
        name_arg = "W" + str(width)

        # if 'NF' in mvalues[device_name].keys():
        #    for key in mvalues:
        #        assert int(mvalues[key]["NF"]), f"unrecognized NF of device {key}:{mvalues[key]['NF']} in {block_name}"
        #        assert int(mvalues[key]["NF"]) % 2 == 0, f"NF must be even for device {key}:{mvalues[key]['NF']} in {block_name}"
        #    name_arg = name_arg+'_NF'+str(int(mvalues[device_name]["NF"]))

        if "M" in mvalues[device_name].keys():
            for key in mvalues:
                assert int(mvalues[key]["M"]), f"unrecognized M of device {key}:{mvalues[key]['M']} in {block_name}"
                if "PARALLEL" in mvalues[key].keys() and int(mvalues[key]["PARALLEL"]) > 1:
                    mvalues[key]["PARALLEL"] = int(mvalues[key]["PARALLEL"])
                    mvalues[key]["M"] = int(mvalues[key]["M"]) * int(mvalues[key]["PARALLEL"])
            name_arg = name_arg + "_M" + str(int(mvalues[device_name]["M"]))
            size = 0

        logger.debug(f"Generating lef for {block_name}")

        if isinstance(size, int):
            for key in mvalues:
                logic = block_name.upper().startswith(LOGIC)  # NMOS and PMOS sized independently (logiccell.py)
                assert logic or int(float(mvalues[device_name]["W"]) * 1e9) == int(float(mvalues[key]["W"]) * 1e9), (
                    f"W should be same for all devices in {block_name} {mvalues}"
                )
                size_device = int(mvalues[key]["NF"]) * int(mvalues[key]["M"])
                size = size + size_device
            no_units = ceil(
                size / (2 * len(mvalues))
            )  # Factor 2 is due to NF=2 in each unit cell; needs to be generalized
            square_y = floor(sqrt(no_units))
            while no_units % square_y != 0:
                square_y -= 1
            yval = square_y
            xval = int(no_units / square_y)

        def total_device_size(v):
            return int(float(v["W"]) * 1e9) * int(v["NF"]) * int(v["M"])

        unequal_devices = None
        if len(device_name_all) == 2:
            unequal_devices = total_device_size(mvalues[device_name_all[0]]) != total_device_size(
                mvalues[device_name_all[1]]
            )
        if unequal_devices:
            yval = 1
            xval = int(no_units)

        if generator_constraint is not None:
            generator_parameters = generator_constraint.parameters
            if generator_parameters is not None:
                exact_patterns = generator_parameters.get("exact_patterns")
                if exact_patterns is not None:
                    yval = len(exact_patterns[0])
                    xval = len(exact_patterns[0][0]) if len(device_name_all) != 2 else len(exact_patterns[0][0]) // 2

        block_args = {
            "primitive": generator_name,
            "value": width,
            "x_cells": xval,
            "y_cells": yval,
            "parameters": mvalues,
        }
        if "STACK" in mvalues[device_name].keys() and int(mvalues[device_name]["STACK"]) > 1:
            block_args["stack"] = int(mvalues[device_name]["STACK"])
        if vt:
            block_args["vt_type"] = vt[0]
        # TODO: remove name based hack
        if "SCM" in block_name and unequal_devices:
            primitives[block_name] = block_args
            primitives[block_name]["abstract_template_name"] = block_name
            primitives[block_name]["concrete_template_name"] = block_name
        else:
            add_primitive(primitives, block_name, block_args, generator_constraint, fold_rows(block_name, mvalues))
    return True
