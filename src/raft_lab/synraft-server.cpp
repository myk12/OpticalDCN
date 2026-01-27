#include "cornerstone.hxx"
#include <iostream>
#include <string>
#include <thread>
#include <vector>
#include <memory>
#include <condition_variable>
#include <toml++/toml.hpp>
#include <spdlog/spdlog.h>
#include "synraft.hpp"

using namespace cornerstone;

// ==================================================
// 1. Cornerstone Interfaces Implementation
// ==================================================
// State Manager Implementation
class synraft_state_mgr : public state_mgr {
public:
    synraft_state_mgr(int32 srv_id, const std::vector<ptr<srv_config>>& cluster)
        : srv_id_(srv_id), cluster_(cluster) {
        store_path_ = sstrfmt("store%d").fmt(srv_id_);
    }

public:
    virtual ptr<cluster_config> load_config() override {
        ptr<cluster_config> conf = cs_new<cluster_config>();
        for (const auto& srv : cluster_) {
            conf->get_servers().push_back(srv);
        }

        return conf;
    }

    virtual void save_config(const cluster_config&) override {}
    virtual void save_state(const srv_state&) override {}
    virtual ptr<srv_state> read_state() override {
        return cs_new<srv_state>();
    }

    virtual ptr<log_store> load_log_store() override {
        mkdir(store_path_.c_str(), 0766);
        return cs_new<fs_log_store>(store_path_);
    }

    virtual int32 server_id() override {
        return srv_id_;
    }

    virtual void system_exit(const int exit_code) override {
        std::cout << "system exiting with code " << exit_code << std::endl;
    }
private:
    int32 srv_id_;
    std::vector<ptr<srv_config>> cluster_;
    std::string store_path_;
};

// State Machine Implementation
class synraft_state_machine : public state_machine {
public:
    synraft_state_machine() : lock_() {}

public:
    virtual void commit(const ulong log_idx, buffer& data, const uptr<log_entry_cookie>& cookie) override {
        auto_lock(lock_);
        std::string msg(reinterpret_cast<const char*>(data.data()), data.size());
        spdlog::trace("Committed log index {}: {}", log_idx, msg);
    }

    virtual void pre_commit(const ulong log_idx, buffer& data, const uptr<log_entry_cookie>& cookie) override {
        auto_lock(lock_);
        std::string msg(reinterpret_cast<const char*>(data.data()), data.size());
        spdlog::trace("Pre-committing log index {}: {}", log_idx, msg);
    }

    virtual void rollback(const ulong log_idx, buffer& data, const uptr<log_entry_cookie>& cookie) override {
        auto_lock(lock_);
        std::string msg(reinterpret_cast<const char*>(data.data()), data.size());
        spdlog::warn("Rolling back log index {}: {}", log_idx, msg);
    }

    virtual void save_snapshot_data(snapshot& s, const ulong offset, buffer& data) override {}
    virtual bool apply_snapshot(snapshot& s) override { return false; }
    virtual int read_snapshot_data(snapshot& s, const ulong offset, buffer& data) override { return 0; }
    virtual ptr<snapshot> last_snapshot() override { return ptr<snapshot>(); }
    virtual ulong last_commit_index() override { return 0; }
    virtual void create_snapshot(snapshot& s, async_result<bool>::handler_type& when_done) override {}
private:
    std::mutex lock_;
};

// Logger Implementation
class synraft_fs_logger : public logger {
public:
    synraft_fs_logger(const std::string& filename) : fs_(filename) {}
    __nocopy__(synraft_fs_logger);

public:
    virtual void debug(const std::string& log_line) override {
        fs_ << log_line << std::endl;
        fs_.flush();
    }

    virtual void info(const std::string& log_line) override {
        fs_ << log_line << std::endl;
        fs_.flush();
    }

    virtual void warn(const std::string& log_line) override {
        fs_ << log_line << std::endl;
        fs_.flush();
    }

    virtual void err(const std::string& log_line) override {
        fs_ << log_line << std::endl;
        fs_.flush();
    }

private:
    std::ofstream fs_;
};

// ==================================================
// 4. Main Function
// ==================================================

int main(int argc, char** argv) {
    if (argc < 2) {
        std::cerr << "Usage: " << argv[0] << " <server_name>" << std::endl;
        return 1;
    }

    std::string server_name = argv[1];
    spdlog::set_level(spdlog::level::info); // Set global log level to info
    spdlog::info("Starting Raft Node with Name: {}", server_name);
    // 1. Load cluster configuration
    auto config = toml::parse_file("cluster-config.toml");

    // servers
    auto servers = config["servers"]["node"].as_array();
    auto cluster = std::vector<ptr<srv_config>>();
    std::string self_address;
    int16_t self_port = 0;
    int32_t server_id = 0;

    for (const auto& srv : *servers) {
        if (!srv.is_table()) {
            continue;
        }
        auto srv_table = srv.as_table();
        int32_t id = (*srv_table)["id"].value_or(0);
        std::string name = (*srv_table)["name"].value_or("");
        std::string address = (*srv_table)["address"].value_or("");
        int port = (*srv_table)["port"].value_or(0);

        std::string endpoint = "tcp://" + address + ":" + std::to_string(port);
        ptr<srv_config> srv_conf = cs_new<srv_config>(id, endpoint);
        cluster.push_back(srv_conf);

        // Identify self address
        if (name == server_name) {
            self_address = endpoint;
            self_port = static_cast<int16_t>(port);
            server_id = id;
            spdlog::info("Identified self address: {}", self_address);
        }
    }

    assert(!self_address.empty() && "Server ID not found in configuration");

    // 2. Create state machine
    ptr<asio_service> asio_svc = cs_new<asio_service>();

    ptr<logger> logger = cs_new<synraft_fs_logger>("raft_node_" + std::to_string(server_id) + ".log");
    ptr<rpc_listener> listener(asio_svc->create_rpc_listener(self_port, logger));
    ptr<state_mgr> smgr = cs_new<synraft_state_mgr>(server_id, cluster);
    ptr<state_machine> sm = cs_new<synraft_state_machine>();
    raft_params* params = new raft_params();
    params->with_election_timeout_lower(200);
    params->with_election_timeout_upper(400);
    params->with_hb_interval(50);
    params->with_rpc_failure_backoff(50);
    params->with_max_append_size(100);
    ptr<delayed_task_scheduler> scheduler = asio_svc;
    ptr<rpc_client_factory> rpc_cli_factory = asio_svc;
    context* ctx = new context(
        smgr, sm, listener, logger, rpc_cli_factory, scheduler, ptr<raft_event_listener>(), params);
    ptr<raft_server> server = cs_new<raft_server>(ctx);
    listener->listen(server);

    spdlog::info("Raft Node {} started at address {}", server_id, self_address);

    // Block the main thread to keep the server running
    while (true) {
        std::this_thread::sleep_for(std::chrono::seconds(10));
    }
}
