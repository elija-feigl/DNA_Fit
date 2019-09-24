#!/usr/bin/env python
import mrcfile
import numpy as np
import MDAnalysis as mda
import sys
import pickle
import os
import ipdb


def mrc_segment(atoms_selection, path_in, path_out, context=2, clipping=0.):

    if not len(atoms_selection):
        print("EXIT - no atoms in this selection")
        return

    u = atoms_selection.universe
    u.trajectory[-1]

    with mrcfile.open(path_in + ".mrc", mode='r') as mrc:
        m_o = np.array(mrc.header["origin"])
        m_origin = np.array([m_o["x"], m_o["y"], m_o["z"]])
        m_c = np.array(mrc.header["cella"])
        m_cell = np.array([m_c["x"], m_c["y"], m_c["z"]])
        m_grid = np.array(
            [mrc.header["nx"], mrc.header["ny"], mrc.header["nz"]])
        m_spacing = m_cell/m_grid
        m_data = np.swapaxes(mrc.data, 0, 2)
        # TODO: -low- faster withoutswap

    data_mask = np.zeros(m_grid, dtype=np.float32)

    grid_positions = np.rint(
        ((atoms_selection.positions-m_origin) / m_spacing)).astype(int)
    for pos in grid_positions:
        x, y, z = pos[0], pos[1], pos[2]
        data_mask[x-context:x+context, y-context:y+context, z-context:z +
                  context] = 1.

    data = m_data * data_mask

    # get rid of zero-padding
    idx_data = np.nonzero(data)

    x_min, x_max = np.min(idx_data[0]),  np.max(idx_data[0])
    y_min, y_max = np.min(idx_data[1]),  np.max(idx_data[1])
    z_min, z_max = np.min(idx_data[2]),  np.max(idx_data[2])

    xyz_diff = max(x_max - x_min, y_max - y_min, z_max - z_min)
    x_pad = 0.5 * (xyz_diff + x_min - x_max)
    y_pad = 0.5 * (xyz_diff + y_min - y_max)
    z_pad = 0.5 * (xyz_diff + z_min - z_max)
    x_low = int(x_pad) if (x_pad % 1.) == 0. else int(x_pad) + 1
    y_low = int(y_pad) if (y_pad % 1.) == 0. else int(y_pad) + 1
    z_low = int(z_pad) if (z_pad % 1.) == 0. else int(z_pad) + 1

    data_small = np.zeros((xyz_diff,  xyz_diff, xyz_diff), dtype=np.float32)
    data_small[x_low: -int(x_pad) or None, y_low: -int(y_pad) or None, z_low: -
               int(z_pad) or None] = data[x_min: x_max, y_min: y_max,
                                          z_min: z_max]

    grid = np.shape(data_small)
    origin = m_origin + ((x_min - x_low) * m_spacing[0], (y_min - y_low) *
                         m_spacing[1], (z_min - z_low) * m_spacing[2])
    cell = grid * m_spacing
    center = np.divide(grid, 2).astype(int)

    with mrcfile.new(path_out + ".mrc", overwrite=True) as mrc_out:
        mrc_out.set_data(np.swapaxes(data_small, 0, 2))
        mrc_out._set_voxel_size(*(cell/grid))
        mrc_out.header["origin"] = tuple(origin)

    path_out_split = path_out.split("/")
    path_star = "Tomograms/seg-co/" + path_out_split[-1]
    with open(path_out + ".star", mode="w") as star_out:
        star_out.write(
            "data_\n\nloop_\n_rlnMicrographName #1\n_rlnCoordinateX #2\n" +
            "_rlnCoordinateY #3\n _rlnCoordinateZ #4\n")
        star_out.write(path_star + ".star " + str(center[0]) + " " +
                       str(center[1]) + " " + str(center[2]))
    return


