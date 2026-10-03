import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PySide6.QtWidgets import QApplication

from eis_studio.circuit_builder import CircuitBuilderDialog, tree_for_spec
from eis_studio.circuit_lab import identifiability_map, local_element_sensitivity
from eis_studio.dc_series_lab import global_fit_dc_series
from eis_studio.models import CIRCUITS, default_custom_values, evaluate_custom_tree


def _app():
    return QApplication.instance() or QApplication([])


def test_live_monitor_sensitivity_and_direct_port_connection(tmp_path):
    _app()
    spec = CIRCUITS["R-C"]
    tree = tree_for_spec(spec)
    values = default_custom_values(tree)
    frequency = np.logspace(5, -1, 45)
    measured = evaluate_custom_tree(tree, frequency, values)
    dialog = CircuitBuilderDialog(
        spec,
        values,
        theme_name="dark",
        frequencies=frequency,
        measured_impedance=measured,
    )
    try:
        assert dialog.live_monitor.embedded
        assert dialog.right_tabs.indexOf(dialog.live_monitor) == 0
        assert dialog.right_tabs.currentWidget() is not dialog.live_monitor
        dialog._show_live_monitor()
        assert dialog.right_tabs.currentWidget() is dialog.live_monitor
        assert len(dialog.live_monitor.simulated) == 280
        assert dialog.live_monitor.plot.measured.size == measured.size
        sensitivity = local_element_sensitivity(tree, values, 1000.0)
        assert sensitivity and np.isclose(max(sensitivity.values()), 1.0)

        dialog._handle_topology_drop({
            "action": "add",
            "kind": "W",
            "target_uid": dialog.tree["uid"],
            "zone": "on",
        })
        elements = list(dialog._all_elements())
        capacitor = next(element for element in elements if element["kind"] == "C")
        warburg = next(element for element in elements if element["kind"] == "W")
        source = dialog.canvas.node_items[warburg["uid"]]
        target = dialog.canvas.node_items[capacitor["uid"]]
        dialog.canvas.begin_port_wire(source, "right", source.port_scene("right"))
        dialog.canvas.update_port_wire(target.port_scene("left"))
        dialog.canvas.end_port_wire(target.port_scene("left"))
        assert [child["kind"] for child in dialog.tree["children"]] == ["R", "W", "C"]

        svg = tmp_path / "publication.svg"
        pdf = tmp_path / "publication.pdf"
        dialog.canvas.export_schematic(svg)
        dialog.canvas.export_schematic(pdf)
        assert svg.stat().st_size > 1000
        assert pdf.stat().st_size > 1000
    finally:
        dialog.close()


def test_identifiability_map_marks_every_element():
    tree = tree_for_spec(CIRCUITS["R-(R||CPE)"])
    values = default_custom_values(tree)
    states, details = identifiability_map(
        tree, values, np.logspace(5, -2, 36), stderr={}
    )
    element_uids = {str(element["uid"]) for element in _walk(tree)}
    assert set(states) == element_uids
    assert set(details) == element_uids
    assert set(states.values()) <= {"good", "warning", "bad"}


def test_same_side_terminal_gesture_creates_parallel_block():
    _app()
    dialog = CircuitBuilderDialog(CIRCUITS["R-C"], theme_name="dark")
    try:
        resistor, capacitor = list(dialog._all_elements())
        dialog._handle_port_connection({
            "source_uid": resistor["uid"],
            "source_side": "left",
            "target_uid": capacitor["uid"],
            "target_side": "left",
        })
        assert len(dialog.tree["children"]) == 1
        parallel = dialog.tree["children"][0]
        assert parallel["type"] == "parallel"
        assert [branch["children"][0]["kind"] for branch in parallel["branches"]] == ["R", "C"]
    finally:
        dialog.close()


def _walk(container):
    for child in container.get("children", []):
        if child.get("type") == "element":
            yield child
        elif child.get("type") == "parallel":
            for branch in child.get("branches", []):
                yield from _walk(branch)


def test_global_dc_series_shared_and_smooth_recovery():
    tree = tree_for_spec(CIRCUITS["R-(R||C)"])
    frequency = np.logspace(4, -1, 55)
    potentials = np.array([-0.25, 0.0, 0.25])
    rct_values = np.array([220.0, 330.0, 470.0])
    studies = []
    for potential, rct in zip(potentials, rct_values):
        values = {"Rs": 12.0, "Rct": float(rct), "Cdl": 2.4e-5}
        studies.append({
            "potential": float(potential),
            "frequency": frequency,
            "impedance": evaluate_custom_tree(tree, frequency, values),
            "source": f"synthetic_{potential:+.2f}V",
        })
    result = global_fit_dc_series(
        tree,
        studies,
        {"Rs": 18.0, "Rct": 300.0, "Cdl": 4e-5},
        {"Rs": "shared", "Rct": "smooth", "Cdl": "shared"},
        smooth_strength=1e-4,
    )
    assert result.success
    assert np.allclose(result.parameter_values["Rs"], 12.0, rtol=.02)
    assert np.allclose(result.parameter_values["Cdl"], 2.4e-5, rtol=.03)
    assert np.allclose(result.parameter_values["Rct"], rct_values, rtol=.04)
    assert np.max(result.rmse) < 1.0
