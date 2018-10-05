class SimpleLogger(object):

    '''
    A class to perform very simple logging to an Sqlite DB
    '''
    
    def __init__(self, db_file, debug=False):
    

        self.db_file = db_file
        self.debug = debug
 

    def log_error(self, err_msg):

        '''
        This function puts an error message in to the local database to indicate 
        something has gone wrong
        '''

        import sqlite3
        import datetime
        import time
        
        if self.debug:
                print("Error : " + err_msg)

        db_conn = sqlite3.connect(self.db_file)
        
        cleartext_date = datetime.datetime.now()
        db_conn.execute("insert into error_logs (timestamp, cleartext_date, error_msg) values (?,?,?)", (int(time.time()), cleartext_date, err_msg))
        db_conn.commit()
            
        # close db connection
        db_conn.close()