"""Unit tests for the ConvexHullOverlay and coordinate projection math."""

from __future__ import annotations

from PyQt6 import QtCore
from PyQt6 import QtGui
from PyQt6 import QtWidgets
import numpy
import pytest

from pymol_copilot.gui.widgets import convex_hull_overlay


class MockCmd:
    """Mock class for the PyMOL cmd interface."""

    def __init__(self) -> None:
        """Initializes the mock interface with default camera/view parameters."""
        self.state: int = 1
        self.orthoscopic: bool = False
        self.field_of_view: float = 20.0
        # Column-major 3x3 rotation matrix (indices 0-8: identity)
        # Camera rotation origin (indices 9-11: (0, 0, -50.0))
        # Model origin (indices 12-14: (0, 0, 0))
        # Near clip plane (index 15: 10.0)
        # Far clip plane (index 16: 100.0)
        # Projection/FOV info (index 17: 20.0)
        self.view: list[float] = [
            1.0,
            0.0,
            0.0,
            0.0,
            1.0,
            0.0,
            0.0,
            0.0,
            1.0,
            0.0,
            0.0,
            -50.0,
            0.0,
            0.0,
            0.0,
            10.0,
            100.0,
            20.0,
        ]
        self.coords: list[list[float]] | None = [[0.0, 0.0, 0.0]]

    def get_state(self) -> int:
        """Returns the current state.

        Returns:
            The current active state.
        """
        return self.state

    def get_coords(
        self,
        selection: str,  # noqa: ARG002
        state: int,  # noqa: ARG002
    ) -> list[list[float]] | None:
        """Returns mock coordinates for a selection.

        Args:
            selection: Selection query name.
            state: The current active state.

        Returns:
            The coordinate list, or None.
        """
        return self.coords

    def get_view(self, output: int) -> list[float]:  # noqa: ARG002
        """Returns the current view parameters.

        Args:
            output: Formatting parameter.

        Returns:
            The 18-element camera state view list.
        """
        return self.view

    def get_setting_boolean(self, name: str) -> bool:
        """Returns the boolean value of a setting.

        Args:
            name: Name of the setting.

        Returns:
            True if setting is enabled.
        """
        if name == "orthoscopic":
            return self.orthoscopic
        return False

    def get_setting_float(self, name: str) -> float:
        """Returns the float value of a setting.

        Args:
            name: Name of the setting.

        Returns:
            The setting float value.
        """
        if name == "field_of_view":
            return self.field_of_view
        return 0.0


@pytest.fixture
def q_app() -> QtWidgets.QApplication:
    """Fixture for providing a QApplication instance.

    Returns:
        The QApplication instance.
    """
    tmp_app = QtWidgets.QApplication.instance()
    if isinstance(tmp_app, QtWidgets.QApplication):
        return tmp_app
    return QtWidgets.QApplication([])


def test_perspective_projection_center(q_app: QtWidgets.QApplication) -> None:
    """Tests that a point at the origin projects to the viewport center.

    Args:
        q_app: The QApplication fixture.
    """
    assert q_app is not None
    tmp_cmd = MockCmd()
    tmp_cmd.coords = [[0.0, 0.0, 0.0]]
    tmp_parent = QtWidgets.QWidget()
    tmp_overlay = convex_hull_overlay.ConvexHullOverlay(tmp_parent, tmp_cmd)
    tmp_overlay.resize(100, 100)

    tmp_path = tmp_overlay._calculate_hull_path(
        numpy.array(tmp_cmd.coords),
        tmp_cmd.view,
        is_ortho=False,
        fov=20.0,
        width=100,
        height=100,
        dpi=1.0,
    )
    assert tmp_path is not None
    # For a single point, calculate_hull_path returns a circular path (ellipse)
    # centered around the projected point.
    tmp_rect = tmp_path.boundingRect()
    assert abs(tmp_rect.center().x() - 50.0) < 1e-4
    assert abs(tmp_rect.center().y() - 50.0) < 1e-4


