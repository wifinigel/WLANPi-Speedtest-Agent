'''
A very simple logging class
'''
from __future__ import print_function

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
        from sys import stderr

        # Ensure we always have a string to prevent silent type failures
        err_msg = str(err_msg)

        if self.debug:
            print("Error : " + err_msg)

        try:
            db_conn = sqlite3.connect(self.db_file)
        except Exception as exception_msg:
            stderr.write("Error connecting to DB: " + str(exception_msg))
            return None

        cleartext_date = datetime.datetime.now()
        try:
            db_conn.execute("insert into error_logs (timestamp, \
            cleartext_date, error_msg) values (?,?,?)", (int(time.time()), \
            cleartext_date, err_msg))
        except Exception as exception_msg:
            stderr.write("Error executing insert to DB: " + str(exception_msg))
            return None

        try:
            db_conn.commit()
        except Exception as exception_msg:
            stderr.write("Error executing commit to DB: " + str(exception_msg))
            return None

        # close db connection
        try:
            db_conn.close()
        except Exception as exception_msg:
            stderr.write("Error closing DB: " + str(exception_msg))
            return None

        return None
