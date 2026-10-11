#!/usr/bin/env python3
"""Assemble clock-profiled runtime demos without changing hardware inputs."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent / "as"))
from axpe_as import AsmError, DELAY_MAX, assemble, format_listing


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def i2c_period(values: dict[str, int]) -> int:
    clock, rate, guard = (values[k] for k in ("clock_hz", "i2c_hz", "i2c_guard_ns"))
    low, high = (4700, 4000) if rate <= 100000 else (1300, 600)
    ceil = lambda numerator, denominator: (numerator + denominator - 1) // denominator
    period = max(ceil(clock, rate), 2 * ceil(clock * (low + guard), 1000000000),
                 2 * ceil(clock * (high + guard), 1000000000))
    return ceil(period, 4) * 4


def settings(profile: Path) -> dict[str, int]:
    owner = json.loads((HERE / "demo.json").read_text())
    source = json.loads(profile.read_text())
    if source.get("schema") != "org.atomix.axpe-demo-profile.v1" or set(source) != {"schema", "settings"}:
        raise ValueError("invalid runtime demo profile")
    values = {name: spec["default"] for name, spec in owner["parameters"].items()}
    if not isinstance(source["settings"], dict) or source["settings"].keys() - values.keys():
        raise ValueError("unknown runtime demo setting")
    values.update(source["settings"])
    if any(type(v) is not int or v < (0 if k == "i2c_guard_ns" else 1) for k, v in values.items()):
        raise ValueError("clock and rates must be positive integers; guard must be nonnegative")
    clock = values["clock_hz"]
    if values["i2c_hz"] > 400000:
        raise ValueError("I2C rate exceeds supported Standard/Fast-mode ceiling")
    uart, spi = (clock // values[k] for k in ("uart_baud", "spi_hz"))
    i2c = i2c_period(values)
    if not 2 <= uart <= DELAY_MAX // 16:
        raise ValueError("UART period/receive timeout does not fit the ISA delay field")
    if not 2 <= spi <= DELAY_MAX or spi % 2:
        raise ValueError("SPI period must fit the ISA and be even")
    if not 4 <= i2c <= DELAY_MAX or i2c % 4:
        raise ValueError("I2C period must fit the ISA and be divisible by four")
    return values


def build(profile: Path, output: Path, imem_words: int) -> dict:
    values = settings(profile)
    if not 1 <= imem_words <= 256:
        raise ValueError("instruction capacity must be in 1..256")
    inputs = [profile.resolve(), HERE / "demo.json", Path(__file__).resolve(),
              HERE.parent / "as/axpe_as.py", ROOT / "tools/axpe_isa.py",
              HERE.parent / "isa/axpe-isa.json"] + sorted(HERE.glob("*.s"))
    hashes = {str(path): sha(path) for path in inputs}
    # Assemble everything before creating output, so invalid rate/capacity
    # settings never leave an apparently usable half-built image.
    programs = {}
    for name, rate_name, symbol in (("uart-demo", "uart_baud", "BAUD_RATE"),
                                    ("spi-demo", "spi_hz", "SPI_HZ"),
                                    ("i2c-demo", "i2c_hz", "SCL_HZ"),
                                    ("autobaud-demo", "uart_baud", "BAUD_RATE")):
        path = HERE / f"{name}.s"
        defines = {"CLK_HZ": values["clock_hz"], symbol: values[rate_name]}
        if name == "i2c-demo":
            defines["BIT_PERIOD"] = i2c_period(values)
        programs[name] = assemble(path.read_text(), path, imem_words, defines)
    if output.exists():
        old = json.loads((output / "profile.json").read_text())
        expected_files = {f"{name}.{suffix}" for name in programs for suffix in ("hex", "listing")}
        expected_files.add("clock-profile.txt")
        if (old.get("inputs_sha256") != hashes or old.get("imem_words") != imem_words or
            old.get("settings") != values or set(old.get("outputs_sha256", {})) != expected_files):
            raise ValueError("existing runtime images have different inputs; use a fresh output")
        for name, digest in old["outputs_sha256"].items():
            if sha(output / name) != digest:
                raise ValueError(f"existing runtime image changed: {name}")
        return old
    output.mkdir(parents=True)
    for name, program in programs.items():
        (output / f"{name}.hex").write_text("".join(f"{i.word:08x}\n" for i in program))
        (output / f"{name}.listing").write_text(format_listing(program) + "\n")
    (output / "clock-profile.txt").write_text(" ".join(str(values[k]) for k in
        ("clock_hz", "uart_baud", "spi_hz", "i2c_hz", "i2c_guard_ns")) + "\n")
    record = {"schema": "org.atomix.axpe-demo-build.v1", "settings": values,
              "imem_words": imem_words, "inputs_sha256": hashes,
              "cycles_per_bit": {"uart_baud": values["clock_hz"] // values["uart_baud"],
                                 "spi_hz": values["clock_hz"] // values["spi_hz"],
                                 "i2c_hz": i2c_period(values)},
              "outputs_sha256": {p.name: sha(p) for p in sorted(output.iterdir())}}
    (output / "profile.json").write_text(json.dumps(record, indent=2) + "\n")
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--imem-words", required=True, type=int)
    args = parser.parse_args()
    try:
        record = build(args.profile, args.output, args.imem_words)
    except (ValueError, OSError, KeyError, AsmError) as exc:
        print(f"axpe runtime demos: FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"axpe runtime demos: PASS: {record['cycles_per_bit']}; {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
