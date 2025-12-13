import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd

from loguru import logger

class MeasurementVisualizer:
    def __init__(self):
        """
        Initialize the visualizer with measurement data.

        Parameters:
        data (pd.DataFrame): A DataFrame containing measurement data with columns 'time', 'value', and 'category'.
        """
        self.data = None
        self.tx_dataframe = None
        self.rx_dataframe = None
    
    ##########################################################################
    #                           Data Loading Methods
    ##########################################################################
    def load_kernel_data(self, filepath):
        """
        Load kernel measurement data from a CSV file.

        Parameters:
        filepath (str): Path to the kernel data CSV file.
        """
        logger.info(f"Loading kernel data from {filepath}")
        records = {} # packet_seq -> [ts1, ts2, ts3, ts4] with ascending order
        with open(filepath, 'r') as file:
            lines = file.readlines()
            for line in lines:
                # TODO: parameterize the probe name
                if "mqnic_ts_probe" not in line:
                     continue

                # parse line
                desired_parts =  line.split(' ')[-1].strip().split(',')
                pkt_seq = int(desired_parts[1].split('=')[1])
                ts = int(desired_parts[2].split('=')[1])

                if pkt_seq not in records:
                    records[pkt_seq] = []
                records[pkt_seq].append(ts)
        
        # Convert records to DataFrame
        # sort timestamps for each packet
        data_list = []
        for pkt_seq, timestamps in records.items():
            timestamps.sort()
            data_list.append({
                'pkt_seq': pkt_seq,
                'ts_driver_tx': timestamps[0],
                'ts_hw_tx': timestamps[1],
                'ts_hw_rx': timestamps[2],
                'ts_driver_rx': timestamps[3],
            })
        self.kernel_data = pd.DataFrame(data_list)
        print(self.kernel_data.head())
    
    def load_userspace_data(self, tx_filepath, rx_filepath):
        """
        Load measurement data from a CSV file.

        Parameters:
        tx_filepath (str): Path to the transmitter data CSV file.
        rx_filepath (str): Path to the receiver data CSV file.
        """
        logger.info(f"Loading TX data from {tx_filepath}")
        logger.info(f"Loading RX data from {rx_filepath}")
        # File format TX: pkt_seq, pkt_size, t_user_tx
        # File format RX: pkt_seq, pkt_size, t_user_rx
        self.tx_dataframe = pd.read_csv(tx_filepath)
        self.rx_dataframe = pd.read_csv(rx_filepath)

        # Merge TX and RX data on packet sequence number
        self.userspace_data = pd.merge(self.tx_dataframe, self.rx_dataframe, on='pkt_seq', suffixes=('_tx', '_rx'))

        print(self.userspace_data.head())
    
    def load_data(self, kernel_filepath, tx_filepath, rx_filepath):
        """
        Load measurement data from CSV files.

        Parameters:
        kernel_filepath (str): Path to the kernel data CSV file.
        tx_filepath (str): Path to the transmitter data CSV file.
        rx_filepath (str): Path to the receiver data CSV file.
        """
        self.load_kernel_data(kernel_filepath)
        self.load_userspace_data(tx_filepath, rx_filepath)
        self.data = pd.merge(self.userspace_data, self.kernel_data, on='pkt_seq')

        # Calculate latency
        self.tx_kernel_time = self.data['ts_driver_tx'] - self.data['t_user_tx_ns']
        self.tx_NIC_time = self.data['ts_hw_tx'] - self.data['ts_driver_tx']
        self.inflight_time = self.data['ts_hw_rx'] - self.data['ts_hw_tx']
        self.rx_NIC_time = self.data['ts_driver_rx'] - self.data['ts_hw_rx']
        self.rx_kernel_time = self.data['t_user_rx_ns'] - self.data['ts_driver_rx']
    
    ##########################################################################
    #                           Visualization Methods
    ##########################################################################
    def plot_latency_boxchart(self):
        """
        Plot a bar chart of average latency per category.
        """
        if self.data is None:
            logger.error("Measurement data not loaded. Please load data before plotting.")
            return
 
        # plot boxchart
        latency_df = pd.DataFrame({
            'tx_kernel_time': self.tx_kernel_time,
            'tx_NIC_time': self.tx_NIC_time,
            'inflight_time': self.inflight_time,
            'rx_NIC_time': self.rx_NIC_time,
            'rx_kernel_time': self.rx_kernel_time
        })
        latency_melted = latency_df.melt(var_name='category', value_name='latency_ns')
        plt.figure(figsize=(5, 4))
        sns.boxplot(x='category', y='latency_ns', data=latency_melted)
        plt.yscale('log')
        plt.title('Latency Breakdown Boxchart')
        plt.xlabel('Category')
        plt.ylabel('Latency (ns)')
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.savefig('latency_boxchart.pdf')
    
    def plot_latency_CDF(self):
        """
        Plot CDF of latency.
        """
        if self.kernel_data is None or self.userspace_data is None:
            logger.error("Measurement data not loaded. Please load data before plotting.")
            return
        # 2 subfigures, one for software, one for hardware
        plt.figure(figsize=(10, 4))
        plt.subplot(1, 2, 1)
        sns.ecdfplot(self.inflight_time, label='In-flight Time')
        plt.title('In-flight Time CDF')
        plt.xlabel('Time (ns)')
        plt.ylabel('CDF')
        plt.legend()

        plt.subplot(1, 2, 2)
        sns.ecdfplot(self.tx_NIC_time, label='TX NIC Time')
        sns.ecdfplot(self.rx_NIC_time, label='RX NIC Time')
        sns.ecdfplot(self.tx_kernel_time, label='TX Kernel Time')
        sns.ecdfplot(self.rx_kernel_time, label='RX Kernel Time')
        plt.xscale('log')
        plt.title('NIC and Kernel Time CDF')
        plt.xlabel('Time (ns)')
        plt.ylabel('CDF')
        plt.legend()

        plt.tight_layout()
        plt.savefig('latency_cdf.pdf')
    
def main():
    logger.info("Starting Measurement Visualizer")
    tx_filepath = 'ts_probe_tx.csv'
    rx_filepath = 'ts_probe_rx.csv'
    kernel_log_filepath = 'trace.log'
    visualizer = MeasurementVisualizer()
    visualizer.load_data(kernel_log_filepath, tx_filepath, rx_filepath)
    visualizer.plot_latency_boxchart()
    visualizer.plot_latency_CDF()

if __name__ == "__main__":
    main()