def test_perspective_vs_orthoscopic_scaling(
    q_app: QtWidgets.QApplication,
) -> None:
    """Tests orthoscopic vs perspective projection depth scaling.

    Args:
        q_app: The QApplication fixture.
    """
    assert q_app is not None
    tmp_cmd = MockCmd()
    tmp_parent = QtWidgets.QWidget()
    tmp_overlay = convex_hull_overlay.ConvexHullOverlay(tmp_parent, tmp_cmd)
    tmp_overlay.resize(100, 100)

    # 1. Perspective mode with point closer to camera (Z = 20)
    # The projected coordinate should scale with depth.
    tmp_coords = numpy.array([[5.0, 0.0, 20.0]])
    tmp_path_persp = tmp_overlay._calculate_hull_path(
        tmp_coords,
        tmp_cmd.view,
        is_ortho=False,
        fov=20.0,
        width=100,
        height=100,
        dpi=1.0,
    )
    assert tmp_path_persp is not None
    tmp_center_persp = tmp_path_persp.boundingRect().center().x()

    # 2. Orthoscopic mode with same point closer to camera (Z = -20)
    # The projected coordinate should NOT scale with depth, but remain
    # identical to the projection of a point at the rotation center (Z = -50)
    # where the orthoscopic scale is defined.
    tmp_path_ortho = tmp_overlay._calculate_hull_path(
        tmp_coords,
        tmp_cmd.view,
        is_ortho=True,
        fov=20.0,
        width=100,
        height=100,
        dpi=1.0,
    )
    assert tmp_path_ortho is not None
    tmp_center_ortho = tmp_path_ortho.boundingRect().center().x()

    # In perspective, moving closer to camera expands the view (coordinate is
    # closer to the edge, i.e., further from center).
    # Since standard camera-space X is positive (right) and maps to the right
    # of the screen (>50), in perspective it should be further to the right
    # (larger x value) than in orthoscopic mode.
    assert tmp_center_persp > tmp_center_ortho


def test_near_plane_clipping(q_app: QtWidgets.QApplication) -> None:
    """Tests that points behind the near plane are clipped correctly.

    Args:
        q_app: The QApplication fixture.
    """
    assert q_app is not None
    tmp_cmd = MockCmd()
    # Near clip is 10.0. Camera translation is (0, 0, -50).
    # So a point at (0, 0, 45.0) in model space has camera Z = -5.0.
    # Since -5.0 > -10.0, it is in front of the near clipping plane (closer to
    # the camera than near clip), so it must be clipped.
    tmp_coords = numpy.array([[0.0, 0.0, 45.0]])
    tmp_parent = QtWidgets.QWidget()
    tmp_overlay = convex_hull_overlay.ConvexHullOverlay(tmp_parent, tmp_cmd)
    tmp_overlay.resize(100, 100)

    tmp_path = tmp_overlay._calculate_hull_path(
        tmp_coords,
        tmp_cmd.view,
        is_ortho=False,
        fov=20.0,
        width=100,
        height=100,
        dpi=1.0,
    )
    assert tmp_path is None


def test_point_count_fallbacks(q_app: QtWidgets.QApplication) -> None:
    """Tests fallbacks for different point counts (1, 2, and collinear).

    Args:
        q_app: The QApplication fixture.
    """
    assert q_app is not None
    tmp_cmd = MockCmd()
    tmp_parent = QtWidgets.QWidget()
    tmp_overlay = convex_hull_overlay.ConvexHullOverlay(tmp_parent, tmp_cmd)
    tmp_overlay.resize(100, 100)

    # 1 Point -> Circle path
    tmp_coords_1 = numpy.array([[0.0, 0.0, 0.0]])
    tmp_path_1 = tmp_overlay._calculate_hull_path(
        tmp_coords_1,
        tmp_cmd.view,
        is_ortho=False,
        fov=20.0,
        width=100,
        height=100,
        dpi=1.0,
    )
    assert tmp_path_1 is not None
    assert tmp_path_1.boundingRect().width() == 20.0

    # 2 Points -> Line path (capsule)
    tmp_coords_2 = numpy.array([[0.0, 0.0, 0.0], [5.0, 0.0, 0.0]])
    tmp_path_2 = tmp_overlay._calculate_hull_path(
        tmp_coords_2,
        tmp_cmd.view,
        is_ortho=False,
        fov=20.0,
        width=100,
        height=100,
        dpi=1.0,
    )
    assert tmp_path_2 is not None

    # 3 Collinear Points -> Graceful fallback path (line loop)
    tmp_coords_collinear = numpy.array(
        [[0.0, 0.0, 0.0], [5.0, 0.0, 0.0], [10.0, 0.0, 0.0]]
    )
    tmp_path_collinear = tmp_overlay._calculate_hull_path(
        tmp_coords_collinear,
        tmp_cmd.view,
        is_ortho=False,
        fov=20.0,
        width=100,
        height=100,
        dpi=1.0,
    )
    assert tmp_path_collinear is not None


