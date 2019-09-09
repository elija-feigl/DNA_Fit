#!/usr/bin/env python3

import argparse

from collections import namedtuple
from pathlib import Path


def number_to_hybrid36_number(number, width):

    digits_upper = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

    def encode_pure(digits, value):
        "encodes value using the given digits"
        assert value >= 0
        if (value == 0):
            return digits[0]
        n = len(digits)
        result = []
        while (value != 0):
            rest = value // n
            result.append(digits[value - rest * n])
            value = rest
        result.reverse()
        return "".join(result)

    digits_lower = digits_upper.lower()
    if (number >= 1-10**(width-1)):
        if (number < 10**width):
            return '{:{width}d}'.format(number, width=width)
        number -= 10**width
        if (number < 26*36**(width-1)):
            number += 10*36**(width-1)
            return encode_pure(digits_upper, number)
        number -= 26*36**(width-1)
        if (number < 26*36**(width-1)):
            number += 10*36**(width-1)
            return encode_pure(digits_lower, number)
    raise ValueError("value out of range.")

# TODO: low- reset atom number, residuenumber, chain number

OCC = "9.99"
BFAC = "1.00"
HEADER = "AUTHORS:     Martin, Casanal, Feigl        VERSION: 0.2.0\n"


class PDB_Corr(object):

    def __init__(self, reverse):
        self.current = {"atom_number": 1, "old_molecule_number": 1,
                        "last_molecule_number": 1, "chain_id": "A",
                        "chain_id_repeats": 1, "chain": None}
        self.reverse = reverse
        self.nomcla = {' O1P': ' OP1', ' O2P': ' OP2', ' C5M': ' C7 '}
        self.nomcla_rev = {' OP1': ' O1P', ' OP2': ' O2P', ' C7 ': ' C5M'}
        self.nomcla_base = {'CYT': ' DC', 'GUA': ' DG', 'THY': ' DT',
                            'ADE': ' DA', 'DA5': ' DA', 'DA3': ' DA',
                            'DT5': ' DT', 'DT3': ' DT', 'DG5': ' DG',
                            'DG3': ' DG', 'DC5': ' DC', 'DC3': ' DC'}
        self.nomcla_base_rev = {' DC': 'CYT', ' DG': 'GUA', ' DT': 'THY',
                                ' DA': 'ADE'}

    def reshuffle_pdb(self, pdb_file):
        unshuff_file = []
        rem = []
        for line in pdb_file:
            lineType = line[0:6]
            if lineType == "ATOM  ":
                unshuff_file.append(line)
            else:
                rem.append(line)
        unshuff_file.sort(key=lambda x: (x[72:76], int(x[22:27].strip())))
        newFile_list = (rem + unshuff_file)
        return newFile_list

    def correct_pdb(self, pdb_file, add_header, nomenclature,
                    molecule_chain, atom_number, occupancy, atomtype,
                    remove_H):
        reset_numbers = True
        # TODO: -low MODEL
        body = []
        if add_header:
            body.append(HEADER)

        for line in pdb_file:
            lineType = line[0:6]
            if lineType in ["TITLE ", "CRYST1"]:
                body.append(line)
            elif lineType == "ATOM  ":
                no_atom_check = line[13:15]
                if not(no_atom_check == "  "):
                    if nomenclature:
                        line = self.correct_nomenclature(line)
                    if molecule_chain:
                        line, is_ter = self.correct_molecule_chain_and_number(
                            line, reset_numbers)
                    if atom_number:
                        line = self.correct_atom_number(line)
                    if occupancy:
                        line = self.correct_occupancy(line)
                    if atomtype:
                        line = self.correct_atomtype(line)
                    if remove_H:
                        line = self.remove_H(line)
                    if is_ter:
                        body.append("TER\n")
                    body.append(line)

        body.append("TER\nEND\n")
        newFile = ''.join(body)
        return newFile

    def correct_atom_number(self, line):
        atom_number_string = number_to_hybrid36_number(
            self.current["atom_number"], 5)
        newline = line[0:5] + " " + atom_number_string + line[11:]
        self.current["atom_number"] += 1
        return newline

    def correct_nomenclature(self, line):
        atom = line[12:16]
        if self.reverse:
            REPLACEMENT = self.nomcla_rev
            REPLACEMENT_BASES = self.nomcla_base_rev
        else:
            REPLACEMENT = self.nomcla
            REPLACEMENT_BASES = self.nomcla_base

        if atom in REPLACEMENT:
            atom = REPLACEMENT.get(atom, '    ')
        base = line[17:20]
        if base in REPLACEMENT_BASES:
            base = REPLACEMENT_BASES.get(base, '   ')
        newline = line[0:12] + atom + ' ' + base + line[20:]
        return newline

    def correct_occupancy(self, line):
        newline = line[:54] + "  " + BFAC + "  " + OCC + line[66:]
        return newline

    def correct_molecule_chain_and_number(self, line, reset_numbers):
        def increase_chain_id(current_chain_id):
            possible_chain_ids = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            pos = possible_chain_ids.find(current_chain_id)
            chlen = len(possible_chain_ids)
            if (pos + 1 < chlen):
                return possible_chain_ids[pos+1]
            else:
                # Don't allow for A again (Scaffold) that's why 1 and not 0
                return possible_chain_ids[1]

        # chain_id = line[21:22]
        # TODO: -low chainID only
        chain = line[72:76]
        is_ter = False

        molecule_number_str = line[22:26]
        molecule_number = int(molecule_number_str.replace(' ', ''))

        if self.current["chain"] is None:
            self.current["chain"] = chain
            new_chain_id = self.current["chain_id"]
            new_molecule_number = 1
        elif chain == self.current["chain"]:
            new_chain_id = self.current["chain_id"]
            if molecule_number == self.current["old_molecule_number"]:
                new_molecule_number = self.current["last_molecule_number"]
            else:
                if (molecule_number ==
                        self.current["old_molecule_number"] + 1):
                    new_molecule_number = (
                        self.current["last_molecule_number"] + 1)
                else:
                    new_molecule_number = (
                        self.current["last_molecule_number"] + 10)
                    is_ter = True
        else:
            new_chain_id = increase_chain_id(self.current["chain_id"])
            is_ter = True
            new_molecule_number = 1
            if self.current["chain_id"] == "Z":
                self.current["chain_id_repeats"] += 1

        new_chain_str = (str(new_chain_id) +
                         str(self.current["chain_id_repeats"]).rjust(3, "0"))
        if reset_numbers is True:
            new_molecule_number_str = number_to_hybrid36_number(
                new_molecule_number, 4)
        else:
            new_molecule_number_str = number_to_hybrid36_number(
                molecule_number, 4)
        newline = (line[0:21] + new_chain_id + new_molecule_number_str +
                   line[26:67] + "     " + new_chain_str + line[76:])

        self.current["chain_id"] = new_chain_id
        self.current["chain"] = chain
        self.current["old_molecule_number"] = molecule_number
        self.current["last_molecule_number"] = new_molecule_number

        return newline, is_ter

    def remove_H(self, line):
        atom = line[12:16]
        if "H" in atom:
            return ""
        else:
            return line

    def correct_atomtype(self, line):
        atom = line[12:14]
        if atom[1] in "0123456789":
            atom = atom[0]

        atom = atom.strip().rjust(2, " ")
        newline = line[:76] + atom + line[78:]
        return newline


