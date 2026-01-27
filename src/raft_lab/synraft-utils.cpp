#include "cornerstone.hxx"
#include <vector>
#include <string>
#include <toml++/toml.hpp>
#include <spdlog/spdlog.h>

using namespace cornerstone;

/*
 * @brief Parses the given TOML configuration file to extract server details
 *        and constructs a vector of srv_config objects representing the cluster.
 * 
 * @param config_file The path to the TOML configuration file.
 * 
 * @return A vector of ptr<srv_config> representing the cluster configuration.
 */
std::vector<ptr<srv_config>> load_cluster_config(const std::string& config_file)
{
    auto config = toml::parse_file(config_file);
    auto servers = config["servers"]["node"].as_array();
    std::vector<ptr<srv_config>> cluster;

    for (const auto& srv : *servers)
    {
        if (!srv.is_table())
        {
            continue;
        }
        auto srv_table = srv.as_table();
        int32_t id = (*srv_table)["id"].value_or(0);
        std::string name = (*srv_table)["name"].value_or("");
        std::string address = (*srv_table)["address"].value_or("");
        int port = (*srv_table)["port"].value_or(0);
        cluster.push_back(cs_new<srv_config>(id, sstrfmt("tcp://%s:%d").fmt(address.c_str(), port)));

        spdlog::info("Configured server - ID: {}, Name: {}, Address: {}, Port: {}", id, name, address, port);
    }

    return cluster;
}

/*
 * @brief Parses the given TOML configuration file to extract server details,
 *        identifies the server with the given name, and constructs a vector of
 *       srv_config objects representing the cluster.
 * 
 * @param config_file The path to the TOML configuration file.
 * @param self_name The name of the server to identify.
 * @param self_id Output parameter to hold the identified server's ID.
 * @param self_port Output parameter to hold the identified server's port.
 */
std::vector<ptr<srv_config>>
load_cluster_config(const std::string& config_file,
                    std::string& self_name,
                    int32_t& self_id,
                    int16_t& self_port)
{
    auto config = toml::parse_file(config_file);
    auto servers = config["servers"]["node"].as_array();
    std::vector<ptr<srv_config>> cluster;
    self_id = 0;

    for (const auto& srv : *servers)
    {
        if (!srv.is_table())
        {
            continue;
        }
        auto srv_table = srv.as_table();
        int32_t id = (*srv_table)["id"].value_or(0);
        std::string name = (*srv_table)["name"].value_or("");
        std::string address = (*srv_table)["address"].value_or("");
        int port = (*srv_table)["port"].value_or(0);
        cluster.push_back(cs_new<srv_config>(id, sstrfmt("tcp://%s:%d").fmt(address.c_str(), port)));

        spdlog::info("Configured server - ID: {}, Name: {}, Address: {}, Port: {}", id, name, address, port);
        if (name == self_name)
        {
            self_id = id;
            spdlog::info("Identified self ID: {}", self_id);
        }
    }

    return cluster;
}

