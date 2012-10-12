import os, logging, time, re
from Framework4.GUI      import Core
from Framework4.GUI.Core import Property, Connection, Signal, Slot

from CollectRobotDialog  import CollectRobotDialog
from ISPyBCollectRobotDialog import ISPyBCollectRobotDialog

from PyQt4               import QtCore, QtGui, Qt
from LeadingZeroSpinBox  import LeadingZeroSpinBox

from Samples             import CollectPars


from pydispatch import dispatcher

logger = logging.getLogger("CollectBrick")

__category__ = "BsxCuBE"


def main_window_visible(_):
    # Helping the starter to know when the main window is visible
    os.system("touch /tmp/.BsxCuBE.GUIStart")
    os.system("chmod 777 /tmp/.BsxCuBE.GUIStart >/dev/null 2>&1")

dispatcher.connect(main_window_visible, "__main_window_visible__")

# Compare outside class
def cmpSEUtemp(a, b):
    return cmp(a["SEUtemperature"], b["SEUtemperature"])
def cmpCode(a, b):
    return cmp(a["code"], b["code"])
def cmpCodeAndSEU(a, b):
    if a["code"] == b["code"]:
        return cmpSEUtemp(a, b)
    else:
        return cmpCode(a, b)

class CollectBrick(Core.BaseBrick):
    properties = {"expertModeOnly": Property("boolean", "Expert mode only", "", "expertModeOnlyChanged", False)}

    connections = {"collect": Connection("Collect object",
                                            [Signal("collectBeamStopDiodeChanged", "collectBeamStopDiodeChanged"),
                                             Signal("collectDirectoryChanged", "collectDirectoryChanged"),
                                             Signal("collectPrefixChanged", "collectPrefixChanged"),
                                             Signal("collectRunNumberChanged", "collectRunNumberChanged"),
                                             Signal("collectNumberFramesChanged", "collectNumberFramesChanged"),
                                             Signal("collectTimePerFrameChanged", "collectTimePerFrameChanged"),
                                             Signal("collectConcentrationChanged", "collectConcentrationChanged"),
                                             Signal("collectCommentsChanged", "collectCommentsChanged"),
                                             Signal("collectCodeChanged", "collectCodeChanged"),
                                             Signal("collectMaskFileChanged", "collectMaskFileChanged"),
                                             Signal("collectDetectorDistanceChanged", "collectDetectorDistanceChanged"),
                                             Signal("collectWaveLengthChanged", "collectWaveLengthChanged"),
                                             Signal("collectPixelSizeXChanged", "collectPixelSizeXChanged"),
                                             Signal("collectPixelSizeYChanged", "collectPixelSizeYChanged"),
                                             Signal("collectBeamCenterXChanged", "collectBeamCenterXChanged"),
                                             Signal("collectBeamCenterYChanged", "collectBeamCenterYChanged"),
                                             Signal("collectNormalisationChanged", "collectNormalisationChanged"),
                                             Signal("collectRadiationDamageChanged", "collectRadiationDamageChanged"),
                                             Signal("collectRelativeRadiationDamageChanged", "collectRelativeRadiationDamageChanged"),
                                             Signal("collectAbsoluteRadiationDamageChanged", "collectAbsoluteRadiationDamageChanged"),
                                             Signal("collectNewFrameChanged", "collectNewFrameChanged"),
                                             Signal("checkBeamChanged", "checkBeamChanged"),
                                             Signal("beamLostChanged", "beamLostChanged"),
                                             Signal("collectProcessingDone", "collectProcessingDone"),
                                             Signal("collectProcessingLog", "collectProcessingLog"),
                                             Signal("collectDone", "collectDone"),
                                             Signal("clearCurve", "clearCurve"),
                                             Signal("transmissionChanged", "transmissionChanged"),
                                             Signal("machineCurrentChanged", "machineCurrentChanged"),
                                             Signal("newSASUrl", "newSASUrl")],
                                            [Slot("testCollect"),
                                             Slot("collect"),
                                             Slot("collectAbort"),
                                             Slot("setCheckBeam"),
                                             Slot("triggerEDNA"),
                                             Slot("blockEnergyAdjust")],
                                            "collectObjectConnected"),
                    "motoralignment": Connection("MotorAlignment object",
                                            [Signal("executeTestCollect", "executeTestCollect")],
                                            []),
                    "energy": Connection("Energy object",
                                            [Signal("energyChanged", "energyChanged")],
                                            [Slot("setEnergy"), Slot("getEnergy"), Slot("pilatusReady"), Slot("setPilatusFill"), Slot("energyAdjustPilatus")],
                                            "connectedToEnergy"),
                    "samplechanger": Connection("Sample Changer object",
                                            [Signal('seuTemperatureChanged', 'seuTemperatureChanged'),
                                             Signal('storageTemperatureChanged', 'storageTemperatureChanged'),
                                             Signal('stateChanged', 'state_changed')],
                                            [],
                                            "connectedToSC"),
                    "image_proxy": Connection("image proxy",
                                            [Signal('new_curves_data', 'y_curves_data'), Signal('erase_curve', 'erase_curve')],
                                            [],
                                            "connectedToImageProxy"),

                    "login": Connection("Login object",
                                            [Signal("loggedIn", "loggedIn")],
                                            [],
                                            "connectedToLogin"),

                    "BiosaxsClient": Connection("BiosaxsClient object",
                                            [],
                                            [Slot("getRobotXML")],
                                            "connectedToBiosaxsClient"),

                    "WebSAS": Connection("Web SAS Browser object",
                                            [],
                                            [Slot("setURL")],
                                            "connectedToSAS")}



    signals = [Signal("displayResetChanged"),
               Signal("displayItemChanged"),
               Signal("transmissionChanged"),
               Signal("grayOut")]
    slots = []

    def __init__(self, *args, **kargs):
        Core.BaseBrick.__init__(self, *args, **kargs)
        self._curveList = []
        self.lastCollectProcessingLog = None
        self.__energy = None
        self.isHPLC = False

    def init(self):
        # The keV to Angstrom calc
        self.hcOverE = 12.3984
        self.deltaPilatus = 0.1
        self.nbPlates = 0
        self.platesIDs = []
        self.plateInfos = []
        self._machineCurrent = 0.0
        self._diodeCurrent = 0.00
        self._frameNumber = 0
        self._feedBackFlag = False
        self._abortFlag = False
        self._currentFrame = 0
        self._currentCurve = 0
        self._waveLengthStr = "0.0"
        self._collectRobotDialog = None
        self._ispybCollect = False
        self.__lastFrame = None
        self.__currentConcentration = None
        self.__isTesting = False
        self.__expertModeOnly = False
        self.__expertMode = False
        self.loginDone = False
        self.contact = False
        self.energyControlObject = None
        self.loginObject = None
        self.biosaxsClientObject = None
        self.__username = None
        self.__password = None
        self.collectObj = None

        self.sasWebObject = None

        self.scObject = None

        self.__validParameters = [False, False, False]

        #TODO: DEBUG
        self.last_dat = None
        self.imageProxy = None

        self.brick_widget.setLayout(Qt.QVBoxLayout())

        self.readOnlyCheckBox = Qt.QCheckBox("Read only", self.brick_widget)
        Qt.QObject.connect(self.readOnlyCheckBox, Qt.SIGNAL("toggled(bool)"), self.readOnlyCheckBoxToggled)
        self.brick_widget.layout().addWidget(self.readOnlyCheckBox)

        self.hBoxLayout0 = Qt.QHBoxLayout()
        self.directoryLabel = Qt.QLabel("Directory", self.brick_widget)
        self.directoryLabel.setFixedWidth(130)
        self.hBoxLayout0.addWidget(self.directoryLabel)
        self.directoryLineEdit = Qt.QLineEdit(self.brick_widget)
        self.directoryLineEdit.setMaxLength(100)
        self.hBoxLayout0.addWidget(self.directoryLineEdit)
        Qt.QObject.connect(self.directoryLineEdit, Qt.SIGNAL("textChanged(const QString &)"), self.directoryLineEditChanged)
        self.directoryPushButton = Qt.QPushButton("...", self.brick_widget)
        self.directoryPushButton.setFixedWidth(25)
        Qt.QObject.connect(self.directoryPushButton, Qt.SIGNAL("clicked()"), self.directoryPushButtonClicked)
        self.hBoxLayout0.addWidget(self.directoryPushButton)
        self.brick_widget.layout().addLayout(self.hBoxLayout0)

        self.hBoxLayout1 = Qt.QHBoxLayout()
        self.prefixLabel = Qt.QLabel("Prefix", self.brick_widget)
        self.prefixLabel.setFixedWidth(130)
        self.hBoxLayout1.addWidget(self.prefixLabel)
        self.prefixLineEdit = Qt.QLineEdit(self.brick_widget)
        self.prefixLineEdit.setMaxLength(30)
        self.prefixLineEdit.setValidator(Qt.QRegExpValidator(Qt.QRegExp("^[a-zA-Z][a-zA-Z0-9_]*"), self.prefixLineEdit))
        Qt.QObject.connect(self.prefixLineEdit, Qt.SIGNAL("textChanged(const QString &)"), self.prefixLineEditChanged)
        self.hBoxLayout1.addWidget(self.prefixLineEdit)
        self.brick_widget.layout().addLayout(self.hBoxLayout1)

        self.hBoxLayout2 = Qt.QHBoxLayout()
        self.runNumberLabel = Qt.QLabel("Run #", self.brick_widget)
        self.runNumberLabel.setFixedWidth(130)
        self.hBoxLayout2.addWidget(self.runNumberLabel)
        self.runNumberSpinBox = LeadingZeroSpinBox(self.brick_widget, 3)
        self.runNumberSpinBox.setRange(1, 999)
        self.hBoxLayout2.addWidget(self.runNumberSpinBox)
        self.brick_widget.layout().addLayout(self.hBoxLayout2)

        self.hBoxLayout3 = Qt.QHBoxLayout()
        self.frameNumberLabel = Qt.QLabel("Frame #", self.brick_widget)
        self.frameNumberLabel.setFixedWidth(130)
        self.hBoxLayout3.addWidget(self.frameNumberLabel)
        self.frameNumberSpinBox = LeadingZeroSpinBox(self.brick_widget, 5)
        self.frameNumberSpinBox.setRange(1, 99999)
        self.hBoxLayout3.addWidget(self.frameNumberSpinBox)
        self.brick_widget.layout().addLayout(self.hBoxLayout3)

        self.hBoxLayout4 = Qt.QHBoxLayout()
        self.timePerFrameLabel = Qt.QLabel("Time per frame", self.brick_widget)
        self.timePerFrameLabel.setFixedWidth(130)
        self.hBoxLayout4.addWidget(self.timePerFrameLabel)
        self.timePerFrameSpinBox = Qt.QSpinBox(self.brick_widget)
        self.timePerFrameSpinBox.setSuffix(" s")
        self.timePerFrameSpinBox.setRange(1, 99)
        self.hBoxLayout4.addWidget(self.timePerFrameSpinBox)
        self.brick_widget.layout().addLayout(self.hBoxLayout4)

        self.hBoxLayout5 = Qt.QHBoxLayout()
        self.concentrationLabel = Qt.QLabel("Concentration", self.brick_widget)
        self.concentrationLabel.setFixedWidth(130)
        self.hBoxLayout5.addWidget(self.concentrationLabel)
        self.concentrationDoubleSpinBox = Qt.QDoubleSpinBox(self.brick_widget)
        self.concentrationDoubleSpinBox.setSuffix(" mg/ml")
        self.concentrationDoubleSpinBox.setDecimals(2)
        self.concentrationDoubleSpinBox.setRange(0, 100)
        self.hBoxLayout5.addWidget(self.concentrationDoubleSpinBox)
        self.brick_widget.layout().addLayout(self.hBoxLayout5)

        self.hBoxLayout6 = Qt.QHBoxLayout()
        self.commentsLabel = Qt.QLabel("Comments", self.brick_widget)
        self.commentsLabel.setFixedWidth(130)
        self.hBoxLayout6.addWidget(self.commentsLabel)
        self.commentsLineEdit = Qt.QLineEdit(self.brick_widget)
        self.commentsLineEdit.setMaxLength(100)
        self.commentsLineEdit.setValidator(Qt.QRegExpValidator(Qt.QRegExp("[a-zA-Z0-9\\%/()=+*^:.\-_ ]*"), self.commentsLineEdit))
        self.hBoxLayout6.addWidget(self.commentsLineEdit)
        self.brick_widget.layout().addLayout(self.hBoxLayout6)


        self.hBoxLayout7 = Qt.QHBoxLayout()
        self.codeLabel = Qt.QLabel("Code", self.brick_widget)
        self.codeLabel.setFixedWidth(130)
        self.hBoxLayout7.addWidget(self.codeLabel)
        self.codeLineEdit = Qt.QLineEdit(self.brick_widget)
        self.codeLineEdit.setMaxLength(30)
        self.codeLineEdit.setValidator(Qt.QRegExpValidator(Qt.QRegExp("^[a-zA-Z][a-zA-Z0-9_]*"), self.codeLineEdit))
        self.hBoxLayout7.addWidget(self.codeLineEdit)
        self.brick_widget.layout().addLayout(self.hBoxLayout7)

        self.hBoxLayout71 = Qt.QHBoxLayout()
        self.blParamsButton = Qt.QPushButton("Show Beamline Parameters", self.brick_widget)
        self.blParamsButton.setFixedWidth(230)
        self.hBoxLayout71.addWidget(self.blParamsButton)
        self.brick_widget.layout().addLayout(self.hBoxLayout71)
        Qt.QObject.connect(self.blParamsButton, Qt.SIGNAL("clicked()"), self.showHideBeamlineParams)

        self.hBoxLayout8 = Qt.QHBoxLayout()
        self.maskLabel = Qt.QLabel("Mask", self.brick_widget)
        self.maskLabel.setFixedWidth(130)
        self.hBoxLayout8.addWidget(self.maskLabel)
        self.maskLineEdit = Qt.QLineEdit(self.brick_widget)
        self.maskLineEdit.setMaxLength(100)
        Qt.QObject.connect(self.maskLineEdit, Qt.SIGNAL("textChanged(const QString &)"), self.maskLineEditChanged)
        self.hBoxLayout8.addWidget(self.maskLineEdit)
        self.maskDirectoryPushButton = Qt.QPushButton("...", self.brick_widget)
        self.maskDirectoryPushButton.setFixedWidth(25)
        Qt.QObject.connect(self.maskDirectoryPushButton, Qt.SIGNAL("clicked()"), self.maskDirectoryPushButtonClicked)
        self.hBoxLayout8.addWidget(self.maskDirectoryPushButton)
        self.maskDisplayPushButton = Qt.QPushButton("Display", self.brick_widget)
        self.maskDisplayPushButton.setFixedWidth(55)
        Qt.QObject.connect(self.maskDisplayPushButton, Qt.SIGNAL("clicked()"), self.maskDisplayPushButtonClicked)
        self.hBoxLayout8.addWidget(self.maskDisplayPushButton)
        self.brick_widget.layout().addLayout(self.hBoxLayout8)

        self.hBoxLayout9 = Qt.QHBoxLayout()
        self.detectorDistanceLabel = Qt.QLabel("Detector distance", self.brick_widget)
        self.detectorDistanceLabel.setFixedWidth(130)
        self.hBoxLayout9.addWidget(self.detectorDistanceLabel)
        self.detectorDistanceDoubleSpinBox = Qt.QDoubleSpinBox(self.brick_widget)
        self.detectorDistanceDoubleSpinBox.setSuffix(" m")
        self.detectorDistanceDoubleSpinBox.setDecimals(3)
        self.detectorDistanceDoubleSpinBox.setRange(0.1, 10)
        self.hBoxLayout9.addWidget(self.detectorDistanceDoubleSpinBox)
        self.brick_widget.layout().addLayout(self.hBoxLayout9)

        self.hBoxLayout11 = Qt.QHBoxLayout()
        self.pixelSizeLabel = Qt.QLabel("Pixel size (x, y)", self.brick_widget)
        self.pixelSizeLabel.setFixedWidth(130)
        self.hBoxLayout11.addWidget(self.pixelSizeLabel)
        self.pixelSizeXDoubleSpinBox = Qt.QDoubleSpinBox(self.brick_widget)
        self.pixelSizeXDoubleSpinBox.setSuffix(" um")
        self.pixelSizeXDoubleSpinBox.setDecimals(1)
        self.pixelSizeXDoubleSpinBox.setRange(10, 500)
        self.hBoxLayout11.addWidget(self.pixelSizeXDoubleSpinBox)
        self.pixelSizeYDoubleSpinBox = Qt.QDoubleSpinBox(self.brick_widget)
        self.pixelSizeYDoubleSpinBox.setSuffix(" um")
        self.pixelSizeYDoubleSpinBox.setDecimals(1)
        self.pixelSizeYDoubleSpinBox.setRange(10, 500)
        self.hBoxLayout11.addWidget(self.pixelSizeYDoubleSpinBox)
        self.brick_widget.layout().addLayout(self.hBoxLayout11)

        self.hBoxLayout12 = Qt.QHBoxLayout()
        self.beamCenterLabel = Qt.QLabel("Beam center (x, y)", self.brick_widget)
        self.beamCenterLabel.setFixedWidth(130)
        self.hBoxLayout12.addWidget(self.beamCenterLabel)
        self.beamCenterXSpinBox = Qt.QSpinBox(self.brick_widget)
        self.beamCenterXSpinBox.setSuffix(" px")
        self.beamCenterXSpinBox.setRange(1, 9999)
        self.hBoxLayout12.addWidget(self.beamCenterXSpinBox)
        self.beamCenterYSpinBox = Qt.QSpinBox(self.brick_widget)
        self.beamCenterYSpinBox.setSuffix(" px")
        self.beamCenterYSpinBox.setRange(1, 9999)
        self.hBoxLayout12.addWidget(self.beamCenterYSpinBox)
        self.brick_widget.layout().addLayout(self.hBoxLayout12)

        self.hBoxLayout13 = Qt.QHBoxLayout()
        self.normalisationLabel = Qt.QLabel("Normalisation", self.brick_widget)
        self.normalisationLabel.setFixedWidth(130)
        self.hBoxLayout13.addWidget(self.normalisationLabel)
        self.normalisationDoubleSpinBox = Qt.QDoubleSpinBox(self.brick_widget)
        self.normalisationDoubleSpinBox.setDecimals(10)
        self.normalisationDoubleSpinBox.setRange(0.0000001, 10000)
        self.hBoxLayout13.addWidget(self.normalisationDoubleSpinBox)
        self.brick_widget.layout().addLayout(self.hBoxLayout13)


        self.vBoxLayout0 = Qt.QVBoxLayout()
        self.vBoxLayout0.addSpacing(15)
        self.brick_widget.layout().addLayout(self.vBoxLayout0)

        # Radiation Damage 
        self.hBoxLayout15 = Qt.QHBoxLayout()
        self.radiationCheckBox = Qt.QCheckBox("Radiation damage (10^-f)", self.brick_widget)
        self.radiationCheckBox.setFixedWidth(160)
        Qt.QObject.connect(self.radiationCheckBox, Qt.SIGNAL("toggled(bool)"), self.radiationCheckBoxToggled)
        self.hBoxLayout15.addWidget(self.radiationCheckBox)
        self.radiationRelativeDoubleSpinBox = Qt.QDoubleSpinBox(self.brick_widget)
        self.radiationRelativeDoubleSpinBox.setRange(0.0, 500.)
        self.radiationRelativeDoubleSpinBox.setDecimals(2)
        self.radiationRelativeDoubleSpinBox.setToolTip("Relative Similarity")
        self.hBoxLayout15.addWidget(self.radiationRelativeDoubleSpinBox)
        self.radiationAbsoluteDoubleSpinBox = Qt.QDoubleSpinBox(self.brick_widget)
        self.radiationAbsoluteDoubleSpinBox.setRange(0.0, 500.)
        self.radiationAbsoluteDoubleSpinBox.setDecimals(2)
        self.radiationAbsoluteDoubleSpinBox.setToolTip("Absolute Similarity")
        self.hBoxLayout15.addWidget(self.radiationAbsoluteDoubleSpinBox)
        self.brick_widget.layout().addLayout(self.hBoxLayout15)

        # Spectro Online
        #TODO: MOVE to Collect box
