#ifndef _RAFT_LAB_RAFT_HPP__
#define _RAFT_LAB_RAFT_HPP_

#include <vector>
#include <string>
#include "cornerstone.hxx"

using namespace cornerstone;

std::vector<ptr<srv_config>> load_cluster_config(const std::string& config_file);
std::vector<ptr<srv_config>> load_cluster_config(const std::string& config_file, std::string& self_name, int32_t& self_id, int16_t& self_port);

#endif // _RAFT_LAB_RAFT_HPP__