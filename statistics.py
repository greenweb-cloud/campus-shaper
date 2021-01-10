#!/usr/bin/python3

import argparse, os, logging, yaml, pickle
from netaddr import IPNetwork, IPAddress

DEBUG=False

IP_CONFIG_FILE='ip-plan.yml'
BASE_CONFIG_FILE='config.yml'

# Try to locate the CONFIG_FILE path in the same directory as this file
ip_config_file_path = os.path.join(*(os.path.split(__file__)[:-1] + (IP_CONFIG_FILE,)))  
# load configuration and set as 'config' variable
with open(ip_config_file_path, 'r') as stream:
    try:
        ip_config = yaml.load(stream)
    except yaml.YAMLError as exc:
        print(exc)                              

# Try to locate the CONFIG_FILE path in the same directory as this file
base_config_file_path = os.path.join(*(os.path.split(__file__)[:-1] + (BASE_CONFIG_FILE,)))  
# load configuration and set as 'config' variable
with open(base_config_file_path, 'r') as stream:
    try:
        base_config = yaml.load(stream)
    except yaml.YAMLError as exc:
        print(exc)

# configure logging dir + format.
os.makedirs(base_config['log']['dir'], exist_ok=True)
log_file = base_config['log']['dir'] +  base_config['log']['statistics']
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(name)-5s %(levelname)-8s %(message)s',
                    datefmt='20%y/%m/%d %H:%M',
                    filename= log_file,
                    filemode='a')
        
class mining:
    def __init__(self):
        self.total_wire_user = 0
        self.total_wireless_user = 0
        
    def load_current_ips(self):
        try:
            f = open(base_config['users']['current_users_path'], 'rb')
            return pickle.load(f)
        except Exception as e:
            print (str(e))
            return {}

    def Grouping(self):
        if DEBUG:
            logger_info = logging.getLogger('DEBUG')

        for ip in self.load_current_ips().keys():
            for dist in ip_config.keys():
           
                if IPAddress(ip) in IPNetwork(ip_config[dist]['wireless_net']):
                    ip_config[dist]['wireless_user'] += 1
                    self.total_wireless_user += 1
                    if DEBUG:
                        logger_info.info("wire_ip:%s\tsummary_net:%s\tdist_name:%s" % (ip, ip_config[dist]['summary_net'],
                                                                                       ip_config[dist]['name'] ))
                    break
                if IPAddress(ip) in IPNetwork(ip_config[dist]['summary_net']):
                    ip_config[dist]['wire_user'] += 1
                    self.total_wire_user += 1
                    if DEBUG:
                        logger_info.info("wireless_ip:%s\twireless_net:%s\tsummary_net:%s\tdist_name:%s" % (ip,
                                        ip_config[dist]['wireless_net'], ip_config[dist]['summary_net'],
                                        ip_config[dist]['name'] ))
                    break

        self.log()
        
    def log(self):
        logger_wire = logging.getLogger("wire_user    ")
        logger_wireless = logging.getLogger("wireless_user")

        for dist in ip_config.keys():
            logger_wire.info("%s\t%s" % (ip_config[dist]['name'], ip_config[dist]['wire_user']))
            logger_wireless.info("%s\t%s" % (ip_config[dist]['name'], ip_config[dist]['wireless_user']))
            
        logger_total_wire = logging.getLogger("total_wire_user    ")
        logger_total_wire.info(self.total_wire_user)
        
        logger_total_wireless = logging.getLogger("total_wireless_user")
        logger_total_wireless.info(self.total_wireless_user)
        
if __name__ == '__main__':

    mining = mining()

    FUNCTION_MAP = {
        'user-count': mining.Grouping
    }
       
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=FUNCTION_MAP.keys(),
                        help='get total number of users per distribution networks')
    args = parser.parse_args()
    func = FUNCTION_MAP[args.command] 
    func()
    
