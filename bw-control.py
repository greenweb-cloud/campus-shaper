#!/usr/bin/python3

import routeros_api, subprocess, os, logging, logging.config, yaml, json, pickle, time, argparse, psutil
import mysql.connector
from mysql.connector import Error
from sys import argv

CONFIG_FILE='config.yml'
DEBUG = False

# Try to locate the CONFIG_FILE path in the same directory as this file
config_file_path = os.path.join(*(os.path.split(__file__)[:-1] + (CONFIG_FILE,)))

# load configuration and set as 'config' variable
with open(config_file_path, 'r') as stream:                
    try:                                              
        config = yaml.safe_load(stream)                 
    except yaml.YAMLError as exc:                     
        print(exc)                                    

# configure logging dir + format.
os.makedirs(config['log']['dir'], exist_ok=True)
log_file = config['log']['dir'] +  config['log']['general']
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(name)-5s %(levelname)-8s %(message)s',   
                    datefmt='20%y/%m/%d %H:%M',
                    filename= log_file,
                    filemode='a')
    
class Controller:
    def counter(self):
        '''
        This function will return number from 0x000a(0) to 0xffff(65535)
        '''
        last_mark = config['iptables']['mark_start']
        try:
            last_mark = int(open(config['iptables']['mark_path_file'], 'r').read())
            if last_mark == int(config['iptables']['mark_end'],16): last_mark =  config['iptables']['mark_start']
            open(config['iptables']['mark_path_file'], 'w').write(str(last_mark+1))
            
        except Exception as e:
            open(config['iptables']['mark_path_file'], 'w').write(str(last_mark+1))
            print ('counter(): %s ' % e)
            logging.error('counter(): %s' % str(e))
            
        return hex(last_mark)

    def reset_counter(self):
        first = config['iptables']['mark_start']
        open(config['iptables']['mark_path_file'], 'w').write(str(first))
        
    def load_current_ips(self):
        try:
            f = open(config['users']['current_users_path'], 'rb')
            return pickle.load(f)
        except Exception as e:
            self.store_current_ips({})
            return {}

    def store_current_ips(self, data):
        f = open(config['users']['current_users_path'], 'wb')
        pickle.dump(data, f)

    def stop_bw_control(self,args):
        iptables = Iptables()
        tc = Tc()
        self.store_current_ips({}) # reset Available ips
        self.reset_counter()
        iptables.flush()
        tc.stop()
    
    def start_bw_control(self, args):
        self.run(args.user_bandwidth_coefficient)

    def restart_bw_control(self,args):
        self.stop_bw_control(args)
        self.start_bw_control(args)

    def run(self, user_bandwidth_coefficient):
        users = Users()
        
        iptables = Iptables()
        tc = Tc(user_bandwidth_coefficient)

        logger = logging.getLogger('run()')
        
        current_users = self.load_current_ips()
        MT_users = users.MT_active_users()
        user_info = users.load_user_info()

        logged_in , logged_out = users.logged_in_out_users(MT_users, current_users, user_info)

        if not current_users:       # so there is no currently users added
            print ('reset every thing ...')
            self.reset_counter()
            tc.reset()
            iptables.flush()

        iptables.update_mangle(logged_out)
        tc.update_filter(logged_out)
        tc.update_leaf(logged_out)
        new_current_users = users.update(current_users.copy(), logged_out)
    
        for ip, userType in logged_in.items():
            tc_id = self.counter()
            
            tc.add_leaf(tc_id, tc_id, userType['type'])
            tc.add_filter(tc_id, tc_id, userType['type'])
            iptables.add_mangle(ip, tc_id)
            
            new_current_users[ip] = userType
            new_current_users[ip]['tc_id'] = tc_id
            
            logger_in = logging.getLogger("LOGGED_IN")
            logger_in.info("%s: %s" % (ip, userType))

        self.store_current_ips(new_current_users)

        prof_count, phd_count, master_count, other_stu_count, staff_count, default_count = (0, 0, 0, 0, 0, 0)
        for val in new_current_users.values():
            if val['type'] == 'OTHER_STU': other_stu_count +=1
            elif val['type'] == 'MASTER': master_count +=1
            elif val['type'] == 'PHD': phd_count +=1
            elif val['type'] == 'STAFF': staff_count +=1
            elif val['type'] == 'PROF': prof_count +=1
            else: default_count +=1

        logger_prof = logging.getLogger('ONLINE_PROF')
        logger_prof.info('%s',prof_count)
        
        logger_student = logging.getLogger('ONLINE_PHD')
        logger_student.info('%s',phd_count)

        logger_student = logging.getLogger('ONLINE_MASTER')
        logger_student.info('%s',master_count)

        logger_student = logging.getLogger('ONLINE_OTHER_STU')
        logger_student.info('%s',other_stu_count)
        
        logger_staff = logging.getLogger('ONLINE_STAFF')
        logger_staff.info('%s',staff_count)
        
        logger_default = logging.getLogger('ONLINE_DEFAULT')
        logger_default.info('%s',default_count)

        logger.info("  Statistics: current_users{ before_update=%d, after_update=%d}, logged_in=%d, logged_out=%d\n" %
                    (len(current_users), len(new_current_users) , len(logged_in), len(logged_out)))
        # print ("\n\n\ntotal current users is: %d\n" % len(current_users))

