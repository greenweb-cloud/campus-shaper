#!/usr/bin/python3

import argparse, os, logging

LOG_DIR = '/var/log/AAA/'
LOG_FILE= 'qos-monitor.log'

os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(name)-5s %(levelname)-8s %(message)s',
                    datefmt='20%y/%m/%d %H:%M',
                    filename= LOG_DIR + LOG_FILE,
                    filemode='w')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    #    parser.parse_args()
    parser.add_argument('-d', '--device', dest='now' , action='store_true', help='network device which root class is attached to.')

    args = parser.parse_args()
    if args.device:
        print ('this is the device')
    print (args)

    exit()
    if not os.path.exists('/sys/class/net/' + args.device):
        err = 'Cannot find device "%s"' % args.device
        logger = logging.getLogger("General")
        logger.error(err)
        print (err)
        exit(1)

    if args.device == 'enp3s0f1':
        print (' run function args.device.  bye ... ! ')
