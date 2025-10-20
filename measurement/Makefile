# Makefile for timestamp measurement

# Variables
CC = gcc				# Compiler
CFLAGS = -Wall -g		# Compiler Flags
LDFLAGS =				# Linker flags
TX_TARGET = tx			# TX
RX_TARGET = rx			# RX

all: $(TX_TARGET) $(RX_TARGET)

$(TX_TARGET): tx.o
	$(CC) tx.o -o $@ $(LDFLAGS)

$(RX_TARGET): rx.o
	$(CC) rx.o -o $@ $(LDFLAGS)

tx.o: timestamp_tx.c
	$(CC) $(CFLAGS) -c $< -o $@

rx.o: timestamp_rx.c
	$(CC) $(CFLAGS) -c $< -o $@

# Clean up build artifacts
.PHONY: clean
clean:
	rm -f tx.o rx.o rx tx
