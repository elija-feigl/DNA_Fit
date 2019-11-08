#!/usr/bin/env python3
import MDAnalysis as mda
import numpy as np
import os

import pickle
import argparse
# import attr

from pathlib import Path
# from typing import Set, Dict, Tuple, Any

from project import Project
from utils import WC_PROPERTIES, DH_ATOMS, ignored
from bdna import BDna
from linker import Linker
from linkage import Linkage


def write_pdb(u, bDNA, PDBs):
    u.add_TopologyAttr(
        mda.core.topologyattrs.Tempfactors(np.zeros(len(u.atoms))))

    u.atoms.tempfactors = -1.
    for res in u.residues:
        try:
            res.atoms.tempfactors = bDNA.bp_quality[res.resindex]["C1'C1'"]
        except KeyError:
            pass
    PDBs["qual"].write(u.atoms)

    for cond in WC_PROPERTIES:
        u.atoms.tempfactors = -1.
        for res in u.residues:
            try:
                res.atoms.tempfactors = (
                    bDNA.bp_geometry_local[res.resindex][cond]["center-C6C8"])
            except KeyError:
                pass
        PDBs[cond].write(u.atoms)

    for dh in DH_ATOMS:
        u.atoms.tempfactors = -1.
        for res in u.residues:
            try:
                res.atoms.tempfactors = bDNA.dh_quality[res.resindex][dh]
            except KeyError:
                pass
        PDBs[dh].write(u.atoms)

    u.atoms.tempfactors = -1.
    ing = 0.00
    for resindex, resindex_wc in bDNA.d_Fbp.items():
        u.residues[resindex].atoms.tempfactors = ing
        u.residues[resindex_wc].atoms.tempfactors = ing
        ing += 0.01
    PDBs["bp"].write(u.atoms)


def get_description():
    return """computes watson crick base pairs.
    they are returned as to dictionaries. this process is repeated for each
     Hbond-deviation criterion
    subsequently universe and dicts are stored into a pickle. each deviation
    criterion is stored in one pickle"""


def proc_input():
    parser = argparse.ArgumentParser(
        description=get_description(),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("--folder",
                        help="input folder",
                        type=str,
                        default="./",
                        )
    parser.add_argument("--name",
                        help="name of design and files",
                        type=str,
                        required="True",
                        default=argparse.SUPPRESS,
                        )
    parser.add_argument("--frames",
                        help="number of frames samples",
                        type=int,
                        default=1,
                        )
    parser.add_argument("--dev",
                        help="deviation of H-bond",
                        type=float,
                        default=0.1,
                        )
    parser.add_argument("--relink",
                        help="force relink fit",
                        action="store_true"
                        )
    args = parser.parse_args()
    project = Project(input=Path(args.folder),
                      output=Path(args.folder) / "analysis",
                      name=args.name,
                      frames=args.frames,
                      dev=args.dev,
                      relink=args.relink,
                      )

    with ignored(FileExistsError):
        os.mkdir(project.output)
    return project


def main():
    project = proc_input()

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

    if project.frames == 1:
        frames = [-1]
    else:
        frames_step = int(len(link.u.trajectory) / project.frames)
        frames = list((range(len(link.u.trajectory) - 1), 0, -frames_step))

    properties = []
    traj_out = project.output / "frames"
    with ignored(FileExistsError):
        os.mkdir(traj_out)

    # open PDB files
    PDBs = {}
    for name in [*WC_PROPERTIES, "bp", "qual"]:
        pdb_name = project.output / "{}__bp_{}.pdb".format(project.name, name)
        PDBs[name] = mda.Writer(pdb_name, multiframe=True)
    for name in DH_ATOMS:
        pdb_name = project.output / "{}__dh_{}.pdb".format(project.name, name)
        PDBs[name] = mda.Writer(pdb_name, multiframe=True)

    # loop over selected frames
    for i, ts in enumerate([link.u.trajectory[i] for i in frames]):
        print(ts)

        # perform analyis
        print("eval_fit", project.name)
        bDNA = BDna(link)
        bDNA.sample()

        properties.append(bDNA)
        props_tuple = [
            (bDNA.bp_geometry_local, "bp_geometry_local"),
            (bDNA.bp_geometry_global, "bp_geometry_global"),
            (bDNA.bp_quality, "bp_quality"),
            (bDNA.dh_quality, "dh_quality"), (bDNA.distances, "distances"),
            (bDNA.co_angles, "co_angles")]
        for prop, prop_name in props_tuple:
            pickle_name = traj_out / "{}__bDNA-{}-{}.p".format(project.name,
                                                               prop_name,
                                                               i,
                                                               )
            pickle.dump((ts, prop), open(pickle_name, "wb"))
        import ipdb
        ipdb.set_trace()
        print("write pdbs", project.name)
        write_pdb(link.u, bDNA, PDBs)

    # close PDB files
    for _, PDB in PDBs.items():
        PDB.close()


if __name__ == "__main__":
    main()
