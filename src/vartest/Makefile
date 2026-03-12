#
PROJECT := meas_proto

CC := gcc
CFLGAS := -O2 -g -Wall -Wextra -Werror -std=c11
CPPFLAGS :=

BUILD_DIR := build

TARGETS := $(BUILD_DIR)/sender $(BUILD_DIR)/receiver

.PHONY: all clean run-recv run-send dirs

all: dirs $(TARGETS)

dirs:
	mkdir -p $(BUILD_DIR)

$(BUILD_DIR)/sender: sender.c meas_hdr.h meas_hdr_user.h
	$(CC) $(CFLAGS) $(CPPFLAGS) -o $@ $<

$(BUILD_DIR)/receiver: receiver.c meas_hdr.h meas_hdr_user.h
	$(CC) $(CFLAGS) $(CPPFLAGS) -o $@ $<

run-recv: $(BUILD_DIR)/receiver
	./$< 1997

run-send: $(BUILD_DIR)/sender
	./$< 127.0.0.1 1997

clean:
	rm -rf $(BUILD_DIR)