#        self.hBoxLayout151 = Qt.QHBoxLayout()
#        self.spectroCheckBox = Qt.QCheckBox("Spectro online", self.brick_widget)
#        self.spectroCheckBox.setFixedWidth(130)
#        Qt.QObject.connect(self.spectroCheckBox, Qt.SIGNAL("toggled(bool)"), self.spectroCheckBoxToggled)
#        self.hBoxLayout151.addWidget(self.spectroCheckBox)
#        self.extinctionCoefficentDoubleSpinBox = Qt.QDoubleSpinBox(self.brick_widget)
#        self.extinctionCoefficentDoubleSpinBox.setRange(0.001, 99.998)
#        self.extinctionCoefficentDoubleSpinBox.setDecimals(3)
#        #TODO: - Change by reading from SPEC/File
#        self.extinctionCoefficentDoubleSpinBox.setValue(1.000)
#        self.extinctionCoefficentDoubleSpinBox.setSuffix(" (ml)*(1/mg)*(1/cm)")
#        self.extinctionCoefficentDoubleSpinBox.setToolTip("Extinction Coefficient")
#        self.hBoxLayout151.addWidget(self.extinctionCoefficentDoubleSpinBox)
#        self.brick_widget.layout().addLayout(self.hBoxLayout151)


        self.hBoxLayout16 = Qt.QHBoxLayout()
        self.robotCheckBox = Qt.QCheckBox("Collect using robot", self.brick_widget)
        Qt.QObject.connect(self.robotCheckBox, Qt.SIGNAL("toggled(bool)"), self.robotCheckBoxToggled)
        self.hBoxLayout16.addWidget(self.robotCheckBox)
        self.ispybRobotCheckBox = Qt.QCheckBox("Collect with ISPyB", self.brick_widget)
        Qt.QObject.connect(self.ispybRobotCheckBox, Qt.SIGNAL("toggled(bool)"), self.ispybRobotCheckBoxToggled)
        self.hBoxLayout16.addWidget(self.ispybRobotCheckBox)
        self.hplcCheckBox = Qt.QCheckBox("Collect using HPLC", self.brick_widget)
        Qt.QObject.connect(self.hplcCheckBox, Qt.SIGNAL("toggled(bool)"), self.CheckBoxToggledHPLC)
        self.hBoxLayout16.addWidget(self.hplcCheckBox)
        self.brick_widget.layout().addLayout(self.hBoxLayout16)

        self.hBoxLayout17 = Qt.QHBoxLayout()
        self.notifyCheckBox = Qt.QCheckBox("Notify when done", self.brick_widget)
        self.notifyCheckBox.setChecked(True)
        self.hBoxLayout17.addWidget(self.notifyCheckBox)
        self.checkBeamBox = Qt.QCheckBox("Check beam", self.brick_widget)
        self.checkBeamBox.setChecked(True)
        Qt.QObject.connect(self.checkBeamBox, Qt.SIGNAL("toggled(bool)"), self.checkBeamBoxToggled)
        self.hBoxLayout17.addWidget(self.checkBeamBox)
        self.pilatusCheckBox = Qt.QCheckBox("Energy adjust pilatus", self.brick_widget)
        Qt.QObject.connect(self.pilatusCheckBox, Qt.SIGNAL("toggled(bool)"), self.pilatusCheckBoxToggled)
        self.pilatusCheckBox.setChecked(True)
        self.hBoxLayout17.addWidget(self.pilatusCheckBox)
        self.brick_widget.layout().addLayout(self.hBoxLayout17)

        self.hBoxLayout18 = Qt.QHBoxLayout()
        self.testPushButton = Qt.QPushButton("Test", self.brick_widget)
        self.testPushButton.setToolTip("Collect test frame (during 1 second) with the specified parameters")
        self.hBoxLayout18.addWidget(self.testPushButton)
        Qt.QObject.connect(self.testPushButton, Qt.SIGNAL("clicked()"), self.testPushButtonClicked)
        self.collectPushButton = Qt.QPushButton("Collect", self.brick_widget)
        self.collectPushButton.setToolTip("Start collecting frame(s) with the specified parameters")
        self.hBoxLayout18.addWidget(self.collectPushButton)
        Qt.QObject.connect(self.collectPushButton, Qt.SIGNAL("clicked()"), self.collectPushButtonClicked)
        self.brick_widget.layout().addLayout(self.hBoxLayout18)

        self.hBoxLayout19 = Qt.QHBoxLayout()
        self.abortPushButton = Qt.QPushButton("Abort", self.brick_widget)
        self.abortPushButton.setToolTip("Abort ongoing data collection")
        self.abortPushButton.setObjectName("abortbutton")
        self.hBoxLayout19.addWidget(self.abortPushButton)
        Qt.QObject.connect(self.abortPushButton, Qt.SIGNAL("clicked()"), self.abortPushButtonClicked)
        self.brick_widget.layout().addLayout(self.hBoxLayout19)

        self.hBoxLayout20 = Qt.QHBoxLayout()
        self.collectStatusLabel = Qt.QLabel("Collection status:")
        self.collectStatusLabel.setAlignment(QtCore.Qt.AlignRight)
        self.collectStatus = Qt.QLabel("")
        self.collectStatus.setAlignment(QtCore.Qt.AlignCenter)
        self.collectStatus.setObjectName("collect")
        self.hBoxLayout20.addWidget(self.collectStatusLabel)
        self.hBoxLayout20.addWidget(self.collectStatus)
        self.brick_widget.layout().addLayout(self.hBoxLayout20)

        #
        # validation colors
        #
        self.brick_widget.setStyleSheet('*[valid="true"]  {background-color: white}\
                            *[valid="false"] {background-color: #faa}\
                            #abortbutton[abortactive="true"]  {background-color: red;color: white}\
                            #abortbutton[abortactive="false"] {background-color: #fff;color: black}\
                            #collect[status="ready"]   {background-color: #0f0;color: black;font-weight: bold; alignment: center}\
                            #collect[status="done"]    {background-color: #0f0;color: black;font-weight: bold; alignment: center}\
                            #collect[status="busy"]    {background-coldisplayItemChangedor: yellow;color: black;font-weight: bold;alignment: center}\
                            #collect[status="aborting"]  {background-color: magenta;color: black;font-weight: bold;alignment: center}\
                            #collect[status="running"] {background-color: yellow;color: black;font-weight: bold;alignment: center}')

        self.setCollectionStatus("ready")

        self.showingBLParams = 1
        self.showHideBeamlineParams(None)

        self.directoryLineEditChanged(None)
        self.prefixLineEditChanged(None)
        self.maskLineEditChanged(None)
        self.radiationCheckBoxToggled(False)
        # TODO : DEBUG
