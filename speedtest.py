#!/usr/bin/python
# -*- coding: latin-1 -*-
 
from __future__ import print_function
import time
import datetime
import sqlite3
import subprocess
import pyspeedtest
import os
import re
import sys
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import ConfigParser
import csv
import os.path

# our modules...
from wirelessadapter import *
from gsheet import *
from simplelogger import *

DEBUG = 0

def read_config(debug):
    '''
    Read in the config file variables
    '''

    config_vars = {}
    
    config = ConfigParser.SafeConfigParser()
    config_file = os.path.dirname(os.path.realpath(__file__)) + "/config.ini"
    config.read(config_file)

    # db file name
    config_vars['db_file'] = config.get('General', 'db_file')

    # create logging object
    logger = SimpleLogger(config_vars['db_file'], debug)

    # Cache file name for local results that fail upload
    config_vars['cache_file'] = config.get('General', 'cache_file')

    # Speedtest server
    config_vars['server_name'] =  config.get('Server', 'server_name')

    # WLAN interface name
    config_vars['wlan_if'] = config.get('General', 'wlan_if')

    # Get platform architecture
    config_vars['platform'] = config.get('General', 'platform')
    
    # Probe location
    config_vars['location'] = config.get('General', 'location')

    if debug:    
        print("Platform = " + config_vars['platform'])

    # Figure out our hostname
    hostname = subprocess.check_output("/bin/hostname", shell=True)
    config_vars['hostname'] = hostname.strip()
    
    if debug:    
        print("Hostname = " + config_vars['hostname'])

    # Google sheet config parameters
    config_vars['spreadsheet_name'] = config.get('General', 'spreadsheet_name')
    config_vars['json_keyfile'] = config.get('General', 'json_keyfile')
    
    return (config_vars, logger)

def dump_result_local_csv(data_list, cache_file, db_file):

    '''
    We had issues saving data to our google sheet, so we'll dump_result_local_csv in a local file and try again later
    
    Fields: timestamp, ping_time, download_rate, upload_rate, ssid, bssid, freq, bit_rate, signal_level, ip_address, speedtest_server, location
    
    '''

    '''
    db_conn = sqlite3.connect(db_file)

    # add data to db
    db_conn.execute("insert into cached_results (timestamp, ping_time, download_rate, upload_rate, ssid, bssid, freq, bit_rate, signal_level, ip_address, speedtest_server, location) values (?,?,?,?,?,?,?,?,?,?,?,?)", data_list)
    db_conn.commit()
    
    # Tidy up cache entries - keep only last 20
    db_conn.execute("delete from cached_results where id not in (select id from cached_results order by id desc limit 20)")
    db_conn.commit()
        
    # close db connection
    db_conn.close()
    
    '''
    
    with open(cache_file, 'a') as csvfile:
        filewriter = csv.writer(csvfile, quoting=csv.QUOTE_MINIMAL)
        filewriter.writerow(data_list)

def push_cached_results(sheet, cache_file, db_file):
    
    '''
    Try and push cached results to gsheet - if we have lots of data to write, have to be careful not to over-run Google API and get throttled (*** Need to put pause in here***)
    '''
    
    '''
    db_conn = sqlite3.connect(db_file)
    
    # close db connection
    db_conn.close()
    '''
    
    
    with open(cache_file, 'rb') as f:
        reader = csv.reader(f)

        for sheet_row_data in reader:
            append_result = sheet.append_row(sheet_row_data)
            if DEBUG:
                print("Result of spreadsheet append operation from cache: " + str(append_result))
        
            if type(append_result) is not dict:     
                logger.log_error("Append operation from cache appears to have failed (should be dict: " + str(append_result))
                return False
        
        # all must have been OK, return True
        return True
 

def speedtest(server_name):

    '''
    This function runs the actual speedtest and returns the result
    as a list: ping_time, download_rate, upload_rate]
    '''

    # perform Speedtest
    st = pyspeedtest.SpeedTest(host=server_name)
    
    try:
        ping_time = int(st.ping())
        if DEBUG:
            print("Ping time = " + str(ping_time) + " ms")
    except Exception as error:
        logger.log_error("Problem with ping test: " + error.message)
        sys.exit()
        
        
    try:
        download_rate = '%.2f' % (st.download()/1024000)
        
        if DEBUG:
            print("Download rate = " + str(download_rate) + " Mbps")
    except Exception as error:
        logger.log_error("Download test error: " + error.message)
        sys.exit()
    
    try:
        upload_rate = '%.2f' % (st.upload()/1024000)
        if DEBUG:
            print("Upload rate = " + str(upload_rate) + " Mbps")
    except Exception as error:
        logger.log_error("Upload test error: " + error.message)
        sys.exit()
        
    return [ping_time, download_rate, upload_rate]


