# -*- coding: utf-8 -*-
"""PySide2 / PySide6 の両対応 shim。

Maya 2024 は PySide2、2025 以降は PySide6 で、**import 名から互換が無い**。
パッケージ内の Qt はすべてここからだけ import する（各ファイルに try/except を
散らすと、必ずどこかが漏れて 2025 で落ちる。 CLAUDE.md「PySide2/6 両対応 shim」）。
"""

from __future__ import annotations

try:                                              # Maya 2025+
    from PySide6 import QtCore, QtGui, QtWidgets
    from shiboken6 import wrapInstance
except ImportError:                               # Maya 2024
    from PySide2 import QtCore, QtGui, QtWidgets
    from shiboken2 import wrapInstance

Qt = QtCore.Qt

__all__ = ["QtCore", "QtGui", "QtWidgets", "Qt", "wrapInstance"]
