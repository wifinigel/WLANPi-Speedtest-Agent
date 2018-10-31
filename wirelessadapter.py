
class WirelessAdapter(object):

    '''
    A class to monitor and manipulate the wireless adapter for the WLANPerfAgent
    '''

    def __init__(self, wlan_if_name, platform="rpi", debug=False):
    
        import subprocess
        
        self.wlan_if_name = wlan_if_name
        self.platform = platform
        self.debug = debug
        
        self.ssid = ''
        self.bssid = ''
        self.freq = ''
        self.bit_rate = ''
        self.signal_level = ''
        
        self.ip_addr = ''
        
        # Get wireless adapter info
        self.ifconfig_info = subprocess.check_output("/sbin/ifconfig " + self.wlan_if_name + " 2>&1", shell=True)

        if self.debug:
            print("Interface config info: " + self.ifconfig_info)

        self.iwconfig_info = subprocess.check_output("/sbin/iwconfig " + self.wlan_if_name + " 2>&1", shell=True)
        
        if self.debug:
            print(self.iwconfig_info)
        
        # fire off methods to pre-load all adapter attributes
        self.get_wireless_info()
        self.get_adapter_ip()

    def get_wireless_info(self):

        '''
        This function will look for various pieces of information from the 
        wireless adapter which will be bundled with the speedtest results.
        
        It is a wrapper around the "iwconfig wlanx", so will no doubt break at
        some stage. 
        
        We cannot assume all of the parameters below are available (sometimes
        they are missing for some reason until device is rebooted). Only
        provide info if they are available, otherwise replace with "NA"

        '''
        import re
        
        # Extract SSID
        ssid_re = re.search('ESSID\:\"(.*?)\"', self.iwconfig_info)
        if ssid_re is None:
            self.ssid = "NA"
        else:            
            self.ssid = ssid_re.group(1)
        
        if self.debug:
            print(self.ssid)
        
        # Extract BSSID (Note that if WLAN adapter not associated, "Access Point: Not-Associated")
        ssid_re = re.search('Access Point[\=|\:] (..\:..\:..\:..\:..\:..)', self.iwconfig_info)
        if ssid_re is None:
            self.bssid = "NA"
        else:            
            self.bssid = ssid_re.group(1)
        
        if self.debug:
            print(self.bssid)
        
        # Extract Frequency
        ssid_re = re.search('Frequency[\:|\=](\d+\.\d+) ', self.iwconfig_info)
        if ssid_re is None:
            self.freq = "NA"
        else:        
            self.freq = ssid_re.group(1)
        
        if self.debug:
            print(self.freq)
        
        # Extract Bit Rate (e.g. Bit Rate=144.4 Mb/s)
        ssid_re = re.search('Bit Rate[\=|\:]([\d|\.]+) ', self.iwconfig_info)
        if ssid_re is None:
            self.bit_rate = "NA"
        else:        
            self.bit_rate = ssid_re.group(1)
        
        if self.debug:
            print(self.bit_rate)
        
        
        # Extract Signal Level
        ssid_re = re.search('Signal level[\=|\:](.+?) ', self.iwconfig_info)
        if ssid_re is None:
            self.signal_level = "NA"
        else:
            self.signal_level = ssid_re.group(1)
            
        if self.debug:
            print(self.signal_level)
        
        return [self.ssid, self.bssid, self.freq, self.bit_rate, self.signal_level]

    def get_adapter_ip(self):
    
        '''
        This method parses the output of the ifconfig command to figure out the
        IP address of the wireless adapter.
        
        As this is a wrapper around a CLI command, it is likely to break at
        some stage
        '''
        
        import re
        
        # Extract IP address info (e.g. inet 10.255.250.157)
        ip_re = re.search('inet .*?(\d+\.\d+\.\d+\.\d+)', self.ifconfig_info)
        if ip_re is None:
            self.ip_addr = "NA"
        else:            
            self.ip_addr = ip_re.group(1)
        
        # Check to see if IP address is APIPA (169.254.x.x)
        apipa_re = re.search('169\.254', self.ip_addr)
        if not apipa_re is None:
            self.ip_addr = "NA"
        
        if self.debug:
            print(self.ip_addr)
        
        return self.ip_addr

    def bounce_wlan_interface(self):
    
        '''
        If we run in to connectivity issues, we may like to try bouncing the
        wireless interface to see if we can recover the connection.
        
        Note: wlanpi must be added to sudoers group using visudo command on RPI
        '''
        import subprocess
        
        if self.debug:
            print("Bouncing interface (platform type = " + self.platform + ")")
        
        if self.platform == 'wlanpi':
            subprocess.call("nmcli radio wifi off", shell=True)
            subprocess.call("nmcli radio wifi on", shell=True)

        elif self.platform == 'rpi':
            subprocess.call("sudo ifdown " + self.wlan_if_name, shell=True)
            subprocess.call("sudo ifup " + self.wlan_if_name, shell=True)


    def get_ssid(self):
        return self.ssid
    
    def get_bssid(self):
        return self.bssid
    
    def get_freq(self):
        return self.freq
    
    def get_bit_rate(self):
        return self.bit_rate
    
    def get_signal_level(self):
        return self.signal_level

    def get_ipaddr(self):
        return self.ip_addr
