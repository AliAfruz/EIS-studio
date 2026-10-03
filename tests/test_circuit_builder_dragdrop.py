import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PySide6.QtCore import QMimeData, QPointF, Qt
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QApplication

from eis_studio.circuit_builder import CircuitBuilderDialog, ELEMENT_MIME
from eis_studio.models import CIRCUITS, evaluate, make_custom_circuit


def _app():
    return QApplication.instance() or QApplication([])


def test_drag_add_rewire_undo_redo_and_evaluate():
    _app()
    dialog = CircuitBuilderDialog(
        CIRCUITS["R-(R||CPE)"], theme_name="dark"
    )
    try:
        initial_count = len(list(dialog._all_elements()))
        dialog._handle_topology_drop({
            "action": "add",
            "kind": "C",
            "target_uid": dialog.tree["uid"],
            "zone": "on",
        })
        added_uid = dialog._selected_uid()
        assert len(list(dialog._all_elements())) == initial_count + 1

        parallel = next(
            child for child in dialog.tree["children"]
            if child["type"] == "parallel"
        )
        target_branch = parallel["branches"][1]
        assert dialog._move_node_to_drop(
            added_uid, target_branch["uid"], "on"
        )
        assert any(
            child.get("uid") == added_uid
            for child in target_branch["children"]
        )

        dialog._undo()
        assert any(
            child.get("uid") == added_uid
            for child in dialog.tree["children"]
        )
        dialog._redo()
        parallel = next(
            child for child in dialog.tree["children"]
            if child["type"] == "parallel"
        )
        assert any(
            child.get("uid") == added_uid
            for child in parallel["branches"][1]["children"]
        )

        spec = make_custom_circuit(dialog.tree, "Drag/drop regression")
        CIRCUITS["CUSTOM"] = spec
        impedance = evaluate(
            "CUSTOM", np.array([1000.0, 10.0]), dialog.values
        )
        assert np.all(np.isfinite(impedance))
        assert dialog.element_palette.count() == 12
    finally:
        dialog.close()


def test_parallel_tile_and_start_empty_history():
    _app()
    dialog = CircuitBuilderDialog(CIRCUITS["R"], theme_name="dark")
    try:
        dialog._start_empty()
        assert list(dialog._all_elements()) == []
        dialog._handle_topology_drop({
            "action": "add",
            "kind": "PARALLEL",
            "target_uid": dialog.tree["uid"],
            "zone": "on",
        })
        assert len(list(dialog._all_elements())) == 2
        assert dialog.tree["children"][0]["type"] == "parallel"
        dialog._undo()
        assert list(dialog._all_elements()) == []
        dialog._redo()
        assert len(list(dialog._all_elements())) == 2
    finally:
        dialog.close()


def test_schematic_canvas_has_real_nodes_wires_and_free_positions():
    _app()
    dialog = CircuitBuilderDialog(CIRCUITS["R-(R||CPE)"], theme_name="dark")
    try:
        assert len(dialog.canvas.node_items) == len(list(dialog._all_elements()))
        assert len(dialog.canvas.wires) >= len(dialog.canvas.node_items)
        assert dialog.canvas.portals

        uid = next(iter(dialog.canvas.node_items))
        dialog._canvas_node_position_changed(uid, QPointF(420.0, 155.0))
        node, _, _ = dialog._find(uid)
        assert node["canvas_pos"] == [420.0, 155.0]
        assert dialog.canvas.node_items[uid].pos() == QPointF(420.0, 155.0)

        dialog._auto_layout_canvas()
        node, _, _ = dialog._find(uid)
        assert "canvas_pos" not in node
    finally:
        dialog.close()


def test_real_canvas_drop_and_magnetic_rewire():
    _app()
    dialog = CircuitBuilderDialog(CIRCUITS["R-(R||CPE)"], theme_name="dark")
    try:
        before = len(list(dialog._all_elements()))
        root_portal = next(
            portal for portal in dialog.canvas.portals
            if portal.payload.get("target_uid") == dialog.tree["uid"]
            and portal.payload.get("zone") == "on"
        )
        view_pos = dialog.canvas.mapFromScene(root_portal.scenePos())
        mime = QMimeData()
        mime.setData(ELEMENT_MIME, b"C")
        drop = QDropEvent(
            QPointF(view_pos), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier
        )
        dialog.canvas.dropEvent(drop)
        assert drop.isAccepted()
        assert len(list(dialog._all_elements())) == before + 1

        added_uid = dialog._selected_uid()
        parallel = next(
            child for child in dialog.tree["children"] if child["type"] == "parallel"
        )
        target_branch = parallel["branches"][1]
        branch_portal = next(
            portal for portal in dialog.canvas.portals
            if portal.payload.get("target_uid") == target_branch["uid"]
            and portal.payload.get("zone") == "on"
        )
        item = dialog.canvas.node_items[added_uid]
        item.setPos(branch_portal.scenePos())
        dialog.canvas.node_released(item, 100.0)
        parallel = next(
            child for child in dialog.tree["children"] if child["type"] == "parallel"
        )
        assert any(
            child.get("uid") == added_uid
            for child in parallel["branches"][1]["children"]
        )
    finally:
        dialog.close()
