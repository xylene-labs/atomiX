# Standalone protocol replay over the exported Tiny Tapeout RTL.
ROOT := $(abspath ..)
BUILD := $(CURDIR)/build
VERILATOR ?= verilator
PYTHON ?= python3
JOBS ?= 2
TOP := tt_um_shubhgau_atomix_axpe

include $(ROOT)/test/profile.mk
RTL := $(wildcard $(ROOT)/src/*.sv)
HEADERS := $(wildcard $(ROOT)/src/*.svh) $(wildcard $(ROOT)/sim/pemu/*.h) \
           $(ROOT)/sw/pemu/model/axpe_model.h $(ROOT)/sw/pemu/isa/axpe_isa.h
MODEL := $(ROOT)/sw/pemu/model/axpe_model.c
BENCH := $(ROOT)/sim/pemu/axpe_tt_tb.cpp
DEMOS := uart-demo spi-demo i2c-demo autobaud-demo
HEX := $(DEMOS:%=$(BUILD)/fw/%.hex)
MAPPED := $(ROOT)/hardened/design.nl.v $(ROOT)/hardened/cells.v
RATE_PROFILES := $(sort $(wildcard $(ROOT)/sw/pemu/firmware/profiles/*.json))

$(BUILD)/obj/V$(TOP): $(RTL) $(HEADERS) $(MODEL) $(BENCH) $(ROOT)/test/profile.mk Makefile
	@mkdir -p $(BUILD)/obj
	$(VERILATOR) --cc --exe --build -j $(JOBS) -Wall --x-initial unique --x-assign unique \
	  -I$(ROOT)/src $(PROFILE_DEFINES) --top-module $(TOP) --Mdir $(BUILD)/obj \
	  $(RTL) $(BENCH) $(MODEL)

$(BUILD)/fw/%.hex: $(ROOT)/sw/pemu/firmware/%.s \
                   $(wildcard $(ROOT)/sw/pemu/firmware/*.s) \
                   $(ROOT)/sw/pemu/as/axpe_as.py $(ROOT)/tools/axpe_isa.py \
                   $(ROOT)/sw/pemu/isa/axpe-isa.json $(ROOT)/test/profile.mk Makefile
	@mkdir -p $(BUILD)/fw
	$(PYTHON) $(ROOT)/sw/pemu/as/axpe_as.py --imem-words $(DEMO_IMEM_WORDS) --hex $@ $<

check: $(BUILD)/obj/V$(TOP) $(HEX)
	$(PYTHON) $(ROOT)/tools/axpe_isa.py check
	$(BUILD)/obj/V$(TOP) $(BUILD)/fw +verilator+rand+reset+2 +verilator+seed+1
	$(BUILD)/obj/V$(TOP) $(BUILD)/fw +verilator+rand+reset+2 +verilator+seed+17
	$(BUILD)/obj/V$(TOP) $(BUILD)/fw +verilator+rand+reset+2 +verilator+seed+91

# Runtime profiles reuse the already compiled hardware. The profile builder
# validates/reuses matching images and refuses stale or altered ones.
rate-check: $(BUILD)/obj/V$(TOP)
	$(PYTHON) $(ROOT)/sw/pemu/firmware/check_demos.py
	@set -e; for profile in $(RATE_PROFILES); do \
	  name=$$(basename "$$profile" .json); \
	  $(PYTHON) $(ROOT)/sw/pemu/firmware/build_demos.py --profile "$$profile" \
	    --imem-words $(DEMO_IMEM_WORDS) --output $(BUILD)/fw-rates/"$$name"; \
	  for seed in 1 17 91; do \
	    $(BUILD)/obj/V$(TOP) $(BUILD)/fw-rates/"$$name" \
	      +verilator+rand+reset+2 +verilator+seed+$$seed; \
	  done; \
	done

mapped-rate-check: $(BUILD)/mapped/V$(TOP)
	@set -e; for profile in $(RATE_PROFILES); do \
	  name=$$(basename "$$profile" .json); \
	  $(PYTHON) $(ROOT)/sw/pemu/firmware/build_demos.py --profile "$$profile" \
	    --imem-words $(DEMO_IMEM_WORDS) --output $(BUILD)/fw-rates/"$$name"; \
	  $(PYTHON) $(ROOT)/verification/check_package.py \
	    --rate-firmware-dir $(BUILD)/fw-rates/"$$name" --rate-profile "$$name"; \
	  for seed in 1 17 91; do \
	    $(BUILD)/mapped/V$(TOP) $(BUILD)/fw-rates/"$$name" \
	      +verilator+rand+reset+2 +verilator+seed+$$seed; \
	  done; \
	done

# Present only in a candidate package; the generic source export stays usable.
package-check:
	$(PYTHON) $(ROOT)/verification/check_package.py

formal-check: package-check
	$(PYTHON) $(ROOT)/verification/check_timing.py

$(BUILD)/mapped/V$(TOP): $(MAPPED) $(HEADERS) $(MODEL) $(BENCH) Makefile | package-check
	$(VERILATOR) --cc --exe --build -j $(JOBS) -Wall \
	  -Wno-DECLFILENAME -Wno-UNUSEDSIGNAL -Wno-PINMISSING \
	  --x-initial unique --x-assign unique --top-module $(TOP) \
	  --Mdir $(BUILD)/mapped $(MAPPED) $(BENCH) $(MODEL)

mapped-check: package-check $(BUILD)/mapped/V$(TOP) $(HEX)
	$(PYTHON) $(ROOT)/tools/axpe_isa.py check
	$(PYTHON) $(ROOT)/verification/check_package.py --firmware-dir $(BUILD)/fw
	$(BUILD)/mapped/V$(TOP) $(BUILD)/fw +verilator+rand+reset+2 +verilator+seed+1
	$(BUILD)/mapped/V$(TOP) $(BUILD)/fw +verilator+rand+reset+2 +verilator+seed+17
	$(BUILD)/mapped/V$(TOP) $(BUILD)/fw +verilator+rand+reset+2 +verilator+seed+91

.DEFAULT_GOAL := check
.PHONY: check rate-check package-check mapped-check mapped-rate-check formal-check