############
class Users:
    def __init__(self):
        self.connection = None
        self.api = None
        self.active_users = None
        
        self.conn_mikrotik()
        self.dbconn = self.db_conn()
   
    def conn_mikrotik(self):
        try:
            self.connection = routeros_api.RouterOsApiPool(host=config['mikrotik']['host'],
                                                           username=config['mikrotik']['username'],
                                                           password=config['mikrotik']['password'],
                                                           port=config['mikrotik']['port'])
            self.api = self.connection.get_api()
        except Exception as e:
            print (ROUTER, str(e))
            logger = logging.getLogger("conn_mikrotik()")
            logger.error(str(e))
            exit(1)

    def load_user_info(self):
        try:
            f = open(config['users']['user_info_path'], 'rb')
            return pickle.load(f)
        except Exception as e:
            return self.cache_user_info()
            

    def cache_user_info(self):
        logger = logging.getLogger("cache_user_info()")
        staff_prof_query = "SELECT WebUserID, PortalType FROM framework.staff_accounts WHERE disabled='NO' ;"
        user_query =  "SELECT ss.StNo, ss.EduSecCode FROM educ.StudentSpecs ss left join educ.StudyStatus s using(StatusID) where  s.StuStatus=1 ;"

        try:
            dbconn = Users.db_conn(self)

            cur = dbconn.cursor()
            cur.execute(staff_prof_query)
            result = cur.fetchall()
            
            cur = dbconn.cursor()
            cur.execute(user_query)
            result += cur.fetchall()
            dbconn.close()
        except Error as e:
            logger.error(str(e))
            logger.error("  could not cache user information")
            return None

        result = dict((x,y) for x,y in result)
        
        f = open(config['users']['user_info_path'], 'wb')
        pickle.dump(result, f)
       
        logger.info("  New user infromation(prof,staff,stu)  cached from database")
        return result

    def MT_active_users(self):
        return self.api.get_resource('/ip/hotspot/active').get()

    def logged_in_out_users (self, MT_users, current_users, user_info):
        logged_in = {} # {'address':{'user':<name>, 'type':<PROF|PHD|MASTER|OTHER_STU|STAFF|DEFAULT>}, ...}
        logged_out = {} # {'address':{'user':<name>, 'type':<PROF|STUDENT|STAFF|DEFAULT>}, ...}
        MT_ips = [] # all users in MT_users (used for generate logged_out users)
        prof_staff = ('','')    # why use two empty '',??!! sometimes we don't have any prof staff users so Query would be in error 
        user_types = {
            config['users']['PHD_A_EduSecCode']: "PHD",
            config['users']['PHD_B_EduSecCode']: "PHD",
            config['users']['MASTER_EduSecCode']: "MASTER",
            config['users']['STAFF_TYPE']: "STAFF",
            config['users']['PROF_TYPE']: "PROF",
            config['users']['OTHER_STU_TYPE']: 'OTHER_STU',
            config['users']['DEFAULT']: "DEFAULT"
            }
        
        for user in MT_users:
            address = user['address'].strip()
            u = user['user'].strip()

            MT_ips.append(address) # store all currently logged in ip's to check logged out users

            if address in current_users: continue # so it means that 'address' is added from last run.
            
            logged_in[address] = {}
            logged_in[address]['user'] = u

            if u in user_info.keys():
                usertype = user_types.get(user_info[u], "OTHER_STU")
            else:
                usertype = user_types['DEFAULT']
                logger = logging.getLogger("MT_active_users") 
                logger.warning(" logged_in(): Active user (( %s )) in %s  does not exist in pooya database" %
                               (u,config['mikrotik']['name']))

            logged_in[address]['type'] = usertype
                
        for ip, val in current_users.items():
            if ip not in MT_ips:
                logged_out[ip] = val

        return logged_in, logged_out

    def total_seconds(self, uptime):
        if uptime.find('w') == -1: uptime = '0w' + uptime
        if uptime.find('d') == -1: uptime = uptime[:uptime.find('w')+1] + '0d' + uptime[uptime.find('w')+1:]
        if uptime.find('h') == -1: uptime = uptime[:uptime.find('d')+1] + '0h' + uptime[uptime.find('d')+1:]
        if uptime.find('m') == -1: uptime = uptime[:uptime.find('h')+1] + '0m' + uptime[uptime.find('h')+1:]
        if uptime.find('s') == -1: uptime = uptime + '0s'

        uptime = uptime.replace('w',',').replace('d',',').replace('h',',').replace('m',',')[:-1]
        uptime = uptime.split(',')
        uptime_sec = int(uptime[0])*604800 + int(uptime[1])*86400 + int(uptime[2])*3600 + int(uptime[3])*60 + int(uptime[4])

        return uptime_sec

    def update(self, current_users, logged_out):
        
        for ip, val in logged_out.items():
            try:
                del(current_users[ip])
                logger_out = logging.getLogger("LOGGED_OUT")
                logger_out.info('%s: %s' % (ip, str(val)))
            except Exception as e:
                print ('users.update(): ' % e)
                logger = logging.getLogger("users.update()")
                logger.error(' %s' % str(e))
                logger.error(' ip %s not found in current_users' % ip)
               
        return current_users
    
    def db_conn(self):
        """ Connect to MySQL database """
        dbconn = None
        try:
            dbconn = mysql.connector.connect(host = config['databases']['pooya']['host'],
                                             #database = config['databases']['pooya']['dbname'],
                                             user = config['databases']['pooya']['username'],
                                             password = config['databases']['pooya']['password'])
            if dbconn.is_connected():
                #print "Connection OK!\n"                                                                                   
                return dbconn
        except Error as e:
            print(e)
            logging.error(str(e))
            return None
    
    def close(self):
        self.connection.disconnect()
        self.dbconn.close()
       
