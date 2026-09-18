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

VFLAGS := --cc --exe --build -Wall -I$(ROOT)/sw/pemu/isa

DEPS := axpe_trace.h $(MODEL) \
	$(ROOT)/sw/pemu/model/axpe_model.h \
	$(ROOT)/sw/pemu/isa/axpe_isa.h

$(BUILD)/Vaxpe: axpe_cosim.cpp $(CORE_RTL) $(DEPS)
	$(VERILATOR) $(VFLAGS) --top-module axpe --Mdir $(BUILD) \
		$(CORE_RTL) axpe_cosim.cpp $(MODEL)

$(BUILD)/chip/Vaxpe_chip: axpe_chip_tb.cpp $(CHIP_RTL) $(DEPS)
	@mkdir -p $(BUILD)/chip
	$(VERILATOR) $(VFLAGS) --top-module axpe_chip --Mdir $(BUILD)/chip \
		$(CHIP_RTL) axpe_chip_tb.cpp $(MODEL)

# Two gates, separately runnable, because they answer different questions:
# `core` is whether the machine keeps its declared cycle counts, `chip` is
# whether a fabricated one could be given a different program at all.
core: $(BUILD)/Vaxpe
	$(BUILD)/Vaxpe

chip: $(BUILD)/chip/Vaxpe_chip
	$(BUILD)/chip/Vaxpe_chip

check: core chip

clean:
	rm -rf $(BUILD)

.PHONY: check core chip clean