def check_config_updates(gsheet, worksheet_titles, config_vars):

    # *** under development *** Check if we have any config updates we need to apply
    # Anything read-in needs sanity checking and cleansing...not yet done
    if DEBUG:
            print("Checking if we have a config sheet...")
            
    # Do we have a config sheet?
    if "Config" not in worksheet_titles:
        if DEBUG:
            print("No config sheet found - no config read will be performed")
        return False
    
    if DEBUG:
        print("Looks like we have a confg sheet - attemping to retrieve")
    
    # read config sheet
    sheet = gsheet.open_gspread_worksheet("Config")
    
    if sheet == False:
        return False
        
    # read all values in to list of lists: [ [col1-row1, col2-row1], [col1-row2, col2-row2] 
    rows = sheet.get_all_values()
    
    if DEBUG:
        print(rows)
    
    allowed_fields = ['server_name', 'location']
    
    # Convert List of lists in to dictionary
    for row in rows:
        [section, parameter] = row[0].split(":")
        
        if parameter in allowed_fields:
            config_vars[parameter]= row[1]
    
    if DEBUG:
        print(config_vars)
    
    return config_vars

    
###############################################################################
# Main
###############################################################################
    
def main():

    # read in our local config file (content in dictionary: config_vars)
    
    (config_vars, logger) = read_config(DEBUG)
    
    wlan_if = config_vars['wlan_if']
    platform = config_vars['platform']
    json_keyfile = config_vars['json_keyfile']
    spreadsheet_name = config_vars['spreadsheet_name']
    cache_file = config_vars['cache_file']
    db_file = config_vars['db_file']
        
    # get wireless info
    adapter = WirelessAdapter(wlan_if, platform, DEBUG)

    # create our Google sheets object
    gsheet = Gsheet(json_keyfile, spreadsheet_name, logger, DEBUG)
    
    # modify config parameters based on config worksheet items (if exists)
    config_vars = check_config_updates(gsheet, gsheet.get_worksheet_titles(), config_vars)
    
    server_name = config_vars['server_name']
    location = config_vars['location']
    
    # if we have no network connection (i.e. no bssid), no point in proceeding...
    if adapter.get_bssid() == 'NA':
        logger.log_error("Problem with wireless connection: not associated to network")
        logger.log_error("Attempting to recover by bouncing wireless interface...")
        adapter.bounce_wlan_interface()
        sys.exit()
    
    # if we have no IP address, no point in proceeding...
    if adapter.get_ipaddr() == 'NA':
        logger.log_error("Problem with wireless connection: no valid IP address")
        logger.log_error("Attempting to recover by bouncing wireless interface...")
        adapter.bounce_wlan_interface()
        sys.exit()

    
    # run speedtest
    speedtest_results = speedtest(server_name)
    if DEBUG:
        print(speedtest_results)


    # Join the results lists
    r = speedtest_results + adapter.get_wireless_info() + [adapter.get_ipaddr()]
    if DEBUG:
        print(r)
    
    # check if we need to create new sheet (new day?)
    
    
    gsheet.create_worksheet_if_needed()
    
    # Send to google sheet
    now = datetime.datetime.now()
    current_timestamp = now.strftime("%Y-%m-%d %H:%M")
    sheet_row_data = [current_timestamp] + r + [server_name] + [location]
    if DEBUG:
        print(sheet_row_data)

    # open the sheet and try to post results (cache locally if fails)
    todays_worksheet_name = gsheet.get_todays_worksheet_name()
    sheet = gsheet.open_gspread_worksheet(todays_worksheet_name)
    
    if sheet != False:
    
        # Let's check to see if we have any old cached results to push before we
        # post latest result to gspread
        if os.path.exists(cache_file):
        
            # If successful, remove cache file
            if push_cached_results(sheet, cache_file, db_file) == True:
                os.remove(cache_file)
    
        # post latest result to worksheet    
        append_result = sheet.append_row(sheet_row_data)
        if DEBUG:
            print("Result of spreadsheet append operation: " + str(append_result))
            print("Append operation result type: " + str(type(append_result)))
        
        if type(append_result) is not dict:
            logger.log_error("Append operation on sheet appears to have failed (should be dict: " + str(append_result))
            # something went wrong with append operation - cache locally
            dump_result_local_csv(sheet_row_data, cache_file, db_file)
            
    else:
        # something went wrong with sheet opening operation - cache result locally for next time
        dump_result_local_csv(sheet_row_data, cache_file, db_file)
    
    db_conn = sqlite3.connect(db_file)
    
    # Tidy up old data to keep db reasonable size
    db_conn.execute("delete from speedtest_data where datetime(timestamp, 'unixepoch') <= date('now', '-7 days')")
    db_conn.commit()
    
    cleartext_date = datetime.datetime.now()
    
    # add data to db
    db_conn.execute("insert into speedtest_data (timestamp, cleartext_date, ping_time, download_rate, upload_rate, ssid, bssid, freq, bit_rate, signal_level, ip_address) values (?,?,?,?,?,?,?,?,?,?,?)", (int(time.time()), cleartext_date, r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8]))
    db_conn.commit()
    
    # Tidy up old logs
    db_conn.execute("delete from error_logs where datetime(timestamp, 'unixepoch') <= date('now', '-2 days')")
    db_conn.commit()
        
    # close db connection
    db_conn.close()

###############################################################################
# End main
###############################################################################
    
if __name__ == "__main__":
    main()
