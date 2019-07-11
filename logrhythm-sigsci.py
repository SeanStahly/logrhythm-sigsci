#!/usr/bin/env python3
from __future__ import absolute_import
from __future__ import print_function
import six.moves.configparser
import argparse
import json
import logging
import os
import sys
import calendar
import requests
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime, timedelta

class BaseLog(object):

    def __init__(self, config, log_path):
        self.config    = config
        self.events    = []
        self.corp_name = config['corp_name']
        self.site      = config['site']
        self.api_host  = config['api_host']
        self.headers   = {
            'Content-type': 'application/json',
            'Authorization': 'Bearer %s' % config['token']
        }

        # We need to give SigSci 5 minutes to ingest, aggregate, and process
        until_time = datetime.utcnow().replace(second=0, microsecond=0)
        until_time = until_time - timedelta(minutes=5)
        self.until_time = calendar.timegm(until_time.utctimetuple())
        

        # Set up our logger
        log_file   = os.path.join(log_path, self.__class__.__name__) + '-' + config['site'] + '.log'
        logger     = logging.getLogger(self.__class__.__name__)
        formatter  = logging.Formatter('%(message)s')
        loghandler = TimedRotatingFileHandler(log_file, 
                                              encoding='utf-8',
                                              when='midnight',
                                              interval=1,
                                              backupCount=7)
        loghandler.setLevel(logging.INFO)
        logger.setLevel(logging.INFO)
        loghandler.setFormatter(formatter)
        logger.addHandler(loghandler)

        self.logger = logger

    def get_events(self):
        try:
            self.fetch_events()
        except RuntimeError as e:
            errmsg = e.args[0]
            if errmsg == 'Received 429 Too Many Requests':
                print("SigSci is throttling requests, exiting.")
                sys.exit(0)

    def fetch_events(self):
        raise NotImplementedError

    def write_logs(self):
        raise NotImplementedError

    def set_from_time(self,new_from_time):
        self.from_time = new_from_time

    def update_from_time(self):
        """
            Determine the from_time based on the timestamp of the last event.
            To avoid duplicate logs, we set the from time to the next minute and zero seconds
        """
        if self.events:
            last_timestamp = self.events[-1]['timestamp'] 
            from_time = (datetime.strptime(last_timestamp[:-1],"%Y-%m-%dT%H:%M:%S").replace(second=0, microsecond=0)) + timedelta(minutes=1)
            self.from_time = calendar.timegm(from_time.utctimetuple())

        return self.from_time

class RequestLog(BaseLog):
    def __init__(self, config, site):
        BaseLog.__init__(self, config, site)

    def fetch_events(self):
        # Note that the API limits the until time to a max of 5 minutes ago
        self.url = self.api_host + ('/api/v0/corps/%s/sites/%s/feed/requests?from=%s&until=%s' % (self.corp_name, self.site, self.from_time, self.until_time))

        self.events = []
        url = self.url
        while True:
            response_raw = requests.get(url, headers=self.headers)
            if response_raw.status_code != 200:
                print ('Unexpected status: %s response %s' % (response_raw.status_code, response_raw.text))
                sys.exit(1)
            response = json.loads(response_raw.text)
            self.events.extend(response['data'])

            next_url = response['next']['uri']
            if next_url == '':
                break
            url = self.api_host + next_url

    def write_logs(self):
        fmtstr = (
            '%(timestamp)s,'
            'serverHostname="%(serverHostname)s",'
            'remoteIP="%(remoteIP)s",'
            'remoteHostname="%(remoteHostname)s",'
            'remoteCountryCode="%(remoteCountryCode)s",'
            'method="%(method)s",'
            'serverName="%(serverName)s",'
            'protocol="%(protocol)s",'
            'path="%(path)s",'
            'uri="%(uri)s",'
            'responseCode="%(responseCode)s",'
            'responseSize="%(responseSize)s",'
            'responseMillis="%(responseMillis)s",'
            'agentResponseCode="%(agentResponseCode)s",'
            'tags="%(tags)s",'
            'userAgent="%(userAgent)s"'
        )
        for event in self.events:
            # Grab our tag names and add them to an array
            tags = []
            for tag in event['tags']:
                tags.append(tag['type'])
            
            event['tags'] = ','.join(tags)
            self.logger.info(fmtstr % event)
        

