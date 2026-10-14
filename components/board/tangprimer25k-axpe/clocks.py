"""nextpnr clock constraints from the resolved board profile."""
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools"))
import configure
resolved = configure.resolved_config(Path(os.environ["ATOMIX_FPGA_PROFILE"]))
configure.to_make(resolved)
board = resolved["components"]["board"]
values = {k:resolved["parameters"].get("board",{}).get(k,s["default"])
          for k,s in board["parameters"].items()}
input_hz = board["make"]["FPGA_INPUT_CLOCK_HZ"]
clock_hz = values["capture_clock_hz"] if values["capture_mode"] else input_hz//2
ctx.addClock("clk_50mhz", input_hz/1_000_000)
ctx.addClock("capture_clk", values["capture_clock_hz"]/1_000_000)
ctx.addClock("clock_ref", clock_hz/1_000_000)
ctx.addClock("bench_clk", clock_hz/1_000_000)
