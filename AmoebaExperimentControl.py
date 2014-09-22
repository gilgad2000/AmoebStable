import xml.etree.ElementTree as ET
from Amoeba import *
import thread
import time
import serial
import AmoebaSerialComms
import AmoebaBusString
from random import shuffle
import PySide.QtCore as QTCore

AMOEBA_EXPERIMENT_CONTROL=0
AMOEBA_ANALYSE_STRING=0

class AmoebaExperimentControl(QTCore.QThread):

    updateUI = QTCore.Signal(int)

    def __init__(self, server, experiment, tabs):
        """
        This class handles the communication with the server.  Through a generic server interface.  (Only send and
        receive functions necessary for the server).
        :param server: The server
        :param experiment:
        """
        QTCore.QThread.__init__(self)
        if AMOEBA_EXPERIMENT_CONTROL:
            print "AmoebaExperimentControl.__init__"
        self.linkString = []
        self.checkString = []
        #  The check array contains all the addresses and channels that need checking.  At the start of each check cycle it is shuffled,
        #  since it appears that where an channel is in the check array effects it's check efficiency.
        self.checkArray = []
        self.server = server
        self.experiment = experiment
        self.tabs = tabs
        self.connectedLocally = False
        self.updateTimer = QTimer()
        self.localUpdateTimer = QTimer()
        self.updateUITimer = QTimer()
        #  Set the time to run for a second.
        self.updateTimer.setInterval(1000)
        #  Link the timer to the update method.
        self.updateTimer.timeout.connect(self.retrieveUpdateFromServer)
        #  Set the time to run for a second.
        self.localUpdateTimer.setInterval(100)
        self.updateTimer.setInterval(1000)
        #  Link the timer to the update method.
        self.localUpdateTimer.timeout.connect(self.startGetLocalReadingsThread)
        self.updateUITimer.timeout.connect(self.updateUI)
        #  Make sure it's off.
        self.updateUITimer.stop()
        self.updateTimer.stop()
        self.stringMeth = AmoebaBusString.AmoebaBusStringMethods()

    def run(self, *args, **kwargs):
        self.startExperiment()

    def startExperiment(self):
        """
        This function tells the server to start the experiment.
        :return: SUCCESS or ERROR strings.
        """
        if AMOEBA_EXPERIMENT_CONTROL:
            print "Start Experiment"
        if self.connectedLocally:
            self.startExperimentLocally()
            if AMOEBA_EXPERIMENT_CONTROL:
                print "Start Locally"
            reply = "starting"
        else:
            reply = self.startExperimentRemotely()
            if AMOEBA_EXPERIMENT_CONTROL:
                print "Start Remotely"
        if reply == "starting":
            return "SUCCESS"
        else:
            return "ERROR"

    def stopExperiment(self,local_mode):
        """
        This function tells the server to stop the experiment.
        :return: Nothing.
        """
        if local_mode:
            self.stopExperimentLocally()
        else:
            self.stopExperimentRemotely()

    def updateUI(self):
        """
        This method updates the user interface.
        """
        #self.tabs.update()
        self.tabs.run()

