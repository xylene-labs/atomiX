SIM ?= icarus
FST ?= -fst
TOPLEVEL_LANG ?= verilog
SRC_DIR := $(PWD)/../src
PROJECT_SOURCES := \
	tt_um_shubhgau_atomix_axpe.sv axpe.sv axpe_decode.sv axpe_timing.sv \
	axpe_shift.sv axpe_pads.sv axpe_imem.sv axpe_host.sv axpe_chip.sv

-include profile.mk

ifneq ($(GATES),yes)
SIM_BUILD := sim_build/rtl
VERILOG_SOURCES += $(addprefix $(SRC_DIR)/,$(PROJECT_SOURCES))
COMPILE_ARGS += $(PROFILE_DEFINES)
ifeq ($(SIM),icarus)
COMPILE_ARGS += -g2012
endif
else
SIM_BUILD := sim_build/gl
COMPILE_ARGS += -DGL_TEST -DFUNCTIONAL -DSIM
VERILOG_SOURCES += $(PDK_ROOT)/ihp-sg13cmos5l/libs.ref/sg13cmos5l_io/verilog/sg13cmos5l_io.v
VERILOG_SOURCES += $(PDK_ROOT)/ihp-sg13cmos5l/libs.ref/sg13cmos5l_stdcell/verilog/sg13cmos5l_stdcell.v
VERILOG_SOURCES += $(PWD)/gate_level_netlist.v
endif

COMPILE_ARGS += -I$(SRC_DIR)
VERILOG_SOURCES += $(PWD)/tb.v
TOPLEVEL := tb
COCOTB_TEST_MODULES := test
include $(shell cocotb-config --makefiles)/Makefile.sim