#        self.spectroCheckBoxToggled(False)
        self.seuTemperature = None
        self.storageTemperature = None
        self.collectionStatus = None

        self.SPECBusyTimer = Qt.QTimer(self.brick_widget)
        Qt.QObject.connect(self.SPECBusyTimer, Qt.SIGNAL("timeout()"), self.SPECBusyTimerTimeOut)

        self._sampleChangerDisplayFlag = False
        self._sampleChangerDisplayMessage = ""

        self.setWidgetState()

    # When connected to Login, then block the brick
    def connectedToLogin(self, pPeer):
        if pPeer is not None:
            self.loginObject = pPeer
            self.brick_widget.setEnabled(False)

    # When connected to the BiosaxsClient
    def connectedToBiosaxsClient(self, pPeer):
        if pPeer is not None:
            self.biosaxsClientObject = pPeer

    # When connected SAS webdisplay
    def connectedToSAS(self, pPeer):
        if pPeer is not None:
            self.sasWebObject = pPeer

    # Logged In : True or False 
    def loggedIn(self, pValue):
        if pValue:
            # get password and username and send it to Collect Object
            if self.loginObject is not None:
                (self.__username, self.__password) = self.loginObject.getUserInfo()
                if (self.__username is not None and self.__password is not None):
                    if self.collectObj is not None:
                        self.collectObj.putUserInfo(self.__username, self.__password)
