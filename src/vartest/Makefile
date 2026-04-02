CC := gcc
CFLAGS := -D_GNU_SOURCE -O2 -g -Wall -Wextra -pthread
BUILD_DIR := build
SOURCE_DIR := sources

COMMON_OBJS := $(BUILD_DIR)/config.o

TARGETS := \
	$(BUILD_DIR)/meas_sender \
	$(BUILD_DIR)/meas_receiver \
	$(BUILD_DIR)/background_gen \
	$(BUILD_DIR)/background_sink \
	$(BUILD_DIR)/hopvar_sender \
	$(BUILD_DIR)/hopvar_receiver \
	$(BUILD_DIR)/fct_pktgen_recv

.PHONY: all clean dirs

all: dirs $(TARGETS)

dirs:
	mkdir -p $(BUILD_DIR)

$(BUILD_DIR)/fct_pktgen_recv: $(SOURCE_DIR)/fct_pktgen_recv.c $(SOURCE_DIR)/config.h $(COMMON_OBJS)
	$(CC) $(CFLAGS) $< $(COMMON_OBJS) -o $@

$(BUILD_DIR)/config.o: $(SOURCE_DIR)/config.c $(SOURCE_DIR)/config.h
	$(CC) $(CFLAGS) -c $< -o $@

$(BUILD_DIR)/meas_sender: $(SOURCE_DIR)/meas_sender.c $(SOURCE_DIR)/meas_hdr.h $(SOURCE_DIR)/meas_hdr_user.h $(SOURCE_DIR)/config.h $(COMMON_OBJS)
	$(CC) $(CFLAGS) $< $(COMMON_OBJS) -o $@

$(BUILD_DIR)/meas_receiver: $(SOURCE_DIR)/meas_receiver.c $(SOURCE_DIR)/meas_hdr.h $(SOURCE_DIR)/meas_hdr_user.h $(SOURCE_DIR)/config.h $(COMMON_OBJS)
	$(CC) $(CFLAGS) $< $(COMMON_OBJS) -o $@

$(BUILD_DIR)/background_gen: $(SOURCE_DIR)/background_gen.c $(SOURCE_DIR)/config.h $(COMMON_OBJS)
	$(CC) $(CFLAGS) $< $(COMMON_OBJS) -o $@

$(BUILD_DIR)/background_sink: $(SOURCE_DIR)/background_sink.c $(SOURCE_DIR)/config.h $(COMMON_OBJS)
	$(CC) $(CFLAGS) $< $(COMMON_OBJS) -o $@

$(BUILD_DIR)/hopvar_sender: $(SOURCE_DIR)/hopvar_sender.c $(SOURCE_DIR)/hopvar_hdr.h $(SOURCE_DIR)/hopvar_hdr_user.h $(SOURCE_DIR)/config.h $(COMMON_OBJS)
	$(CC) $(CFLAGS) $< $(COMMON_OBJS) -o $@

$(BUILD_DIR)/hopvar_receiver: $(SOURCE_DIR)/hopvar_receiver.c $(SOURCE_DIR)/hopvar_hdr.h $(SOURCE_DIR)/hopvar_hdr_user.h $(SOURCE_DIR)/config.h $(COMMON_OBJS)
	$(CC) $(CFLAGS) $< $(COMMON_OBJS) -o $@
	
clean:
	rm -rf $(BUILD_DIR)
