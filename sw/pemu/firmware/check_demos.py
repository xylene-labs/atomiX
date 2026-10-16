#!/usr/bin/env python3
"""Reject unsafe/stale runtime profiles and prove constants reach images."""
import json
from pathlib import Path
import tempfile
from build_demos import HERE, build
from axpe_as import AsmError, assemble


def main():
    with tempfile.TemporaryDirectory(prefix="axpe-runtime-check-") as tmp:
        root = Path(tmp)
        standard = HERE / "profiles/40mhz-standard.json"
        fast = HERE / "profiles/40mhz-fast-i2c.json"
        a = build(standard, root / "standard", 64)
        b = build(fast, root / "fast", 64)
        slow = build(HERE / "profiles/40mhz-slow.json", root / "slow", 64)
        assert slow["cycles_per_bit"] == {"uart_baud": 347, "spi_hz": 4000, "i2c_hz": 4000}
        assert a["cycles_per_bit"] == {"uart_baud": 347, "spi_hz": 40, "i2c_hz": 400}
        assert b["cycles_per_bit"] == {"uart_baud": 694, "spi_hz": 20, "i2c_hz": 112}
        for name in ("uart-demo", "spi-demo", "i2c-demo"):
            assert (root / "standard" / f"{name}.hex").read_bytes() != (root / "fast" / f"{name}.hex").read_bytes()
        # Omitted overrides must preserve the historical 50 MHz images.
        for name in ("uart-demo", "spi-demo", "i2c-demo", "autobaud-demo"):
            p = HERE / f"{name}.s"
            assert len(assemble(p.read_text(), p, 64)) <= 64
        assert build(standard, root / "standard", 64) == a
        guard_profile = root / "guard-zero.json"
        guard_values = json.loads(fast.read_text())
        guard_values["settings"]["i2c_guard_ns"] = 0
        guard_profile.write_text(json.dumps(guard_values))
        c = build(guard_profile, root / "guard-zero", 64)
        assert c["cycles_per_bit"]["i2c_hz"] == 104
        assert (root / "guard-zero/i2c-demo.hex").read_bytes() != (root / "fast/i2c-demo.hex").read_bytes()
        bad = [({"typo": 1}, "unknown"), ({"clock_hz": True}, "positive"),
               ({"uart_baud": 0}, "positive"), ({"uart_baud": 1}, "UART"),
               ({"spi_hz": 930000}, "even"), ({"i2c_hz": 400001}, "ceiling"),
               ({"i2c_guard_ns": -1}, "nonnegative"), ({"i2c_guard_ns": True}, "nonnegative"),
               ({"clock_hz": 1}, "UART")]
        for i, (override, diagnostic) in enumerate(bad):
            profile = root / f"bad-{i}.json"
            value = json.loads(standard.read_text())
            value["settings"].update(override)
            profile.write_text(json.dumps(value))
            output = root / f"bad-output-{i}"
            try:
                build(profile, output, 64)
            except ValueError as exc:
                assert diagnostic in str(exc), str(exc)
                assert not output.exists()
            else:
                raise AssertionError(f"bad runtime profile accepted: {override}")
        try:
            build(standard, root / "too-small", 16)
        except AsmError:
            assert not (root / "too-small").exists()
        else:
            raise AssertionError("payload overflow accepted")
        try:
            build(fast, root / "standard", 64)
        except ValueError:
            pass
        else:
            raise AssertionError("stale profile reused")
        image = root / "standard/spi-demo.hex"
        image.write_text("00000000\n")
        try:
            build(standard, root / "standard", 64)
        except ValueError:
            pass
        else:
            raise AssertionError("altered image reused")
    print("axpe runtime profile check: PASS (three non-default rate profiles; 12 refusals)")


if __name__ == "__main__":
    main()
