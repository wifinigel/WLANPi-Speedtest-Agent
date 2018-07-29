#!/usr/bin/python
# -*- coding: latin-1 -*-

'''

To Do:
    1. *** Done *** Detect if wireless connection up before start test
    2. *** Done *** Create db table for error logs
    3. *** Done *** Check we have IP address before test
    5. *** Done *** Clear old logs/data after test (keep only last 7 days?)
    6. Use different SSID profiles ?
    7. Would be nice to find best server if possible
    8. *** Done *** get_wireless_info needs to fail when info not available (as is an error condition)

'''
 
from __future__ import print_function
import time
import datetime
import sqlite3
import subprocess
import pyspeedtest
import os
import re
import sys
import requests
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import ConfigParser

DEBUG = 0

# Read in config file
config = ConfigParser.SafeConfigParser()
config_file = os.path.dirname(os.path.realpath(__file__)) + "/config.ini"
config.read(config_file)

# db file name
DB_FILE = config.get('General', 'db_file')

# Speedtest server
server_name =  config.get('General', 'server_name')


# Google sheet config parameters
spreadsheet_name = "Speedtester-DB"
worksheet_name = "Sheet1"
todays_worksheet_name = time.strftime("%d-%b-%Y")
oldest_sheet = 5


###############################################################################
def open_gspread_spreadsheet(spreadsheet_name):

    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        credentials = ServiceAccountCredentials.from_json_keyfile_name(config.get('General', 'json_keyfile'), scope)
        client = gspread.authorize(credentials)
        spreadsheet = client.open(spreadsheet_name)
        return spreadsheet
    except Exception as ex:
        log_error("Error opening Google spreadsheet: " + str(ex))
        return False

def open_gspread_worksheet(spreadsheet_name, worksheet_name):

    try:
        spreadsheet = open_gspread_spreadsheet(spreadsheet_name)
        worksheet = spreadsheet.worksheet(worksheet_name)
        return worksheet
    except Exception as ex:
        log_error("Error opening Google worksheet: " + str(ex))
        return False

def create_worksheet_if_needed(spreadsheet):

    global spreadsheet_name

    todays_worksheet_name = time.strftime("%d-%b-%Y")
    
    # have a look to see if the sheet already exists
    spreadsheet = open_gspread_spreadsheet(spreadsheet_name)
    
    # get a list of the worksheet names
    worksheet_list = spreadsheet.worksheets()
    
    # 
    worksheet_titles = []
    for sheet_instance in worksheet_list:

        worksheet_titles.append(sheet_instance.title)
    
    # create new sheet is todays worksheet no present
    if todays_worksheet_name not in worksheet_titles:
    
        try:
            worksheet = spreadsheet.add_worksheet(todays_worksheet_name, 600, 26)
        except Exception as ex:
            log_error("Error adding new worksheet: " + str(ex))
            return False
        
        col_headers = ["timestamp","ping_time (ms)","download_rate (mbps)","upload_rate (mbps)", "ssid","bssid","freq","bit_rate","signal_level","ip_address","speedtest_server"]
        
        try:
            append_result = worksheet.append_row(col_headers)
        except Exception as ex:
            log_error("Error adding col headers to new sheet: " + str(ex))

        
        if DEBUG:
            print("Result of spreadsheet col headers append operation: " + str(append_result))
            print("Col headers append operation result type: " + str(type(append_result)))
            
        if type(append_result) is not dict:
            log_error("col headers append operation on sheet appears to have failed (should be dict: " + str(append_result))
        
        return True
    else:
        return False
    

def lock_db(DB_FILE):

    '''
    This function creates a lock file that can be used to indicate that the db
    is in uses and that other processes should not update it
    '''

    now = str(time.time())
    fh = open(DB_FILE + "lock", "w+")
    fh.write(now)
    fh.close()

def unlock_db(DB_FILE):

    '''
    This function removes a lock file that can be used to indicate that the db
    is in uses and that other processes should not update it
    '''
    
    if os.path.exists(DB_FILE + "lock"):
        os.remove(DB_FILE + "lock")

