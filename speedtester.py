#!/usr/bin/python
# -*- coding: latin-1 -*-
 
from __future__ import print_function
import time
import datetime
import sqlite3
import subprocess
from socket import gethostbyname
import speedtest
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
from pinger import *

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

def dump_result_local_db(data_list, db_file, logger, debug):

    '''
    We had issues saving data to our google sheet, so we'll dump_result_local_db in a local sqlite db and try again later
    
    Fields: timestamp, ping_time, download_rate, upload_rate, ssid, bssid, freq, bit_rate, signal_level, ip_address, location, speedtest_server
    
    '''
  
    # dump to sqlite DB
    try:
        db_conn = sqlite3.connect(db_file)
    except Exception as error:
        logger.log_error("Db connection error when trying to dump local results: " + error.message)
    
    # add data to db
    try:
        db_conn.execute("insert into cached_results (timestamp, ping_time, download_rate, upload_rate, ssid, bssid, freq, bit_rate, signal_level, ip_address, location, speedtest_server,ping_host1,pkts_tx1,percent_loss1,rtt_avg1,ping_host2,pkts_tx2,percent_loss2,rtt_avg2,ping_host3,pkts_tx3,percent_loss3,rtt_avg3) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", data_list)
        db_conn.commit()
    except Exception as error:
        logger.log_error("Db execute error when trying to dump local results: " + error.message)
    
    # Tidy up cache entries - keep only last 20
    try:
        db_conn.execute("delete from cached_results where id not in (select id from cached_results order by id desc limit 20)")
        db_conn.commit()
    except Exception as error:
        logger.log_error("Db execute error when trying to delete older cached results: " + error.message)
        
    # close db connection
    db_conn.close()


def push_cached_results(sheet, cache_file, db_file, logger, debug):
    
    '''
    Try and push cached results to gsheet - if we have lots of data to write, have to be careful not to over-run Google API and get throttled (cached results limited to 20 in dump_result_local_db)
    
    '''
    
    # give us dictionary results
    db_conn = sqlite3.connect(db_file)
    
    cursor = db_conn.cursor()
    
    try:
        cursor.execute("select timestamp, ping_time, download_rate, upload_rate, ssid, bssid, freq, bit_rate, signal_level, ip_address, location, speedtest_server,ping_host1,pkts_tx1,percent_loss1,rtt_avg1,ping_host2,pkts_tx2,percent_loss2,rtt_avg2,ping_host3,pkts_tx3,percent_loss3,rtt_avg3 from cached_results")
        if debug:
            print("Checking to see if we have cached data to send to google sheet...")
    except Exception as error:
        logger.log_error("Db execute error when trying to select cached data: " + error.message)        
    
    # retrieve all cached data from db
    cached_data = cursor.fetchall()
    
    # clear the cache table
    try:
        db_conn.execute("delete from cached_results")
        db_conn.commit()
    except Exception as error:
        logger.log_error("Db execute error when trying to delete old cached data: " + error.message)
    
    # step through results & upload to sheet
    for sheet_row_data in cached_data:
        
        if debug:
            print("cached data row: ")
            print(sheet_row_data)
            
        append_result = sheet.append_row(sheet_row_data)
        
        if debug:
            print("Result of spreadsheet append operation from cache: " + str(append_result))
        
        if type(append_result) is not dict:     
            logger.log_error("Append operation from cache appears to have failed (should be dict: " + str(append_result))
            return False
    
    # close db connection
    db_conn.close()

    # all must have been OK, return True
    return True
 

