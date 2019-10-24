#!/usr/bin/env python3
import numpy as np
import MDAnalysis as mda

import attr
from typing import Dict, Tuple

from utils import _norm


@attr.s(slots=True, frozen=True)
class BasePairPlane(object):
    P: Dict[str, "np.ndarray"] = attr.ib()
    a: Dict[str, "np.ndarray"] = attr.ib()
    n0: "np.ndarray" = attr.ib()


@attr.s(slots=True, frozen=True)
class BasePlane(object):
    P: Dict[str, "np.ndarray"] = attr.ib()
    n0: "np.ndarray" = attr.ib()


@attr.s
class BasePair(object):
    """ every square of the JSON can be represented as BP
    """
    sc: "mda.Residue" = attr.ib()
    st: "mda.Residue" = attr.ib()
    hp: Tuple[int, int] = attr.ib()

    def __attrs_post_init__(self):
        if self.sc is None or self.st is None:
            self.is_ds = False
        else:
            self.is_ds = True

    def calculate_baseplanes(self):
        self.sc_plane = (self._get_base_plane(self.sc)
                         if self.sc is not None else None)
        self.st_plane = (self._get_base_plane(self.st)
                         if self.st is not None else None)
        self.plane = (self._get_bp_plane(sc=self.sc_plane, st=self.st_plane)
                      if self.is_ds else None)
        return

    def _get_base_plane(self, res: "mda.Residue") -> BasePlane:
        P = dict()
        atom = []
        for atom_name in ["C2", "C4", "C6"]:
            A = res.atoms.select_atoms("name " + atom_name)[0]
            atom.append(A.position)

        n0 = _norm(np.cross((atom[1] - atom[0]), (atom[2] - atom[1])))
        P["diazine"] = sum(atom) / 3.

        C6C8 = "C8" if res.resname in ["ADE", "GUA"] else "C6"
        P["C6C8"] = res.atoms.select_atoms("name " + C6C8)[0].position

        P["C1'"] = res.atoms.select_atoms("name C1'")[0].position

        return BasePlane(n0=n0, P=P)

    def _get_bp_plane(self, sc, st) -> BasePairPlane:
        a, P = dict(), dict()
        n0 = (sc.n0 + st.n0) * 0.5
        for n in sc.P:
            P[n] = (sc.P[n] + st.P[n]) * 0.5
            a[n] = sc.P[n] - st.P[n]

        return BasePairPlane(n0=n0, a=a, P=P)
