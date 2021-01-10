# campus-shaper

This program is developed for traffic shaping of internet in the campus university.

##Description
bw-control.py: is python program which is called by crontab (/etc/crontab) every minute and get list of online users from mikrotik hotspot and shape users's traffic with linux "TC" command

##Requirements
- Server Linux OS uses netfilter core-firewall that facilitates Network Address Translation (NAT), packet filtering, and packet mangling.
- Server Linux OS uses iptables that is a ultility which control netfilter operation through iptables rule settings.
- Git tool on system.
- User has privilege to use iptables ultility (like wheel group - root).
- User has permission to write/create file in temp directory.

## Enable IP forwarding
The procedure to enable IP forwarding in Linux is the same as the above procedure to disable it, but instead, we use number 1 to turn IP forwarding ON.
$ sudo sysctl -w net.ipv4.ip_forward=1
  net.ipv4.ip_forward = 1
or alternatively:
   echo 1 > /proc/sys/net/ipv4/ip_forward
To make the change permanent insert or edit the following line in edit /etc/sysctl.conf:
  net.ipv4.ip_forward = 1

##Installation

**+ Linux**
Install following packages: 
	# apt install python3-pip
	# apt install python3-mysql.connector
	# pip3 install RouterOS-api
	# pip3 install tcconfig
	# pip3 install pyyaml
	# pip3 install psutil
	# pip3 install netaddr

##Example Usage
- add <PATH-TO-SCRIPT>/bw-control.py path to /etc/crontab. for example:
  *  *    * * *   root    /opt/AAA/fum-shaper/bw-control.py start --user-bandwidth-coefficient=1

note: by using '--user-bandwidth-coefficient' option user limit bandwith rate can be changed. default user bandwidth rate is defined in config.yml/tc/classify/{PROF,STUDENT,STAFF,DEFAULT}/user_bw variable. so if you set --user-bandwidth-coefficient=2, all users's rate would be double and if you set 0.5, users's rate would be half. sample configuration of /etc/crontab can be find in Documentation folder named 'crontab-example.txt' 

## cache user information:
"./bw-control.py cache_user_info" command will get all user names and user types from pooya database and will store them in /dev/shm/fumShaper-userInfo.data, so every time ./bw-control starts, it will load user infromations from that file. to update this file on 2 AM every day this command should be inserted to /etc/crontab:
*  2    * * *   root    /opt/AAA/fum-shaper/bw-control.py cache_user_info  

## statistics.py script:
you can add this script to crontab like this:
  *  *    * * *   root    /opt/AAA/fum-shaper/statistics.py user-count
  
By using "user-count" parameter in this script,it calculates currently logged in ips ( fetch ips from /dev/shm/fumShaper-currentIPs )
and Group users by distibution network which is defined in ((ip-plan.yml)). output of this script is saved in
(/var/log/AAA/qos-monitor.log) file and variables can be send to zabbix as needed. more documentation about defining zabbix
configuration can be found in Documentation folder. 

## Tuning Guide
Tuned is an adaptive system tuning daemon. It can be used to apply a variety of system settings
gathered together into a collection called a profile.

   $ sudo apt install tuned
   $ tuned-adm list   # list Available profiles
   $ sudo tuned-adm profile network-throughput
   
 
## Documentations
- All documentations and sample scripts are in Documentation/ folder. read before run ;).

##Author
**Name** : iman darabi

**Website** : https://www.linkedin.com/in/imandarabi/
