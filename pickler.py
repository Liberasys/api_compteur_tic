# Droits d'auteur : HUSSON CONSULTING SAS - Liberasys
# 2016/09
# Donne en licence selon les termes de l EUPL V.1.1 (EUPL : European Union Public Licence)
# Voir EUPL V1.1 ici : http://ec.europa.eu/idabc/eupl.html

import syslog
import threading
import time
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
    def __init__(self, file_path, delay):
        threading.Thread.__init__(self)
        self.setDaemon(True)
        self._my_data = None
        self._file = None
        self._delay = delay
        self.__cb_function = None
        self._running = False
        self._mutex_taken = False
        self.__make_sure_file_path_exists(file_path)
        try:
            self._file = open(file_path, "r+b")
        except IOError, e:
            print("Error opening output file whereas all precautions were taken : "  + f_path + " : " + str(e))
            syslog.syslog(syslog.LOG_CRIT, "Error opening output file : "  + f_path + " : " + str(e))
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
        del self._my_data

    def __make_sure_file_path_exists(self, f_path):
        """ Makes sure a file exists, creates directories and file if not"""
        filedscr = None

        # tries to create directories
        try:
            os.makedirs(os.path.dirname(f_path))
        except OSError as exception:
            if exception.errno != errno.EEXIST:
                print("Problem while creating directories")
                syslog.syslog(syslog.LOG_CRIT, "Problem while creating directories")
                print(exception.errno)
                raise

        # tries to create the file if it does not exists
        if not os.path.exists(f_path):
            try:
                filedscr = open(f_path, 'w')
                filedscr.close()
            except e as exception:
                print("Error while creating output file : " + f_path + " : " + str(e))
                syslog.syslog(syslog.LOG_CRIT, "Error while creating output file : " + f_path + " : " + str(e))

        # tries to open the file
        try:
            filedscr = open(f_path, 'r+b')
        except IOError, e:
            print("Error opening output file : " + f_path + " : " + str(e))
            syslog.syslog(syslog.LOG_CRIT, "Error opening output file : " + f_path + " : " + str(e))
        else:
            filedscr.close()

    def set_callback(self, fonction):
        if fonction != None:
            self.__cb_function = fonction

    def get_data(self):
        """ Get the object data """
        if  self.__get_mutex():
            return copy.deepcopy(self._my_data)
            self.__release_mutex()

    def set_data(self, dataset):
        """ Set the data to pickle """
        if  self.__get_mutex():
            self._my_data = copy.deepcopy(dataset)
            self.__release_mutex()

    def pickles_data(self):
        """ Pickels data to file """
        if self._my_data != None:
            self._file.seek(0)
            if self.__get_mutex():
                pickle.dump(self._my_data, self._file)
                self.__release_mutex()
            self._file.seek(0)

    def get_and_pickles_data(self):
        """ Get dataset from callback and piclkes dataset """
        callback_data = None
        if self.__cb_function != None:
            callback_data = self.__cb_function()
            self.set_data(callback_data)
            self.pickles_data()

    def run(self):
        """ main thread that pickles a data set gottent from the callback to a file """
        while self._running == True:
            self.get_and_pickles_data()
            time.sleep(self._delay)
        del callback_data

    def stop(self):
        self._running = False

    def close(self):
        self._running = False
        self.__del__()
        if self._file != None:
            self._file.close()

    def __get_mutex(self):
        """ Tries to get the mutex on the data """
        mutex_timeout = 5
        start_epoch = time.time()
        got_mutex = False
        while ((time.time() - start_epoch) < mutex_timeout) and \
              (got_mutex == False):
            if self._mutex_taken == True:
                print("Pickler mutex busy...")
                syslog.syslog(syslog.LOG_WARNING, "Pickler mutex busy...")
            else:
                got_mutex = True
                self._mutex_taken = False
                #print("Got pickler mutex...")
            time.sleep(0.2)
        return got_mutex

    def __release_mutex(self):
        """ Releases the mutex on the data """
        self._mutex_taken = False
        #print("Pickler Mutex released")



if __name__ == "__main__":
    countdown=0

    def cb_gen_dataset():
        favorite_color = { "lion": "yellow", "kitty": "red", "time": (time.time(), "epoch") }
        return favorite_color

    pickeler = PicklesMyData("/tmp/plop/plop.pkl", 2)
    pickeler.set_callback(cb_gen_dataset)

    print(pickeler.get_data())
    time.sleep(0.2)
    print(pickeler.get_data())
    pickeler.start()
    time.sleep(0.2)
    print(pickeler.get_data())
    time.sleep(0.2)
    print(pickeler.get_data())
    pickeler.set_data({ "forced data set" : "TEST"})
    print(pickeler.get_data())
    time.sleep(0.2)
    print(pickeler.get_data())
    time.sleep(0.2)
    print(pickeler.get_data())
    time.sleep(0.2)
    print(pickeler.get_data())
    time.sleep(0.2)
    print(pickeler.get_data())
    time.sleep(0.2)
    print(pickeler.get_data())
    time.sleep(0.2)
    print(pickeler.get_data())
    time.sleep(0.2)
    print(pickeler.get_data())
    time.sleep(0.2)
    print(pickeler.get_data())
    time.sleep(0.2)
    print(pickeler.get_data())
    time.sleep(0.2)
    print(pickeler.get_data())
    time.sleep(0.2)
    print(pickeler.get_data())
    time.sleep(0.2)
    pickeler.stop()