def test_invalid_selection_lifecycle(q_app: QtWidgets.QApplication) -> None:
    """Tests selection lifecycle handling with invalid selection names.

    Args:
        q_app: The QApplication fixture.
    """
    assert q_app is not None
    tmp_cmd = MockCmd()

    # Mock get_coords raising error for invalid selection
    def mock_get_coords_error(sel: str, state: int) -> None:  # noqa: ARG001
        raise Exception("Selection does not exist")

    tmp_cmd.get_coords = mock_get_coords_error  # type: ignore

    tmp_parent = QtWidgets.QWidget()
    tmp_overlay = convex_hull_overlay.ConvexHullOverlay(tmp_parent, tmp_cmd)
    tmp_overlay.resize(100, 100)
    tmp_overlay.set_selection("nonexistent_selection")

    # Call paintEvent to trigger coordinate lookup
    tmp_overlay.paintEvent(QtGui.QPaintEvent(QtCore.QRect(0, 0, 100, 100)))

    # Should clear cache and not crash
    assert tmp_overlay._cached_coords_3d is None
    assert tmp_overlay._cached_path is None


def test_coordinate_clustering(q_app: QtWidgets.QApplication) -> None:
    """Tests density-based coordinate clustering.

    Args:
        q_app: The QApplication fixture.
    """
    assert q_app is not None
    tmp_cmd = MockCmd()
    tmp_parent = QtWidgets.QWidget()
    tmp_overlay = convex_hull_overlay.ConvexHullOverlay(tmp_parent, tmp_cmd)

    # Coordinates with two clusters: one at origin, one panned far away (>12Å)
    tmp_coords = numpy.array(
        [[0.0, 0.0, 0.0], [1.0, 1.0, 1.0], [50.0, 50.0, 50.0]]
    )
    tmp_clusters = tmp_overlay._cluster_coordinates(tmp_coords, eps=12.0)
    assert len(tmp_clusters) == 2
    # Verify contents of clusters
    assert any(len(tmp_c) == 2 for tmp_c in tmp_clusters)
    assert any(len(tmp_c) == 1 for tmp_c in tmp_clusters)

    # Coordinates within 12Å of each other (should form 1 cluster)
    tmp_coords_single = numpy.array(
        [[0.0, 0.0, 0.0], [5.0, 5.0, 5.0], [10.0, 10.0, 10.0]]
    )
    tmp_clusters_single = tmp_overlay._cluster_coordinates(
        tmp_coords_single, eps=12.0
    )
    assert len(tmp_clusters_single) == 1


def test_multi_cluster_path_rendering(
    q_app: QtWidgets.QApplication,
) -> None:
    """Tests projection and rendering of multiple coordinate clusters.

    Args:
        q_app: The QApplication fixture.
    """
    assert q_app is not None
    tmp_cmd = MockCmd()
    tmp_parent = QtWidgets.QWidget()
    tmp_overlay = convex_hull_overlay.ConvexHullOverlay(tmp_parent, tmp_cmd)
    tmp_overlay.resize(100, 100)

    # Two spatially distinct points, each forming its own single-point cluster
    tmp_coords = numpy.array([[0.0, 0.0, 0.0], [50.0, 50.0, 50.0]])
    tmp_path = tmp_overlay._calculate_hull_path(
        tmp_coords,
        tmp_cmd.view,
        is_ortho=False,
        fov=20.0,
        width=100,
        height=100,
        dpi=1.0,
    )
    assert tmp_path is not None
    # The path bounding rect should span both circles
    tmp_rect = tmp_path.boundingRect()
    assert tmp_rect.width() > 0
    assert tmp_rect.height() > 0
