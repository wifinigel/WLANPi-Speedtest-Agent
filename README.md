# WLANPi-Speedtest-Agent

A very simple Speedtest Agent for the WLANPi - this project is under initial development and will change continually for the foreseeable future.

## Description

This software is uses Python to run some simple scripts to create a very low budget speed-test solution. It runs speed tests to public speedtest servers. The results are then stored in a Google spreadsheet for later review - a new worksheet is created for each day.


## Running This Software

There are a number of steps to get this running on your WLANPi:

 1. Configure networking on your WLANPi (wlan0 and eth0)
 2. Create a Google spreadsheet
 3. Create some JSON service account credentials (https://www.twilio.com/blog/2017/02/an-easy-way-to-read-and-write-to-a-google-spreadsheet-in-python.html)
 4. Add some python modules to your WLANPi:
    
    sudo apt-get update\
    sudo apt-get install git\
    sudo apt-get install python-pip\
    sudo pip install pyspeedtest gspread oauth2client ConfigParser\
    sudo pip install --upgrade oauth2client\
    sudo apt-get install sqlite3\
 5. Create the required environment on your WLANPi:
    cd ~\
    mkdir python\
    cd ./python\\
    mkdir speedtest
    cd ./speedtest\
    Configure config.ini for the env\
 6. Copy the files from ths project in to ~/python/speedtest
 7. Copy the Google sheet JSON credential file in to ~/python/speedtest
 8. chmod a+x ~/python/speedtest/speedtest.py
 7. configure crontab to run the script every 5 mins:
    */5 * * * * /usr/bin/python /home/wlanpi/python/speedtest/speedtest.py >> /home/wlanpi/python/speedtest/speedtest.log\

(Sorry, I will document this properly one day when things are more finalized)
    