def load_config(config_path):
    """
    Return a config created using the parameters
    stored in a config file.
    """
    config = six.moves.configparser.ConfigParser()
    config.read(config_path)
    config_s = dict(config.items('sigsci'))

    # Change csv to array
    config_s['site_names'] = [x.strip() for x in config_s['site_names'].split(',')]

    return config_s

def parse_args():
    parser = argparse.ArgumentParser(description='Download Signal Sciences logs to the local filesystem for LogRhythm consumption.')

    parser.add_argument("-c", "--config-file", help="Path to sigsci.conf, defaults to sigsci.conf in same directory as this script.",
                        default=os.path.join(sys.path[0], 'sigsci.conf'))
    parser.add_argument("-l", "--log-path", help="Path to store the log file in, defaults to the 'logs' directory beneath this script.",
                        default=os.path.join(sys.path[0], 'logs'))
    parser.add_argument("-s", "--state-path", help="Path to store the state file in, defaults to the same directory as the log file.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose mode.")
    return parser.parse_args()

def load_state_from_file(statefile):
    try:
        with open(statefile, 'r') as json_file:
            state = json.load(json_file)
    except IOError:
        state = {}
    return state

def write_state_to_file(statefile,state):
    try:
        with open(statefile, 'w') as outfile:
            json.dump(state, outfile)
    except IOError:
        print("Unable to write to " + statefile + ", exiting.")
        sys.exit(1)

def fetch_token(config):
    auth = requests.post(
        config['api_host'] + '/api/v0/auth',
        data = {"email": config['email'], "password": config['password']}
    )

    if auth.status_code == 401:
        print ('Invalid login. ' + auth.text)
        sys.exit(1)
    elif auth.status_code != 200:
        print ('Unexpected status: %s response %s' % (auth.status_code, auth.text))
        sys.exit(1)

    return auth.json()['token']

def main():
    # Parse the commandline args, load our config, and set our paths
    args        = parse_args()
    config_path = args.config_file
    log_path    = args.log_path
    state_path  = args.state_path if args.state_path else args.log_path
    state_file  = os.path.join(state_path,'.state.json')
    if not os.path.exists(log_path):
        os.makedirs(log_path)

    # Load our last timestamps to prevent dupes
    state = load_state_from_file(state_file)

    # This is our config
    config = load_config(config_path)

    # Get our auth token
    token = fetch_token(config)
    
    config['token'] = token

    for logclass in (RequestLog,): # Support for future other logtypes
        for site in config['site_names']:
            print ('Fetching requests since last run for site \'' + site +'\'')

            config['site'] = site
            log = logclass(config,log_path)

            # Load our previous state, creating the default if it doesn't exist
            state_index = log.__class__.__name__ + "-" + site
            try:
                from_time = state[state_index]['last_timestamp'] 
            except KeyError:
                # Only grab the last 24 hours if we haven't ran before, this is limited by the API
                from_time = (datetime.utcnow().replace(second=0, microsecond=0)) - timedelta(hours=24)
                from_time = calendar.timegm(from_time.utctimetuple())
                state[state_index] = {'last_timestamp': 0}

            log.set_from_time(from_time)
            # Fetch the events
            log.get_events()
            if args.verbose: print("Recieved " + str(len(log.events)) + " logs from the " + log.__class__.__name__)
            # Format the events and write them to the logs
            log.write_logs()
            # Update our last recorded timestamp
            state[state_index]['last_timestamp'] = log.update_from_time()

            # Save our state to a json file
            write_state_to_file(state_file, state)

if __name__ == '__main__':
    main()