def get_description():
    return """namd (enrgMD) PDB to chimera PDB.
           """


def proc_input():
    parser = argparse.ArgumentParser(
        description=get_description(),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
        )
    parser.add_argument("--input",
                        help="input file",
                        type=str,
                        required="True",
                        default=argparse.SUPPRESS,
                        )
    parser.add_argument("--output",
                        help="output file",
                        type=str,
                        required="True",
                        default=argparse.SUPPRESS,
                        )
    parser.add_argument("--reverse",
                        help="reset nomenclature enrgMD",
                        action="store_true"
                        )
    parser.add_argument("--reshuffle",
                        help="reshuffle pdb by residue (for subsets)",
                        action="store_true"
                        )
    parser.add_argument("--header",
                        help="keep header",
                        action="store_true"
                        )
    args = parser.parse_args()
    Project = namedtuple("Project", ["input",
                                     "output",
                                     "reverse",
                                     "reshuffle",
                                     "header",
                                     ]
                         )
    project = Project(input=Path(args.input),
                      output=Path(args.output),
                      reverse=args.reverse,
                      reshuffle=args.reshuffle,
                      header=args.header,
                      )
    return project


def main():
    project = proc_input()

    print("start")
    pdb_Corr = PDB_Corr(project.reverse)
    with open(project.input, 'r') as file_init:
        if project.reshuffle:
            file_list = pdb_Corr.reshuffle_pdb(file_init)
        else:
            file_list = file_init
        newFile = pdb_Corr.correct_pdb(pdb_file=file_list,
                                       add_header=project.header,
                                       nomenclature=True,
                                       molecule_chain=True,
                                       atom_number=True,
                                       occupancy=True,
                                       atomtype=True,
                                       remove_H=False,
                                       )
    with open(project.output, "w") as file_corr:
        file_corr.write(newFile)

    print("done")
    return


if __name__ == "__main__":
    main()
