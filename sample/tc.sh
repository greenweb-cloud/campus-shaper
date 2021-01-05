#!/bin/sh

DEV=enp3s0f0
DEVUP=enp3s0f1

# Reset everything to a known state (cleared)
tc qdisc del dev $DEV root 2> /dev/null > /dev/null
tc qdisc del dev $DEVUP root 2> /dev/null > /dev/null
iptables -F -t mangle

if [ "$1" = "stop" ]
then
        echo "Shaping removed on $DOWN."
        exit
fi

echo 'initializing ...'
/sbin/tc qdisc add dev $DEV root handle 1: htb default 40

# parent class
/sbin/tc class add dev $DEV parent 1:  classid 1:1  htb rate 5mbit  ceil 9mbit 
#/sbin/tc class add dev $DEV parent 1:1 classid 1:10 htb rate 5mbit ceil 5mbit prio 1
#/sbin/tc class add dev $DEV parent 1:1 classid 1:20 htb rate 5mbit ceil 3mbit prio 2
/sbin/tc class add dev $DEV parent 1:1 classid 1:30 htb rate 2mbit ceil 2mbit prio 3 # 101, 102
/sbin/tc class add dev $DEV parent 1:1 classid 1:40 htb rate 1mbit ceil 1mbit prio 4

# child class
tc class add dev $DEV parent 1:30 classid 1:60 htb rate 900kbit ceil 1024kbit  
tc class add dev $DEV parent 1:30 classid 1:70 htb rate 8192kbit ceil 2024kbit  

# add queue disk to child class
tc qdisc add dev $DEV parent 1:60 handle 60: pfifo limit 5
tc qdisc add dev $DEV parent 1:70 handle 70: pfifo limit 5

# add filter
tc filter add dev $DEV protocol ip parent 1: prio 1 handle 60 fw classid 1:60  flowid 1:60
tc filter add dev $DEV protocol ip parent 1: prio 2 handle 70 fw classid 1:70  flowid 1:70


iptables -t mangle -A PREROUTING  --dest 172.21.15.101 -j MARK --set-mark 60
#iptables -t mangle -A PREROUTING --dest 172.21.15.101 -j RETURN

iptables -t mangle -A PREROUTING  --dest 172.21.15.102 -j MARK --set-mark 70


### to delete ...
# tc filter del dev $DEV protocol ip parent 1: prio 1 handle 60 fw classid 1:60
# iptables -t mangle -D PREROUTING --dest 172.21.15.101 -j MARK --set-mark 60
