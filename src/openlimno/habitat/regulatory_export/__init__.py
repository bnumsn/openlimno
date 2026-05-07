"""Regulatory output templates. SPEC §4.2.4.2, ADR-0009.

Three frameworks, each is a separate submodule:
- ``cn_sl712`` — China SL/Z 712-2014 河湖生态流量计算规范 ("four-tuple")
- ``us_ferc_4e`` — US FERC 4(e) conditions (M3 stub)
- ``eu_wfd`` — EU Water Framework Directive (M3 stub)

Each exposes ``render(...) -> Path`` writing CSV (and optional PDF) to disk.
"""

from __future__ import annotations

from . import cn_sl712, eu_wfd, us_ferc_4e

__all__ = ["cn_sl712", "eu_wfd", "us_ferc_4e"]