#                        (sampleCode, exposureTemperature, storageTemperature, timePerFrame, \
#                           start, end, energy, detectorDistance, edfFileArray, snapshotCapillary, \
#                           currentMachine) = self.collectObj.getIspyByParams(self)
                #TODO: DEBUG
                print "Now we are logged in as %s woith pwd %s " % (self.__username, self.__password)

            else:
                self.__username = None
                self.__password = None

        self.loginDone = pValue
        self.brick_widget.setEnabled(pValue)

    def connectedToSC(self, pPeer):
        if pPeer is not None:
            self.scObject = pPeer
            self.nbPlates = 3
            self.plateInfos = [self.scObject.getPlateInfo(i) for i in range(1, self.nbPlates + 1)]
            print "sample changer connected in CollectBrick>>>> %r" % self.plateInfos
            self.seuTemperature = self.scObject.getSEUTemperature()
            self.storageTemperature = self.scObject.getSampleStorageTemperature()

    def seuTemperatureChanged(self, seuTemperature):
        self.seuTemperature = seuTemperature

    def storageTemperatureChanged(self, storageTemperature):
        self.storageTemperature = storageTemperature

    def state_changed(self, state, status):
        # not used, so we do not care
        pass

    def connectedToImageProxy(self, imageProxy):
        self.imageProxy = imageProxy

    def exp_spec_connected(self, spec):
        if spec != None:
            self.spec = spec

    def collectBeamStopDiodeChanged(self, pValue):
        self._diodeCurrent = pValue

    def collectDirectoryChanged(self, pValue):
        self.directoryLineEdit.setText(pValue)

    def collectPrefixChanged(self, pValue):
        self.prefixLineEdit.setText(pValue)

    def collectRunNumberChanged(self, pValue):
        self.runNumberSpinBox.setValue(int(pValue))

    def collectNumberFramesChanged(self, pValue):
        self.frameNumberSpinBox.setValue(int(pValue))

    def collectTimePerFrameChanged(self, pValue):
        self.timePerFrameSpinBox.setValue(int(pValue))

    def collectConcentrationChanged(self, pValue):
        self.concentrationDoubleSpinBox.setValue(float(pValue))

    def collectCommentsChanged(self, pValue):
        self.commentsLineEdit.setText(pValue)

    def collectCodeChanged(self, pValue):
        self.codeLineEdit.setText(pValue)

    def collectMaskFileChanged(self, pValue):
        self.maskLineEdit.setText(pValue)

    def collectDetectorDistanceChanged(self, pValue):
        self.detectorDistanceDoubleSpinBox.setValue(float(pValue))

    def collectWaveLengthChanged(self, pValue):
        self._waveLengthStr = pValue

    def collectPixelSizeXChanged(self, pValue):
        self.pixelSizeXDoubleSpinBox.setValue(float(pValue))

    def collectPixelSizeYChanged(self, pValue):
        self.pixelSizeYDoubleSpinBox.setValue(float(pValue))

    def collectBeamCenterXChanged(self, pValue):
        self.beamCenterXSpinBox.setValue(int(pValue))

    def collectBeamCenterYChanged(self, pValue):
        self.beamCenterYSpinBox.setValue(int(pValue))

    def collectNormalisationChanged(self, pValue):
        self.normalisationDoubleSpinBox.setValue(float(pValue))

    def collectRadiationDamageChanged(self, pValue):
        if pValue is not None:
            self.radiationCheckBox.setChecked(pValue == "1")

    def collectAbsoluteRadiationDamageChanged(self, pValue):
        if pValue is not None:
            self.radiationAbsoluteDoubleSpinBox.setValue(float(pValue))

    def collectRelativeRadiationDamageChanged(self, pValue):
        if pValue is not None:
            self.radiationRelativeDoubleSpinBox.setValue(float(pValue))

    def collectProcessingDone(self, dat_filename):
        #TODO : DEBUG
        ##print ">>>>>> Collect Processing Done filename is %r and will be displayed in 1D " % dat_filename
        #TODO remove this hack ASAP (SO 27/9 11)
        ### HORRIBLE CODE
        if self.last_dat is None :
            #TODO remove this hack ASAP (SO 27/9 11)
            ### TO BE REMOVED WHEN FWK4 IS FIXED (MG)
            logger.info("processing done, file is %s", dat_filename)
            # Only display 1d images like XXXX/1d/<at least on char>.dat
            if re.match(r".*/1d/[^/]+\.dat$", dat_filename):
                #DEBUG: get file size
                if os.path.exists(dat_filename):
                    filesize = os.path.getsize(dat_filename)
                    print ">>> File info 0 %r  %s " % (filesize, type(filesize))
                    self.display1D(dat_filename)
                else:
                    logger.warning("processing done but no file, will not display file %s", dat_filename)
            self.last_dat = dat_filename
        else:
            if self.last_dat == dat_filename:
                return
            else:
                logger.info("processing done, file is %s", dat_filename)
                # Only display 1d images like XXXX/1d/<at least on char>.dat
                if re.match(r".*/1d/[^/]+\.dat$", dat_filename):
                    #DEBUG: get file size
                    if os.path.exists(dat_filename):
                        filesize = os.path.getsize(dat_filename)
                        print ">>> File info 1 %r  %s " % (filesize, type(filesize))
                        self.display1D(dat_filename)
                    else:
                        logger.warning("processing done but no file, will not display file %s", dat_filename)
                self.last_dat = dat_filename


    def collectProcessingLog(self, level, logmsg, notify):
        #TODO : DEBUG
        print ">>>>>>> CollectProcessingLog logmsg %r and level %d " % (logmsg, level)
        # Level 0 = info, Level 1 = Warning, Level 2 = Error 
        if level == 0:
            logmethod = logger.info
        elif level == 1:
            logmethod = logger.warning
        elif level == 2:
            logmethod = logger.error

        #TODO remove this hack ASAP (SO 9/7 12)
        ### HORRIBLE CODE
        if logmsg != self.lastCollectProcessingLog:
            for line in logmsg.split(os.linesep):
                logmethod(line.rstrip())
            if notify:
                self.messageDialog(level, logmsg)

        self.lastCollectProcessingLog = logmsg
        self._collectRobotDialog.addHistory(level, logmsg)


    def clearCurve(self):
        self.displayReset()

    def collectNewFrameChanged(self, pValue):
        filename0 = pValue.split(",")[0]
        if os.path.dirname(filename0).endswith("/raw"):
            directory = os.path.join(os.path.dirname(filename0)[:-4], "1d")
        else:
            directory = os.path.join(os.path.dirname(filename0), "1d")

        if self.__lastFrame is None or self.__lastFrame != pValue:
            self.__lastFrame = pValue
            if self._isCollecting:
                self.collectObj.triggerEDNA(filename0, oneway = True)
                message = "The frame '%s' was collected... (diode: %.3e, machine: %5.2f mA)" % (filename0, float(self._diodeCurrent), float(self._machineCurrent))
                logger.info(message)
                if self.robotCheckBox.isChecked() or self.ispybRobotCheckBox.isChecked():
                    self._collectRobotDialog.addHistory(0, message)

                self._currentFrame += 1

                self.setCollectionStatus("running")

                # Waiting for the file to appear
                t0 = time.time()
                fileFound = False
                while time.time() - t0 < 7:
                    #TODO: DEBUG - Before we check existence/size, do a small sleep
                    time.sleep(0.1)
                    if os.path.exists(filename0):
                        filesize = os.path.getsize(filename0)
                        if filesize > 4000000:
                            time.sleep(0.1)
                            # we got file
                            fileFound = True
                            print ">>> File info 3 %r  %s " % (filesize, type(filesize))
                            print "display1D: %r" % filename0
                            self.emit("displayItemChanged", filename0)
                            break
                    # before getting back, let us treat Qt events
                    QtGui.qApp.processEvents()
                if not fileFound:
                    timestr = str(time.time() - t0)
                    print ">>> No file 3 %s seen after %s seconds. We do not display it " % (filename0, timestr)

                if self._currentFrame == self._frameNumber:
                    splitList = os.path.basename(filename0).split("_")
                    # Take away last _ piece
                    filename1 = "_".join(splitList[:-1])
                    ave_filename = os.path.join(directory, filename1 + "_ave.dat")
                    #DEBUG: get file size
                    if os.path.exists(ave_filename):
                        filesize = os.path.getsize(ave_filename)
                        #TODO: DEBUG
                        print ">>> File info 4 %r  %s " % (filesize, type(filesize))
                        print "display1D: %r" % ave_filename
                        self.display1D(ave_filename)
                    else:
                        #TODO: DEBUG
                        print ">>> No file 4 %s seen. We do not display it " % ave_filename
            else:

                if os.path.exists(filename0):
                    if not filename0.endswith(".dat"):
                        self.emit("displayItemChanged", filename0)
                        fileBaseName = os.path.splitext(os.path.basename(filename0))[0]
                        filename1 = os.path.join(directory, fileBaseName + ".dat")
                        if os.path.exists(filename1):
                            print "display1D: %r" % filename1
                            self.display1D(filename1)