def log_error(err_msg):

    '''
    This function puts an error message in to the local database to indicate 
    something has gone wrong
    '''

    if DEBUG:
            print("Error : " + err_msg)

    # create DB lock file        
    lock_db(DB_FILE)
    db_conn = sqlite3.connect(DB_FILE)
    
    cleartext_date = datetime.datetime.now()
    #db_conn.execute("insert into error_logs (timestamp, error_msg) values (?,?)", (int(time.time()), err_msg))
    db_conn.execute("insert into error_logs (timestamp, cleartext_date, error_msg) values (?,?,?)", (int(time.time()), cleartext_date, err_msg))
    db_conn.commit()
        
    # close db connection
    db_conn.close()
    unlock_db(DB_FILE)

   

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
        log_error("Problem with ping test: " + error.message)
        sys.exit()
        
        
    try:
        download_rate = '%.2f' % (st.download()/1024000)
        #download_rate = st.pretty_speed(st.download())
        if DEBUG:
            print("Download rate = " + str(download_rate) + " Mbps")
    except Exception as error:
        log_error("Download test error: " + error.message)
        sys.exit()
    
    try:
        upload_rate = '%.2f' % (st.upload()/1024000)
        if DEBUG:
            print("Upload rate = " + str(upload_rate) + " Mbps")
    except Exception as error:
        log_error("Upload test error: " + error.message)
        sys.exit()
        
    return [ping_time, download_rate, upload_rate]

def get_wireless_info():

    '''
    This function will look for various pieces of information from the 
    wireless adapter which will be bundles with the speedtest results.
    
    It is a wrapper around the "iwconfig wlan0", so will no doubt break at
    some stage. 
    
    '''
 
    # Get some wireless link info
    iwconfig_info = subprocess.check_output("/sbin/iwconfig wlan0 2>&1", shell=True)
    
    if DEBUG:
        print(iwconfig_info)
    
    ''' 
    We cannot assume all of the parameters below are available (sometimes
    they are missing for some reason until device is rebooted). Only
    provide info if they are available, otherwise replace with "NA"

    '''
    
    # Extract SSID
    ssid_re = re.search('ESSID\:\"(.*?)\"', iwconfig_info)
    if ssid_re is None:
        ssid = "NA"
    else:            
        ssid = ssid_re.group(1)
    
    if DEBUG:
        print(ssid)
    
    # Extract BSSID (Note that if WLAN adapter not associated, "Access Point: Not-Associated")
    ssid_re = re.search('Access Point\: (..\:..\:..\:..\:..\:..)', iwconfig_info)
    if ssid_re is None:
        bssid = "NA"
    else:            
        bssid = ssid_re.group(1)
    
    if DEBUG:
        print(bssid)
    
    # Extract Frequency
    ssid_re = re.search('Frequency\:(\d+\.\d+) ', iwconfig_info)
    if ssid_re is None:
        freq = "NA"
    else:        
        freq = ssid_re.group(1)
    
    if DEBUG:
        print(freq)
    
    # Extract Bit Rate (e.g. Bit Rate=144.4 Mb/s)
    ssid_re = re.search('Bit Rate\=([\d|\.]+) ', iwconfig_info)
    if ssid_re is None:
        bit_rate = "NA"
    else:        
        bit_rate = ssid_re.group(1)
    
    if DEBUG:
        print(bit_rate)
    
    
    # Extract Signal Level
    ssid_re = re.search('Signal level\=(.+?) ', iwconfig_info)
    if ssid_re is None:
        signal_level = "NA"
    else:
        signal_level = ssid_re.group(1)
        
    if DEBUG:
        print(signal_level)
    
    return [ssid, bssid, freq, bit_rate, signal_level]

