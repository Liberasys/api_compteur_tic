# Droits d'auteur : HUSSON CONSULTING SAS - Liberasys
# 2016/09
# Donne en licence selon les termes de l EUPL V.1.1 (EUPL : European Union Public Licence)
# Voir EUPL V1.1 ici : http://ec.europa.eu/idabc/eupl.html

import syslog
import threading
import time
import syslog
import os
import errno
import pickle
import copy

########################################################################
class PicklesMyData(threading.Thread):
    """
    Data structure cyclic backup to file class
    Args :
        - file path (for reading and writing data structure)
        - delay between two writes
        - callback for getting data structure
    Returns :
        - if file is read returns a data structure, else returns None
    """
    def __init__(self, file_path, delay, cb_function):
        threading.Thread.__init__(self)
        self.setDaemon(True)
        
        self._my_data = None
        self._file = None
        self._delay = delay
        self.__cb_function = cb_function
        self._running = False

        self.__make_sure_file_path_exists(file_path)
        
        try:
            self._file = open(file_path, "r+b")
        except IOError, e:
            print("Error opening output file : " + str(e))
            syslog.syslog(syslog.LOG_CRIT, "Error opening output file : " + str(e))
        else:
            self._file.seek(0)
        
        try:
            self._my_data = pickle.load(self._file)
        except EOFError:
            print("Initial pickle file empty : " + file_path)
            syslog.syslog(syslog.LOG_CRIT, "Initial pickle file empty : " + file_path)
            self._my_data = None
        else:
            self._file.seek(0)

        self._running = True

    def __del__(self):
        self._running = False
        if self._file != None:
            self._file.close()
        del self._my_data

    def __make_sure_file_path_exists(self, f_path):
        """ Makes sure a file exists, creates directories and file if not"""
        filedscr = None
        
        # tries to create directories
        try:
            os.makedirs(os.path.dirname(f_path))
        except OSError as exception:
            if exception.errno != errno.EEXIST:
                raise

        # tries to create the file if it doesn not exists
        if not os.path.exists(f_path):
            open(f_path, 'w').close() 

        # tries to open the file
        try:
            filedscr = open('f_path', 'r+b')
        except IOError, e:
            print("Error opening output file : " + str(e))
            syslog.syslog(syslog.LOG_CRIT, "Error opening output file : " + str(e))
        else:
            filedscr.close()
    
    def get_data(self):
        """ Get the object data """
        # WARNING : subject to race conditions
        # TODO : implement mutex
        return copy.deepcopy(self._my_data)
  
    def run(self):
        while self._running == True:
            print("loop")
            self._my_data = self.__cb_function()
            if self._my_data != None:
                self._file.seek(0)
                pickle.dump(self._my_data, self._file)
                self._file.seek(0)
            time.sleep(self._delay)

    def stop(self):
        self._running = False

if __name__ == "__main__":
    countdown=0
    
    def gen_donnee():
        favorite_color = { "lion": "yellow", "kitty": "red", "time": (time.time(), "epoch") }
        return favorite_color
    
    pickeler = PicklesMyData("/tmp/plop/plop.pkl", 2, gen_donnee)

    print(pickeler.get_data())
    time.sleep(0.2)
    print(pickeler.get_data())
    pickeler.start()
    time.sleep(0.2)
    print(pickeler.get_data())
    time.sleep(2)
    print(pickeler.get_data())
    



