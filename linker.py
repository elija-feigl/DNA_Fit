#!/usr/bin/env python
# -*- coding: utf-8 -*-3#
import attr
import nanodesign as nd

from nanodesign.data.base import DnaBase
from typing import Dict, Tuple, Optional, List, Set

from project import Project
from fit import Fit
from design import Design
from crossover import Crossover
from linkage import Linkage
from basepair import BasePair

""" DESCR:
    create Linkage. first loads pickled linkage if available.
"""


@attr.s
class Linker(object):
    """ Linker class
    """
    # TODO: move categorize to linker?
    project: Project = attr.ib()
    Fbp: Dict[int, int] = dict()
    DidFid: Dict[int, int] = dict()
    DhpsDid: Dict[Tuple[int, int, bool], int] = dict()
    Fnicks: Dict[int, int] = dict()
    FidSeq_local: Dict[int, str] = dict()
    FidSeq_global: Dict[int, str] = dict()
    Fco: Dict[str, Crossover] = dict()

    def __attrs_post_init__(self) -> None:
        self.fit: Fit = Fit(self.project)
        self.design: Design = Design(self.project)
        self.Dhp_skips: Set[Tuple[int, int]] = self.design.Dhp_skips

    def _eval_sequence(self, steps=5) -> None:
        """ Affects
            -------
                self.FidSeq_local
                self.FidSeq_global

        """
        self.FidSeq: Dict[int, str] = dict()
        for base in self.design.allbases:
            # local: scaffold 5'->3'
            sequence = ""
            for stp in range(steps + 1):
                neighbor = self._get_n_strand(
                    base=base,
                    direct="down",
                    steps=stp,
                    local=True
                )
                if neighbor is None:
                    sequence += "N"
                elif neighbor.h != base.h:
                    sequence += "X"
                else:
                    n_resindex = self.DidFid[neighbor.id]
                    sequence += self.fit.u.residues[n_resindex].resname[0]
            resindex = self.DidFid[base.id]
            self.FidSeq_local[resindex] = sequence

            # global: even helix scaffold 5'->3', odd helix scaffold 3'->5'
            sequence = ""
            for stp in range(0, -(steps + 1), -1):
                neighbor = self._get_n_strand(
                    base=base,
                    direct="down",
                    steps=stp,
                    local=False,
                )
                if neighbor is None:
                    sequence += "N"
                elif neighbor.h != base.h:
                    sequence += "X"
                else:
                    n_resindex = self.DidFid[neighbor.id]
                    sequence += self.fit.u.residues[n_resindex].resname[0]
            resindex = self.DidFid[base.id]
            self.FidSeq_global[resindex] = sequence

    def _eval_FidHelixneighbors(self, steps=5) -> None:
        """ Affects
            -------
                self.FidHN
        """
        def is_occupied_helix(H: Optional["nd.DnaStructureHelix"],
                              p: int,
                              ) -> bool:
            if H is None:
                return False
            elif (H.id, p, True) in self.design.Dhps_base:
                return True
            elif (H.id, p, False) in self.design.Dhps_base:
                return True
            else:
                return False

        self.FidHN: Dict[int, List[int]] = dict()
        for base in self.design.allbases:
            HidH = self.design.design.structure_helices_map
            HrcH = self.design.design.structure_helices_coord_map
            h_col = HidH[base.h].lattice_col
            h_row = HidH[base.h].lattice_row

            nhelices = list()
            for stp in range(1, steps + 1):
                number_nhelices = 0
                for rc in [(h_row - stp, h_col),
                           (h_row + stp, h_col),
                           (h_row, h_col - stp),
                           (h_row, h_col + stp)
                           ]:
                    n_H = HrcH.get(rc, None)
                    is_nh_occupied = is_occupied_helix(H=n_H, p=base.p)
                    if is_nh_occupied:
                        number_nhelices += 1
                nhelices.append(number_nhelices)
            resindex = self.DidFid[base.id]
            self.FidHN[resindex] = nhelices

    def create_linkage(self) -> Linkage:
        """ invoke _link_scaffold, _link_staples, _link_bp to compute mapping
            of every base design-id to fit-id as well as the basepair mapping.
            basepairs are mapped from scaffold to staple, unique (invertable).
            updates linker attributes corresponding to the respective mapping
            and returns them.
        """
        self._link()
        self._identify_bp()
        self._identify_crossover()
        self._identify_nicks()
        self._eval_sequence()
        self._eval_FidHelixneighbors()
        self.link = Linkage(
            Fbp=self.Fbp,
            DidFid=self.DidFid,
            DhpsDid=self.DhpsDid,
            Dcolor=self.Dcolor,
            Fco=self.Fco,
            Fnicks=self.Fnicks,
            FidSeq_local=self.FidSeq_local,
            FidSeq_global=self.FidSeq_global,
            FidHN=self.FidHN,
            u=self.fit.u,
            Dhp_skips=self.Dhp_skips
        )
        return self.link

    def _link(self) -> Tuple[Dict[int, int],
                             Dict[Tuple[int, int, bool], int],
                             ]:
        def link_scaffold() -> Tuple[Dict[int, int],
                                     Dict[Tuple[int, int, bool], int],
                                     ]:
            """ collect position in scaffold (0-x) by comparing index in list
                of scaffold_design positions
            -------
                Returns
                -------
                DidFid
                    design-id -> fit-id
                DhpsDid
                    helix-number, base-position, is_scaffold -> design-id
            """
            Dscaffold = self.design.scaffold
            Did = [base.id for base in Dscaffold]
            Dhp = [(base.h, base.p, True) for base in Dscaffold]
            Fid_local = [Did.index(base.id) for base in Dscaffold]
            Fid_global = self.fit.scaffold.residues[Fid_local].resindices

            DidFid = dict(zip(Did, Fid_global))
            DhpsDid = dict(zip(Dhp, Did))
            return (DidFid, DhpsDid)

        def link_staples() -> Tuple[Dict[int, int],
                                    Dict[Tuple[int, int, bool], int],
                                    Dict[int, int],
                                    ]:
            """same procedure as scaffold for each
            -------
            Returns
                -------
                DidFid
                    design-id -> fit-id
                DhpsDid
                    helix-number, base-position, is_scaffold -> design-id
                dict color
                    fit-segment-id -> color
            """
            def get_resid(segindex: int, resindex_local: int) -> int:
                segment = self.fit.staples[segindex]
                return segment.residues[resindex_local].resindex

            DidFid: Dict[int, int] = {}
            DhpsDid: Dict[Tuple[int, int, bool], int] = {}
            color: Dict[int, int] = {}

            for i, staple in enumerate(self.design.staples):
                seg_id = self.design.stapleorder[i]

                Did = [base.id for base in staple]
                Dhp = [(base.h, base.p, False) for base in staple]

                Fid_local = [Did.index(base.id)for base in staple]
                Fid_global = [get_resid(seg_id, resid) for resid in Fid_local]

                icolor = self.design.design.strands[staple[0].strand].icolor
                segidxforcolor = self.fit.staples[seg_id].segindex
                color[segidxforcolor] = icolor

                DidFid_add = dict(zip(Did, Fid_global))
                DhpsDid_add = dict(zip(Dhp, Did))
                DidFid = {**DidFid, **DidFid_add}
                DhpsDid = {**DhpsDid, **DhpsDid_add}

            return (DidFid, DhpsDid, color)

        DidFid_sc, DhpsDid_sc = link_scaffold()
        DidFid_st, DhpsDid_st, self.Dcolor = link_staples()

        self.DidFid = {**DidFid_sc, **DidFid_st}
        self.DhpsDid = {**DhpsDid_sc, **DhpsDid_st}
        return (self.DidFid, self.DhpsDid)

    def _identify_bp(self) -> Dict[int, int]:
        """ link basepairs by mapping indices according to json (cadnano).
            basepairs are mapped from scaffold to staple, unique (invertable).
        -------
         Returns
            -------
            self.Fbp
                fit-id -> fit-id
        """
        self.Fbp = {
            self.DidFid[base.id]: self.DidFid[base.across.id]
            for base in self.design.scaffold
            if base.across is not None
        }
        return self.Fbp

    def _get_n_strand(self, base: DnaBase, direct: str, steps=1, local=True
                      ) -> Optional[DnaBase]:
        """direct = ["up","down"]"""
        if steps == 0:
            return base
        if steps < 0:
            direct = "up" if direct == "down" else "down"
        if (base.h % 2) == 1 and not local:
            direct = "up" if direct == "down" else "down"

        for _ in range(abs(steps)):
            base = (base.up if direct == "up" else base.down)
            if base is None:
                return None
        return base

    def _get_n_helix(self, base: DnaBase, direct: int, steps=1
                     ) -> Optional[DnaBase]:
        """direct = [1,-1]"""
        if steps == 0:
            return base
        helix, position, is_scaf = base.h, base.p, base.is_scaf
        if steps < 0:
            steps = abs(steps)
            direct = -direct
        # first check the number of skips passed
        n_skips = 0
        for n in range(direct, direct * (steps + 1), direct):
            n_position = position + n
            if (helix, n_position) in self.design.Dhp_skips:
                n_skips += 1
        # move one position further if on skip
        n_position = position + direct * (steps + n_skips)
        if (helix, n_position) in self.design.Dhp_skips:
            n_position += direct
        return self.design.Dhps_base.get((helix, n_position, is_scaf), None)

    def _get_bp(self, base: "nd.residue") -> Optional[BasePair]:
        if base is None:
            return None
        else:
            resindex = self.DidFid[base.id]
            Fbp_all = {**self.Fbp, **{v: k for k, v in iter(self.Fbp.items())}}
            wcindex = Fbp_all.get(resindex, None)
            sc_index = resindex if base.is_scaf else wcindex
            st_index = wcindex if base.is_scaf else resindex

            sc = None if sc_index is None else self.fit.u.residues[sc_index]
            st = None if st_index is None else self.fit.u.residues[st_index]
            hp = (base.h, base.p)
            return BasePair(sc=sc, st=st, hp=hp)

    def is_co(self, base: DnaBase, neighbor: Optional[DnaBase]
              ) -> bool:
        if neighbor is None:
            return False
        else:
            return neighbor.h != base.h

    def _identify_crossover(self) -> None:
        """ Affects
            -------
                self.Fco
        """
        def get_co_leg(base: Optional[DnaBase], direct: int
                       ) -> Optional[DnaBase]:
            if base is None:
                return None
            else:
                return self._get_n_helix(base=base, direct=direct, steps=2)

        def get_co(bA: DnaBase,
                   bC: DnaBase,
                   bB: Optional[DnaBase],
                   bD: Optional[DnaBase],
                   direct: int,
                   typ: str,
                   ) -> Tuple[str, Crossover]:

            bA_ = get_co_leg(base=bA, direct=(-1 * direct))
            bB_ = get_co_leg(base=bB, direct=direct)
            bC_ = get_co_leg(base=bC, direct=(-1 * direct))
            bD_ = get_co_leg(base=bD, direct=direct)

            Ps, Ls = list(), list()
            co_pos = list()
            for bP, bL in zip([bA, bB, bC, bD], [bA_, bB_, bC_, bD_]):
                Ps.append(self._get_bp(base=bP))
                if bP is not None:
                    co_pos.append((bP.h, bP.p))
                Ls.append(self._get_bp(base=bL))
            co = Crossover(
                Ps=Ps,
                Ls=Ls,
                typ=typ,
                is_scaf=bA.is_scaf,
            )
            key = str(sorted(co_pos))
            return key, co

        co_subparts = set()
        for base in self.design.allbases:
            for direct in ["up", "down"]:
                neighbor = self._get_n_strand(base, direct)
                if self.is_co(base=base, neighbor=neighbor):
                    co_subparts.add(frozenset([base, neighbor]))
                    break

        while co_subparts:
            bA, bC = co_subparts.pop()
            co_direct = "up" if self._get_n_strand(bA, "up") == bC else "down"
            bN = bA.up if co_direct == "down" else bA.down
            direct_int = bA.p - bN.p
            bB = self._get_n_helix(base=bA, direct=direct_int)
            bD = self._get_n_helix(base=bC, direct=direct_int)
            bBbD = frozenset([bB, bD])

            if bBbD in co_subparts:
                co_subparts.remove(bBbD)
                typ = "full"
            elif (bB is not None) and (bD is not None):
                typ = "half"
            else:
                typ = "end"

            key, co = get_co(bA=bA, bB=bB, bC=bC, bD=bD,
                             direct=direct_int, typ=typ)
            self.Fco[key] = co

    def _identify_nicks(self) -> None:
        """ Affects
            -------
                self.Fnicks
        """
        def is_nick(candidate: DnaBase, base: DnaBase) -> bool:
            is_onhelix = (candidate.h == base.h)
            is_neighbor = (abs(base.p - candidate.p) <= 2)  # skip = 2
            is_base = (candidate is base)
            b_Fid = self.DidFid[base.id]
            c_Fid = self.DidFid[candidate.id]
            is_ds = all([(x in self.Fbp.values()) for x in [b_Fid, c_Fid]])
            return all([is_onhelix, is_neighbor, not is_base, is_ds])

        def Fid(Did: int) -> int:
            return self.DidFid[Did]

        start_bases = [s[0] for s in self.design.staples]
        end_bases = [s[-1] for s in self.design.staples]

        self.Fnicks = {
            Fid(start.id): Fid(candi.id)
            for start in start_bases
            for candi in end_bases
            if is_nick(candidate=candi, base=start)
        }


def get_linkage(project: Project) -> Linkage:
    if project.relink:
        print("relink_fit {}".format(project.name))
        linker = Linker(project)
        link = linker.create_linkage()
        link.dump_linkage(project)
    else:
        try:
            link = Linkage()
            link.load_linkage(project=project)
            print("found linkage for {}".format(project.name))
        except BaseException:
            print("link_fit {}".format(project.name))
            linker = Linker(project)
            link = linker.create_linkage()
            link.dump_linkage(project)
    return link
