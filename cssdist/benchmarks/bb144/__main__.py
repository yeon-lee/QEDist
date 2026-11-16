"""Audit or repeat the BB144 single-cycle fault-distance benchmark."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from ...circuit_run import _RECURSIVE_SOURCES, source_hashes

HERE = Path(__file__).resolve().parent
NATIVE = HERE.parents[1] / "native_circuit"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_events(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--search", action="store_true", help="repeat the weight-nine exclusions")
    parser.add_argument("--large-capacity", action=argparse.BooleanOptionalAction, default=False,
                        help="use expanded storage for the fresh search; default uses the faster engine")
    parser.add_argument("--ibm-source", type=Path, metavar="decoder_setup.py",
                        help="regenerate the inputs and replay witnesses with IBM's simulator")
    options = parser.parse_args()
    record = json.loads((HERE / "record.json").read_text())
    with tempfile.TemporaryDirectory() as folder:
        work = Path(folder)
        def run_python(name):
            subprocess.run([sys.executable, "-E", name], cwd=work, check=True)

        for name in ("models.py", "neutral.py", "symmetry.py", "replay.py"):
            shutil.copyfile(HERE / name, work / name)
        for path in HERE.glob("*.jsonl"):
            shutil.copyfile(path, work / path.name)
        for sector in "XZ":
            shutil.copyfile(HERE / (sector + ".model"), work / (sector + ".model"))
        run_python("symmetry.py")
        if options.ibm_source:
            require(digest(options.ibm_source) == record["upstream_sha256"], "Unrecognized IBM source")
            source = options.ibm_source.read_text()
            require(source.count("num_cycles = 12") == 1, "Unexpected cycle setting")
            (work / "decoder_setup.py").write_text(source.replace("num_cycles = 12", "num_cycles = 1"))
            (work / "TMP").mkdir()
            run_python("replay.py")
            require(json.loads((work / "replayed.json").read_text()) == record["witness_replay"],
                    "Physical witness replay disagrees with the reference")
            run_python("models.py")
        run_python("neutral.py")
        recorded_sources = {name: record["sha256"][name] for name in ("exact.cpp", "common.hpp")}
        require(recorded_sources in (_RECURSIVE_SOURCES, source_hashes()),
                "Unrecognized engine identity in the archived BB144 record")
        for name, expected in record["sha256"].items():
            if name not in recorded_sources:
                require(digest(work / name) == expected, f"Digest mismatch for {name}")

        if options.search:
            native = NATIVE if options.large_capacity else NATIVE / "fixed"
            subprocess.run([os.environ.get("CXX", "c++"), *record["compiler_flags"],
                            str(native / "exact.cpp"), "-o", str(work / "exact")], check=True)
        for sector in "XZ":
            model = work / (sector + ".relations")
            lines = model.read_text().splitlines()
            _, n, m, o, _ = lines[0].split()
            roots = json.loads((work / (sector + ".sym.json")).read_text())["roots"]
            witness, terminal = read_events(work / (sector + "-relations-10.jsonl"))
            support = set(witness["support"])
            require(witness["event"] == "witness" and terminal["status"] == "witness"
                    and witness["weight"] == len(witness["support"]) == len(support) == 10
                    and min(support) >= 0 and max(support) < int(n), "Invalid witness")
            parity = [sum(int(j) in support for j in line.split()[1:]) % 2
                      for line in lines[1:1 + int(m) + int(o)]]
            flips = [j for j, bit in enumerate(parity[int(m):]) if bit]
            physical = record["witness_replay"][sector + "-relations-10.jsonl"]
            require(not any(parity[:int(m)]) and flips and flips == physical["logical_bits"],
                    "Witness syndrome or logical action disagrees")
            result, = read_events(work / (sector + "-relations-9.jsonl"))
            def check_exclusion(r):
                require(r["status"] == "excluded" and r["W"] == 9 and r["root_begin"] == 0
                        and r["root_end"] == r["roots_completed"] == roots
                        and r["roots_total"] == int(n), "Incomplete orbit exclusion")

            check_exclusion(result)
            if options.search:
                command = [str(work / "exact"), str(model), "9", "3600", "1000000000000",
                           "weighted=on", "neutral=on", f"root-end={roots}"]
                output = subprocess.check_output(command, text=True)
                fresh = json.loads(output.strip())
                check_exclusion(fresh)
                print(f"{sector}: fresh exclusion through 9 in {fresh['search_seconds']:.3f} s")
            print(f"{sector}: verified {roots} orbit roots, recorded exclusion through 9, "
                  f"and weight-10 logical on observables {flips}")


if __name__ == "__main__":
    main()