def ooklaspeedtest(server_name=""):

    '''
    This function runs the actual speedtest and returns the result
    as a dictionary: 
        { 'ping_time':  ping_time,
          'download_rate': download_rate,
          'upload_rate': upload_rate,
          'server_name': server_name
        }
    
    
    Speedtest server list format (dict):
    19079.416816052293: [{'cc': 'NZ',
                       'country': 'New Zealand',
                       'd': 19079.416816052293,
                       'host': 'speed3.snap.net.nz:8080',
                       'id': '6056',
                       'lat': '-45.8667',
                       'lon': '170.5000',
                       'name': 'Dunedin',
                       'sponsor': '2degrees',
                       'url': 'http://speed3.snap.net.nz/speedtest/upload.php',
                       'url2': 'http://speed-dud.snap.net.nz/speedtest/upload.php'},
                      {'cc': 'NZ',
                       'country': 'New Zealand',
                       'd': 19079.416816052293,
                       'host': 'speedtest.wic.co.nz:8080',
                       'id': '5482',
                       'lat': '-45.8667',
                       'lon': '170.5000',
                       'name': 'Dunedin',
                       'sponsor': 'WIC NZ Ltd',
                       'url': 'http://speedtest.wic.co.nz/speedtest/upload.php',
                       'url2': 'http://speedtest.wickednetworks.co.nz/speedtest/upload.php'},
                      {'cc': 'NZ',
                       'country': 'New Zealand',
                       'd': 19079.416816052293,
                       'host': 'speedtest.unifone.net.nz:8080',
                       'id': '12037',
                       'lat': '-45.8667',
                       'lon': '170.5000',
                       'name': 'Dunedin',
                       'sponsor': 'Unifone NZ LTD',
                       'url': 'http://speedtest.unifone.net.nz/speedtest/upload.php'}]
    '''

    import sys
    
    # perform Speedtest
    st = speedtest.Speedtest()
    st.get_best_server()
    
    try:
        download_rate = '%.2f' % (st.download()/1024000)
        
        if DEBUG:
            print("Download rate = " + str(download_rate) + " Mbps")
    except Exception as error:
        logger.log_error("Download test error: " + error.message)
        sys.exit()
    
    try:
        upload_rate = '%.2f' % (st.upload(pre_allocate=False)/1024000)
        if DEBUG:
            print("Upload rate = " + str(upload_rate) + " Mbps")
    except Exception as error:
        logger.log_error("Upload test error: " + error.message)
        sys.exit()

    results_dict = st.results.dict()
    ping_time = int(results_dict['ping'])
    server_name = results_dict['server']['host']
    
    return {'ping_time': ping_time, 'download_rate': download_rate, 'upload_rate': upload_rate, 'server_name': server_name}


def check_config_updates(gsheet, worksheet_titles, config_vars):

    ###########################################################################
    # FIXME: 
    # *** under development *** Check if we have any config updates we need to 
    # apply. Anything read-in needs sanity checking and cleansing...not yet 
    # done. Some being done in ping section of main to figure out if valid host
    # host entered - probably best here
    #
    # Need to ensure server name undefined if field exists by no value (or)
    # whitespace entered
    ###########################################################################
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
    
    allowed_fields = ['server_name', 'location', 'ping_1', 'ping_2', 'ping_3']
    
    # Convert List of lists in to dictionary
    for row in rows:
        [section, parameter] = row[0].split(":")
        
        if parameter in allowed_fields:
            config_vars[parameter]= row[1]
    
    if DEBUG:
        print(config_vars)
    
    return config_vars