#           TODO: This is how put in a breakpoint 
#           import pdb; pdb.set_trace()
            if self._currentFrame == self._frameNumber:
                # data collection done = Last frame
                if self._isCollecting:
                    if self.__isTesting:
                        if self.SPECBusyTimer.isActive():
                            self.SPECBusyTimerTimeOut()
                        logger.info("The data collection is done!")
                        self.grayOut(False)
                        self.emit("grayOut", False)
                    else:
                        feedBackFlag = self._feedBackFlag
                        if self.robotCheckBox.isChecked():
                            self.setCollectionStatus("done")
                            self._feedBackFlag = False
                            self.__isTesting = False
                            logger.info("The data collection is done!")
                            self.grayOut(False)
                            self.emit("grayOut", False)
                        else:
                            if self.SPECBusyTimer.isActive():
                                self.SPECBusyTimerTimeOut()
                        if feedBackFlag:
                            if self.notifyCheckBox.isChecked():
                                Qt.QMessageBox.information(self.brick_widget, "Info", "\n                       The data collection is done!                                       \n")



    def beamLostChanged(self, pValue):
        if pValue != None and pValue != "":
            logger.warning("BEAM LOST: %s" % pValue)

    def checkBeamChanged(self, pValue):
        if pValue == 1:
            self.checkBeamBox.setChecked(True)
        else:
            self.checkBeamBox.setChecked(False)

    # When a macro in spec changes the value of SPEC_STATUS variable to busy
    def specStatusChanged(self, pValue):
        if pValue == "busy":
            self.setCollectionStatus("busy")
        else:
            self.setCollectionStatus("ready")

    def expertModeOnlyChanged(self, pValue):
        self.__expertModeOnly = pValue
        self.expert_mode(self.__expertMode)

    def expert_mode(self, expert):
        self.__expertMode = expert
        self.setWidgetState()

    def executeTestCollect(self):
        self.testPushButtonClicked()

    def display1D(self, pValue):

        if self.imageProxy is None:
            return
        try:
            self.imageProxy.load_files(str(pValue), oneway = True)
        except Exception, e:
            logger.error("Could not read file " + str(pValue))
            logger.error("Full Exception: " + str(e))

    def y_curves_data(self, pPeer):
        pass

    def erase_curve(self, pPeer):
        pass



    def collectObjectConnected(self, collect_obj):
        if collect_obj is not None:
            # we reconnected.. Let us put back light if out
            self.setButtonState(0)
            self.brick_widget.setEnabled(self.loginDone)
            self.collectObj = collect_obj
            self.collectObj.updateChannels(oneway = True)

    def connectedToEnergy(self, pPeer):
        if pPeer is None:
            self.energyControlObject = None
        else:
            if self.energyControlObject is None:
                self.energyControlObject = pPeer
                self.contact = True
                # read energy when getting contact with CO Object
                self.__energy = float(self.energyControlObject.getEnergy())
                wavelength = self.hcOverE / self.__energy
                wavelengthStr = "%.4f" % wavelength
                self._waveLengthStr = wavelengthStr
                # Set energy when connected
                self.energyControlObject.setEnergy(self.__energy)



    def energyChanged(self, pValue):
        if pValue is not None:
            self.__energy = float(pValue)
            wavelength = self.hcOverE / self.__energy
            wavelengthStr = "%.4f" % wavelength
            self._waveLengthStr = wavelengthStr


    def validParameters(self):

        # This routine checks:
        #   - that there is at least one sample defined and active
        #   - that there are not two buffers with same name
        #   - that the buffer assigned to a sample is existing
        #

        self.robotParams = self.getCollectPars(robot = 1)
        valid = True

        if len(self.robotParams["sampleList"]) == 0:
            valid = False
            Qt.QMessageBox.information(self.brick_widget, "Warning", "No sample to collect in robot!")
        else:
            buffernames = []

            for myBuffer in self.robotParams["bufferList"]:
                # NOW myBuffers of same name are allowed.  But we should do something about it during collect

                if myBuffer not in buffernames:
                    buffernames.append(myBuffer["buffername"])

            for sample in self.robotParams["sampleList"]:
                if sample["buffername"] not in buffernames:
                    Qt.QMessageBox.information(self.brick_widget, "Warning", "Sample with no buffer assignment or buffer name does not exist")
                    valid = False
                    break

        return valid

    def getRadiationRelativeLinear(self):
        val = float(self.radiationRelativeDoubleSpinBox.value())
        if val == 0.:
            return 0
        else:
            return 10 ** (-val)

    def getRadiationAbsoluteLinear(self):
        val = float(self.radiationAbsoluteDoubleSpinBox.value())
        if val == 0.:
            return 0
        else:
            return 10 ** (-val)



    def getFileInfo(self):
        generalParsWidget = self
        filepars = CollectPars()
        filepars.prefix = generalParsWidget.prefixLineEdit.text()
        filepars.runNumber = generalParsWidget.runNumberSpinBox.value()
        filepars.frameNumber = generalParsWidget.frameNumberSpinBox.value()
        return filepars

    def getCollectPars(self, robot = 1):
        if robot:
            # return a dictionary
            collectpars = { "directory": str(self.directoryLineEdit.text()),
                            "prefix": str(self.prefixLineEdit.text()),
                            "runNumber": int(self.runNumberSpinBox.value()),
                            "frameNumber": int(self.frameNumberSpinBox.value()),
                            "timePerFrame": int(self.timePerFrameSpinBox.value()),
                            "currentConcentration": float(self.concentrationDoubleSpinBox.value()),
                            "currentComments":str(self.commentsLineEdit.text()),
                            "currentCode": str(self.codeLineEdit.text()),
                            "mask":str(self.maskLineEdit.text()),
                            "detectorDistance": float(self.detectorDistanceDoubleSpinBox.value()),
                            "waveLength": float(self._waveLengthStr),
                            "pixelSizeX":float(self.pixelSizeXDoubleSpinBox.value()),
                            "pixelSizeY":float(self.pixelSizeYDoubleSpinBox.value()),
                            "beamCenterX": int(self.beamCenterXSpinBox.value()),
                            "beamCenterY": int(self.beamCenterYSpinBox.value()),
                            "normalisation": float(self.normalisationDoubleSpinBox.value()),
                            "radiationChecked":self.radiationCheckBox.isChecked(),
                            "radiationRelative": self.getRadiationRelativeLinear(),
                            "radiationAbsolute": self.getRadiationAbsoluteLinear(),
                            "SEUTemperature": self.seuTemperature}

            robotpars = { "sampleType": str(self._collectRobotDialog.sampleTypeComboBox.currentText()),
                          "storageTemperature": float(self._collectRobotDialog.storageTemperatureDoubleSpinBox.value()),
                          "extraFlowTime": int(self._collectRobotDialog.extraFlowTimeSpinBox.value()),
                          "optimization": str(self._collectRobotDialog.optimizationComboBox.currentIndex()),
                          "optimizationText": str(self._collectRobotDialog.optimizationComboBox.currentText()),
                          "initialCleaning": self._collectRobotDialog.initialCleaningCheckBox.isChecked(),
                          "bufferMode": str(self._collectRobotDialog.bufferModeComboBox.currentIndex()),
                          "bufferFirst": False,
                          "bufferBefore": False,
                          "bufferAfter": False }

            filepars = { "runNumber": self.runNumberSpinBox.value(),
                         "frameNumber": self.frameNumberSpinBox.value() }
            collectpars.update(filepars)

            if robotpars["bufferMode"] == '0':
                robotpars.update({ "bufferFirst":True, "bufferAfter": True })
            elif robotpars["bufferMode"] == '1':
                robotpars["bufferBefore"] = True
            elif robotpars["bufferMode"] == '2':
                robotpars["bufferAfter"] = True

            robotpars["optimSEUtemp"] = False
            robotpars["optimCodeAndSEU"] = False
            if robotpars["optimization"] == 1:
                robotpars["optimSEUtemp"] = True
            elif robotpars["optimization"] == 2:
                robotpars["optimCodeAndSEU"] = True

            bufferList = []
            sampleList = []
            robotpars.update({ "bufferList": bufferList, "sampleList": sampleList })

            for i in range(0, self._collectRobotDialog.tableWidget.rowCount()):
                sample = self._collectRobotDialog.getSampleRow(i)

                if sample.enable:
                    if sample.isBuffer():
                        bufferList.append(sample.__dict__)
                    else:
                        sampleList.append(sample.__dict__)

            for sample in sampleList:
                sample["buffer"] = []
                if len(bufferList) == 1:   # if there is one and only one buffer defined dont look at name. assign
                    sample["buffer"].append(bufferList[0])
                else:
                    for bufferEntry in bufferList:
                        if bufferEntry["buffername"] == sample["buffername"]:
                            sample["buffer"].append(bufferEntry)
            if robotpars["optimSEUtemp"]:
                sampleList.sort(cmpSEUtemp)
            elif robotpars["optimCodeAndSEU"]:
                sampleList.sort(cmpCodeAndSEU)

            collectpars.update(robotpars)

            collectpars["flowTime"] = collectpars["timePerFrame"] * collectpars["frameNumber"] + collectpars["extraFlowTime"]
            # always processData
            collectpars["processData"] = 1
        else:
            collectpars = CollectPars()

            logger.info("   - reading collection parameters")
            #
            #  I should actually separate values so that each widget represents a certain data in a clear way
            #
            collectpars.directory = self.directoryLineEdit.text()
            collectpars.prefix = self.prefixLineEdit.text()
            collectpars.runNumber = self.runNumberSpinBox.value()
            collectpars.frameNumber = self.frameNumberSpinBox.value()
            collectpars.timePerFrame = self.timePerFrameSpinBox.value()
            collectpars.currentConcentration = self.concentrationDoubleSpinBox.value()
            collectpars.currentComments = self.commentsLineEdit.text()
            collectpars.currentCode = self.codeLineEdit.text()


            collectpars.mask = self.maskLineEdit.text()
            collectpars.detectorDistance = self.detectorDistanceDoubleSpinBox.value()
            collectpars.waveLength = self._waveLengthStr
            collectpars.pixelSizeX = self.pixelSizeXDoubleSpinBox.value()
            collectpars.pixelSizeY = self.pixelSizeYDoubleSpinBox.value()
            collectpars.beamCenterX = self.beamCenterXSpinBox.value()
            collectpars.beamCenterY = self.beamCenterYSpinBox.value()
            collectpars.normalisation = self.normalisationDoubleSpinBox.value()
            collectpars.radiationChecked = self.radiationCheckBox.isChecked()
            collectpars.radiationRelative = self.getRadiationRelativeLinear()
            collectpars.radiationAbsolute = self.getRadiationAbsoluteLinear()
            collectpars.SEUTemperature = self.seuTemperature
            collectpars.storageTemperature = self.storageTemperature

            # always process data
            collectpars.processData = 1


            #=================================================
            #  Calculate total flow time
            #=================================================
            collectpars.flowTime = collectpars.timePerFrame * collectpars.frameNumber + collectpars.extraFlowTime

        return collectpars

    #def delete(self):
    #    self._collectRobot.terminate()

    def showHideBeamlineParams(self, pValue = None):

        if self.showingBLParams:
            self.showingBLParams = 0
            self.blParamsButton.setText("Show Beamline Parameters")
            self.maskLineEdit.hide()
            self.maskDirectoryPushButton.hide()
            self.maskDisplayPushButton.hide()
            self.detectorDistanceDoubleSpinBox.hide()
            self.pixelSizeXDoubleSpinBox.hide()
            self.pixelSizeYDoubleSpinBox.hide()
            self.beamCenterXSpinBox.hide()
            self.beamCenterYSpinBox.hide()
            self.normalisationDoubleSpinBox.hide()
            self.maskLabel.hide()
            self.detectorDistanceLabel.hide()
            self.pixelSizeLabel.hide()
            self.beamCenterLabel.hide()
            self.normalisationLabel.hide()
        else:
            self.blParamsButton.setText("Hide Beamline Parameters")
            self.showingBLParams = 1
            self.maskLineEdit.show()
            self.maskDirectoryPushButton.show()
            self.maskDisplayPushButton.show()
            self.detectorDistanceDoubleSpinBox.show()
            self.pixelSizeXDoubleSpinBox.show()
            self.pixelSizeYDoubleSpinBox.show()
            self.beamCenterXSpinBox.show()
            self.beamCenterYSpinBox.show()
            self.normalisationDoubleSpinBox.show()
            self.maskLabel.show()
            self.detectorDistanceLabel.show()
            self.pixelSizeLabel.show()
            self.beamCenterLabel.show()
            self.normalisationLabel.show()

    def readOnlyCheckBoxToggled(self, pValue):

        self.directoryLineEdit.setEnabled(not pValue)
        self.directoryPushButton.setEnabled(not pValue)
        self.prefixLineEdit.setEnabled(not pValue)
        self.runNumberSpinBox.setEnabled(not pValue)
        self.frameNumberSpinBox.setEnabled(not pValue)
        self.timePerFrameSpinBox.setEnabled(not pValue)
        self.maskLineEdit.setEnabled(not pValue and (not self.__expertModeOnly or self.__expertMode))
        self.maskDirectoryPushButton.setEnabled(not pValue and (not self.__expertModeOnly or self.__expertMode))
        self.maskDisplayPushButton.setEnabled(not pValue and (not self.__expertModeOnly or self.__expertMode))
        self.detectorDistanceDoubleSpinBox.setEnabled(not pValue and (not self.__expertModeOnly or self.__expertMode))
        self.pixelSizeXDoubleSpinBox.setEnabled(not pValue and (not self.__expertModeOnly or self.__expertMode))
        self.pixelSizeYDoubleSpinBox.setEnabled(not pValue and (not self.__expertModeOnly or self.__expertMode))
        self.beamCenterXSpinBox.setEnabled(not pValue and (not self.__expertModeOnly or self.__expertMode))
        self.beamCenterYSpinBox.setEnabled(not pValue and (not self.__expertModeOnly or self.__expertMode))
        self.normalisationDoubleSpinBox.setEnabled(not pValue and (not self.__expertModeOnly or self.__expertMode))
        self.radiationCheckBox.setEnabled(not pValue)
        self.radiationRelativeDoubleSpinBox.setEnabled(not pValue and self.radiationCheckBox.isChecked())
        self.radiationAbsoluteDoubleSpinBox.setEnabled(not pValue and self.radiationCheckBox.isChecked())

    def directoryLineEditChanged(self, pValue):
        if self._isCollecting:
            return

        self.__validParameters[0] = pValue is not None and os.path.exists(pValue) and not os.path.isfile(pValue)

        if self.__validParameters[0]:
            self.directoryLineEdit.setProperty("valid", "true")
        else:
            self.directoryLineEdit.setProperty("valid", "false")

        self.testPushButton.setEnabled(False not in self.__validParameters)
        self.collectPushButton.setEnabled(False not in self.__validParameters)

        self.brick_widget.setStyleSheet(self.brick_widget.styleSheet())

    def directoryPushButtonClicked(self):
        directory = QtGui.QFileDialog.getExistingDirectory(self.brick_widget, "Choose a directory", self.directoryLineEdit.text())
        if directory != "":
            self.directoryLineEdit.setText(directory)

    def prefixLineEditChanged(self, pValue):
        if self._isCollecting:
            return

        self.__validParameters[1] = pValue is not None and self.prefixLineEdit.hasAcceptableInput()
        if self.__validParameters[1]:
            self.prefixLineEdit.setProperty("valid", "true")
        else:
            self.prefixLineEdit.setProperty("valid", "false")

        self.testPushButton.setEnabled   (False not in self.__validParameters)
        self.collectPushButton.setEnabled(False not in self.__validParameters)

        self.brick_widget.setStyleSheet(self.brick_widget.styleSheet())

    def maskLineEditChanged(self, pValue):
        if self._isCollecting:
            return

        if pValue is not None:
            pValue = str(pValue)
            if os.path.isfile(pValue):
                i = pValue.rfind(".")
                if i != -1 and pValue[i - 4:i] == "_msk" and pValue[i + 1:] == "edf" and pValue.find(" ") == -1:
                    flag = 0
                else:
                    flag = 1
            else:
                flag = 2
        else:
            flag = 2
        if flag == 0:
            self.__validParameters[2] = True
            self.maskLineEdit.setProperty("valid", "true")
        elif flag == 1:
            self.__validParameters[2] = True
            self.maskLineEdit.setProperty("valid", "true")
        else:
            self.__validParameters[2] = False
            self.maskLineEdit.setProperty("valid", "false")

        self.maskDisplayPushButton.setEnabled(self.__validParameters[2] and (not self.__expertModeOnly or self.__expertMode))
        self.testPushButton.setEnabled(False not in self.__validParameters)
        self.collectPushButton.setEnabled(False not in self.__validParameters)

        self.brick_widget.setStyleSheet(self.brick_widget.styleSheet())


    def maskDirectoryPushButtonClicked(self):
        qFileDialog = QtGui.QFileDialog(self.brick_widget, "Choose a mask file", self.maskLineEdit.text())
        qFileDialog.setAcceptMode(QtGui.QFileDialog.AcceptOpen)
        qFileDialog.setFilters(["ESRF Data Format (*.edf)"])
        if qFileDialog.exec_():
            self.maskLineEdit.setText(str(qFileDialog.selectedFiles()[0]))


    def maskDisplayPushButtonClicked(self):
        self.emit("displayItemChanged", str(self.maskLineEdit.text()))

    def radiationCheckBoxToggled(self, pValue):
        if pValue:
            if self.isHPLC:
                Qt.QMessageBox.critical(self.brick_widget, "Error", "You can not do Radiation Damage when HPLC is selected", Qt.QMessageBox.Ok)
                self.radiationCheckBox.setChecked(False)
                return
        self.radiationRelativeDoubleSpinBox.setEnabled(pValue)
        self.radiationAbsoluteDoubleSpinBox.setEnabled(pValue)

