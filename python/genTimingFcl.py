#!/usr/bin/env python
# Generate timing test fcl

import os

from argparse import ArgumentParser
from codecs import open


# --------------------------------------------------------------------------------
# Parse the trigger sequences
# --------------------------------------------------------------------------------
def parse_sequences(online, verbose):
    file_path = "mu2e-trig-config/core/trigSequences.fcl"
    if online: file_path = 'srcs/' + file_path
    with open(file_path, "r") as f:
        paths = dict()
        current = ""
        started = False
        ended = False
        for line in f:
            if "#" in line:
                continue
            line = " ".join(line.split())  # remove multiple spaces
            if ": [" in line or ":[" in line:  # new sequence
                current = line.split()[0]
                current = current.replace(":", "")
                paths[current] = []
                if verbose > 0:
                    print(f"  Found new sequence {current}")
                line = line.split(": [")[1]
                started = True
                ended = False
            if "]" in line:
                ended = True
            elif ended or not started:
                continue
            line = line.replace("]", "")
            line = line.replace('"', "")
            line = line.replace(" ", "")
            if verbose > 2:
                print(f"    Parsing line {line} for modules in {current} path")
            modules = line.split(",")
            for module in modules:
                if module == "":
                    continue
                paths[current].append(module)
            if ended and verbose > 1:
                print(f"    {current} path is {paths[current]}")

        return paths


# --------------------------------------------------------------------------------
# Add the header info
# --------------------------------------------------------------------------------
def start_fcl(f, fragments):
    f.write("# Trigger timing fcl\n\n")
    if fragments:
        f.write('#include "mu2e-trig-config/test/timingTestFragments.fcl"\n\n')
    else:
        f.write('#include "mu2e-trig-config/test/timingTest.fcl"\n\n')


# --------------------------------------------------------------------------------
# Add the timing paths for a specific path
# --------------------------------------------------------------------------------
def add_path(path, sequence_map, f, verbose):
    if verbose > 0:
        print(f"Adding path {path}")
    module_list = ""
    counter = 0
    timing_list = f"Timing_paths.{path} : ["
    for module in sequence_map[path]:
        if "filter" in module.lower():
            f.write(f"physics.{path}_timing_{counter} : [{module_list}]\n")
            if counter > 0:
                timing_list += ", "
            timing_list += f"{path}_timing_{counter}"
            counter += 1
        if module_list == "":
            module_list = module
        else:
            module_list = module_list + ", " + module
    f.write(f"{timing_list} ]\n\n")


# --------------------------------------------------------------------------------
# Generate the fcl
# --------------------------------------------------------------------------------
def generate(name, paths, online, fragments, verbose):
    sequence_map = parse_sequences(online, verbose)
    with open(name, "w") as f:
        start_fcl(f, fragments)
        trigger_paths = "physics.trigger_paths : [ "
        counter = 0
        for path in paths:
            if path not in sequence_map:
                print(f"!!! Path {path} not found in the sequence map!")
                continue
            add_path(path, sequence_map, f, verbose)
            if counter > 0:
                trigger_paths += ", "
            trigger_paths += f"{path}, @sequence::Timing_paths.{path}"
            counter += 1
        f.write(f"{trigger_paths} ]\n")
        print(f">>> Created timing fcl {name}")


# --------------------------------------------------------------------------------
# Main function
# --------------------------------------------------------------------------------
if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument(
        "-p",
        "--paths",
        dest="paths",
        default="",
        help="Comma separated list of trigger paths",
    )
    parser.add_argument(
        "-n",
        "--name",
        dest="name",
        default="trigger_timing",
        help="Name for output file",
    )
    parser.add_argument(
        "-o", "--online", dest="online", default=False, type=bool, help="Assume Online setup"
    )
    parser.add_argument(
        "-f", "--fragments", dest="fragments", default=False, type=bool, help="Run from fragments"
    )
    parser.add_argument(
        "-v", "--verbose", dest="verbose", default=0, type=int, help="Verbosity"
    )

    args = parser.parse_args()
    paths = args.paths.split(",")
    name = args.name
    online = args.online
    fragments = args.fragments
    verbose = args.verbose

    if not name.endswith(".fcl"):
        name = name + ".fcl"

    if verbose > 0:
        print(f"Using output fcl {name} with trigger paths {paths}")

    generate(name, paths, online, fragments, verbose)