def update_console(gsheet, worksheet_titles, db_file, logger, DEBUG):

    '''
    If we have any error messages, send them to the console sheet
      
    '''
    # max number of rows allowed in console
    max_rows = 50

    # If we have a console sheet, upload the latest error messages to items
    if DEBUG:
            print("Checking if we have a console sheet...")
    
    # FIXME: Only open sheet if we have error messages to send
    # Do we have a config sheet?
    if "Console" not in worksheet_titles:
        if DEBUG:
            print("No console sheet found - no logs will be reported")
        return False
    
    if DEBUG:
        print("Looks like we have a console sheet - attemping to open")
    
    # read config sheet
    sheet = gsheet.open_gspread_worksheet("Console")
    
    if sheet == False:
        return False
    
    # read latest error logs from probe
    db_conn = sqlite3.connect(db_file)
    
    cursor = db_conn.cursor()
    
    try:
        cursor.execute("select cleartext_date, error_msg from error_logs")
        if DEBUG:
            print("Checking to see if we have error logs to send to console sheet...")
    except Exception as error:
        print("Db execute error when trying to select error logs: " + error.message)
        #logger.log_error("Db execute error when trying to select error logs: " + error.message)
        #FIXME: Any point in carrying on here ? Should exit or return as wasting our time here...
    
    # retrieve all cached data from db
    error_log_data = cursor.fetchall()
    
    # clear the log table
    try:
        db_conn.execute("delete from error_logs")
        db_conn.commit()
    except Exception as error:
        logger.log_error("Db execute error when trying to delete old error log data: " + error.message)
        #FIXME: Any point in carrying on here ? Should exit or return as wasting our time here...
    
    last_row_number = 0
    
    # step through results & upload to sheet
    for sheet_row_data in error_log_data:
        
        if DEBUG:
            print("cached data row: ")
            print(sheet_row_data)
            
        append_result = sheet.append_row(sheet_row_data)
        
        if DEBUG:
            print("Result of spreadsheet append operation from error log: " + str(append_result))
        
        if type(append_result) is not dict:     
            logger.log_error("Append operation from error log appears to have failed (should be dict: " + str(append_result))
            return False

        updated_range = append_result['updates']['updatedRange']
        
        row_number_re = re.search('.*?\!A(\d+)', updated_range)
        
        if row_number_re is None:
            logger.log_error("Unable to extract last row number in error sheet")
        else:
            last_row_number = int(row_number_re.group(1))
        
        if DEBUG:
            print("Last console sheet row: " + str(last_row_number))
            
    if last_row_number > max_rows:
        # we need to do something here to remove rows in console sheet
        
        for i in range(last_row_number - max_rows):
            sheet.delete_row(1)
    
    # close db connection
    db_conn.close()

    # all must have been OK, return True
    return True

