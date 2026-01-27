#include <iostream>
#include <vector>
#include <chrono>
#include <atomic>
#include <mutex>
#include <algorithm>
#include <spdlog/spdlog.h>
#include "cornerstone.hxx"
#include "synraft.hpp"

using namespace cornerstone;

// statistic
struct Statscollector
{
    std::atomic<uint64_t> sent_count{0};
    std::atomic<uint64_t> success_count{0};
    std::atomic<uint64_t> failure_count{0};
    std::mutex latency_mtx;
    std::vector<double> latencies; // unit: ms

    void add_latency(double ms)
    {
        std::lock_guard<std::mutex> lock(latency_mtx);
        latencies.push_back(ms);
    }
};

class RaftBenchmark : public std::enable_shared_from_this<RaftBenchmark>
{
public:
    RaftBenchmark(ptr<asio_service> svc, std::vector<ptr<srv_config>> cluster, std::string init_addr)
        : asio_svc_(svc),
          cluster_(cluster),
          current_leader_addr_(init_addr),
          last_stats_time_(std::chrono::steady_clock::now())
    {
        client_ = asio_svc_->create_client(init_addr);
        assert(client_ != nullptr);

        // set latency log file
        latency_log_file_ = "latency_log.csv";
        latency_log_stream_.open(latency_log_file_, std::ios::out | std::ios::app);
        latency_log_stream_ << "RequestID,Latency(ms)" << std::endl;
        latency_log_stream_.flush();
    }

    void send_request(int req_id)
    {
        // construct message
        ptr<req_msg> msg = cs_new<req_msg>(0, msg_type::client_request, 0, 1, 0, 0, 0);
        bufptr buf = buffer::alloc(100);
        // clean buffer
        memset(buf->data(), 0, buf->size()); // important to zero out the buffer

        buf->put("hallo_" + std::to_string(req_id));
        buf->pos(0);
        msg->log_entries().push_back(cs_new<log_entry>(0, std::move(buf)));

        auto start = std::chrono::high_resolution_clock::now();
        stats_.sent_count++;

        auto self = shared_from_this();

        // get a local copy of client
        ptr<rpc_client> l_client;
        {
            std::lock_guard<std::mutex> lock(client_mtx_);
            l_client = client_;
        }

        auto handler_sp = std::make_shared<rpc_handler>();

        {
            std::lock_guard<std::mutex> lock(pending_mtx_);
            pending_[req_id] = handler_sp;
        }

        // define handler
        *handler_sp = [self, start, req_id, l_client](ptr<resp_msg> &rsp, const ptr<rpc_exception> &err)
        {
            auto end = std::chrono::high_resolution_clock::now();
            double lat = std::chrono::duration<double, std::milli>(end - start).count();

            // remove from pending
            {
                std::lock_guard<std::mutex> lock(self->pending_mtx_);
                self->pending_.erase(req_id);
            }

            if (err)
            {
                spdlog::error("Request {} failed: {}", req_id, err->what());
                self->stats_.failure_count++;
                return;
            }

            assert(rsp != nullptr);

            if (rsp->get_accepted())
            {
                self->stats_.success_count++;
                self->stats_.add_latency(lat);

                spdlog::trace("Request {} succeeded in {:.2f} ms", req_id, lat);
                // record latency
                {
                    std::lock_guard<std::mutex> lock(self->request_times_mtx_);
                    auto it = self->request_start_times_.find(req_id);
                    if (it != self->request_start_times_.end())
                    {
                        double total_lat = std::chrono::duration<double, std::milli>(
                                               std::chrono::steady_clock::now() - it->second)
                                               .count();
                        spdlog::trace("Request {} total latency: {:.2f} ms", req_id, total_lat);

                        // record to latency map
                        self->request_latencies_mtx_.lock();
                        self->request_latencies_[req_id] = total_lat;
                        self->request_latencies_mtx_.unlock();

                        self->request_start_times_.erase(it);
                    }
                }
            }
            else if (rsp->get_dst() > 0)
            {
                // handle redirect
                uint32_t new_leader_id = rsp->get_dst();
                self->update_leader(new_leader_id);
                spdlog::warn("Request {} redirected to leader {}", req_id, new_leader_id);
            }
        };

        assert(l_client != nullptr);
        l_client->send(msg, *handler_sp);

        // record request start time
        {
            std::lock_guard<std::mutex> lock(request_times_mtx_);
            request_start_times_[req_id] = std::chrono::steady_clock::now();
        }
    }

    void update_leader(uint32_t leader_id)
    {
        std::lock_guard<std::mutex> lock(client_mtx_);
        // find new leader address
        std::string new_addr = cluster_[leader_id - 1]->get_endpoint();
        if (new_addr != current_leader_addr_)
        {
            current_leader_addr_ = new_addr;
            auto new_client = asio_svc_->create_client(new_addr);

            assert(new_client != nullptr);
            client_ = new_client;
            spdlog::info("Updated leader to ID {} at {}", leader_id, new_addr);
        }
    }