def mrc_localres(atoms, path_in, path_out):
    def get_localres(atoms, m_data, m_origin, m_spacing):
        locres = 0.
        for atom in atoms:
            grid_position = np.rint(((atom.position-m_origin) / m_spacing)).astype(int)
            locres += m_data[grid_position[0], grid_position[1], grid_position[2]]
        locres /= len(atoms)
        return locres

    if not len(atoms):
        print("EXIT - no atoms in this selection")
        return

    u = atoms.universe
    u.trajectory[-1]

    with mrcfile.open(path_in + ".mrc", mode='r') as mrc:
        m_o = np.array(mrc.header["origin"])
        m_origin = np.array([m_o["x"], m_o["y"], m_o["z"]])
        m_c = np.array(mrc.header["cella"])
        m_cell = np.array([m_c["x"], m_c["y"], m_c["z"]])
        m_grid = np.array(
            [mrc.header["nx"], mrc.header["ny"], mrc.header["nz"]])
        m_spacing = m_cell/m_grid
        m_data = np.swapaxes(mrc.data, 0, 2)

    dict_localres = {}
    for res in atoms.residues:
        localres = get_localres(res.atoms, m_data, m_origin, m_spacing)
        dict_localres[res.resindex] = localres

    return dict_localres


def _categorise_lists(topo, plus=3):
    # TODO. check: names set list etc
    dict_FidDid = {v: k for k, v in iter(topo["dict_idid"].items())}
    dict_DidDhps = {v: k for k, v in iter(topo["dict_hpid"].items())}
    dict_bpFULL = {**topo["dict_bp"], **{v: k for k, v in iter(topo["dict_bp"].items())}}

    id_ds = set()
    id_coplus = set()

    for wc_id1, wc_id2 in iter(topo["dict_bp"].items()):
        id_ds.add(wc_id1)
        id_ds.add(wc_id2)
    id_ss = set(topo["dict_idid"].values()) - id_ds

    id_co = set()
    id_co_init = {id_design for id_design in topo["dict_coid"].keys()
                  if id_design not in id_ss}
    allready_done = set()
    for base in id_co_init:
        typ = topo["dict_coid"][base]["type"][0]
        co_index = topo["dict_coid"][base]["co_index"]

        if base not in allready_done:
            allready_done.add(base)
            co = topo["dict_coid"][base]["co"]
            allready_done.add(co)

            co_bp = dict_bpFULL[co]
            bp = dict_bpFULL[base]

            if topo["dict_coid"][base]["type"][0] == "double":
                dou = topo["dict_coid"][base]["type"][1]
                allready_done.add(dou)
                dou_co = topo["dict_coid"][dou]["co"]
                allready_done.add(dou_co)

                dou_co_bp = dict_bpFULL[dou_co]
                dou_bp = dict_bpFULL[dou]

                tup = (base, bp, co, co_bp, dou,
                       dou_bp, dou_co, dou_co_bp, co_index, typ)
            else:
                tup = (base, bp, co, co_bp, co_index, typ)

            tup_plus = []
            for x in tup[:-2]:
                h, p, is_scaf = dict_DidDhps[dict_FidDid[x]]
                for i in range(-plus, plus):
                    try:
                        tup_plus.append(
                            topo["dict_idid"][topo["dict_hpid"][(h,
                                                                 p+i,
                                                                 is_scaf)]])
                    except KeyError:
                        pass  # helix end

            tup_plus.append(co_index)
            tup_plus.append(typ)
            id_co.add(tup)
            id_coplus.add(tuple(tup_plus))

    nick_allready_done = set()
    id_nick = set()
    for id1, id2 in iter(topo["dict_nicks"].items()):
        if id1 not in nick_allready_done:
            nick_allready_done.add(id1)
            nick_allready_done.add(id2)
            tup = (id1, id2, dict_bpFULL[id1], dict_bpFULL[id2])
            id_nick.add(tup)

    id_nick_plus = []
    for nick in id_nick:
        tup_plus = []
        for x in nick:
            h, p, is_scaf = dict_DidDhps[dict_FidDid[x]]
            for i in range(-plus, plus):
                try:
                    tup_plus.append(
                        topo["dict_idid"][topo["dict_hpid"][(h,
                                                             p+i,
                                                             is_scaf)]])
                except KeyError:
                    pass  # helix end
        id_nick_plus.append(tup_plus)
    return id_co, id_coplus, id_nick, id_nick_plus


