from Framework4.Control.Core.CObject import CObjectBase, Signal, Slot
from PyQt4 import QtCore
import os
import logging
import numpy
import gevent
import time
import pprint
import math
from XSDataCommon import XSDataString, XSDataImage, XSDataBoolean, \
        XSDataInteger, XSDataDouble, XSDataFile, XSDataStatus, \
        XSDataLength, XSDataWavelength, XSDataDouble, XSDataTime
from XSDataBioSaxsv1_0 import XSDataInputBioSaxsProcessOneFilev1_0, \
        XSDataResultBioSaxsProcessOneFilev1_0, XSDataBioSaxsSample, \
        XSDataBioSaxsExperimentSetup, XSDataInputBioSaxsSmartMergev1_0, XSDataResultBioSaxsSmartMergev1_0
from XSDataSAS import XSDataInputSolutionScattering

class Collect(CObjectBase):
    signals = [Signal("collectProcessingDone"),
               Signal("collectProcessingLog"),
               Signal("collectDone")]
    slots = [Slot("testCollect"),
             Slot("collect"),
             Slot("collectAbort"),
             Slot("setCheckBeam"),
             Slot("triggerEDNA")]

    def __init__(self, *args, **kwargs):
        CObjectBase.__init__(self, *args, **kwargs)
        self.__collectWithRobotProcedure = None
        self.xsdin = XSDataInputBioSaxsProcessOneFilev1_0(experimentSetup = XSDataBioSaxsExperimentSetup(), sample = XSDataBioSaxsSample())
        self.xsdin.rawImageSize = XSDataInteger(4093756)                     #Hardcoded for Pilatus
        self.xsdout = None
        self.lastPrefixRun = None
        self.ednaJob = None
        self.dat_filenames = {}
        self.pluginIntegrate = "EDPluginBioSaxsProcessOneFilev1_1"
        self.pluginMerge = "EDPluginBioSaxsSmartMergev1_3"
        self.pluginSAS = "EDPluginControlSolutionScatteringv0_3"

        self.storageTemperature = -374
        self.exposureTemperature = -374
        self.xsdAverage = None

        # get machdevice from config file
        # <data name="uri"  value="orion:10000/FE/D/29" />
        self.machDevName = str(self.config["/object/data[@name='uri']/@value"][0])

    def __getattr__(self, attr):
        if not attr.startswith("__"):
            try:
                return self.channels[attr]
            except KeyError:
                pass
        raise AttributeError, attr

    def init(self):
        self.collecting = False
        self.machineCurrent = 0.00
        self.nextRunNumber = -1
        self.deltaPilatus = 0.1
        try:
            self.channels["jobSuccess_edna1"].connect("update", self.processingDone)
            #self.channels["jobFailure_edna1"].connect("update", self.processingDone)
            self.commands["initPlugin_edna1"](self.pluginIntegrate)
            self.commands["initPlugin_edna1"](self.pluginMerge)
            self.edna1Dead = False
        except:
            logging.error("Unable to connect to EDNA 1")
            message = "EDNA server 1 is dead, please restart EDNA 1"
            self.showMessage(2, message, notify = 1)
            logging.error("ENDA 1 is dead")
            self.edna1Dead = True

        #TODO: DEBUG - No EDNA 2 yet 13/6 2012
