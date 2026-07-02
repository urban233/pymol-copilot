"""Convex hull overlay widget for highlighting PyMOL selections."""

from __future__ import annotations

import logging
import math
import typing

from PyQt6 import QtCore
from PyQt6 import QtGui
from PyQt6 import QtWidgets
import numpy
import scipy.spatial


class ConvexHullOverlay(QtWidgets.QWidget):
    """Transparent overlay for drawing a 2D convex hull of a PyMOL selection."""

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
        self._selection_name = selection_name
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


class PyMOLWidgetEventFilter(QtCore.QObject):
    """Event filter to synchronize ConvexHullOverlay with PyMOLGLWidget."""

    def __init__(self, overlay_widget: QtWidgets.QWidget) -> None:
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
        return False
