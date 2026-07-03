# cBioMOL - open C++ and Python platform for BioMOLecular visualization and analysis
# -------------------------------------------------------------------
# This file contains source code for the cBioMOL computer program
# Copyright (C) 2026 Hannah Kullik, Martin Urban (hannah.kullik@studmail.w-hs.de, martin.urban@studmail.w-hs.de)
# Source code is available at <https://github.com/urban233/cBioMOL>
# -------------------------------------------------------------------
# It is unlawful to modify or remove this copyright notice.
# -------------------------------------------------------------------
# Please see the accompanying LICENSE file for further information.
# -------------------------------------------------------------------
# Primary author of this source file:
# Martin Urban
# -------------------------------------------------------------------
# Additional authors of this source file include:
#
# ==============================================================================
"""Module for importing Qt modules."""

try:
    from PyQt6 import QtCore  # noqa: F401
    from PyQt6 import QtGui  # noqa: F401
    from PyQt6 import QtOpenGL  # noqa: F401
    from PyQt6 import QtOpenGLWidgets  # noqa: F401
    from PyQt6 import QtSql  # noqa: F401
    from PyQt6 import QtWidgets  # noqa: F401
    from PyQt6 import sip  # noqa: F401
except ImportError:
    raise ImportError("PyQt6 is not installed.")