#        try:
#            self.channels["jobSuccess_edna2"].connect("update", self.processingDone)
#            #self.channels["jobFailure_edna2"].connect("update", self.processingDone)
#            self.commands["initPlugin_edna2"](self.pluginSAS)
#            self.edna2Dead = False
#        except:
#            logging.error("Unable to connect to EDNA 2")
#            message = "EDNA server 2 is dead, please restart EDNA 2"
#            self.showMessage(2, message, notify = 1)
#            logging.error("ENDA 2 is dead")
#            self.edna2Dead = True
        # add a channel to read machine current (with polling)
        self.addChannel('tango',
                        'read_current_value',
                        self.machDevName,
                        'SR_Current',
                        polling = 3000)
        # set up a connect to the Tango channel
        readMachCurrentValue = self.channels.get('read_current_value')
        if readMachCurrentValue is not None:
            readMachCurrentValue.connect('update', self.currentChanged)
        # set up a channel
        self.channels["collectRunNumber"].connect("update", self.runNumberChanged)
        # set up a channel for energy
        self.__energyMotor = self.objects["getEnergy"]
        if self.__energyMotor is not None:
            # connect to the signals from the CO Object specmotor
            self.__energyMotor.connect("positionChanged", self.newEnergy)
        else:
            logging.error("No connection to energy motor in spec")

    def newEnergy(self, pValue):
        self.__energy = float(pValue)
        self.channels["pilatus_threshold"].set_value(self.__energy)
        while not self.pilatusReady() :
            time.sleep(0.5)


    def currentChanged(self, current):
        self.machineCurrent = current

    def runNumberChanged(self, runNumber):
        # set new run number from Spec - Convert it to int
        self.nextRunNumber = int(runNumber)

    def testCollect(self, pDirectory, pPrefix, pRunNumber, pConcentration, pComments, pCode, pMaskFile, pDetectorDistance, pWaveLength, pPixelSizeX, pPixelSizeY, pBeamCenterX, pBeamCenterY, pNormalisation):
        self.collectDirectory.set_value(pDirectory)
        self.collectPrefix.set_value(pPrefix)
        self.collectRunNumber.set_value(pRunNumber)
        self.collectConcentration.set_value(pConcentration)
        self.collectComments.set_value(pComments)
        self.collectCode.set_value(pCode)
        self.collectMaskFile.set_value(pMaskFile)
        self.collectDetectorDistance.set_value(pDetectorDistance)
        self.collectWaveLength.set_value(pWaveLength)
        self.collectPixelSizeX.set_value(pPixelSizeX)
        self.collectPixelSizeY.set_value(pPixelSizeY)
        self.collectBeamCenterX.set_value(pBeamCenterX)
        self.collectBeamCenterY.set_value(pBeamCenterY)
        self.collectNormalisation.set_value(pNormalisation)
        self.commands["testCollect"]()


    def collect(self, pDirectory, pPrefix, pRunNumber, pNumberFrames, pTimePerFrame, pConcentration, pComments, pCode, pMaskFile, pDetectorDistance, pWaveLength, pPixelSizeX, pPixelSizeY, pBeamCenterX, pBeamCenterY, pNormalisation, pRadiationChecked, pRadiationAbsolute, pRadiationRelative, pProcessData, pSEUTemperature, pStorageTemperature):
        #TODO: DEBUG
        self.showMessage(0, "entered collect call")
        #TODO: DEBUG
        logging.info("Starting collection now")
        try:
            self.storageTemperature = float(pStorageTemperature)
        except:
            self.storageTemperature = 4
            logging.error("Could not read storage Temperature - Check sample changer connection")
        try:
            self.exposureTemperature = float(pSEUTemperature)
        except:
            self.storageTemperature = 4
            logging.error("Could not read exposure Temperature - Check sample changer connection")
        self.collecting = True
        self.collectDirectory.set_value(pDirectory)
        self.collectPrefix.set_value(pPrefix)
        self.collectRunNumber.set_value(pRunNumber)
        self.collectNumberFrames.set_value(pNumberFrames)
        self.collectTimePerFrame.set_value(pTimePerFrame)
        self.collectConcentration.set_value(pConcentration)
        self.collectComments.set_value(pComments)
        self.collectCode.set_value(pCode)
        self.collectMaskFile.set_value(pMaskFile)
        self.collectDetectorDistance.set_value(pDetectorDistance)
        self.collectWaveLength.set_value(pWaveLength)
        self.collectPixelSizeX.set_value(pPixelSizeX)
        self.collectPixelSizeY.set_value(pPixelSizeY)
        self.collectBeamCenterX.set_value(pBeamCenterX)
        self.collectBeamCenterY.set_value(pBeamCenterY)
        self.collectNormalisation.set_value(pNormalisation)
        self.collectProcessData.set_value(pProcessData)
        #TODO: DEBUG
        logging.info("Prepare EDNA input")
        #Prepare EDNA input
        self.xsdin.sample.concentration = XSDataDouble(float(pConcentration))
        self.xsdin.sample.code = XSDataString(str(pCode))
        self.xsdin.sample.comments = XSDataString(str(pComments))

        xsdExperiment = self.xsdin.experimentSetup
        xsdExperiment.detector = XSDataString("Pilatus")                    #Hardcoded for Pilatus
        xsdExperiment.detectorDistance = XSDataLength(value = float(pDetectorDistance))
        xsdExperiment.pixelSize_1 = XSDataLength(value = float(pPixelSizeX) * 1.0e-6)
        xsdExperiment.pixelSize_2 = XSDataLength(value = float(pPixelSizeY) * 1.0e-6)
        xsdExperiment.beamCenter_1 = XSDataDouble(float(pBeamCenterX))
        xsdExperiment.beamCenter_2 = XSDataDouble(float(pBeamCenterY))
        xsdExperiment.wavelength = XSDataWavelength(float(pWaveLength) * 1.0e-10)
        xsdExperiment.maskFile = XSDataImage(path = XSDataString(str(pMaskFile)))
        xsdExperiment.normalizationFactor = XSDataDouble(float(pNormalisation))
        xsdExperiment.frameMax = XSDataInteger(int(pNumberFrames))
        xsdExperiment.exposureTime = XSDataTime(float(pTimePerFrame))

        sPrefix = str(pPrefix)
        ave_filename = os.path.join(pDirectory, "1d", "%s_%03d_ave.dat" % (sPrefix, pRunNumber))
        sub_filename = os.path.join(pDirectory, "ednaSub", "%s_%03d_sub.dat" % (sPrefix, pRunNumber))
        self.xsdAverage = XSDataInputBioSaxsSmartMergev1_0(\
                                inputCurves = [XSDataFile(path = XSDataString(os.path.join(pDirectory, "1d", "%s_%03d_%02d.dat" % (sPrefix, pRunNumber, i)))) for i in range(1, pNumberFrames + 1)],
                                mergedCurve = XSDataFile(path = XSDataString(ave_filename)),
                                subtractedCurve = XSDataFile(path = XSDataString(sub_filename)))
        if pRadiationChecked:
            self.xsdAverage.absoluteFidelity = XSDataDouble(float(pRadiationAbsolute))
            self.xsdAverage.relativeFidelity = XSDataDouble(float(pRadiationRelative))
        prefixRun = "%s_%03d" % (sPrefix, pRunNumber)
        if (self.lastPrefixRun == prefixRun):
            logging.error("Collecting the same run again %s_%03d", sPrefix, pRunNumber)
        else:
            self.lastPrefixRun = prefixRun
            logging.info("Starting collect of run %s_%03d ", sPrefix, pRunNumber)
        #TODO: DEBUG
        logging.info("Starting spec Collect")
        #TODO: DEBUG
        self.showMessage(0, "calls spec collect")
        self.commands["collect"](callback = self.specCollectDone, error_callback = self.collectFailed)


    def triggerEDNA(self, raw_filename):
        # TODO: DEBUG
        logging.info("Trigger EDNA with filename %s", raw_filename)
        raw_filename = str(raw_filename)
        tmp, suffix = os.path.splitext(raw_filename)
        tmp, base = os.path.split(tmp)
        directory, local = os.path.split(tmp)
        frame = ""
        for c in base[-1::-1]:
            if c.isdigit():
                frame = c + frame
            else:
                break

        self.xsdin.experimentSetup.storageTemperature = XSDataDouble(self.storageTemperature)
        self.xsdin.experimentSetup.exposureTemperature = XSDataDouble(self.exposureTemperature)
        self.xsdin.experimentSetup.frameNumber = XSDataInteger(int(frame))
        self.xsdin.experimentSetup.beamStopDiode = XSDataDouble(float(self.channels["collectBeamStopDiode"].value()))
        # self.machineCurrent is already float
        self.xsdin.experimentSetup.machineCurrent = XSDataDouble(self.machineCurrent)
        self.xsdin.rawImage = XSDataImage(path = XSDataString(raw_filename))
        self.xsdin.logFile = XSDataFile(path = XSDataString(os.path.join(directory, "misc", base + ".log")))
        self.xsdin.normalizedImage = XSDataImage(path = XSDataString(os.path.join(directory, "2d", base + ".edf")))
        self.xsdin.integratedImage = XSDataImage(path = XSDataString(os.path.join(directory, "misc", base + ".ang")))
        self.xsdin.integratedCurve = XSDataFile(path = XSDataString(os.path.join(directory, "1d", base + ".dat")))

        jobId = self.commands["startJob_edna1"]([self.pluginIntegrate, self.xsdin.marshal()])
        self.dat_filenames[jobId] = self.xsdin.integratedCurve.path.value
        logging.info("Processing job %s started", jobId)
        #For debugging
        xmlFilename = os.path.splitext(raw_filename)[0] + ".xml"
        logging.info("Saving XML data to %s", xmlFilename)
        self.xsdin.exportToFile(xmlFilename)

    def specCollectDone(self, returned_value):
        #TODO: DEBUG
        logging.info("Spec Collect done")
        self.collecting = False
        # start EDNA to calculate average at the end
        jobId = self.commands["startJob_edna1"]([self.pluginMerge, self.xsdAverage.marshal()])
        self.dat_filenames[jobId] = self.xsdAverage.mergedCurve.path.value


    def processingDone(self, jobId):
        if jobId in self.dat_filenames:
            filename = self.dat_filenames.pop(jobId)
            logging.info("processing Done from EDNA: %s -> %s", jobId, filename)
            self.emit("collectProcessingDone", filename)
            if jobId.startswith(self.pluginMerge):
                try:
                    strXsdout = self.commands["getJobOutput_edna1"](jobId)
                    xsd = XSDataResultBioSaxsSmartMergev1_0.parseString(strXsdout)
                    self.edna1Dead = False
                except:
                    logging.error("Unable to parse string from Tango/EDNA")
                    message = "EDNA server 1 is dead, please restart EDNA 1"
                    self.showMessage(2, message, notify = 1)
                    logging.error("ENDA 1 is dead")
                    self.edna1Dead = True
                if not self.edna1Dead:
                    log = xsd.status.executiveSummary.value
                    logging.info(log)
                    # Log on info on Pipeline
                    self.showMessage(0, "collectProcessingLog")
                #TODO: DEBUG SAS pipeline to be put back
                # If autoRG has been used, launch the SAS pipeline (very time consuming)
