#
# Makefile for P4 program compilation
#
TARGET_NAME=spineleaf
NOPAXOS_TARGET_NAME=nopaxos_tofino

TOOLS_PATH=~/tools/
BUILD_TOOLS=$(TOOLS_PATH)p4_build.sh
P4_SRC=p4src/$(TARGET_NAME).p4
NOPAXOS_P4_SRC=p4src/$(NOPAXOS_TARGET_NAME).p4
BUILD_FLAGS=--with-tofino2

RUN_SWITCH=$(SDE)/run_switchd.sh

nopaxos: nopaxos_tofino
	$(RUN_SWITCH) -p $(NOPAXOS_TARGET_NAME) --arch tofino2

# launch p4 program build
run_switch: spineleaf
	$(RUN_SWITCH) -p $(TARGET_NAME) --arch tofino2

# build p4 program
spineleaf:
	$(BUILD_TOOLS) $(P4_SRC) $(BUILD_FLAGS)

nopaxos_tofino:
	$(BUILD_TOOLS) $(NOPAXOS_P4_SRC) $(BUILD_FLAGS)

clean:
	rm -rf build/ $(TARGET_NAME).p4.json $(NOPAXOS_TARGET_NAME).p4.json

.PHONY: build clean run_switch spineleaf
