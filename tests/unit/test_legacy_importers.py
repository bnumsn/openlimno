"""HEC-RAS .g0X + River2D .cdg legacy importer tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from openlimno.preprocess import read_hecras_geometry, read_river2d_cdg


# Small synthetic .g03 fragment with two cross-sections on one reach.
_HECRAS_G03 = """\
Geom Title=Synthetic Test Geometry
Program Version=6.10
River Reach=Lemhi      ,Main
Type RM Length L Ch R= 1 ,    100.0,    50.0
X1=  100.0,      4,      0.,     20.,      0.,      0.
GR=     1.5,      0.,     1.0,      5.,     0.5,    10.0,     1.0,    20.0
Type RM Length L Ch R= 1 ,    200.0,    60.0
X1=  200.0,      3,      0.,     18.,      0.,      0.
GR=     1.6,      0.,     1.1,      9.,     1.6,    18.0
"""


_CDG_BED = """\
HEADER River2D Bed File v1.0
NODES 4
1   0.0   0.0   1.5  0.5
2   1.0   0.0   1.0  0.6
3   1.0   1.0   1.1  0.55
4   0.0   1.0   1.2  0.5
ELEMENTS 2
1 1 2 3
2 1 3 4
"""


def test_read_hecras_geometry_finds_two_xs(tmp_path: Path) -> None:
    p = tmp_path / "synthetic.g03"
    p.write_text(_HECRAS_G03)
    df = read_hecras_geometry(p)
    assert {"river", "reach", "station_m", "distance_m", "elevation_m"}.issubset(df.columns)
    stations = sorted(set(df["station_m"]))
    assert stations == [100.0, 200.0]
    # First XS has 4 points, second has 3
    n_at_100 = (df["station_m"] == 100.0).sum()
    n_at_200 = (df["station_m"] == 200.0).sum()
    assert n_at_100 == 4
    assert n_at_200 == 3
    assert (df["river"] == "Lemhi").all()


def test_read_hecras_geometry_empty_raises(tmp_path: Path) -> None:
    p = tmp_path / "empty.g03"
    p.write_text("Geom Title=Empty\n")
    with pytest.raises(ValueError, match="No cross-sections found"):
        read_hecras_geometry(p)


def test_read_river2d_cdg(tmp_path: Path) -> None:
    p = tmp_path / "bed.cdg"
    p.write_text(_CDG_BED)
    df = read_river2d_cdg(p)
    assert len(df) == 4
    assert set(df.columns) >= {"node_id", "x", "y", "z"}
    assert "depth" in df.columns
    assert df.loc[df["node_id"] == 1, "z"].iloc[0] == 1.5


def test_read_river2d_cdg_no_nodes_raises(tmp_path: Path) -> None:
    p = tmp_path / "broken.cdg"
    p.write_text("HEADER junk\nELEMENTS 0\n")
    with pytest.raises(ValueError, match="No NODES"):
        read_river2d_cdg(p)
