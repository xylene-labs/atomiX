ROOT := ../..
VERILATOR ?= verilator
BUILD := build

CORE_RTL := \
	$(ROOT)/components/pemu/axpe/axpe.sv \
	$(ROOT)/components/pemu/axpe/axpe_decode.sv \
	$(ROOT)/components/pemu/axpe/axpe_timing.sv \
	$(ROOT)/components/pemu/axpe/axpe_shift.sv \
	$(ROOT)/components/pemu/axpe/axpe_pads.sv

# The chip adds what makes it loadable after fabrication.
CHIP_RTL := $(CORE_RTL) \
	$(ROOT)/components/pemu/axpe/axpe_imem.sv \
	$(ROOT)/components/pemu/axpe/axpe_host.sv \
	$(ROOT)/components/pemu/axpe/axpe_chip.sv

MODEL := $(ROOT)/sw/pemu/model/axpe_model.c
PYTHON ?= python3

# The chip bench runs the firmware in sw/pemu/firmware, assembled here rather
# than transcribed into the testbench, so what the peers judge is what the
# submission ships.
FIRMWARE := $(ROOT)/sw/pemu/firmware
DEMOS := uart-demo spi-demo i2c-demo
HEX := $(DEMOS:%=$(BUILD)/fw/%.hex)

VFLAGS := --cc --exe --build -Wall -I$(ROOT)/sw/pemu/isa

DEPS := axpe_trace.h $(MODEL) \
	$(ROOT)/sw/pemu/model/axpe_model.h \
	$(ROOT)/sw/pemu/isa/axpe_isa.h

$(BUILD)/Vaxpe: axpe_cosim.cpp $(CORE_RTL) $(DEPS)
	$(VERILATOR) $(VFLAGS) --top-module axpe --Mdir $(BUILD) \
		$(CORE_RTL) axpe_cosim.cpp $(MODEL)

$(BUILD)/fw/%.hex: $(FIRMWARE)/%.s $(wildcard $(FIRMWARE)/*.s) \
		$(ROOT)/sw/pemu/as/axpe_as.py $(ROOT)/sw/pemu/isa/axpe-isa.json
	@mkdir -p $(BUILD)/fw
	$(PYTHON) $(ROOT)/sw/pemu/as/axpe_as.py --hex $@ $<

$(BUILD)/chip/Vaxpe_chip: axpe_chip_tb.cpp axpe_peers.h $(CHIP_RTL) $(DEPS)
	@mkdir -p $(BUILD)/chip
	$(VERILATOR) $(VFLAGS) --top-module axpe_chip --Mdir $(BUILD)/chip \
		$(CHIP_RTL) axpe_chip_tb.cpp $(MODEL)

# Two gates, separately runnable, because they answer different questions:
# `core` is whether the machine keeps its declared cycle counts, `chip` is
# whether a fabricated one could be given a different program at all.
core: $(BUILD)/Vaxpe
	$(BUILD)/Vaxpe

chip: $(BUILD)/chip/Vaxpe_chip $(HEX)
	$(BUILD)/chip/Vaxpe_chip $(BUILD)/fw

check: core chip

clean:
	rm -rf $(BUILD)

.PHONY: check core chip clean
