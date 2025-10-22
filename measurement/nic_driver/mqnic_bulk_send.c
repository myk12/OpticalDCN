#include "mqnic.h"

void mqnic_packet_work(struct work_struct *work) {
    struct mqnic_bulk_send_work *priv = container_of(work, struct mqnic_bulk_send_work, packet_work.work);

    // 这里添加数据包发送逻辑
    // 假设 mqnic_send_packet 是发送数据包的函数
    mqnic_send_packet(priv);

    // 重新调度任务，延迟 1 秒后再次执行
    schedule_delayed_work(&priv->packet_work, msecs_to_jiffies(1000));
}
EXPORT_SYMBOL(mqnic_packet_work);

int mqnic_bulk_send_open(struct net_device *ndev) {
    struct mqnic_bulk_send_work *priv = netdev_priv(ndev);
    
    // 其他初始化操

    // 创建工作队列
    priv->packet_workqueue = create_singlethread_workqueue("mqnic_packet_wq");
    if (!priv->packet_workqueue) {
        netdev_err(ndev, "Failed to create packet workqueue");
        return -ENOMEM;
    }

    // 初始化并调度 delayed_work，1 秒后开始第一次执行
    INIT_DELAYED_WORK(&priv->packet_work, mqnic_packet_work);
    queue_delayed_work(priv->packet_workqueue, &priv->packet_work, msecs_to_jiffies(1000));

    return 0;
}

int mqnic_bulk_send_close(struct net_device *ndev) {
    struct mqnic_bulk_send_work *priv = netdev_priv(ndev);

    // 取消延迟工作
    cancel_delayed_work_sync(&priv->packet_work);

    // 销毁工作队列
    if (priv->packet_workqueue) {
        destroy_workqueue(priv->packet_workqueue);
        priv->packet_workqueue = NULL;
    }

    // 其他关闭操作
    
    return 0;
}

void mqnic_send_packet(struct mqnic_bulk_send_work *priv) {

    // just print a log 
    printk("mqnic_send_packet called\n");

    return;
}

