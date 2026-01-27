# Makefile for Raft Lab
CC = g++
CFLAGS = -Wall -Wextra -g
RAFT_SERVER_SRC = synraft-server.cpp synraft-utils.cpp
RAFT_CLIENT_SRC = synraft-client.cpp synraft-utils.cpp
RAFT_SERVER_OBJ = $(RAFT_SERVER_SRC:.cpp=.o)
RAFT_CLIENT_OBJ = $(RAFT_CLIENT_SRC:.cpp=.o)
TARGETS = server client
INCLUDES = -I./include

# ASIO
ASIO_DIR = cornerstone/asio/asio
INCLUDES += -I$(ASIO_DIR)/include
CFLAGS += -DASIO_STANDALONE

# Cornerstone
CORNERSTONE_DIR = cornerstone
INCLUDES += -I$(CORNERSTONE_DIR)/include
CFLAGS += -std=c++17 -Wall -O2
LDFLAGS += -L$(CORNERSTONE_DIR)/build -lcornerstone -lpthread

all: $(TARGETS)

server: $(RAFT_SERVER_OBJ)
	$(CC) $(CFLAGS) $(INCLUDES) -o $@ $^ $(LDFLAGS)

client: $(RAFT_CLIENT_OBJ)
	$(CC) $(CFLAGS) $(INCLUDES) -o $@ $^ $(LDFLAGS)

%.o: %.cpp
	$(CC) $(CFLAGS) $(INCLUDES) -c $< -o $@

clean:
	rm -f $(RAFT_SERVER_OBJ) $(RAFT_CLIENT_OBJ) $(TARGETS)

.PHONY: all clean