    void print_stats()
    {
        auto now = std::chrono::steady_clock::now();

        // get current stats
        uint64_t curr_success = stats_.success_count.load();
        uint64_t curr_sent = stats_.sent_count.load();
        uint64_t curr_fail = stats_.failure_count.load();

        // calculate time interval
        std::chrono::duration<double> interval = now - last_stats_time_;
        double interval_sec = interval.count();

        if (interval_sec > 0)
        {
            uint64_t interval_success = curr_success - last_success_count_;
            uint64_t interval_sent = curr_sent - last_sent_count_;

            double tps = interval_success / interval_sec;

            spdlog::info("Stats - Sent: {}, Success: {}, Failure: {}, TPS: {:.2f}",
                         curr_sent, curr_success, curr_fail, tps);
        }

        // update last stats
        last_stats_time_ = now;
        last_success_count_ = curr_success;
        last_sent_count_ = curr_sent;

        if (enable_latency_logging_)
        {
            // save latency stats to file
            {
                std::lock_guard<std::mutex> lock(latency_log_mtx_);
                if (!latency_log_file_.empty())
                {
                    if (!latency_log_stream_.is_open())
                    {
                        latency_log_stream_.open(latency_log_file_, std::ios::out | std::ios::app);
                    }
                    if (latency_log_stream_.is_open())
                    {
                        std::lock_guard<std::mutex> lat_lock(request_latencies_mtx_);
                        for (const auto &entry : request_latencies_)
                        {
                            latency_log_stream_ << entry.first << "," << entry.second << std::endl;
                        }
                        request_latencies_.clear();
                    }
                }
                latency_log_stream_.flush();
            }
        }
    }

    uint64_t get_success_count()
    {
        return stats_.success_count.load();
    }

    uint64_t get_failure_count()
    {
        return stats_.failure_count.load();
    }

private:
    ptr<asio_service> asio_svc_;
    std::vector<ptr<srv_config>> cluster_;

    std::mutex client_mtx_;
    ptr<rpc_client> client_;
    std::string current_leader_addr_;

    std::mutex pending_mtx_;
    std::unordered_map<int, std::shared_ptr<rpc_handler>> pending_;

    Statscollector stats_;

    // used for periodic stats printing
    std::chrono::steady_clock::time_point last_stats_time_;
    uint64_t last_success_count_ = 0;
    uint64_t last_sent_count_ = 0;

    // used for request completion tracking
    bool enable_latency_logging_ = true;
    std::unordered_map<int, std::chrono::steady_clock::time_point> request_start_times_;
    std::mutex request_times_mtx_;
    // output filename for latency logs
    std::string latency_log_file_;
    std::mutex latency_log_mtx_;
    std::ofstream latency_log_stream_;
    // latency statistics
    std::unordered_map<int, double> request_latencies_;
    std::mutex request_latencies_mtx_;
};

int main(int argc, char **argv)
{
    // 1. parse arguments
    if (argc < 2)
    {
        std::cerr << "Usage: " << argv[0] << " <leader_endpoint>" << std::endl;
        return 1;
    }
    std::string target = argv[1];
    int num_reqs = 10000000;
    int rate = 1000; // requests per second

    // 2. initialize environment
    ptr<asio_service> asio_svc = cs_new<asio_service>();
    auto cluster = load_cluster_config("cluster-config.toml");

    auto benchmark = std::make_shared<RaftBenchmark>(asio_svc, cluster, target);

    auto start_time = std::chrono::steady_clock::now();

    benchmark->send_request(0); // send one request to warm up

    // sleep a bit to ensure connection is established
    std::this_thread::sleep_for(std::chrono::milliseconds(1000));

    // 3. main loop: control rate of sending requests
    for (int i = 1; i < num_reqs; ++i)
    {
        benchmark->send_request(i);

        // control rate with slideding window according to pending requests
        while (true)
        {
            if (i - benchmark->get_success_count() - benchmark->get_failure_count() < rate)
            {
                break;
            }
            std::this_thread::sleep_for(std::chrono::microseconds(10));
        }

        if (i % 10000 == 0)
            benchmark->print_stats();
    }

    // 4. final stats
    spdlog::info("All requests sent, waiting for responses...");
    int timeout_count = 0;
    while (benchmark->get_success_count() + benchmark->get_failure_count() < num_reqs && timeout_count < 300)
    {
        std::this_thread::sleep_for(std::chrono::seconds(1));
        timeout_count++;
    }

    if (timeout_count >= 300)
    {
        spdlog::warn("Timeout waiting for all responses.");
    }

    benchmark->print_stats();

    return 0;
}