#                if xsd.autoRg is None:
#                    logging.info("SAS pipeline not executed")
#                else:
#                    rgOut = xsd.autoRg
#                    filename = rgOut.filename.path.value
#                    logging.info("filename as input for SAS %s", filename)
#                    datapoint = numpy.loadtxt(filename)
#                    startPoint = rgOut.firstPointUsed.value
#                    q = datapoint[:, 0][startPoint:]
#                    I = datapoint[:, 1][startPoint:]
#                    s = datapoint[:, 2][startPoint:]
#                    mask = (q < 3)
#                    self.xsdin = XSDataInputSolutionScattering(title = XSDataString(os.path.basename(filename)))
#                    #NbThreads=XSDataInteger(4))
#                    self.xsdin.experimentalDataQ = [ XSDataDouble(i / 10.0) for i in q[mask]] #pipeline expect A-1 not nm-1
#                    self.xsdin.experimentalDataValues = [ XSDataDouble(i) for i in I[mask]]
#                    self.xsdin.experimentalDataStdDev = [ XSDataDouble(i) for i in s[mask]]
#                    logging.info("Starting SAS pipeline for file %s", filename)
#                    #TODO: DEBUG workaround EDNA problem
#                    try:
#                        ednaState = self.channels["state_edna2"].Value()
#                        self.edna2Dead = False
#                    except:
#                        message = "EDNA server 2 is dead, please restart EDNA 2"
#                        self.showMessage(2, message, notify = 1)
#                        self.edna2Dead = True
#                    if not self.edna2Dead:
#                        try:
#                            sasJobId = self.commands["startJob_edna2"]([self.pluginSAS, self.xsdin.marshal()])
#                        except:
#                            message = "EDNA server 2 is dead, please restart EDNA 2"
#                            self.showMessage(2, message, notify = 1)
#                            logging.error("ENDA 2 is dead")
        else:
            logging.warning("processing Done from EDNA: %s -X-> None", jobId)

    def _abortCollectWithRobot(self):
        if  self.__collectWithRobotProcedure is not None:
            self.__collectWithRobotProcedure.kill()

    def collectFailed(self, error):
        """Callback when collect is aborted in spec (CTRL-C or error)"""
        self.collecting = False
        self._abortCollectWithRobot()

    def collectAbort(self):
        logging.info("sending abort to stop spec collection")
        #TODO: understand what this is doing SO 13/3
        self.abortCollect.set_value(1)

        # abort data collection in spec (CTRL-C) ; maybe it will do nothing if spec is idle
        # self.commands["collect"].abort()

        self._abortCollectWithRobot()


    def testCollectAbort(self):
        logging.info("sending abort to stop spec test collection")
        self.abortCollect.set_value(1)

        #self.commands["testCollect"].abort()

    def setCheckBeam(self, flag):
        if flag:
            self.channels["checkBeam"].set_value(1)
        else:
            self.channels["checkBeam"].set_value(0)

    # overwrite connectNotify ; first values will be read by brick
    def connectNotify(self, signal_name):
        pass


    def updateChannels(self):
        for channel_name, channel in self.channels.iteritems():
            if channel_name.startswith("jobSuccess"):
                continue
            channel.update(channel.value())


    def pilatusReady(self):
        # Check if Pilatus is ready
        self.__pilatus_status = self.channels["pilatus_status"].value()
        if self.__pilatus_status == "Ready":
            return True
        else:
            return False

    def showMessage(self, level, msg, notify = 0):
        self.emit("collectProcessingLog", level, msg, notify)


    def _collectOne(self, sample, pars, mode = None):
        # ==================================================
        #  SETTING VISCOSITY
        # ==================================================
        if mode == "buffer_before":
            # this will allow to use several buffers of same name for same sample
            # we should check if enough volume is not available then go to next buffer in list
            tocollect = sample["buffer"][0]
        elif mode == "buffer_after":
            tocollect = sample["buffer"][0]
        else:
            tocollect = sample


        #
        # set the energy if needed 
        #
        self.__currentPilatusThreshold = float(self.channels["pilatus_threshold"].value())
        if math.fabs(self.__energy - self.__currentPilatusThreshold) > self.deltaPilatus:
            self.pilatusThreshold.set_value(self.__energy)
            while not self.pilatusReady() :
                time.sleep(0.5)

        #
        # SET gapfill on the Pilatus (Even if not needed)
        #   
        self.channels["fill_mode"].set_value("ON")

        self.showMessage(0, "Setting viscosity to '%s'..." % tocollect["viscosity"])
        if self.objects["sample_changer"].setViscosityLevel(tocollect["viscosity"].lower()) == -1:
            self.showMessage(2, "Error when trying to set viscosity to '%s'..." % tocollect["viscosity"])

        # ==================================================
        #  SETTING SEU TEMPERATURE
        # ==================================================                        
        # temperature is taken from sample (not from buffer) even if buffer is collected
        self.showMessage(0, "Setting SEU temperature to '%s'..." % sample["SEUtemperature"])
        try:
            self.objects["sample_changer"].doSetSEUTemperatureProcedure(sample["SEUtemperature"])
        except RuntimeError:
            self.showMessage(2, "Error when setting SEU temperature ")
            raise

        # ==================================================
        #  FILLING 
        # ==================================================        
        self.showMessage(0, "Filling (%s) from plate '%s', row '%s' and well '%s' with volume '%s'..." % (mode, tocollect["plate"], tocollect["row"], tocollect["well"], tocollect["volume"]))
        try:
            self.objects["sample_changer"].doFillProcedure(tocollect["plate"], tocollect["row"], tocollect["well"], tocollect["volume"])
        except RuntimeError, ErrMsg:
            message = "Error when trying to fill from plate '%s', row '%s' and well '%s' with volume '%s'.\nSampleChanger Error: %r\nAborting collection!" % (tocollect["plate"], tocollect["row"], tocollect["well"], tocollect["volume"], ErrMsg)
            self.showMessage(2, message, notify = 1)
            raise

        # ==================================================
        #  FLOW
        # ==================================================
        self.showMessage(0, "Setting Flow or Fix")
        if tocollect["flow"]:
            self.showMessage(0, "Flowing with volume '%s' during '%s' second(s)..." % (tocollect["volume"], pars["flowTime"]))
            try:
                #TODO: DEBUG
                self.showMessage(0, "start flowing asynch")
                self.objects["sample_changer"].flow(tocollect["volume"], pars["flowTime"])
                self.showMessage(0, "return flowing asynch")
            except RuntimeError:
                self.showMessage(2, "Error when trying to flow with volume '%s' during '%s' second(s)..." % (tocollect["volume"], pars["flowTime"]))
        else:
            self.showMessage(0, "Fixing liquid position...")
            self.objects["sample_changer"].setLiquidPositionFixed(True)
            self.showMessage(0, "  - liquid position fixed.")

        self.showMessage(0, "Setting Flow or Fix done")

        # ==========================
        #  SETTING TRANSMISSION 
        # ========================== 
        #self.showMessage(0, "Setting transmission for plate '%s', row '%s' and well '%s' to %s%s..." % (tocollect["plate"], tocollect["row"], tocollect["well"], tocollect["transmission"], "%"))
        #self.__parent.emit("transmissionChanged", tocollect.transmission)

        # ==================================================
        #  PERFORM COLLECT
        # ==================================================
        self.showMessage(0, "  - Start collecting (%s) '%s'..." % (mode, pars["prefix"]))
        self.emit(QtCore.SIGNAL("displayReset"))
        self.collect(pars["directory"],
                     pars["prefix"], pars["runNumber"],
                     pars["frameNumber"], pars["timePerFrame"], tocollect["concentration"], tocollect["comments"],
                     tocollect["code"], pars["mask"], pars["detectorDistance"], pars["waveLength"],
                     pars["pixelSizeX"], pars["pixelSizeY"], pars["beamCenterX"], pars["beamCenterY"],
                     pars["normalisation"], pars["radiationChecked"], pars["radiationAbsolute"],
                     pars["radiationRelative"],
                     pars["processData"], pars["SEUTemperature"], pars["storageTemperature"])

        # wait for flowing if we started it
        if tocollect["flow"]:
            self.objects["sample_changer"].wait()

        while self.collecting:
            time.sleep(1)

        self.showMessage(0, "  - Finish collecting '%s'..." % pars["prefix"])

        # ======================
        #  WAIT FOR END OF FLOW 
        # ======================
        if tocollect["flow"]:
            self.showMessage(0, "Waiting for end of flow...")
            try:
                self.objects["sample_changer"].wait()
            except RuntimeError:
                self.showMessage(2, "Error when waiting for end of flow...")

        # =============
        #  RECUPERATE 
        # =============
        if tocollect["recuperate"]:
            self.showMessage(0, "Recuperating to plate '%s', row '%s' and well '%s'..." % (tocollect["plate"], tocollect["row"], tocollect["well"]))
            try:
                self.objects["sample_changer"].doRecuperateProcedure(tocollect["plate"], tocollect["row"], tocollect["well"])
            except RuntimeError:
                self.showMessage(2, "Error when trying to recuperate to plate '%s', row '%s' well '%s'..." % (tocollect["plate"], tocollect["row"], tocollect["well"]))

        # ==================================================
        #  CLEANING
        # ==================================================
        self.showMessage(0, "Cleaning...")

        try:
            self.objects["sample_changer"].doCleanProcedure()
        except RuntimeError:
            message = "Error when trying to clean. Aborting collection!"
            self.showMessage(2, message, notify = 1)
            raise


    def _collectWithRobot(self, pars):
        lastBuffer = ""
        # 
        # Setting sample type
        # ===================                                                
        self.showMessage(0, "Setting sample type to '%s'..." % pars["sampleType"])
        # Synchronous - no exception handling
        self.objects["sample_changer"].setSampleType(pars["sampleType"].lower())

        # 
        #  Setting storage temperature
        # ============================
        self.showMessage(0, "Setting storage temperature to '%s' C..." % pars["storageTemperature"])
        # ASynchronous - Treated in sample Changer
        self.objects["sample_changer"].setStorageTemperature(pars["storageTemperature"])

        # Open guillotine
        self.commands["guillopen"]()
        # count for 30s and then give alarm
        count = 0
        # wait  for "3" = open
        while self.channels["guillstate"].value() != "3":
            time.sleep(0.5)
            if count > 60 :
                self.showMessage(2, "Error when trying to open guillotine")
                self.collectAbort()
                break

        #TODO: Be smarter than just open
        self.commands["shopen"]()

        if pars["initialCleaning"]:
            self.showMessage(0, "Initial cleaning...")
            try:
                self.objects["sample_changer"].doCleanProcedure()
            except RuntimeError:
                message = "Error when trying to clean. Aborting collection!"
                self.showMessage(2, message, notify = 1)
                raise

        self.lastSampleTime = time.time()
        prevSample = None
        runNumberSet = True
        # ==================================================
        #   MAIN LOOP on Samples
        # ==================================================        
        for sample in pars["sampleList"]:
            #
            #  Collect buffer before
            #     - in mode BufferBefore  , always
            #     - in mode BufferFirst   , at beginning and every time buffer changes
            # 
            # In buffer first mode check also if temperature has changed. If so, consider as
            #    a change in buffer
            doFirstBuffer = pars["bufferBefore"]
            # in bufferFirst mode decide when to collect the buffer 
            if pars["bufferFirst"]:
                if sample["buffername"] != lastBuffer:
                    doFirstBuffer = True
                if prevSample is not None:
                    if prevSample["SEUtemperature"] != sample["SEUtemperature"]:
                        self.showMessage(0, "SEU Temperature different from previous. Collecting buffer.")
                        doFirstBuffer = True

            if doFirstBuffer:
                if sample["buffername"] != lastBuffer:
                    lastBuffer = sample["buffername"]
                if runNumberSet:
                    # Using pars["runNumber"] from collect brick
                    runNumberSet = False
                else:
                    # need to increase run number
                    pars["runNumber"] = self.nextRunNumber
                self._collectOne(sample, pars, mode = "buffer_before")

            #
            # Wait if necessary before collecting sample
            #
            if sample["waittime"]:
                time_to_wait = sample["waittime"]
                while time_to_wait > 0:
                    self.showMessage(0, "Waiting to start next sample. %d secs left..." % time_to_wait)
                    time.sleep(min(10, time_to_wait))
                    time_to_wait = time_to_wait - 10
                self.showMessage(0, "    Done waiting.")

            self.lastSampleTime = time.time()

            #
            # Collect sample
            #
            if runNumberSet:
                # Using pars["runNumber"] from collect brick
                runNumberSet = False
            else:
                # need to increase run number
                pars["runNumber"] = self.nextRunNumber
            self._collectOne(sample, pars, mode = "sample")

            if pars["bufferAfter"]:
                if runNumberSet:
                    # Using pars["runNumber"] from collect brick
                    runNumberSet = False
                else:
                    # need to increase run number
                    pars["runNumber"] = self.nextRunNumber
                self._collectOne(sample, pars, mode = "buffer_after")

            prevSample = sample

        #
        # End of for sample loop
        #---------------------------------- 
        self.showMessage(0, "The data collection is done!")

        self.emit("collectDone")


    def collectWithRobot(self, *args):
        self.__collectWithRobotProcedure = gevent.spawn(self._collectWithRobot, *args)