def _topology(name, path):
    DICTS = ["dict_bp", "dict_idid", "dict_hpid", "dict_color",
             "dict_coid", "dict_nicks", "list_skips", "universe"]
    # read general info
    topo = {}
    for pickle_name in DICTS:
        topo[pickle_name] = pickle.load(
            open(path + name + "__" + pickle_name + ".p", "rb"))

    return topo


def proc_input():
    if len(sys.argv) < 2:
        print_usage()
    name = sys.argv[1]
    cwd = os.getcwd()
    path = cwd + "/"

    if len(sys.argv) > 2:
        rang = int(sys.argv[2])
    else:
        rang = 5

    if len(sys.argv) > 3:
        context = int(sys.argv[3])
    else:
        context = 3

    return path, name, rang, context


def print_usage():
    print("""
          usage: designname [range = 5] [context = 3]  ...
          """)


def main():

    path_in, name, rang, context = proc_input()
    print("input from ", path_in)

    path_analysis = path_in + "/analysis/"

    topo = _topology(name, path_analysis)
    _, id_coplus_lists, _, id_nickplus_list = _categorise_lists(
        topo,
        plus=rang,
    )

    # initialize universe and select final frame
    u = mda.Universe(*topo["universe"])
    u.trajectory[-1]

    # full map masked
    mrc_segment(
        u.atoms,
        path_in + name,
        path_analysis + name + "-masked",
        context=context,
    )

    color_exists = os.path.isfile(path_in + name + "_localres.mrc")
    if color_exists:
        dict_localres = mrc_localres(atoms=u.atoms,
                                     path_in=path_in + name,
                                     path_out=path_analysis + name + "-localres",
                                     )
        pickle.dump(dict_localres, open(path_analysis + name + "-localres.p", "wb"))

    # crossovers
    motif_cat = {"co": id_coplus_lists, "nick": id_nickplus_list}

    for motif in ["nick", "co"]:
        path_out = path_analysis + motif + "/"
        print("output to ", path_out)
        try:
            os.mkdir(path_out)
        except FileExistsError:
            pass

        h1_exists = os.path.isfile(path_in + name + "_unfil_half1.mrc")
        h2_exists = os.path.isfile(path_in + name + "_unfil_half2.mrc")
        calculate_halfmaps = True if h1_exists and h2_exists else False
        if calculate_halfmaps:
            print("segmenting halfmaps")
        for index, co_select_typ in enumerate(motif_cat[motif]):
            if motif == "co":
                co_select = co_select_typ[:-2]
                typ = co_select_typ[-1]
                index = co_select_typ[-2]
                atoms_select = mda.AtomGroup([], u)
                for base_id in co_select:
                    atoms_select += u.residues[base_id].atoms

            elif motif == "nick":
                typ = ""
                atoms_select = mda.AtomGroup([], u)
                for base_id in co_select_typ:
                    atoms_select += u.residues[base_id].atoms

            mrc_segment(atoms_select, path_in + name, path_out +
                        name + "__" + typ + motif + str(index),
                        context=context)
            if calculate_halfmaps:
                mrc_segment(atoms_select, path_in + name + "_unfil_half1",
                            path_out + name + "__h1-" + typ + motif +
                            str(index), context=context)
                mrc_segment(atoms_select, path_in + name + "_unfil_half2",
                            path_out + name + "__h2-" + typ + motif +
                            str(index), context=context)


if __name__ == "__main__":
    main()
