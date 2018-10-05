
class Gsheet(object):

    '''
    A class to read and manipulate a Google sheet for the WLANPerfAgent
    '''

    def __init__(self, json_keyfile, spreadsheet_name, logger_obj, debug=False):
    
        import subprocess
        import time
        
        self.json_keyfile = json_keyfile
        self.spreadsheet_name = spreadsheet_name
        self.debug = debug
        self.logger_obj = logger_obj
        
        # open the spreadsheet and return object
        self.spreadsheet = self.open_gspread_spreadsheet(self.spreadsheet_name, self.json_keyfile)
        
        # create the worksheet title list
        self._worksheet_list = self.spreadsheet.worksheets()
        
        self.worksheet_titles = []
        for sheet_instance in self._worksheet_list:
            self.worksheet_titles.append(sheet_instance.title)
        
        self.todays_worksheet_name = time.strftime("%d-%b-%Y")

        
    def open_gspread_spreadsheet(self, spreadsheet_name, json_keyfile):
    
        import gspread
        from oauth2client.service_account import ServiceAccountCredentials

        try:
            scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
            credentials = ServiceAccountCredentials.from_json_keyfile_name(json_keyfile, scope)
            client = gspread.authorize(credentials)
            spreadsheet = client.open(spreadsheet_name)
            return spreadsheet
        except Exception as ex:
            self.logger_obj.log_error("Error opening Google spreadsheet: " + str(ex))
            return False

    def open_gspread_worksheet(self, worksheet_name):

        try:
            spreadsheet = self.spreadsheet
            worksheet = spreadsheet.worksheet(worksheet_name)
            return worksheet
        except Exception as ex:
            self.logger_obj.log_error("Error opening Google worksheet: " + str(ex))
            return False

    def worksheet_exists(self, worksheet_name):

        if worksheet_name not in self.worksheet_titles:
            return False
        else:
            return True
 
    def create_worksheet_if_needed(self):
    
        import time

        # create new sheet is todays worksheet no present
        if not self.worksheet_exists(self.todays_worksheet_name):
        
            try:
                worksheet = self.spreadsheet.add_worksheet(self.todays_worksheet_name, 600, 26)
            except Exception as ex:
                self.logger_obj.log_error("Error adding new worksheet: " + str(ex))
                return False
            
            col_headers = ["timestamp","ping_time (ms)","download_rate (mbps)","upload_rate (mbps)", "ssid","bssid","freq","bit_rate","signal_level","ip_address","speedtest_server","location"]
            
            try:
                append_result = worksheet.append_row(col_headers)
            except Exception as ex:
                self.logger_obj.log_error("Error adding col headers to new sheet: " + str(ex))

            
            if self.debug:
                print("Result of spreadsheet col headers append operation: " + str(append_result))
                print("Col headers append operation result type: " + str(type(append_result)))
                
            if type(append_result) is not dict:
                self.logger_obj.log_error("col headers append operation on sheet appears to have failed (should be dict: " + str(append_result))
            
            return True
        else:
            return False  

    def get_todays_worksheet_name(self):
        return self.todays_worksheet_name
    
    def get_worksheet_titles(self):
        return self.worksheet_titles
        