def bounce_error_exit(adapter, logger, error_msg, debug=False): 
    '''
    Log an error before bouncing the wlan interface and then exiting as we have an unrecoverable error with the network connection
    '''
    import sys
    
    logger.log_error(error_msg)
    adapter.bounce_wlan_interface()
    logger.log_error("Exiting...")
    sys.exit()   
    
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
    
    now = datetime.datetime.now()
    current_timestamp = now.strftime("%Y-%m-%d %H:%M")
        
    # get wireless info
    adapter = WirelessAdapter(wlan_if, logger, platform=platform, debug=DEBUG)   

    # if we have no network connection (i.e. no bssid), no point in proceeding...
    if adapter.get_wireless_info() == False:
        error_msg = "Unable to get wireless info due to failure with ifconfig command"
        bounce_error_exit(adapter, logger, error_msg, DEBUG) # exit here
        
    if adapter.get_bssid() == 'NA':
        error_msg = "Problem with wireless connection: not associated to network"
        error_msg = error_msg + "Attempting to recover by bouncing wireless interface..."
        bounce_error_exit(adapter, logger, error_msg, DEBUG) # exit here
    
    # if we have no IP address, no point in proceeding...
    if adapter.get_adapter_ip() == False:
        error_msg = "Unable to get wireless adapter IP info"
        bounce_error_exit(adapter, logger, error_msg, DEBUG) # exit here
    
    if adapter.get_route_info() == False:
        error_msg = "Unable to get wireless adapter route info"
        bounce_error_exit(adapter, logger, error_msg, DEBUG) # exit here
    
    if adapter.get_ipaddr() == 'NA':
        error_msg = "Problem with wireless connection: no valid IP address"
        error_msg = error_msg + "Attempting to recover by bouncing wireless interface..."
        bounce_error_exit(adapter, logger, error_msg, DEBUG) # exit here
    
    # final connectivity check: see if we can resolve an address 
    # (network connection and DNS must be up)
    try:
        gethostbyname('oauth2.googleapis.com')
    except Exception as ex:
        error_msg_msg = "DNS seems to be failing, bouncing wireless interface..."
        bounce_error_exit(adapter, logger, error_msg, DEBUG) # exit here
        
    
    # create our Google sheets object
    try:
        gsheet = Gsheet(json_keyfile, spreadsheet_name, logger, DEBUG)
    except Exception as ex:
        logger.log_error("Error opening Google spreadsheet: " + str(ex))
        gsheet = False
    
    # modify config parameters based on config worksheet items (if exists)
    if gsheet:
        config_vars = check_config_updates(gsheet, gsheet.get_worksheet_titles(), config_vars)
    
    server_name = config_vars['server_name']
    location = config_vars['location']
    
    # Clean up the content to get rid of whitespace
    server_name = server_name.strip()
    location = location.strip()
    
    ###########################################################################
    # FIXEME: Server name not currently used in Speedtest function.Need to fix 
    # this and ensure that if no server passed, uses "best" (which is diff
    # server every time)
    ###########################################################################
    
    # run speedtest
    speedtest_results = ooklaspeedtest(server_name)
    
    if DEBUG:
        print("Main: Speedtest results:")
        print(speedtest_results)
    
    # hold all results in one place
    results_dict = {}
    
    # speedtest results
    results_dict['ping_time'] = speedtest_results['ping_time']
    results_dict['download_rate'] = speedtest_results['download_rate']
    results_dict['upload_rate'] = speedtest_results['upload_rate']
    results_dict['server_name'] = speedtest_results['server_name']
    
    results_dict['ssid'] = adapter.get_ssid()
    results_dict['bssid'] = adapter.get_bssid()
    results_dict['freq'] = adapter.get_freq()
    results_dict['bit_rate'] = adapter.get_bit_rate()
    results_dict['signal_level'] = adapter.get_signal_level()
    results_dict['ip_addr'] = adapter.get_ipaddr()
    
    ####################################################################
    # FIXME: Need to re-factor to remove repetitive code for ping tests 
    #
    # Create functions to pre-fill dict values with NA (use 
    # dict2.update(dict2) feature to update results_dict
    #
    # Also, put ping process in to single function
    #
    ####################################################################
    # check if we have ping 1 test defined & run test if exists
    results_dict['ping_host1'] =  "NA"
    results_dict['pkts_tx1'] =  "NA"
    results_dict['pkts_rx1'] =  "NA"
    results_dict['percent_loss1'] =  "NA"
    results_dict['test)time1'] =  "NA"
    results_dict['rtt_min1'] =  "NA"
    results_dict['rtt_avg1'] =  "NA"
    results_dict['rtt_max1'] =  "NA"
    results_dict['rtt_mdev1'] =  "NA"
    
    ping_host1 = False
    if 'ping_1' in config_vars.keys():
        ping_host1 = config_vars['ping_1']
        
        # Clean up the content to get rid of whitespace
        ping_host1 = ping_host1.strip()
        
        # if not in correct format, make false & register error
        if ping_host1 == '':
            # blank entry ignore
            ping_host1 = False
        elif not re.match(r"\S+\.\S+", ping_host1):            
            logger.log_error("Error with ping host format: \'" + str(ping_host1) + "\'")
            logger.log_error("Ping host must be IP address of resolvable hostname")
            ping_host1 = False            
        
    if ping_host1:
        
        # check for def.gw keyword
        if  ping_host1 == "def.gw":
            ping_host1 = adapter.get_def_gw()
    
        # run 1st ping test
        ping_obj1 = Pinger(platform = platform, debug = DEBUG)
        
        # initial ping to clear out arp
        ping_obj1.ping_host(ping_host1, 1)
        
        # ping test
        ping_result1 = ping_obj1.ping_host(ping_host1, 10)
        
        # ping1 results
        if ping_result1:
            results_dict['ping_host1'] =  ping_result1['host']
            results_dict['pkts_tx1'] =  ping_result1['pkts_tx']
            results_dict['pkts_rx1'] =  ping_result1['pkts_rx']
            results_dict['percent_loss1'] =  ping_result1['pkt_loss']
            results_dict['test)time1'] =  ping_result1['test_time']
            results_dict['rtt_min1'] =  ping_result1['rtt_min']
            results_dict['rtt_avg1'] =  ping_result1['rtt_avg']
            results_dict['rtt_max1'] =  ping_result1['rtt_max']
            results_dict['rtt_mdev1'] =  ping_result1['rtt_mdev']
        
        if DEBUG:
            print("Main: Ping1 test results:")
            print(ping_result1)
    
    # check if we have ping 2 test defined & run test if exists
    results_dict['ping_host2'] =  "NA"
    results_dict['pkts_tx2'] =  "NA"
    results_dict['pkts_rx2'] =  "NA"
    results_dict['percent_loss2'] =  "NA"
    results_dict['test)time2'] =  "NA"
    results_dict['rtt_min2'] =  "NA"
    results_dict['rtt_avg2'] =  "NA"
    results_dict['rtt_max2'] =  "NA"
    results_dict['rtt_mdev2'] =  "NA"
    
    ping_host2 = False
    if 'ping_2' in config_vars.keys():
        ping_host2 = config_vars['ping_2']
        
        # Clean up the content to get rid of whitespace
        ping_host2 = ping_host2.strip()
        
        # if not in correct format, make false & register error
        if ping_host2 == '':
            # blank entry ignore
            ping_host2 = False
        elif not re.match(r"\S+\.\S+", ping_host2):            
            logger.log_error("Error with ping host format: \'" + str(ping_host2) + "\'")
            logger.log_error("Ping host must be IP address of resolvable hostname")
            ping_host2 = False            
        
    if ping_host2:
        
        # check for def.gw keyword
        if  ping_host2 == "def.gw":
            ping_host2 = adapter.get_def_gw()
    
        # run 2nd ping test
        ping_obj2 = Pinger(platform = platform, debug = DEBUG)
        
        # initial ping to clear out arp
        ping_obj2.ping_host(ping_host2, 1)
        
        # ping test
        ping_result2 = ping_obj2.ping_host(ping_host2, 10)
        
        # ping2 results
        if ping_result2:
            results_dict['ping_host2'] =  ping_result2['host']
            results_dict['pkts_tx2'] =  ping_result2['pkts_tx']
            results_dict['pkts_rx2'] =  ping_result2['pkts_rx']
            results_dict['percent_loss2'] =  ping_result2['pkt_loss']
            results_dict['test)time2'] =  ping_result2['test_time']
            results_dict['rtt_min2'] =  ping_result2['rtt_min']
            results_dict['rtt_avg2'] =  ping_result2['rtt_avg']
            results_dict['rtt_max2'] =  ping_result2['rtt_max']
            results_dict['rtt_mdev2'] =  ping_result2['rtt_mdev']
        
        if DEBUG:
            print("Main: Ping2 test results:")
            print(ping_result2)

    # check if we have ping 3 test defined & run test if exists
    results_dict['ping_host3'] =  "NA"
    results_dict['pkts_tx3'] =  "NA"
    results_dict['pkts_rx3'] =  "NA"
    results_dict['percent_loss3'] =  "NA"
    results_dict['test)time3'] =  "NA"
    results_dict['rtt_min3'] =  "NA"
    results_dict['rtt_avg3'] =  "NA"
    results_dict['rtt_max3'] =  "NA"
    results_dict['rtt_mdev3'] =  "NA"
            
    ping_host3 = False
    if 'ping_3' in config_vars.keys():
        ping_host3 = config_vars['ping_3']
        
        # Clean up the content to get rid of whitespace
        ping_host3 = ping_host3.strip()
        
        # if not in correct format, make false & register error
        if ping_host3 == '':
            # blank entry ignore
            ping_host1 = False
        elif not re.match(r"\S+\.\S+", ping_host3):            
            logger.log_error("Error with ping host format: \'" + str(ping_host3) + "\'")
            logger.log_error("Ping host must be IP address of resolvable hostname")
            ping_host3 = False            
        
    if ping_host3:
        
        # check for def.gw keyword
        if  ping_host3 == "def.gw":
            ping_host3 = adapter.get_def_gw()
    
        # run 3rd ping test
        ping_obj3 = Pinger(platform = platform, debug = DEBUG)
        
        # initial ping to clear out arp
        ping_obj3.ping_host(ping_host3, 1)
        
        # ping test
        ping_result3 = ping_obj3.ping_host(ping_host3, 10)
        
        # ping3 results
        if ping_result3:
            results_dict['ping_host3'] =  ping_result3['host']
            results_dict['pkts_tx3'] =  ping_result3['pkts_tx']
            results_dict['pkts_rx3'] =  ping_result3['pkts_rx']
            results_dict['percent_loss3'] =  ping_result3['pkt_loss']
            results_dict['test)time3'] =  ping_result3['test_time']
            results_dict['rtt_min3'] =  ping_result3['rtt_min']
            results_dict['rtt_avg3'] =  ping_result3['rtt_avg']
            results_dict['rtt_max3'] =  ping_result3['rtt_max']
            results_dict['rtt_mdev3'] =  ping_result3['rtt_mdev']
        
        if DEBUG:
            print("Main: Ping3 test results:")
            print(ping_result3)
   
    sheet_row_data = [
        current_timestamp,
        results_dict['ping_time'],
        results_dict['download_rate'],
        results_dict['upload_rate'],
        results_dict['ssid'], 
        results_dict['bssid'],
        results_dict['freq'],
        results_dict['bit_rate'],
        results_dict['signal_level'],
        results_dict['ip_addr'],
        location,
        results_dict['server_name'],
        results_dict['ping_host1'],
        results_dict['pkts_tx1'],
        results_dict['percent_loss1'],
        results_dict['rtt_avg1'],
        results_dict['ping_host2'],
        results_dict['pkts_tx2'],
        results_dict['percent_loss2'],
        results_dict['rtt_avg2'],
        results_dict['ping_host3'],
        results_dict['pkts_tx3'],
        results_dict['percent_loss3'],
        results_dict['rtt_avg3']
    ]
    
    if DEBUG:
        print(sheet_row_data)
    
    # check if we need to create new sheet (new day?)
    sheet = False
    
    if gsheet:
        gsheet.create_worksheet_if_needed()
    
        # open the Google sheet and try to post results (cache locally if fails)
        todays_worksheet_name = gsheet.get_todays_worksheet_name()
        sheet = gsheet.open_gspread_worksheet(todays_worksheet_name)
    
    if sheet != False:
    
        # Let's check to see if we have any old cached results to push before we
        # post latest result to gspread

        push_cached_results(sheet, cache_file, db_file, logger, DEBUG)
    
        # post latest result to worksheet    
        append_result = sheet.append_row(sheet_row_data)

        if DEBUG:
            print("Result of spreadsheet append operation: " + str(append_result))
            print("Append operation result type: " + str(type(append_result)))
        
        if type(append_result) is not dict:
            logger.log_error("Append operation on sheet appears to have failed (should be dict: " + str(append_result))
            # something went wrong with append operation - cache locally
            dump_result_local_db(sheet_row_data, db_file, logger, DEBUG)
            
    else:
        # something went wrong with sheet opening operation - cache result locally for next time
        dump_result_local_db(sheet_row_data, db_file, logger, DEBUG)
    
    db_conn = sqlite3.connect(db_file)
    
    # Tidy up old data to keep db reasonable size
    db_conn.execute("delete from speedtest_data where datetime(timestamp, 'unixepoch') <= date('now', '-7 days')")
    db_conn.commit()
    
    cleartext_date = datetime.datetime.now()
    
    # add data to db
    db_conn.execute("insert into speedtest_data (timestamp, cleartext_date, ping_time, download_rate, upload_rate, ssid, bssid, freq, bit_rate, signal_level, ip_address) values (?,?,?,?,?,?,?,?,?,?,?)", (
        int(time.time()), 
        cleartext_date,
        results_dict['ping_time'],
        results_dict['download_rate'],
        results_dict['upload_rate'],
        results_dict['ssid'], 
        results_dict['bssid'],
        results_dict['freq'],
        results_dict['bit_rate'],
        results_dict['signal_level'],
        results_dict['ip_addr']))
        
    db_conn.commit()
    
    # Tidy up old logs
    db_conn.execute("delete from error_logs where datetime(timestamp, 'unixepoch') <= date('now', '-2 days')")
    db_conn.commit()
        
    # close db connection
    db_conn.close()

    # send error messages to console
    update_console(gsheet, gsheet.get_worksheet_titles(), db_file, logger, DEBUG)
    
###############################################################################
# End main
###############################################################################
    
if __name__ == "__main__":
    main()
