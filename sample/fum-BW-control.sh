#!/bin/sh

#
# START Configuration Options
#
DOWN=ens160
UP=ens192

TOTAL_BW=15mbit		# Total bandwidth
LOW_DELAY=800kbit       # class 1:10  
DEFAULT=4mbit		# class 1:15

PROF_BW=2mbit		
STU_BW=1mbit
STAFF_BW=1mbit

PROF_MARK=2
STU_MARK=3
STAFF_MARK=4
DEFAULT_MARK=5

#
# End Configuration Options
#

if [ "$1" = "status" ]
then
        echo "[qdisc]"
        tc -s qdisc show dev $DOWN
        echo "[class]"
        tc -s class show dev $DOWN
        echo "[filter]"
        tc -s filter show dev $DOWN
        echo "[iptables]"
        iptables -t mangle -L MYSHAPER-OUT -v -x 2> /dev/null
        exit
fi

# Reset everything to a known state (cleared)                                                                                              
tc qdisc del dev $DEV root 2> /dev/null > /dev/null
iptables -t mangle -D POSTROUTING -o $DEV -j MYSHAPER-OUT 2> /dev/null > /dev/null
iptables -t mangle -F MYSHAPER-OUT 2> /dev/null > /dev/null
iptables -t mangle -X MYSHAPER-OUT 2> /dev/null > /dev/null

if [ "$1" = "stop" ]
then
        echo "Shaping removed on $DOWN."
        exit
fi

# add HTB root qdisc
tc qdisc add dev $DOWN root handle 1: htb default 15

# add main rate limit classes
tc class add dev $DOWN parent 1:  classid 1:1  htb rate $TOTAL_BW  ceil $TOTAL_BW # parent class

# add leaf classes - We grant each class at LEAST it's "fair share" of bandwidth.
#                    this way no class will ever be starved by another class.  Each
#                    class is also permitted to consume all of the available bandwidth
#                    if no other classes are in use.
tc class add dev $DOWN parent 1:1 classid 1:10 htb rate $LOW_DELAY ceil $LOW_DELAY prio 0 # low delay (ssh, telnet, dns, SYN flag)
tc class add dev $DOWN parent 1:1 classid 1:20 htb rate $PROF_BW   ceil $PROF_BW   prio 2 # PROF
tc class add dev $DOWN parent 1:1 classid 1:30 htb rate $STAFF_BW  ceil $STAFF_BW  prio 3 # STU
tc class add dev $DOWN parent 1:1 classid 1:40 htb rate $STU_BW    ceil $STU_BW    prio 4 # STAFF
tc class add dev $DOWN parent 1:1 classid 1:50 htb rate $DEFAULT   ceil $DEFAULT   prio 5 # Default

# attach qdisc to leaf classes - here we at SFQ to each priority class.  SFQ insures that
#                                within each class connections will be treated (almost) fairly.
tc qdisc add dev $DOWN parent 1:10 handle 10: sfq perturb 10 # LOW LATENCY
tc qdisc add dev $DOWN parent 1:20 handle 20: sfq perturb 10 # PROF
tc qdisc add dev $DOWN parent 1:30 handle 30: sfq perturb 10 # STUDENT
tc qdisc add dev $DOWN parent 1:40 handle 40: sfq perturb 10 # STAFF
tc qdisc add dev $DOWN parent 1:50 handle 50: sfq perturb 10 # DEFAULT
exit
# filter traffic into classes by fwmark - here we direct traffic into priority class according to
#                                         the fwmark set on the packet (we set fwmark with iptables
#                                         later).  Note that above we've set the default priority
#                                         class to 1:26 so unmarked packets (or packets marked with
#                                         unfamiliar IDs) will be defaulted to the lowest priority
#                                         class.
tc filter add dev $DOWN parent 1:0 protocol ip prio 0 handle 0             fw classid 1:10
tc filter add dev $DOWN parent 1:0 protocol ip prio 0 handle $PROF_MARK    fw classid 1:20 # PROF
tc filter add dev $DOWN parent 1:0 protocol ip prio 0 handle $STU_MARK     fw classid 1:30 # STUDENT
tc filter add dev $DOWN parent 1:0 protocol ip prio 0 handle $STAFF_MARK   fw classid 1:40 # STAFF
tc filter add dev $DOWN parent 1:0 protocol ip prio 0 handle $DEFAULT_MARK fw classid 1:50 # DEFAULT

# #############################################################################
iptables -t mangle -F PREROUTING

# (prio 0): Prioritize packets to begin tcp connections (those with SYN flag set):
iptables -t mangle -I PREROUTING -p tcp -m tcp --tcp-flags SYN,RST,ACK SYN -j MARK --set-mark 0x1
iptables -t mangle -I PREROUTING -p tcp -m tcp --tcp-flags SYN,RST,ACK SYN -j RETURN
iptables -t mangle -A PREROUTING -p udp -j MARK --set-mark 0x1 # (prio 0): Set non-tcp packets to highest priority
iptables -t mangle -A PREROUTING -p udp -j RETURN
iptables -t mangle -A PREROUTING -m tos --tos Minimize-Delay -j MARK --set-mark 0x1 # (prio 0): tos = Minimize-Delay
iptables -t mangle -A PREROUTING -m tos --tos Minimize-Delay -j RETURN
iptables -t mangle -A PREROUTING -p icmp -j MARK --set-mark 0x1 # (prio 0): Prioritize ICMP packets
iptables -t mangle -A PREROUTING -p icmp -j RETURN
iptables -t mangle -A PREROUTING -p tcp -m tcp --sport ssh -j MARK --set-mark 0x1 # (prio 0): SSH
iptables -t mangle -A PREROUTING -p tcp -m tcp --sport ssh -j RETURN    
iptables -t mangle -A PREROUTING -p tcp -m tcp --dport ssh -j MARK --set-mark 0x1 # (prio 0): SSH
iptables -t mangle -A PREROUTING -p tcp -m tcp --dport ssh -j RETURN    
iptables -t mangle -A PREROUTING -p tcp -m tcp --sport telnet -j MARK --set-mark 0x1 # (prio 0): Prioritize TELNET packets
iptables -t mangle -A PREROUTING -p tcp -m tcp --sport telnet -j RETURN    
iptables -t mangle -A PREROUTING -p tcp -m tcp --dport telnet -j MARK --set-mark 0x1
iptables -t mangle -A PREROUTING -p tcp -m tcp --dport telnet -j RETURN

# (prio 1): HTTP/s traffic
iptables -t mangle -A PREROUTING --dest 172.21.15.101 -j MARK --set-mark 0x$PROF_MARK
iptables -t mangle -A PREROUTING --dest 172.21.15.102 -j MARK --set-mark 0x$STU_MARK
iptables -t mangle -A PREROUTING  -j RETURN

# Terminate the PREROUTING table
iptables -t mangle -A PREROUTING -j MARK --set-mark 0x6