# TODO: DEBUG
#    def spectroCheckBoxToggled(self, pValue):
#        self.extinctionCoefficentDoubleSpinBox.setEnabled(pValue)

    def pilatusCheckBoxToggled(self, pValue):
        if not pValue:
            # not follow value
            if self.energyControlObject is not None:
                self.energyControlObject.energyAdjustPilatus(False)
            if self.collectObj is not None:
                self.collectObj.blockEnergyAdjust(True)
        else:
            # normal behavior
            if self.energyControlObject is not None:
                self.energyControlObject.energyAdjustPilatus(True)
            if self.collectObj is not None:
                self.collectObj.blockEnergyAdjust(False)
            # Put back Energy if connected
            if self.energyControlObject is not None:
                self.__energy = float(self.energyControlObject.getEnergy())
                self.energyControlObject.setEnergy(self.__energy)

    def robotCheckBoxToggled(self, pValue):

        if pValue:
            # Inform that manual and ISPyB are not compatible
            if self.ispybRobotCheckBox.isChecked():
                Qt.QMessageBox.critical(self.brick_widget, "Error", "You can not collect data manually and with ISpYB", Qt.QMessageBox.Ok)
                self.robotCheckBox.setChecked(False)
                return
            # We put it on.. Inform user that Collect with Robot is incompatible with HPLC
            if self.isHPLC:
                Qt.QMessageBox.critical(self.brick_widget, "Error", "You can not do a Robot Collect when HPLC is selected", Qt.QMessageBox.Ok)
                self.robotCheckBox.setChecked(False)
                return
            self._ispybCollect = False
            self._collectRobotDialog = CollectRobotDialog(self)
            if self._collectRobotDialog.isVisible():
                self._collectRobotDialog.activateWindow()
                self._collectRobotDialog.raise_()
            else:
                self._collectRobotDialog.show()
        else:
            if not self._collectRobotDialog is None:
                self._collectRobotDialog.hide()
            self._collectRobotDialog = None

    def ispybRobotCheckBoxToggled(self, pValue):
        if pValue:
            # Inform that manual and ISPyB are not compatible
            if self.robotCheckBox.isChecked():
                Qt.QMessageBox.critical(self.brick_widget, "Error", "You can not collect data manually and with ISpYB", Qt.QMessageBox.Ok)
                self.ispybRobotCheckBox.setChecked(False)
                return
            # We put it on.. Inform user that Collect with Robot is incompatible with HPLC
            if self.isHPLC:
                Qt.QMessageBox.critical(self.brick_widget, "Error", "You can not do a Robot Collect when HPLC is selected", Qt.QMessageBox.Ok)
                self.ispybRobotCheckBox.setChecked(False)
                return
            self._ispybCollect = True
            self._collectRobotDialog = ISPyBCollectRobotDialog(self)
            if self._collectRobotDialog.isVisible():
                self._collectRobotDialog.activateWindow()
                self._collectRobotDialog.raise_()
            else:
                self._collectRobotDialog.show()
        else:
            if not self._collectRobotDialog is None:
                self._collectRobotDialog.hide()
            self._collectRobotDialog = None


    def CheckBoxToggledHPLC(self, pValue):
        v = bool(pValue)
        self.isHPLC = v
        if v:
            if self.robotCheckBox.isChecked():
                Qt.QMessageBox.critical(self.brick_widget, "Error", "You can not do a HPLC Collect when Robot is selected", Qt.QMessageBox.Ok)
                self.hplcCheckBox.setChecked(False)
                self.isHPLC = False
                return
            if self.radiationCheckBox.isChecked():
                Qt.QMessageBox.critical(self.brick_widget, "Error", "You can not do a HPLC Collect when Radiation damage is selected", Qt.QMessageBox.Ok)
                self.hplcCheckBox.setChecked(False)
                self.isHPLC = False
                return
        self.collectObj.setHPLC(v)


    def checkBeamBoxToggled(self, pValue):
        self.collectObj.setCheckBeam(pValue)

    def checkPilausReady(self):
        # Check if pilatus is ready
        #TODO: DEBUG
        if self.energyControlObject is None:
            print ">>> No BsxCUBE contact with Pilatus"
        else:
            print ">> info on self.energyControlObject"
            print dir(self.energyControlObject)
            try:
                testPilatus = self.energyControlObject.pilatusReady()
            except:
                raise
            print ">>> Testing %s " % self.energyControlObject.pilatusReady()
        if (self.energyControlObject is None) or ("pilatusReady" not in dir(self.energyControlObject)):
            if self.contact:
                logger.warning("Lost contact with Pilatus")
            self.contact = False
            return False
        else:
            if not self.contact:
                logger.warning("Found Pilatus again")
                self.contact = True
        if not self.energyControlObject.pilatusReady():
            Qt.QMessageBox.critical(self.brick_widget, "Error", "Pilatus detector is busy.. Try later or try restarting the Pilatus", Qt.QMessageBox.Ok)
            return False
        return True

    def testPushButtonClicked(self):
        if not self.checkPilausReady():
            return
        self.grayOut(True)
        self.emit("grayOut", True)
        # For test allow 30s
        self.SPECBusyTimer.start(30000)

        self.startCollection(mode = 'test')

        self._feedBackFlag = False
        self._abortFlag = False
        self._frameNumber = 1
        self._currentFrame = 0

        self.getObject("collect").testCollect(str(self.directoryLineEdit.text()),
                                               str(self.prefixLineEdit.text()),
                                               self.runNumberSpinBox.value(),
                                               self.concentrationDoubleSpinBox.value(),
                                               str(self.commentsLineEdit.text()),
                                               str(self.codeLineEdit.text()),
                                               str(self.maskLineEdit.text()),
                                               self.detectorDistanceDoubleSpinBox.value(),
                                               self._waveLengthStr,
                                               self.pixelSizeXDoubleSpinBox.value(),
                                               self.pixelSizeYDoubleSpinBox.value(),
                                               self.beamCenterXSpinBox.value(),
                                               self.beamCenterYSpinBox.value(),
                                               self.normalisationDoubleSpinBox.value())


    def collectPushButtonClicked(self):
        if not self.checkPilausReady():
            return
        if not self.robotCheckBox.isChecked() or self.validParameters():
            # Check Temperature changes are not too big when doing robot collection
            if self.robotCheckBox.isChecked():
                # check temperature moving upwards - Storage temperature first - 1 degree move ...
                oldTemp = 100.0
                if self.scObject.getSampleStorageTemperature() != "":
                    oldTemp = float(self.scObject.getSampleStorageTemperature())
                else:
                    logger.warning("Can not get current Storage temperature from Sample Changer")
                newTemp = float(self._collectRobotDialog.storageTemperatureDoubleSpinBox.value())
                if newTemp > (oldTemp + 1.0) :
                    answer = Qt.QMessageBox.question(self.brick_widget, "Question", \
                                 "Do you want to increase the Storage Temp from " + "%.1f C" % oldTemp + \
                                 " to " + "%.1f C" % newTemp + "?\nIt will take time to cool down later.", \
                                 Qt.QMessageBox.Yes, Qt.QMessageBox.No, Qt.QMessageBox.NoButton)
                    if answer == Qt.QMessageBox.No:
                        return
                # Check SEU Temperatures (max) - 4 degree move max...
                oldTemp = 100.0
                if self.scObject.getSEUTemperature() != "":
                    oldTemp = float(self.scObject.getSEUTemperature())
                else:
                    logger.warning("Can not get current SEU temperature from Sample Changer")
                newTemp = 0.0
                for checkSample in self.robotParams["sampleList"]:
                    if newTemp < checkSample["SEUtemperature"]:
                        newTemp = checkSample["SEUtemperature"]
                if newTemp > (oldTemp + 4.0):
                    answer = Qt.QMessageBox.question(self.brick_widget, "Question", \
                                 "Do you want to increase the SEU Temp from " + "%.1f C" % oldTemp + \
                                 " to " + "%.1f C" % newTemp + "?\nIt will take time to cool down later.", \
                                 Qt.QMessageBox.Yes, Qt.QMessageBox.No, Qt.QMessageBox.NoButton)
                    if answer == Qt.QMessageBox.No:
                        return
            self.displayReset()
            directory = str(self.directoryLineEdit.text()) + "/raw"
            runNumber = "%03d" % self.runNumberSpinBox.value()

            flag = True

            if os.path.isdir(directory):
                for filename in os.listdir(directory):
                    if os.path.isfile(os.path.join(directory, filename)):
                        if filename.startswith(str(self.prefixLineEdit.text())) and \
                           (filename.split("_")[-1] != "00000.edf") \
                           and (filename.split("_")[-1] != "00000.xml") \
                           and (filename.split(".")[-1] != "h5") \
                           and (filename.split(".")[-1] != "json"):
                            # Check if we have a run number higher than the requested run number:
                            try:
                                existingRunNumber = filename.split("_")[-2]
                                if int(existingRunNumber) >= int(runNumber):
                                    logger.info("Existing run number %r is higher than requested run number %r" % (existingRunNumber, runNumber))
                                    flag = False
                                    break
                            except IndexError:
                                #TODO: DEBUG
                                print ">>> got totally unexpected filename %s " % filename
                                Qt.QMessageBox.critical(self.brick_widget, "Error", "Something wrong with the directory, prefix or something else. Please rewrite run info", Qt.QMessageBox.Ok)
                                raise RuntimeError, "Creating of filename from info not possible"
                            except ValueError:
                                #TODO: DEBUG
                                print ">>> got totally unexpected filename %s " % filename
                                Qt.QMessageBox.critical(self.brick_widget, "Error", "Something wrong with the directory, prefix or something else. Please rewrite run info", Qt.QMessageBox.Ok)
                                raise RuntimeError, "Creating of filename from info not possible"

            if not flag:
                flag = (Qt.QMessageBox.question(self.brick_widget, "Warning", \
                                "The run '%s' with prefix '%s' has run numbers already existing in the directory '%s' that might be overwritten. Proceed?" % \
                                (runNumber, self.prefixLineEdit.text(), self.directoryLineEdit.text()), \
                                Qt.QMessageBox.Yes, Qt.QMessageBox.No, Qt.QMessageBox.NoButton) == Qt.QMessageBox.Yes)

            if not flag:
                return

            if self.robotCheckBox.isChecked():
                self.startCollectWithRobot()
            else:
                if not (not self.__expertModeOnly or self.__expertMode):

                    if self.__currentConcentration is not None and self.__currentConcentration == self.concentrationDoubleSpinBox.value():
                        flag = (Qt.QMessageBox.question(self.brick_widget, \
                                    "Warning", "The value of the concentration '%s' is the same than the previous collection. Continue?" % \
                                                  self.concentrationDoubleSpinBox.value(), \
                                                  Qt.QMessageBox.Yes, \
                                                  Qt.QMessageBox.No, Qt.QMessageBox.NoButton) == Qt.QMessageBox.Yes)

                if flag:
                    self.startCollectWithoutRobot()

    def setCollectionStatus(self, status):
        self.collectionStatus = status
        if status == "running":
            self._isCollecting = True
            self.abortPushButton.setEnabled(True)
            self.abortPushButton.setProperty("abortactive", "true")
        else:
            self._isCollecting = False
            self.abortPushButton.setEnabled(False)
            self.abortPushButton.setProperty("abortactive", "false")

        self.brick_widget.setStyleSheet(self.brick_widget.styleSheet())
        self.collectStatus.setText(status)
        self.collectStatus.setProperty("status", status)

        self.brick_widget.setStyleSheet(self.brick_widget.styleSheet())

    def startCollectWithRobot(self):
        # starts a series of individual collections
        #  blocks widget or whatever during the time of the collection
        self.grayOut(True)
        self.emit("grayOut", True)
        self._abortFlag = False
        self.startCollection(mode = "with robot")
        self._collectRobotDialog.clearHistory()
        self.getObject("collect").collectWithRobot(self.getCollectPars(), oneway = True)


    def grayOut(self, pValue):
        # if True - gray out if False - allow all buttons to be manipulated
        if pValue is not None:
            if pValue is True:
                self.setButtonState(1)
            else:
                self.setButtonState(0)

    def machineCurrentChanged(self, pValue):
        self._machineCurrent = pValue

    def newSASUrl(self, url):
        #TODO: DEBUG
        print "- newSASUrl - got url %s " % url
        if self.sasWebObject is not None:
            #TODO: DEBUG
            print "set URL on object"
            self.sasWebObject.setUrl(url)

    def transmissionChanged(self, percentage):
        pass

    def endCollectWithRobot(self):
        # should unblock things here at the end
        pass

    def startCollectWithoutRobot(self):
        # starts a single collection 
        self.grayOut(True)
        self.emit("grayOut", True)
        self._abortFlag = False

        # always process
        processData = 1

        self.startCollection(mode = "no robot")

        self.collect(1,
                      str(self.directoryLineEdit.text()),
                      str(self.prefixLineEdit.text()),
                      self.runNumberSpinBox.value(),
                      self.frameNumberSpinBox.value(),
                      self.timePerFrameSpinBox.value(),
                      self.concentrationDoubleSpinBox.value(),
                      str(self.commentsLineEdit.text()),
                      str(self.codeLineEdit.text()),
                      str(self.maskLineEdit.text()),
                      self.detectorDistanceDoubleSpinBox.value(),
                      self._waveLengthStr,
                      self.pixelSizeXDoubleSpinBox.value(),
                      self.pixelSizeYDoubleSpinBox.value(),
                      self.beamCenterXSpinBox.value(),
                      self.beamCenterYSpinBox.value(),
                      self.normalisationDoubleSpinBox.value(),
                      self.radiationCheckBox.isChecked(),
                      self.getRadiationAbsoluteLinear(),
                      self.getRadiationRelativeLinear(),
                      processData,
                      self.seuTemperature,
                      self.storageTemperature)

        self.__currentConcentration = self.concentrationDoubleSpinBox.value()

    def startCollection(self, mode = "normal"):

        self.setCollectionStatus("running")

        if mode == "test":
            self.__isTesting = True

        logger.info("   - collection started (mode: %s)" % mode)

    def collectDone(self):
        #TODO : DEBUG
        # Workaround for framework 4 sending collectDone signal five times...
        ##print ">>>>>>>>>>>>> in collectDone %s " % self.collectionStatus
        if self.collectionStatus != "done":
            self.setCollectionStatus("done")
            self.grayOut(False)
            self.emit("grayOut", False)
            if self.notifyCheckBox.isChecked():
                #TODO: Can we "spawn this"  to avoid stopping updating the 
                Qt.QMessageBox.information(self.brick_widget, "Info", "\n                       The data collection is done!                                       \n")


    def collect(self, pFeedBackFlag, pDirectory, pPrefix, pRunNumber, pFrameNumber , \
                pTimePerFrame, pConcentration, pComments, pCode, pMaskFile, pDetectorDistance, \
                pWaveLength, pPixelSizeX, pPixelSizeY, pBeamCenterX, pBeamCenterY, pNormalisation, \
                pRadiationChecked, pRadiationAbsolute, pRadiationRelative, pProcessData, pSEUTemperature, pStorageTemperature):
        if not self.robotCheckBox.isChecked():
            self.SPECBusyTimer.start(pFrameNumber * (pTimePerFrame + 5) * 1000 + 12000)

        self.__isTesting = False
        self._feedBackFlag = (pFeedBackFlag == 1)
        self._frameNumber = pFrameNumber
        self._currentFrame = 0
        self._currentCurve = 0
        self.getObject("collect").collect(str(pDirectory),
                                          str(pPrefix),
                                          pRunNumber,
                                          pFrameNumber,
                                          pTimePerFrame,
                                          pConcentration,
                                          str(pComments),
                                          str(pCode),
                                          str(pMaskFile),
                                          pDetectorDistance,
                                          pWaveLength,
                                          pPixelSizeX,
                                          pPixelSizeY,
                                          pBeamCenterX,
                                          pBeamCenterY,
                                          pNormalisation,
                                          pRadiationChecked,
                                          pRadiationAbsolute,
                                          pRadiationRelative,
                                          pProcessData,
                                          pSEUTemperature,
                                          pStorageTemperature)


    def displayReset(self):
        self.emit("displayResetChanged")
        if self.imageProxy is None:
            return
        try:
            self.imageProxy.erase_curves()
        except Exception, e:
            logger.error("Full Exception: " + str(e))

    def messageDialog(self, pType, pMessage):
        if pType == 0:
            Qt.QMessageBox.information(self.brick_widget, "Info", pMessage)
        else:
            Qt.QMessageBox.critical(self.brick_widget, "Error", pMessage)

    def showMessage(self, pLevel, pMessage, notify = 0):
        if pLevel == 0:
            logging.info(pMessage)
        elif pLevel == 1:
            logging.warning(pMessage)
        elif pLevel == 2:
            logging.error(pMessage)
        self._collectRobotDialog.addHistory(pLevel, pMessage)

        if notify:
            self.messageDialog(pLevel, pMessage)


    def abortPushButtonClicked(self):
        if self.robotCheckBox.isChecked():
            answer = Qt.QMessageBox.question(self.brick_widget, "Info", "Do you want to abort the ongoing data collection?", Qt.QMessageBox.Yes, Qt.QMessageBox.No, Qt.QMessageBox.NoButton)
            if answer == Qt.QMessageBox.No:
                return

        logger.info("Aborting!")
        logger.warning("Wait for current action to finish...")

        self._abortFlag = True

        if self.__isTesting:
            self.getObject("collect").testCollectAbort(oneway = True)
        else:
            self.getObject("collect").collectAbort(oneway = True)

        #if self.robotCheckBox.isChecked():
        #   self._collectRobot.abort()

        #
        # Stop all timers 
        #
        self.SPECBusyTimerTimeOut()

        for timer in self._curveList:
            timer.stop()

        self.setCollectionStatus("aborting")
        self._curveList = []

        answer = Qt.QMessageBox.question(self.brick_widget, "Info", "Please wait for current action to finish", Qt.QMessageBox.Yes, Qt.QMessageBox.No, Qt.QMessageBox.NoButton)

    def setWidgetState(self):

        enabled = (not self.__expertModeOnly or self.__expertMode) and (not self.readOnlyCheckBox.isChecked())


        self.maskLineEdit.setEnabled(enabled)
        self.maskDirectoryPushButton.setEnabled(enabled)
        self.maskDisplayPushButton.setEnabled(enabled and self.__validParameters[2])
        self.detectorDistanceDoubleSpinBox.setEnabled(enabled)
        self.pixelSizeXDoubleSpinBox.setEnabled(enabled)
        self.pixelSizeYDoubleSpinBox.setEnabled(enabled)
        self.beamCenterXSpinBox.setEnabled(enabled)
        self.beamCenterYSpinBox.setEnabled(enabled)
        self.normalisationDoubleSpinBox.setEnabled(enabled)

    def setButtonState(self, pOption):
        widgets = (self.readOnlyCheckBox, \
                   self.directoryLineEdit, \
                   self.directoryPushButton, \
                   self.prefixLineEdit, \
                   self.runNumberSpinBox,
                   self.frameNumberSpinBox, \
                   self.timePerFrameSpinBox, \
                   self.concentrationDoubleSpinBox, \
                   self.commentsLineEdit, \
                   self.codeLineEdit, \
                   self.blParamsButton, \
                   self.maskLineEdit, \
                   self.maskDirectoryPushButton, \
                   self.maskDisplayPushButton, \
                   self.detectorDistanceDoubleSpinBox, \
                   self.pixelSizeXDoubleSpinBox, \
                   self.pixelSizeYDoubleSpinBox, \
                   self.beamCenterXSpinBox, \
                   self.beamCenterYSpinBox, \
                   self.normalisationDoubleSpinBox, \
                   self.radiationCheckBox, \
                   self.radiationRelativeDoubleSpinBox, \
                   self.radiationAbsoluteDoubleSpinBox, \
                   self.pilatusCheckBox, \
                   self.notifyCheckBox, \
                   self.checkBeamBox, \
                   self.testPushButton, \
                   self.collectPushButton, \
                   self.robotCheckBox, \
                   self.testPushButton, \
                   self.abortPushButton)

        def enable_widgets(*args):
            if len(args) == 1:
                for widget in widgets:
                    widget.setEnabled(args[0])
            else:
                for i in range(len(widgets)):
                    widgets[i].setEnabled(args[i])
        if pOption == 0:     # normal      
            enable_widgets(True)
            self.abortPushButton.setEnabled(False)
        elif pOption == 1:   # collecting
            enable_widgets(False)
            self.abortPushButton.setEnabled(True)

        if self.abortPushButton.isEnabled():
            self.abortPushButton.setProperty("abortactive", "true")
        else:
            self.abortPushButton.setProperty("abortactive", "false")

        self.brick_widget.setStyleSheet(self.brick_widget.styleSheet())

    def SPECBusyTimerTimeOut(self):
        #
        # this should be done otherwise.  Checking the status of the spec ready channel
        #
        self.SPECBusyTimer.stop()
        self.setCollectionStatus("done")

        self._feedBackFlag = False
        self.__isTesting = False
        self.grayOut(False)
        self.emit("grayOut", False)

        if not self._abortFlag and self._currentFrame < self._frameNumber:
            logger.warning("The frame was not collected or didn't appear on time! (%d,%d)" % \
                            (self._currentFrame, self._frameNumber))

    def getFilenameDetails(self, pFilename):
        pFilename = str(pFilename)
        i = pFilename.rfind(".")
        if i == -1:
            myFile = pFilename
            extension = ""
        else:
            myFile = pFilename[:i]
            extension = pFilename[i + 1:]
        items = myFile.split("_")
        prefix = items[0]
        run = ""
        frame = ""
        extra = ""
        i = len(items)
        j = 1
        while j < i:
            if items[j].isdigit():
                run = items[j]
                j += 1
                break
            else:
                prefix.join("_".join(items[j]))
                j += 1
        if j < i:
            if items[j].isdigit():
                frame = items[j]
                j += 1
            while j < i:
                if extra == "":
                    extra = items[j]
                else:
                    extra.join("_".join(items[j]))
                j += 1

        return prefix, run, frame, extra, extension
