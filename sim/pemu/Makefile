ROOT := ../..
VERILATOR ?= verilator
BUILD := build

RTL := \
	$(ROOT)/components/pemu/axpe/axpe.sv \
	$(ROOT)/components/pemu/axpe/axpe_decode.sv \
	$(ROOT)/components/pemu/axpe/axpe_timing.sv \
	$(ROOT)/components/pemu/axpe/axpe_shift.sv \
	$(ROOT)/components/pemu/axpe/axpe_pads.sv

$(BUILD)/Vaxpe: axpe_cosim.cpp $(RTL) \
		$(ROOT)/sw/pemu/model/axpe_model.c \
		$(ROOT)/sw/pemu/model/axpe_model.h \
		$(ROOT)/sw/pemu/isa/axpe_isa.h
	$(VERILATOR) --cc --exe --build -Wall \
		--top-module axpe --Mdir $(BUILD) \
		-I$(ROOT)/sw/pemu/isa $(RTL) axpe_cosim.cpp \
		$(ROOT)/sw/pemu/model/axpe_model.c

check: $(BUILD)/Vaxpe
	$(BUILD)/Vaxpe

clean:
	rm -rf $(BUILD)

.PHONY: check clean