class Iptables:
    def __init__(self):
        self.last_mark = None

    def flush(self):
        cmd_iptables_flush = 'iptables -t mangle -F'
        os.system(cmd_iptables_flush)
        
    def update_mangle(self, logged_out):
        for ip, user_val in logged_out.items():
            self.del_mangle(ip, user_val['tc_id'])
                
    def add_mangle (self, ip, mark):
        cmd_add_mangle = "iptables -t mangle -A PREROUTING --dest %s -j MARK --set-mark %s " % (ip, mark) # add
        os.system(cmd_add_mangle)
        if DEBUG:
            logging.warning("  add_mangle(): %s" % cmd_add_mangle)

    def del_mangle (self, ip, mark):
        cmd_del_mangle = "iptables -t mangle -D PREROUTING --dest %s -j MARK --set-mark %s " % (ip, mark) # delete

        os.system(cmd_del_mangle)
        if DEBUG:
            logging.warning("  del_mangle(): %s" % cmd_del_mangle)

class Tc:
    def __init__(self, u=1):
        self.coefficient = u # user bandwidth coefficient
        self.init_shaper()
        
    def status(self):
        cmd_qdisc_stat = ''
        cmd_class_stat = ''
        cmd_filter_stat = ''
        cmd_iptabes_stat = ''

    def reset(self):
        self.stop()
        self.init_shaper()

    def stop(self):
        stop_down = "%s qdisc del dev %s root" % (config['tc']['cmd'], config['tc']['dev']['down'])
        stop_up = "%s qdisc del dev %s root" % (config['tc']['cmd'], config['tc']['dev']['up'])
        os.system(stop_down)
        os.system(stop_up)

    def init_shaper(self):
        cmd_add_root = "%s qdisc add dev %s root handle 1: htb default %d" % (config['tc']['cmd'],
                                                                              config['tc']['dev']['down'],
                                                                              config['tc']['classify']['DEFAULT']['classid'])

        msg = os.popen(cmd_add_root + " 2>&1").read() # /sbin/tc return error in stderr, so use 2>&1 to redirect error to stdout
        if 'File exists' in msg:
            return
        print ("initializing ... ")
        add_main_class = "%s class add dev %s parent 1:  classid 1:1  htb rate %s  ceil %s " % (
            config['tc']['cmd'], 
            config['tc']['dev']['down'], config['tc']['dev']['rate'], config['tc']['dev']['rate'])

        add_prof_class="%s class add dev %s parent 1:1 classid 1:%d htb rate %s ceil %s prio %d" % (
            config['tc']['cmd'], 
            config['tc']['dev']['down'],
            config['tc']['classify']['PROF']['classid'], config['tc']['classify']['PROF']['total_bw'],
            config['tc']['classify']['PROF']['ceil'], config['tc']['classify']['PROF']['prio'])

        add_phd_class="%s class add dev %s parent 1:1 classid 1:%d htb rate %s ceil %s prio %d" % (
            config['tc']['cmd'], 
            config['tc']['dev']['down'],
            config['tc']['classify']['PHD']['classid'], config['tc']['classify']['PHD']['total_bw'],
            config['tc']['classify']['PHD']['ceil'], config['tc']['classify']['PHD']['prio'])

        add_master_class="%s class add dev %s parent 1:1 classid 1:%d htb rate %s ceil %s prio %d" % (
            config['tc']['cmd'], 
            config['tc']['dev']['down'],
            config['tc']['classify']['MASTER']['classid'], config['tc']['classify']['MASTER']['total_bw'],
            config['tc']['classify']['MASTER']['ceil'], config['tc']['classify']['MASTER']['prio'])

        add_otherstu_class="%s class add dev %s parent 1:1 classid 1:%d htb rate %s ceil %s prio %d" % (
            config['tc']['cmd'], 
            config['tc']['dev']['down'],
            config['tc']['classify']['OTHER_STU']['classid'], config['tc']['classify']['OTHER_STU']['total_bw'],
            config['tc']['classify']['OTHER_STU']['ceil'], config['tc']['classify']['OTHER_STU']['prio'])
        
        add_staff_class="%s class add dev %s parent 1:1 classid 1:%d htb rate %s ceil %s prio %d" % (
            config['tc']['cmd'], 
            config['tc']['dev']['down'],
            config['tc']['classify']['STAFF']['classid'], config['tc']['classify']['STAFF']['total_bw'],
            config['tc']['classify']['STAFF']['total_bw'], config['tc']['classify']['STAFF']['prio'])

        add_default_class="%s class add dev %s parent 1:1 classid 1:%d htb rate %s ceil %s prio %d" % (
            config['tc']['cmd'], 
            config['tc']['dev']['down'],
            config['tc']['classify']['DEFAULT']['classid'], config['tc']['classify']['DEFAULT']['total_bw'],
            config['tc']['classify']['DEFAULT']['total_bw'], config['tc']['classify']['DEFAULT']['prio'])

        #cmd_flush_mangle='iptables -F -t mangle' # This command should be run in iptables class but i'm lazy right now... .
        #os.system(cmd_flush_mangle)
        
        os.system(add_main_class)
        os.system(add_prof_class)
        os.system(add_phd_class)
        os.system(add_master_class)
        os.system(add_otherstu_class)
        os.system(add_staff_class)
        os.system(add_default_class)

    def get_info_class(self):
        cmd = '%s -j class show dev %s' % (config['tc']['cmd'], config['tc']['dev']['down'])

    def get_info_qdisc(self):
        cmd = '%s -json qdisc show dev %s' % (config['tc']['cmd'], config['tc']['dev']['down'])
        qdisc_list = os.popen(cmd).read()

        print (qdisc_list[1:-3])
        dic = json.loads(qdisc_list[1:-3])
        dic = dic.replace("'", "\"")
        print (dic)
        
    def add_leaf(self, handle, classid, userType):
        cmd_add_class = "%s class add dev %s parent 1:%s classid 1:%s htb rate %smbit ceil %smbit prio %d" % (
            config['tc']['cmd'], 
            config['tc']['dev']['down'], config['tc']['classify'][userType]['classid'], classid,
            float(config['tc']['classify'][userType]['user_bw'])*self.coefficient,
            float(config['tc']['classify'][userType]['user_bw'])*self.coefficient,
            config['tc']['classify'][userType]['prio']
        )
        cmd_add_queue = "%s qdisc add dev %s parent 1:%s handle %s: pfifo limit 5" % (
            config['tc']['cmd'], 
            config['tc']['dev']['down'], classid, handle)

        os.system(cmd_add_class)
        os.system(cmd_add_queue)
        if DEBUG:
            logging.warning("  tc.add_leaf(): %s" % cmd_add_class)
            logging.warning("  tc.add_leaf(): %s" % cmd_add_queue)

    def del_leaf(self, dev, parent, classid, handle):
        cmd_del_qdisc = '%s qdisc del dev %s parent 1:%s handle %s: ;' % (config['tc']['cmd'],
                                                                          dev, classid, handle)
        cmd_del_class = '%s class del dev %s parent 1:%s classid 1:%s ;' % (config['tc']['cmd'],
                                                                            dev, parent, classid)

        os.system(cmd_del_qdisc)
        os.system(cmd_del_class)
        if DEBUG:
            logging.warning("  tc.del_leaf(): %s" % cmd_del_qdisc)
            logging.warning("  tc.del_leaf(): %s" % cmd_del_class)
            
    def update_leaf(self, logged_out):
        for ip, user_val in logged_out.items():
            self.del_leaf(config['tc']['dev']['down'], # dev
                          config['tc']['classify'][user_val['type']]['classid'], # parent
                          user_val['tc_id'], # classid
                          user_val['tc_id']) # handle

    def add_filter(self, handle, classid, userType):
        cmd_add_filter = '%s filter add dev %s protocol ip parent 1: prio %s handle %s fw classid 1:%s ' % (
            config['tc']['cmd'], config['tc']['dev']['down'] , config['tc']['classify'][userType]['prio'], handle, classid)

        #        cmd_add_filter = '%s filter add dev %s parent 1:0 protocol ip prio %s u32 match ip dst %s/32 flowid 1:%s'
        #% (config['tc']['cmd'], config['tc']['dev']['down'], config['tc']['classify'][userType]['prio'], ip, classid)
        os.system(cmd_add_filter)
        if DEBUG: logging.warning("  tc.add_filter(): %s" % cmd_add_filter)


    def del_filter(self, dev, handle, classid, userType):
        cmd_del_filter = '%s filter del dev %s protocol ip parent 1: prio %s handle %s fw classid 1:%s' % (
            config['tc']['cmd'], dev, config['tc']['classify'][userType]['prio'], handle, classid)
            
        os.system(cmd_del_filter)
        if DEBUG: logging.warning("  tc.del_filter(): %s" % cmd_del_filter)
        
    def update_filter(self, logged_out):
        for ip, user_val in logged_out.items():
            self.del_filter(config['tc']['dev']['down'], # dev
                            user_val['tc_id'], # handle
                            user_val['tc_id'], # classid
                            user_val['type'])  # userType

################################################################
if __name__ == '__main__':

    controller = Controller()

    parser = argparse.ArgumentParser()
    parser.add_argument('--version', action='version', version='1.0.0')
    subparsers = parser.add_subparsers()
    
    start_parser = subparsers.add_parser('start')
    start_parser.add_argument('--user-bandwidth-coefficient', '-u', type=float, default=1,
                              help='user bandwidth coefficient to increase or decrease maximum download speed. default is set to 1.')
    start_parser.set_defaults(func=controller.start_bw_control)

    stop_parser = subparsers.add_parser('stop', help='stop traffic shaper.')
    stop_parser.set_defaults(func=controller.stop_bw_control)
    
    restart_parser = subparsers.add_parser('restart')
    restart_parser.add_argument('--user-bandwidth-coefficient', '-u', type=float, default=1,
                              help='user bandwidth coefficient to increase or decrease maximum download speed. default is set to 1.')
    restart_parser.set_defaults(func=controller.restart_bw_control)

    cache_user_info = subparsers.add_parser('cache_user_info')
    cache_user_info.set_defaults(func=Users.cache_user_info)
    
    args = parser.parse_args()
    args.func(args)