def get_adapter_ip():
    
    # Get wireless adapter ip info
    ifconfig_info = subprocess.check_output("/sbin/ifconfig wlan0 2>&1", shell=True)
    
    if DEBUG:
        print(ifconfig_info)
    
    # Extract IP address info (e.g. inet 10.255.250.157)
    ip_re = re.search('inet (\d+\.\d+\.\d+\.\d+)', ifconfig_info)
    if ip_re is None:
        ip_addr = "NA"
    else:            
        ip_addr = ip_re.group(1)
    
    # Check to see if IP address is APIPA (169.254.x.x)
    apipa_re = re.search('169\.254', ip_addr)
    if not apipa_re is None:
        ip_addr = "NA"
    
    if DEBUG:
        print(ip_addr)
    
    return ip_addr

###############################################################################
# Main
###############################################################################
    
def main():

    # get wireless info
    wireless_info = get_wireless_info()
    if DEBUG:
        print(wireless_info)
    
    # if we have no network connection (i.e. no bssid), no point in proceeding...
    if wireless_info[1] == 'NA':
        log_error("Problem with wireless connection: not associated to network")
        log_error("Attempting to recover by bouncing wireless interface...")
        subprocess.call("nmcli radio wifi off", shell=True)
        subprocess.call("nmcli radio wifi on", shell=True)
        sys.exit()
    
    
    # get wireless adapter ip address info
    wireless_ip = get_adapter_ip()
    if DEBUG:
        print(wireless_ip)
    
    # if we have no IP address, no point in proceeding...
    if wireless_ip == 'NA':
        log_error("Problem with wireless connection: no valid IP address")
        log_error("Attempting to recover by bouncing wireless interface...")
        subprocess.call("nmcli radio wifi off", shell=True)
        subprocess.call("nmcli radio wifi on", shell=True)
        sys.exit()

    
    # run speedtest
    speedtest_results = speedtest(server_name)
    if DEBUG:
        print(speedtest_results)


    # Join the results lists
    r = speedtest_results + wireless_info + [wireless_ip]
    if DEBUG:
        print(r)
    
    # check if we ned to create new sheet (new day?)
    global todays_worksheet_name
    create_worksheet_if_needed(todays_worksheet_name)
    
    # Send to google sheet
    now = datetime.datetime.now()
    current_timestamp = now.strftime("%Y-%m-%d %H:%M")
    sheet_row_data = [current_timestamp] + r + [server_name]
    if DEBUG:
        print(sheet_row_data)
    '''
    Need to add check here to verify that row append actually works - tuple
    returned, but not sure of contents. Use this to track what has been 
    successfully added to sheet and maybe recover failed additions during later
    attempts (this could happen in stance of very slow responses and would be
    useful to know after the event)
    '''
    sheet = open_gspread_worksheet(spreadsheet_name, todays_worksheet_name)
    
    if sheet != False:
        append_result = sheet.append_row(sheet_row_data)
        if DEBUG:
            print("Result of spreadsheet append operation: " + str(append_result))
            print("Append operation result type: " + str(type(append_result)))
        
        if type(append_result) is not dict:
            log_error("Append operation on sheet appears to have failed (should be dict: " + str(append_result))
        
    
    # create DB lock file        
    lock_db(DB_FILE)
    db_conn = sqlite3.connect(DB_FILE)
    
    # Tidy up old data
    db_conn.execute("delete from speedtest_data where datetime(timestamp, 'unixepoch') <= date('now', '-7 days')")
    db_conn.commit()
     
    #db_conn.execute("insert into speedtest_data (timestamp, ping_time, download_rate, upload_rate, ssid, bssid, freq, bit_rate, signal_level, ip_address) values (?,?,?,?,?,?,?,?,?,?)", (int(time.time()), r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8]))
    
    cleartext_date = datetime.datetime.now()
    
    db_conn.execute("insert into speedtest_data (timestamp, cleartext_date, ping_time, download_rate, upload_rate, ssid, bssid, freq, bit_rate, signal_level, ip_address) values (?,?,?,?,?,?,?,?,?,?,?)", (int(time.time()), cleartext_date, r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8]))
    db_conn.commit()
    
    # Tidy up old logs
    db_conn.execute("delete from error_logs where datetime(timestamp, 'unixepoch') <= date('now', '-2 days')")
    db_conn.commit()
        
    # close db connection
    db_conn.close()
    unlock_db(DB_FILE)

    
if __name__ == "__main__":
    main()
