# -*- coding: utf-8 -*-
"""PySide のスタブ（PySide を使うツールのテスト用。 `_bootstrap` の後に import）。

開発機には PySide が無いので、そのままではツールを import すらできない。
ここでは**何を呼んでも何かを返す**寛容な Qt を `PySide2` / `shiboken2` として
`sys.modules` に入れ、import → `show()` を一往復できるようにする。

担保するのは「Qt 以外の部分（自前の名前・定数・組み立て順）で落ちない」こと
だけ。 **Qt の実挙動・見た目・PySide6 との差は何も検証していない。**
実機確認は Maya 2024（PySide2）と 2025（PySide6）の両方で行う。

なお `PySide6` は入れない。 shim（`qt.py`）は PySide6 を先に試すので、
入れないことで「2024 の経路」を通る。 shim の分岐自体は `test_qt.py` が
別に検査する。
"""

from __future__ import annotations

import sys
import types

import _bootstrap  # noqa: F401  （maya スタブが先に入っていること）


class _AnyMeta(type):
    """クラス属性の参照（`Qt.AlignLeft` など）も寛容にする。"""

    def __getattr__(cls, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return _Any

    def __or__(cls, _other):
        return cls

    __ror__ = __or__


class _Any(metaclass=_AnyMeta):
    """どの属性を引いても、何を呼んでも、`_Any` を返す。"""

    def __init__(self, *_args, **_kwargs):
        pass

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return _Any()

    def __call__(self, *_args, **_kwargs):
        return _Any()

    def __iter__(self):
        return iter(())

    def __len__(self):
        return 0

    def __bool__(self):
        return False

    def __int__(self):
        return 0

    def __float__(self):
        return 0.0

    # 比較は常に偽（`while layout.count() > 1:` のようなループを即座に抜ける）
    def __lt__(self, _other):
        return False

    __le__ = __gt__ = __ge__ = __lt__

    def __add__(self, _other):
        return self

    __radd__ = __sub__ = __rsub__ = __mul__ = __rmul__ = __add__

    def __or__(self, _other):
        return self

    __ror__ = __or__


class _QtModule(types.ModuleType):
    """`QtWidgets.QLabel` などを**名前ごとに別のクラス**として返す。

    全部を同じ `_Any` にすると、継承や isinstance の区別が付かなくなる。
    """

    def __init__(self, name):
        super().__init__(name)
        self._classes = {}

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        classes = self.__dict__["_classes"]
        if name not in classes:
            classes[name] = _AnyMeta(name, (_Any,), {})
        return classes[name]


def _install():
    if "PySide2" in sys.modules:
        return   # 冪等

    pyside = types.ModuleType("PySide2")
    for sub in ("QtCore", "QtGui", "QtWidgets"):
        module = _QtModule("PySide2." + sub)
        setattr(pyside, sub, module)
        sys.modules["PySide2." + sub] = module
    sys.modules["PySide2"] = pyside

    shiboken = types.ModuleType("shiboken2")
    shiboken.wrapInstance = lambda _ptr, cls: cls()
    sys.modules["shiboken2"] = shiboken

    # `MQtUtil.mainWindow()` を引けるようにする（_bootstrap のスタブは空の型）
    om_ui = sys.modules["maya.OpenMayaUI"]
    om_ui.MQtUtil.mainWindow = staticmethod(lambda: 1)


_install()
