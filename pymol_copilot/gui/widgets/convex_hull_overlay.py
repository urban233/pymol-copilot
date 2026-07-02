"""Convex hull overlay widget for highlighting PyMOL selections."""

from __future__ import annotations

import logging
import math
import typing
from typing import override

from PyQt6 import QtCore
from PyQt6 import QtGui
from PyQt6 import QtWidgets
import numpy
import scipy.spatial

from pymol_copilot.gui.qt import styles
from pymol_copilot.gui.qt.widgets import flyout


FLYOUT_MIN_HULL_SCREEN_AREA_PX: int = 2500


class ConvexHullOverlay(QtWidgets.QWidget):
    """Transparent overlay for drawing a 2D convex hull of a PyMOL selection."""

    accept_clicked = QtCore.pyqtSignal(int, str)
    reject_clicked = QtCore.pyqtSignal(int, str)

    def __init__(
        self, parent: QtWidgets.QWidget, cmd_instance: typing.Any
    ) -> None:
        """Initializes the overlay widget.

        Args:
            parent: The parent widget (typically PyMOLGLWidget).
            cmd_instance: The PyMOL command interface (cmd).
        """
        super().__init__(parent)
        self._cmd: typing.Any = cmd_instance
        self._selection_name: str = ""
        self._color: QtGui.QColor = QtGui.QColor(0, 255, 0, 80)
        self._border_color: QtGui.QColor = QtGui.QColor(0, 255, 0, 255)
        self._border_width: int = 2

        # Cache variables
        self._cached_coords_3d: numpy.ndarray | None = None
        self._cached_selection: str = ""
        self._cached_state: int = -1
        self._cached_view: list[float] | None = None
        self._cached_is_ortho: bool = False
        self._cached_fov: float = 0.0
        self._cached_w: int = 0
        self._cached_h: int = 0
        self._cached_dpi: float = 0.0
        self._cached_path: QtGui.QPainterPath | None = None

        # Flyout list and debounce state
        self._flyouts: list[flyout.FloatingFlyout] = []
        self._cached_camera_view: list[float] | None = None

        # Configure timers on main thread
        self._poll_timer = QtCore.QTimer(self)
        self._poll_timer.setInterval(100)
        self._poll_timer.timeout.connect(self._poll_camera)

        self._debounce_timer = QtCore.QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.timeout.connect(self._on_camera_still)

        # Setup flags for transparency and mouse event pass-through
        self.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True
        )
        self.setAutoFillBackground(False)

    def set_selection(self, selection_name: str) -> None:
        """Sets the PyMOL selection to highlight.

        Args:
            selection_name: The name of the PyMOL selection.
        """
        if selection_name == self._selection_name:
            return

        if not selection_name:
            self.cleanup()
            self.update()
            return

        tmp_current_state = int(self._cmd.get_state())
        try:
            tmp_coords = self._cmd.get_coords(
                selection_name, state=tmp_current_state
            )
            if tmp_coords is not None:
                tmp_coords_3d = numpy.array(tmp_coords)
            else:
                tmp_coords_3d = None
        except Exception:
            tmp_coords_3d = None

        if tmp_coords_3d is not None and len(tmp_coords_3d) > 0:
            tmp_clusters = self._cluster_coordinates(tmp_coords_3d, eps=12.0)
            tmp_n = len(tmp_clusters)
        else:
            tmp_n = 0

        # Synchronize flyout widget list size
        while len(self._flyouts) > tmp_n:
            tmp_flyout = self._flyouts.pop()
            tmp_flyout.hide()
            tmp_flyout.deleteLater()

        while len(self._flyouts) < tmp_n:
            tmp_parent = self.parentWidget()
            assert tmp_parent is not None
            tmp_flyout = flyout.FloatingFlyout(tmp_parent)
            tmp_flyout.adjustSize()
            self._flyouts.append(tmp_flyout)

        # Fresh signal reconnection capturing correct parameters
        for tmp_idx, tmp_flyout in enumerate(self._flyouts):
            try:
                tmp_flyout.accepted.disconnect()
                tmp_flyout.rejected.disconnect()
            except (TypeError, RuntimeError):
                pass

            tmp_flyout.accepted.connect(
                lambda idx=tmp_idx, sel=selection_name: (
                    self.accept_clicked.emit(idx, sel)
                )
            )
            tmp_flyout.rejected.connect(
                lambda idx=tmp_idx, sel=selection_name: (
                    self.reject_clicked.emit(idx, sel)
                )
            )

        self._selection_name = selection_name
        self._poll_timer.start()
        self.update()

    def set_colors(
        self, fill_color: QtGui.QColor, border_color: QtGui.QColor
    ) -> None:
        """Sets the colors of the overlay.

        Args:
            fill_color: Semi-transparent color to fill the hull.
            border_color: Color of the hull border.
        """
        self._color = fill_color
        self._border_color = border_color
        # Invalidate view cache to force repaint with new colors
        self._cached_view = None
        self.update()

    def paintEvent(  # noqa: N802
        self,
        event: QtGui.QPaintEvent,  # noqa: ARG002
    ) -> None:
        """Paints the convex hull on top of the parent widget.

        Args:
            event: The paint event object.
        """
        if not self._selection_name:
            return

        tmp_current_state = int(self._cmd.get_state())
        tmp_coords_changed = False

        if (
            self._selection_name != self._cached_selection
            or tmp_current_state != self._cached_state
            or self._cached_coords_3d is None
        ):
            try:
                # state=current_state retrieves the coordinates for the
                # active frame/state
                tmp_coords = self._cmd.get_coords(
                    self._selection_name, state=tmp_current_state
                )
                if tmp_coords is not None:
                    self._cached_coords_3d = numpy.array(tmp_coords)
                else:
                    self._cached_coords_3d = None
            except Exception as tmp_err:
                logging.getLogger(__name__).warning(
                    "Failed to fetch coordinates for selection '%s': %s",
                    self._selection_name,
                    tmp_err,
                )
                self._cached_coords_3d = None

            self._cached_selection = self._selection_name
            self._cached_state = tmp_current_state
            tmp_coords_changed = True

        if self._cached_coords_3d is None or len(self._cached_coords_3d) == 0:
            self._cached_path = None
            return

        try:
            tmp_view = list(self._cmd.get_view(output=1))
            tmp_is_ortho = bool(self._cmd.get_setting_boolean("orthoscopic"))
            # Index 17 contains FOV/ortho flag.
            tmp_view_17 = float(tmp_view[17])
            if abs(tmp_view_17) > 1.0:
                tmp_fov = abs(tmp_view_17)
            else:
                tmp_fov = float(self._cmd.get_setting_float("field_of_view"))
        except Exception:
            return

        try:
            tmp_viewport = self._cmd.get_viewport()
            tmp_viewport_w = int(tmp_viewport[0])
            tmp_viewport_h = int(tmp_viewport[1])
        except Exception:
            tmp_viewport_w = int(self.width() * self.devicePixelRatioF())
            tmp_viewport_h = int(self.height() * self.devicePixelRatioF())

        tmp_parent = self.parentWidget()
        tmp_fb_scale = float(getattr(tmp_parent, "fb_scale", 1.0))
        tmp_w = int(tmp_viewport_w / tmp_fb_scale)
        tmp_h = int(tmp_viewport_h / tmp_fb_scale)
        tmp_dpi = tmp_fb_scale

        # Check if cache is still valid
        tmp_cache_valid = (
            not tmp_coords_changed
            and self._cached_view is not None
            and self._cached_view == tmp_view
            and self._cached_is_ortho == tmp_is_ortho
            and self._cached_fov == tmp_fov
            and self._cached_w == tmp_w
            and self._cached_h == tmp_h
            and self._cached_dpi == tmp_dpi
            and self._cached_path is not None
        )

        if not tmp_cache_valid:
            self._cached_view = tmp_view
            self._cached_is_ortho = tmp_is_ortho
            self._cached_fov = tmp_fov
            self._cached_w = tmp_w
            self._cached_h = tmp_h
            self._cached_dpi = tmp_dpi
            self._cached_path = self._calculate_hull_path(
                self._cached_coords_3d,
                tmp_view,
                tmp_is_ortho,
                tmp_fov,
                tmp_w,
                tmp_h,
                tmp_dpi,
            )

        if self._cached_path is None:
            return

        tmp_painter = QtGui.QPainter(self)
        tmp_painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        tmp_painter.fillPath(self._cached_path, QtGui.QBrush(self._color))
        tmp_pen = QtGui.QPen(self._border_color, float(self._border_width))
        tmp_painter.setPen(tmp_pen)
        tmp_painter.drawPath(self._cached_path)
        tmp_painter.end()

    def _cluster_coordinates(
        self, coords: numpy.ndarray, eps: float
    ) -> list[numpy.ndarray]:
        """Clusters 3D coordinates using density-based spatial clustering.

        Uses a fast BFS connected-components algorithm equivalent to DBSCAN
        with min_samples=1, grouping coordinates that are within the eps
        cutoff of each other.

        Args:
            coords: A numpy.ndarray of shape (N, 3) containing 3D coordinates.
            eps: The spatial distance threshold (epsilon) for clustering.

        Returns:
            A list of numpy.ndarray coordinate clusters.
        """
        tmp_n = len(coords)
        if tmp_n == 0:
            return []

        # Calculate pairwise Euclidean distances between all points
        # shape: (N, N, 3) -> (N, N)
        tmp_diff = coords[:, numpy.newaxis, :] - coords[numpy.newaxis, :, :]
        tmp_dists = numpy.linalg.norm(tmp_diff, axis=2)

        # Adjacency list: indices of neighbors for each point (distance <= eps)
        tmp_adj = [
            numpy.where(tmp_dists[tmp_i] <= eps)[0] for tmp_i in range(tmp_n)
        ]

        tmp_visited = numpy.zeros(tmp_n, dtype=bool)
        tmp_clusters = []

        for tmp_i in range(tmp_n):
            if tmp_visited[tmp_i]:
                continue

            # Perform BFS to find connected component (cluster)
            tmp_cluster_indices = []
            tmp_queue = [tmp_i]
            tmp_visited[tmp_i] = True

            while tmp_queue:
                tmp_curr = tmp_queue.pop(0)
                tmp_cluster_indices.append(tmp_curr)

                for tmp_neighbor in tmp_adj[tmp_curr]:
                    if not tmp_visited[tmp_neighbor]:
                        tmp_visited[tmp_neighbor] = True
                        tmp_queue.append(tmp_neighbor)

            tmp_clusters.append(coords[tmp_cluster_indices])

        return tmp_clusters

    def _calculate_hull_path(
        self,
        coords_3d: numpy.ndarray,
        view: list[float],
        is_ortho: bool,
        fov: float,
        width: int,
        height: int,
        dpi: float,
    ) -> QtGui.QPainterPath | None:
        """Projects 3D points and constructs the 2D path.

        Args:
            coords_3d: The 3D coordinate array.
            view: The 18-element list representing camera state.
            is_ortho: True if orthoscopic projection is active.
            fov: The vertical field of view in degrees.
            width: Widget logical width.
            height: Widget logical height.
            dpi: Device pixel ratio of the screen.

        Returns:
            The painter path representing the hull overlay, or None.
        """
        if width <= 0 or height <= 0:
            return None

        # 1. Cluster 3D model-space coordinates using a 12.0 Å cutoff
        tmp_clusters = self._cluster_coordinates(coords_3d, eps=12.0)
        if not tmp_clusters:
            return None

        # Extract matrices & translation vectors
        tmp_r = numpy.array(view[0:9]).reshape((3, 3), order="F")
        tmp_cam_orig = numpy.array(view[9:12])
        tmp_model_orig = numpy.array(view[12:15])
        tmp_near_clip = float(view[15])

        tmp_unified_path = QtGui.QPainterPath()
        tmp_has_path = False

        for tmp_cluster_coords in tmp_clusters:
            # 2. Transform Model to Camera space (accounting for PyMOL's
            # left-handed view matrix)
            tmp_shifted = tmp_cluster_coords - tmp_model_orig
            tmp_rotated = tmp_shifted @ tmp_r.T

            # Convert camera-space origin (where PyMOL has +X left, +Y down)
            # to standard right-handed space (subtract instead of add).
            tmp_x_cam = tmp_rotated[:, 0] - tmp_cam_orig[0]
            tmp_y_cam = tmp_rotated[:, 1] - tmp_cam_orig[1]
            tmp_z_cam = tmp_rotated[:, 2] + tmp_cam_orig[2]
            tmp_coords_cam = numpy.column_stack(
                (tmp_x_cam, tmp_y_cam, tmp_z_cam)
            )

            # 3. Near clipping plane filter (z_cam <= -near_clip)
            # Drop points that are too close or behind the camera
            tmp_min_z = -max(tmp_near_clip, 1e-3)
            tmp_valid_mask = tmp_coords_cam[:, 2] <= tmp_min_z
            tmp_coords_cam_clipped = tmp_coords_cam[tmp_valid_mask]

            if len(tmp_coords_cam_clipped) == 0:
                continue

            # 4. Projection Math
            tmp_aspect = float(width) / float(height)
            tmp_tan_fov = math.tan(math.radians(fov / 2.0))

            if is_ortho:
                tmp_d = -tmp_cam_orig[2]
                tmp_h_half = tmp_d * tmp_tan_fov
            else:
                tmp_d = -tmp_coords_cam_clipped[:, 2]
                tmp_h_half = tmp_d * tmp_tan_fov

            tmp_w_half = tmp_h_half * tmp_aspect

            # Guard against zero height/width
            tmp_w_half = numpy.where(tmp_w_half == 0.0, 1e-5, tmp_w_half)
            tmp_h_half = numpy.where(tmp_h_half == 0.0, 1e-5, tmp_h_half)

            # NDC coordinates
            tmp_x_ndc = tmp_coords_cam_clipped[:, 0] / tmp_w_half
            tmp_y_ndc = tmp_coords_cam_clipped[:, 1] / tmp_h_half

            # Map to physical screen viewport coordinates, then scale to
            # logical pixels using DPI ratio
            tmp_screen_x = (
                (tmp_x_ndc + 1.0) * (float(width) * dpi / 2.0)
            ) / dpi
            tmp_screen_y = (
                (1.0 - tmp_y_ndc) * (float(height) * dpi / 2.0)
            ) / dpi

            tmp_coords_2d = numpy.column_stack((tmp_screen_x, tmp_screen_y))

            # 5. Determine points to render for this cluster
            tmp_count = len(tmp_coords_2d)
            if tmp_count == 0:
                continue

            tmp_cluster_path = QtGui.QPainterPath()
            if tmp_count == 1:
                # Draw circle around the single point
                tmp_cluster_path.addEllipse(
                    QtCore.QPointF(tmp_coords_2d[0][0], tmp_coords_2d[0][1]),
                    10.0,
                    10.0,
                )
            elif tmp_count == 2:
                # Draw a thick capsule/line path
                tmp_cluster_path.moveTo(
                    QtCore.QPointF(tmp_coords_2d[0][0], tmp_coords_2d[0][1])
                )
                tmp_cluster_path.lineTo(
                    QtCore.QPointF(tmp_coords_2d[1][0], tmp_coords_2d[1][1])
                )
            else:
                try:
                    # Calculate convex hull
                    tmp_hull = scipy.spatial.ConvexHull(tmp_coords_2d)
                    tmp_hull_points = tmp_coords_2d[tmp_hull.vertices]

                    # Build QPainterPath from ordered vertices
                    tmp_cluster_path.moveTo(
                        QtCore.QPointF(
                            tmp_hull_points[0][0], tmp_hull_points[0][1]
                        )
                    )
                    for tmp_idx in range(1, len(tmp_hull_points)):
                        tmp_cluster_path.lineTo(
                            QtCore.QPointF(
                                tmp_hull_points[tmp_idx][0],
                                tmp_hull_points[tmp_idx][1],
                            )
                        )
                    tmp_cluster_path.closeSubpath()
                except Exception:
                    # Fallback to drawing a simple line-loop of points if Qhull
                    # fails due to collinearity
                    tmp_cluster_path.moveTo(
                        QtCore.QPointF(tmp_coords_2d[0][0], tmp_coords_2d[0][1])
                    )
                    for tmp_idx in range(1, len(tmp_coords_2d)):
                        tmp_cluster_path.lineTo(
                            QtCore.QPointF(
                                tmp_coords_2d[tmp_idx][0],
                                tmp_coords_2d[tmp_idx][1],
                            )
                        )
                    tmp_cluster_path.closeSubpath()

            tmp_unified_path.addPath(tmp_cluster_path)
            tmp_has_path = True

        if tmp_has_path:
            return tmp_unified_path
        return None

    def _calculate_cluster_bboxes(
        self,
        coords_3d: numpy.ndarray,
        view: list[float],
        is_ortho: bool,
        fov: float,
        width: int,
        height: int,
    ) -> list[tuple[float, float, float, float] | None]:
        """Calculates 2D bounding boxes of projected coordinate clusters.

        Args:
            coords_3d: The 3D coordinates.
            view: Camera state list.
            is_ortho: True if orthoscopic view is active.
            fov: Field of view value.
            width: Widget width.
            height: Widget height.

        Returns:
            A list of bounding boxes (min_x, min_y, max_x, max_y) or None.
        """
        if width <= 0 or height <= 0:
            return []

        tmp_clusters = self._cluster_coordinates(coords_3d, eps=12.0)
        if not tmp_clusters:
            return []

        tmp_r = numpy.array(view[0:9]).reshape((3, 3), order="F")
        tmp_cam_orig = numpy.array(view[9:12])
        tmp_model_orig = numpy.array(view[12:15])
        tmp_near_clip = float(view[15])
        tmp_far_clip = float(view[16])

        tmp_bboxes = []

        for tmp_cluster_coords in tmp_clusters:
            # Translation to model origin
            tmp_shifted = tmp_cluster_coords - tmp_model_orig
            # Rotation to camera space
            tmp_rotated = tmp_shifted @ tmp_r
            # Translation to camera origin
            tmp_x_cam = tmp_rotated[:, 0] + tmp_cam_orig[0]
            tmp_y_cam = tmp_rotated[:, 1] + tmp_cam_orig[1]
            tmp_z_cam = tmp_rotated[:, 2] + tmp_cam_orig[2]

            # Strict frustum visibility check
            tmp_valid_mask = (tmp_z_cam >= -tmp_far_clip) & (
                tmp_z_cam <= -tmp_near_clip
            )
            if not numpy.any(tmp_valid_mask):
                tmp_bboxes.append(None)
                continue

            tmp_x_cam_clipped = tmp_x_cam[tmp_valid_mask]
            tmp_y_cam_clipped = tmp_y_cam[tmp_valid_mask]
            tmp_z_cam_clipped = tmp_z_cam[tmp_valid_mask]

            # Exclude any points with z_cam >= 0 or -z_cam < 1e-4
            tmp_div_mask = (tmp_z_cam_clipped < 0) & (
                -tmp_z_cam_clipped >= 1e-4
            )
            if not numpy.any(tmp_div_mask):
                tmp_bboxes.append(None)
                continue

            tmp_x_cam_div = tmp_x_cam_clipped[tmp_div_mask]
            tmp_y_cam_div = tmp_y_cam_clipped[tmp_div_mask]
            tmp_z_cam_div = tmp_z_cam_clipped[tmp_div_mask]

            tmp_aspect = float(width) / float(height)
            tmp_tan_fov = math.tan(math.radians(fov / 2.0))

            if is_ortho:
                tmp_h_half = -tmp_cam_orig[2] * tmp_tan_fov
            else:
                tmp_h_half = -tmp_z_cam_div * tmp_tan_fov

            tmp_w_half = tmp_h_half * tmp_aspect

            tmp_x_ndc = tmp_x_cam_div / tmp_w_half
            tmp_y_ndc = tmp_y_cam_div / tmp_h_half

            # Convert NDC to viewport pixels
            tmp_screen_x = (tmp_x_ndc + 1.0) * width / 2.0
            tmp_screen_y = (1.0 - tmp_y_ndc) * height / 2.0

            # Filter out points that fall outside viewport bounds
            tmp_on_screen_mask = (
                (tmp_screen_x >= 0)
                & (tmp_screen_x <= width)
                & (tmp_screen_y >= 0)
                & (tmp_screen_y <= height)
            )
            if not numpy.any(tmp_on_screen_mask):
                tmp_bboxes.append(None)
                continue

            tmp_screen_x_visible = tmp_screen_x[tmp_on_screen_mask]
            tmp_screen_y_visible = tmp_screen_y[tmp_on_screen_mask]

            tmp_min_x = float(numpy.min(tmp_screen_x_visible))
            tmp_max_x = float(numpy.max(tmp_screen_x_visible))
            tmp_min_y = float(numpy.min(tmp_screen_y_visible))
            tmp_max_y = float(numpy.max(tmp_screen_y_visible))

            # Area prominence check
            tmp_area = (tmp_max_x - tmp_min_x) * (tmp_max_y - tmp_min_y)
            if tmp_area < FLYOUT_MIN_HULL_SCREEN_AREA_PX:
                tmp_bboxes.append(None)
                continue

            tmp_bboxes.append((tmp_min_x, tmp_min_y, tmp_max_x, tmp_max_y))

        return tmp_bboxes

    def _poll_camera(self) -> None:
        """Polls PyMOL view and hides flyouts/restarts timer on camera change."""
        try:
            tmp_view = list(self._cmd.get_view(quiet=1))
        except Exception:
            return

        if (
            self._cached_camera_view is None
            or tmp_view[0:12] != self._cached_camera_view[0:12]
        ):
            self._cached_camera_view = tmp_view
            self._hide_flyouts_instantly()
            self._debounce_timer.start(300)

    def _hide_flyouts_instantly(self) -> None:
        """Hides all active flyouts immediately without deleting them."""
        for tmp_flyout in self._flyouts:
            tmp_flyout.hide()

    def handle_resize(self) -> None:
        """Handles widget resize events by hiding flyouts and restarting timer."""
        self._hide_flyouts_instantly()
        self._debounce_timer.start(300)

    def _on_camera_still(self) -> None:
        """Calculates bboxes and positions/shows flyouts once camera is still."""
        if not self._flyouts or not self._selection_name:
            return

        tmp_current_state = int(self._cmd.get_state())
        if (
            self._cached_coords_3d is None
            or tmp_current_state != self._cached_state
        ):
            try:
                tmp_coords = self._cmd.get_coords(
                    self._selection_name, state=tmp_current_state
                )
                if tmp_coords is not None:
                    self._cached_coords_3d = numpy.array(tmp_coords)
                else:
                    self._cached_coords_3d = None
            except Exception:
                self._cached_coords_3d = None
            self._cached_state = tmp_current_state

        if self._cached_coords_3d is None or len(self._cached_coords_3d) == 0:
            self._hide_flyouts_instantly()
            return

        try:
            tmp_view = list(self._cmd.get_view(quiet=1))
            tmp_is_ortho = bool(self._cmd.get_setting_boolean("orthoscopic"))
            tmp_view_17 = float(tmp_view[17])
            if abs(tmp_view_17) > 1.0:
                tmp_fov = abs(tmp_view_17)
            else:
                tmp_fov = float(self._cmd.get_setting_float("field_of_view"))
        except Exception:
            return

        tmp_w = self.width()
        tmp_h = self.height()

        tmp_bboxes = self._calculate_cluster_bboxes(
            self._cached_coords_3d,
            tmp_view,
            tmp_is_ortho,
            tmp_fov,
            tmp_w,
            tmp_h,
        )

        tmp_margin = styles.dp(8)

        for tmp_idx, tmp_flyout in enumerate(self._flyouts):
            if tmp_idx >= len(tmp_bboxes) or tmp_bboxes[tmp_idx] is None:
                tmp_flyout.hide()
                continue

            tmp_bbox = tmp_bboxes[tmp_idx]
            assert tmp_bbox is not None
            tmp_min_x, tmp_min_y, tmp_max_x, tmp_max_y = tmp_bbox
            tmp_center_x = (tmp_min_x + tmp_max_x) / 2.0

            tmp_flyout_w = tmp_flyout.sizeHint().width()
            tmp_flyout_h = tmp_flyout.sizeHint().height()

            tmp_x = int(tmp_center_x - tmp_flyout_w / 2.0)

            # Vertically flip to bottom if top touches viewport top boundary
            if tmp_min_y <= 0:
                tmp_y = int(tmp_max_y + tmp_margin)
            else:
                tmp_y = int(tmp_min_y - tmp_flyout_h - tmp_margin)
                if tmp_y < 0:
                    tmp_y = int(tmp_max_y + tmp_margin)

            # Clamp coordinates within screen boundaries
            tmp_x = max(0, min(tmp_x, tmp_w - tmp_flyout_w))
            tmp_y = max(0, min(tmp_y, tmp_h - tmp_flyout_h))

            tmp_flyout.move(tmp_x, tmp_y)
            tmp_flyout.show()
            tmp_flyout.raise_()

    @override
    def hideEvent(self, event: QtGui.QHideEvent) -> None:
        """Stops the timers and hides flyout widgets without deleting them.

        Args:
            event: The QHideEvent instance.
        """
        self._poll_timer.stop()
        self._debounce_timer.stop()
        self._hide_flyouts_instantly()
        super().hideEvent(event)

    @override
    def showEvent(self, event: QtGui.QShowEvent) -> None:
        """Starts the timers and schedules layout calculations immediately.

        Args:
            event: The QShowEvent instance.
        """
        super().showEvent(event)
        if self._selection_name:
            self._poll_timer.start()
            QtCore.QTimer.singleShot(50, self._on_camera_still)

    def cleanup(self) -> None:
        """Stops timers and deletes all floating flyouts from PyMOLGLWidget."""
        self._poll_timer.stop()
        self._debounce_timer.stop()

        for tmp_flyout in self._flyouts:
            tmp_flyout.hide()
            tmp_flyout.deleteLater()

        self._flyouts.clear()
        self._selection_name = ""


class PyMOLWidgetEventFilter(QtCore.QObject):
    """Event filter to synchronize ConvexHullOverlay with PyMOLGLWidget."""

    def __init__(self, overlay_widget: ConvexHullOverlay) -> None:
        """Initializes the event filter.

        Args:
            overlay_widget: The overlay widget to control.
        """
        super().__init__()
        self._overlay = overlay_widget

    def eventFilter(  # noqa: N802
        self, watched: QtCore.QObject, event: QtCore.QEvent
    ) -> bool:
        """Filters events to update ConvexHullOverlay size and visibility.

        Args:
            watched: The observed QObject.
            event: The QEvent instance.

        Returns:
            Always False, to let the observed widget process the event.
        """
        if event.type() in (
            QtCore.QEvent.Type.Paint,
            QtCore.QEvent.Type.Resize,
        ) and isinstance(watched, QtWidgets.QWidget):
            self._overlay.setGeometry(watched.rect())
            self._overlay.raise_()
            self._overlay.update()
            if event.type() == QtCore.QEvent.Type.Resize:
                self._overlay.handle_resize()
        return False