#####################    Local functions  ##############################

    def startExperimentLocally(self):
        """
        This function runs an experiment locally.
        """
        self.checkString = []
        self.checkArray = []
        able_to_run = True
        if AMOEBA_EXPERIMENT_CONTROL:
            print "Run Experiment Locally."
        for inst in self.experiment.instruments:
            for param in inst.parameters:
                chkstr = self.stringMeth.requestData(inst.address,param.number)
                if AMOEBA_EXPERIMENT_CONTROL:
                    print chkstr
                #Create the bus string to poll for data.
                self.checkString.append(chkstr)
            for j in inst.parameters:
                self.checkArray.append([int(inst.address),int(j.number)])
            if AMOEBA_EXPERIMENT_CONTROL:
                print self.checkArray
        # Program Bus
        if able_to_run == True:
            #Program module links.
            for lnk in self.experiment.links:
                #Test to see if instrument is connected to the bus,
                if AMOEBA_EXPERIMENT_CONTROL:
                    print "Checking for instrument links:\nController: " + str(lnk.controlleraddress) + " Sensor: " + str(lnk.sensoraddress)
                if int(lnk.inversly_proportional)==0:
                    inverse = False
                else:
                    inverse = True
                #  Program the controllers.
                self.localServer.program(lnk.controlleraddress,lnk.channel,lnk.sensoraddress,
                                         lnk.sensorchannel,lnk.value,inverse,lnk.boundaries)
            # Program control modules.
            for ctrl in self.experiment.control:
                self.localServer.control(ctrl.address,ctrl.channel,ctrl.value)
            if able_to_run == True:
                # Start experiment
                self.localServer.start()
                self.localUpdateTimer.start()
                self.updateUITimer.start()
                if AMOEBA_EXPERIMENT_CONTROL:
                    print "Experiment starting."

    def stopExperimentLocally(self):
        """
        This function stops an experiment which is being run locally.
        """
        if AMOEBA_EXPERIMENT_CONTROL:
            print "Stop Experiment Locally."
        # Stop Experiment
        self.localUpdateTimer.stop()
        self.localServer.stop()
        self.updateUITimer.stop()
        self.localServer.clearAll()
        self.checkArray = []

    def startGetLocalReadingsThread(self):
        """
        This thread starts the get Local Readings thread.
        """
        #thread.start_new_thread(self.getLocalReadings)
        self.getLocalReadings()

    def getLocalReadings(self):
        #  For each instrument
        #Update UI
        self.analyseStringFromBus()
        shuffle(self.checkArray)
        for i in self.checkArray:
            #  i[0]  = address   i[1] = channel
            self.localServer.requestData(int(i[0]),int(i[1]))
            time.sleep(1/300)

    def analyseStringFromBus(self):
        """
        This method analyses the strings received from the bus.
        """
        for i in self.localServer.stringFromBus:
            #  i[0] = received string,  i[1] = time
            address, chan, reading = self.localServer.stringMaker.AnalyseDataFromServer(i[0],i[1])
            #  -1 is returned on al the results if there is an error in analysing the string returned from the server.
            if AMOEBA_ANALYSE_STRING:
                print "AmoebaExperimentControl.analyseStringFromBus"
                print "Address = " + str(address) + " Channel = " + str(chan) + " Reading = " + str(reading) + " "
            if address != chan != reading != -1:
                for j in self.experiment.instruments:
                    if j.address == address:
                        ##  Continue form here, add readings to instrument, the update graphs.
                        j.add_reading(chan,reading)
            self.localServer.stringFromBus = []

    def connectToLocalServer(self,port):
        """
        This method connects to a local server.
        """
        rec = ""
        i = 0
        success = True
        msgBox = QMessageBox()
        try:
            self.localServer = AmoebaSerialComms.AmoebaSerialComms(port)
            self.localServer.connect()
        except:
            success = False
            if AMOEBA_EXPERIMENT_CONTROL:
                print "Wrong serial port, try checking the connection."
            msgBox.setText("Error:  Did not connect to AMOEBA system.")
        msgBox.exec_()
        print "Returning: " + str(success)
        if success == True:
            self.connectedLocally = True
        return success

    def disconnectFromLocalServer(self):
        """
        This method disconnects from
        """
        try:
            self.localServer.disconnect()
            self.connectedLocally = False
        except:
            print "Failed to disconnect."


#######################   Remote functions.  ########################################

    def startExperimentRemotely(self):
            #  Clear the data from the past experiments.
            self.experiment.clear_data()
            #  Update the UI Accordingly
            self.tabs.clear()
            #  Send start experiment signal.
            reply = self.server.send("experiment.start")
            #  Start timer which sends the listen signal.
            self.updateTimer.start()

    def stopExperimentRemotely(self):
        if AMOEBA_EXPERIMENT_CONTROL:
            print "Stop Experiment"
        #Send Stop experiment signal.
        self.updateTimer.stop()
        #  Add a small delay incase data is currently being returned.
        time.sleep(0.1)
        self.server.send("experiment.stop")


    def sendExperimentToServer(self):
        """
        This function sends the experiment to the server.
        """
        sendString = ""
        if AMOEBA_EXPERIMENT_CONTROL:
            print "Send Experiment."
        try:
            if AMOEBA_EXPERIMENT_CONTROL:
                print "Try 1"
            treeString = ET.tostring(self.experiment.tree.getroot())
        except:
            if AMOEBA_EXPERIMENT_CONTROL:
                print "Try 2"
            tmp = ET.ElementTree(self.experiment.tree.getroot())
            treeString = ET.tostring(tmp)
        if AMOEBA_EXPERIMENT_CONTROL:
            print treeString
        sendString = "experiment.receive||" + treeString
        self.server.send(sendString)

    def retrieveDataFromServer(self):
        """
        This function retrieves the experiment the server is currently running.
        :return:  Either XML string of the experiment or ERROR string.
        """
        if AMOEBA_EXPERIMENT_CONTROL:
            print "Retrieve data from server."
        experiment = self.server.send("experiment.requestExperiment")
        if experiment == "ERROR":
            print "No Experiment Loaded."
            return 0
        #Update experiment.
        print experiment
        self.experiment.read_in_from_XML_string(experiment)
        #Update UIs.
        self.tabs.clear_gui()
        self.tabs.make_gui(self.experiment)
        self.tabs.update()

    def retrieveUpdateFromServer(self):
        """
        This function will retrieve the readings since they were last received.
        """
        if AMOEBA_EXPERIMENT_CONTROL:
            print "Request Update."
        try:
            #self.server.retrieveUpdate()
            update = self.server.send("experiment.requestUpdate")
            print update
            #  Add the new readings to the experiment.
            self.experiment.add_readings_from_XMLString(update)
            #  Update UI.
            self.tabs.update()
        except:
            print "Socket timed out."