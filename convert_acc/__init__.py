# Filename: __init__.py

"""Visualization and conversion of accelerometer data to velocity and displacement using Python and PyQt5."""
import sys
import os
import subprocess
import time
from shutil import copy
import logging

import pandas as pd
from scipy.signal import butter, lfilter, detrend
from fpdf import FPDF
from PyPDF2 import PdfFileMerger
from PyQt5.QtWidgets import QApplication
from PyQt5.QtWidgets import QMainWindow
from PyQt5.QtWidgets import QWidget
from PyQt5.QtWidgets import QLineEdit
from PyQt5.QtWidgets import QPushButton
from PyQt5.QtWidgets import QVBoxLayout
from PyQt5.QtWidgets import QLabel
from PyQt5.QtWidgets import QButtonGroup
from PyQt5.QtWidgets import QRadioButton
from PyQt5.QtWidgets import QScrollArea

from PyQt5 import QtWebEngineWidgets
# from PyQt5.QtWidgets import QDialog
# from PyQt5.QtWidgets import QProgressBar
from PyQt5.QtCore import QRegExp
from PyQt5.QtGui import QRegExpValidator
# from PyQt5.QtWidgets import QErrorMessage
from PyQt5.QtWidgets import QMessageBox
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure
import matplotlib.pyplot as plt

from obspy import read
from obspy import UTCDateTime

from reportlab.platypus import SimpleDocTemplate
from reportlab.platypus import Image
from reportlab.lib.pagesizes import letter
from reportlab.platypus import Table
from reportlab.platypus import TableStyle
from reportlab.platypus.flowables import HRFlowable


# for conversion of tables to pdf: use weasyprint on Linux, xhtml2pdf on Windows and MacOS
try:
    from weasyprint import HTML
except ImportError:
    from xhtml2pdf import pisa


__version__ = '0.1'
__author__ = 'Nick LiBassi'

start_time = time.time()
print(time.strftime("start time after imports: %a, %d %b %Y %H:%M:%S", time.localtime()))

ERROR_MSG = 'ERROR'

# set logging to 'DEBUG' to print debug statements to console
logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(levelname)s - %(message)s')

"""
General Notes:
use camelCase throughout as Qt uses it

"""

SENSOR_CODES = ('N39', 'S39', 'N24', 'S24', 'N12', 'S12', 'B4F', 'FF')

# in order of those on page 5 of third-party report          
SENSOR_CODES_WITH_CHANNELS = [
                            'N39x',
                            'N39y',
                            'N39z',
                            'S39x',
                            'S39y',
                            'S39z',
                            'N24x',
                            'N24y',
                            'N24z',
                            'S24x',
                            'S24y',
                            'S24z',
                            'N12x',
                            'N12y',
                            'N12z',
                            'S12x',
                            'S12y',
                            'S12z',
                            'B4Fx',                             
                            'B4Fy',
                            'B4Fz',
                            'FFN',
                            'FFW',
                            'FFZ'
                            ]


def getSensorCodeInfo(inputFile):
    """
    Return strings holding sensor code only and sensor code with channel
    In far field cases, these will be identical ('FFW', 'FFN', 'FFZ')
    inputFile: string holding either filename or path of .txt or .m file
    return: tuple of strings holding sensor code info ex. ('B4F', 'B4Fx')
    """
    # get string holding file extension - either 'txt' or 'm' (without dot)
    inputFileExt = inputFile.split('.')[-1]
    inputFileBase = inputFile.split('.' + inputFileExt)[0]
    # info in filenames are separated by dots
    sensorCodeWithChannel = inputFileBase.rsplit('.')[-1]

    lastLetter = sensorCodeWithChannel[-1]
    if lastLetter.islower():
        sensorCode = sensorCodeWithChannel[:-1]
    else:
        sensorCode = sensorCodeWithChannel

    return sensorCode, sensorCodeWithChannel


def getFloor(sensorCodeText):
    """
    Return string holding only floor portion (only digits) of sensor code
    sensorCodeText: string holding either sensor code or sensor code with channel
    """
    floorChars = [c for c in sensorCodeText if c.isdigit()]
    floor = ''.join(floorChars)
    return floor


def getFloorCode(sensorCodeText):
    """
    Return string holding floor code.
    Sample input: 'N39x'
    Sample ouput: 'L40'
    """
    if sensorCodeText[0] == 'F':
        return 'GF'
    elif sensorCodeText[0] in ['N', 'S']:
        letter = 'L'
        numeric = str(int(getFloor(sensorCodeText)) + 1)
    elif sensorCodeText[0] == 'B':
        letter = 'B'
        numeric = getFloor(sensorCodeText)
    return letter + numeric


def getAxis(sensorCodeWithChannel):
    """
    return upper case version of axis: 'X', 'Y', or 'Z'
    """
    lastLetter = sensorCodeWithChannel[-1]
    if lastLetter in ['x', 'y', 'z']:
        return lastLetter.upper()
    else:
        dirDict = {'N': 'X', 'W': 'Y', 'Z': 'Z'}
        return dirDict[lastLetter]


def getTimeText(inputFile):
    """
    Get hour (int) and full timestamp (string) from given miniseed or text file name.
    inputFile: string holding either filename or path of .txt or .m file
    return:
    tuple in form: (int holding hour between 0-23, string holding full timestamp)
    ex. (10, '20190926100000')
    """
    filename = inputFile.split('/')[-1]
    timestampText = filename.split('.')[0]
    UTCHour = timestampText[8:10]
    return (UTCHour, timestampText)


def sortFilesBySensorCode(inputFileList):
    """
    Sort given list of files alphabetically by sensor code.
    inputFileList: list of strings holding filenames (or paths?) of miniseed or text files.
    return: list of files sorted by sensor code (according to order of SENSOR_CODES).
    """
    sortedList = []
    for code in SENSOR_CODES:
        fileGroup = [f for f in inputFileList if code in f]
        sortedFileGroup = sorted(fileGroup)
        sortedList += sortedFileGroup
    return sortedList


def sortFiles(inputFileList):
    """
    Sort given list of files according to order in third-party report.
    inputFileList: list of strings holding filenames or full paths of miniseed or text files.
    return: sorted list of input text files
    """
    uniqueTimeTuples = list(set([getTimeText(file) for file in inputFileList]))
    numHours = len(uniqueTimeTuples)
    if numHours == 1:
        return sortFilesBySensorCode(inputFileList)
    elif numHours == 2:
        if uniqueTimeTuples[0][0] < uniqueTimeTuples[1][0]:
            firstTime = uniqueTimeTuples[0][1]
        else:
            firstTime = uniqueTimeTuples[1][1]
        firstFileList = sortFilesBySensorCode([f for f in inputFileList if firstTime in f])
        secondFileList = sortFilesBySensorCode([f for f in inputFileList if firstTime not in f])
        return firstFileList + secondFileList


def getReadableTimestamp(eventTimestamp):
    """return string holding readable version of timestamp"""
    eventTimestamp = pd.Timestamp(eventTimestamp)
    eventTimestampReadable = eventTimestamp.strftime('%m/%d/%y %H:%M:%S')
    return eventTimestampReadable


def getResourcePath(relativePath):
    """ 
    Get absolute path to resource, works for dev and for PyInstaller 
    relativePath: string holding relative path of file whose absolute path will be returned
    return: string holding absolute path of given file
    """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        basePath = sys._MEIPASS
    except Exception:
        basePath = os.path.abspath("./convert_acc")

    return os.path.join(basePath, relativePath)


def getReportHeader(eventTimestampReadable):
    """
    return elements of report header
    eventTimestampReadable: string holding readable event timestamp
    return: list of header elements
    """
    clientImagePath = getResourcePath('resources/placeholder.png')
    reportTextImagePath = getResourcePath('resources/report_image.png')

    clientImage = Image(clientImagePath, 105, 40)
    clientImage.hAlign = 'LEFT'

    reportTextImage = Image(reportTextImagePath, 74, 12)
    reportTextImage.hAlign = 'RIGHT'

    line1 = [[clientImage,'','','','','',reportTextImage],['','','','','','','automatic impact assessment due to building movement']]
    line2 = [['EVENT:', eventTimestampReadable,'','','','SITE:','Istanbul']]

    table1 = Table(line1, colWidths=[84, 84], rowHeights=20)
    table2 = Table(line2, colWidths=[82, 82], rowHeights=20)

    style1 = TableStyle([
    ('ALIGN', (6, 0), (6, 0), 'DECIMAL'),
    ('FONTSIZE', (0, 0), (6, 0), 20),
    ('FONTNAME', (0, 0), (6, 0), 'Courier-Bold'),
    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
    ('ALIGN', (6, 1), (6, -1), 'DECIMAL'),
    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    (('TEXTCOLOR', (6, 1), (6, -1), "#949494"))
    ])

    style2 = TableStyle([
    ('ALIGN', (6, 0), (6, 0), 'DECIMAL'),
    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
    ('ALIGN', (6, 0), (6, -1), 'DECIMAL'),
    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ('TEXTCOLOR', (1, 0), (1, 0), "#0000FF"),
    ('TEXTCOLOR', (-1, -1), (-1, -1), "#0000FF"),
    ])

    table1.setStyle(style1)
    table2.setStyle(style2)

    flowable = HRFlowable(width='100%', thickness=0.2, color="#000000")

    return [table1, flowable, table2]


# get clean df from single text file
class ProcessedFromTxtFile:
    def __init__(self, txtFilePath):
        self.txtFilePath = txtFilePath
        # sensor code info not used within ProcessedFromTxtFile but necessary for Conversion instances
        self.sensorCode, self.sensorCodeWithChannel = getSensorCodeInfo(self.txtFilePath)

        self.rawDf = self.convertTxtToDf()
        self.df = self.getCleanDf(self.rawDf)

    def convertTxtToDf(self):
        """
        return pandas dataframe converted from text file with no processing
        (input text data contains timestamp and count data in a single column separated by spaces)
        """
        df = pd.read_csv(self.txtFilePath, header=0)
        return df

    def getCleanDf(self, df):
        """
        return dataframe holding only timestamp and count values as separate columns
        df: raw df containing both timestamp and count data in first column (space-delimited)
        return: df holding only timestamp and count values as separate columns
        """
        singleColumnDf = df.iloc[:, [0]]
        # get column name of first column
        columnName = singleColumnDf.columns[0]
        timestampSeries, countSeries = singleColumnDf[columnName].str.split(' ', 1).str
        cleanDf = pd.DataFrame({'timestamp': timestampSeries, 'count': countSeries.astype('int32')})
        return cleanDf

        
# class used to convert data (in single dataframe) from
# count to acceleration, velocity, and displacement
class Conversion:
    def __init__(self, df, sensorCode, sensorCodeWithChannel, eventTimestamp):
        """
        Initializer for Conversion class
        df: pandas df from ProcessedFromTxtFile object
        sensorCode: string holding sensor code ex. 'B4F'
        sensorCodeWithChannel: string holding sensor code and axis ex. 'B4Fx'
        eventTimestamp: string holding event timestamp ex.'2020-01-13T163712'
        """
        self.df = df
        self.sensorCode = sensorCode
        self.sensorCodeWithChannel = sensorCodeWithChannel
        self.floor = getFloor(self.sensorCode)
        self.eventTimestamp = eventTimestamp
        self.sensitivity = self.setSensitivity(self.sensorCodeWithChannel)
        # self.accRawStats = None
        self.accOffsetStats = None
        self.accBandpassedStats = None
        self.velStats = None
        self.dispStats = None

        # these may be taken from user in future
        # low cutoff frequency for bandpass and highpass filters
        self.lowcut = 0.05
        # high cutoff frequency for bandpass filter
        self.highcut = 40
        # sampling frequency
        self.fs = 100
        # order of filters
        self.order = 2
        # time between samples in seconds
        self.dt = 1 / float(self.fs)

        self.zeroPadLength = 500
        self.ignoredSamples = 6000

        self.resultsSubplotDict = dict(zip(SENSOR_CODES_WITH_CHANNELS, [x for x in range(1, 25)]))

        # key '4' refers to floor 'B4'
        self.comparisonSubplotDict = {'39': 1, '24': 2, '12': 3, '4': 4}

        # manipulate input dataframe

        self.df['g'] = self.df['count'].apply(lambda x: self.convertCountToG(x))
        self.df = self.getZeroPaddedDf(self.df, ['timestamp', 'g'])
        # add 'offset_g' column by detrending 'g'
        self.df['offset_g'] = detrend(self.df['g'], type='constant')
        self.df['acc_ms2'] = self.df['offset_g'].apply(lambda x: self.convertGToMetric(x))

        self.butterBandpassFilter('offset_g', 'bandpassed_g')
        self.butterBandpassFilter('acc_ms2', 'bandpassed_ms2')
        self.df['velocity_ms'] = self.integrateSeries(self.df['bandpassed_ms2'])

        self.removeExtraneousSamples()
        self.df['detrended_velocity_ms'] = detrend(self.df['velocity_ms'], type='constant')
        self.df['detrended_velocity_cms'] = self.df['detrended_velocity_ms'].apply(lambda x: self.convertMToCm(x))
        # self.convertMToCm('detrended_velocity_ms', 'detrended_velocity_cms')
        self.df['displacement_m'] = self.integrateSeries(self.df['detrended_velocity_ms'])

        self.df['detrended_displacement_m'] = detrend(self.df['displacement_m'], type='constant')
        self.butterHighpassFilter('detrended_displacement_m', 'highpassed_displacement_m')
        self.df['highpassed_displacement_cm'] = self.df['highpassed_displacement_m'].apply(lambda x: self.convertMToCm(x))

        # self.accRawStats = self.getStats('g')
        self.accOffsetStats = self.getStats('offset_g')
        self.accBandpassedStats = self.getStats('bandpassed_g')
        self.velStats = self.getStats('detrended_velocity_cms')
        self.dispStats = self.getStats('highpassed_displacement_cm')

    def logHeadTail(self):
        """print head and tail of self.df to console"""
        logging.debug(self.df.head())
        logging.debug(self.df.tail())

    def printDfDesc(self):
        """print head and tail of self.df to console"""
        print('columns')
        print(self.df.columns)
        print('head')
        print(self.df.head())
        print('tail')
        print(self.df.tail())
        print('length of df: {0}'.format(len(self.df)))

    def setSensitivity(self, sensorCodeWithChannel):
        """
        return float holding sensitivity in V/g based on given sensorCode
        sensorCodeWithChannel: string of form 'B4Fx'
        """
        groundFloorSensorCodes = [c for c in SENSOR_CODES_WITH_CHANNELS if 'F' in c]
        upperFloorSensorCodes = [c for c in SENSOR_CODES_WITH_CHANNELS if 'F' not in c]
        if sensorCodeWithChannel in groundFloorSensorCodes:
            return 1.25
        elif sensorCodeWithChannel in upperFloorSensorCodes:
            return 0.625
        else:
            raise ValueError('Sensitivity must contain non-null value.')

    def convertCountToG(self, count):
        """
        convert acceleration as raw count to acceleration as g
        count: int holding acceleration data collected by sensor
        """
        g = count * (2.5 / 8388608) * (1 / self.sensitivity)
        return g

    def getZeroPaddedDf(self, df, columns):
        """
        return pandas dataframe with zeropad added to both head and tail of data in given df
        (length of zero pad determined by instance variable zeroPadLength) 
        df: pandas dataframe used as input
        columns: list of strings holding names of columns to be padded and
            returned in new dataframe ['timestamp', 'g']
        return: pandas dataframe with only padded columns
        """
        # zeros = np.zeros(shape=(self.zeroPadLength))
        zeros = [0] * self.zeroPadLength
        zeroPad = pd.Series(zeros)
        nullList = [None] * self.zeroPadLength
        nullSeries = pd.Series(nullList)
        paddedColumns = []
        for column in columns:
            if column == 'timestamp':
                paddedColumn = pd.concat([nullSeries, df[column], nullSeries])
            else:
                paddedColumn = pd.concat([zeroPad, df[column], zeroPad])
            paddedColumn.reset_index(drop=True, inplace=True)
            paddedColumns.append(paddedColumn)
        paddedData = dict(zip(columns, paddedColumns))
        return pd.DataFrame(paddedData, columns=columns)

    def convertGToMetric(self, g):
        """
        return acceleration in m/s^2 from acceleration in g
        g: float holding acceleration in g
        """
        return g * 9.80665

    def butterPass(self, filterType):
        """
        return bandpass or highpass filter coefficients...
        from https://scipy-cookbook.readthedocs.io/items/ButterworthBandpass.html
        filterType: string holding 'band' or 'high'
        return:
            b: numerator of filter
            a: denominator of filter
        """
        nyq = 0.5 * self.fs
        low = self.lowcut / nyq
        high = self.highcut / nyq
        if filterType == 'band':
            b, a = butter(self.order, [low, high], btype='band')
        elif filterType == 'high':
            b, a = butter(self.order, low, btype='high')
        logging.info('butterworth coefficients - b: {0}, a: {1}'.format(b, a))
        return b, a

    def butterBandpassFilter(self, inputColumn, outputColumn):
        """
        create columns in df holding bandpassed acceleration data
        (apply bandpass filter to data using filter coefficients b and a)
        from https://scipy-cookbook.readthedocs.io/items/ButterworthBandpass.html
        """
        b, a = self.butterPass('band')
        self.df[outputColumn] = lfilter(b, a, self.df[inputColumn])

    def integrateSeries(self, inputSeries):
        """return integrated series from given pandas series"""
        inputList = list(inputSeries)
        inputListFromIndex1 = inputList[1:]
        zipped = zip(inputList, inputListFromIndex1)
        # values will be appended to integratedList
        integratedList = [0]
        for z in zipped:
            integrated = self.dt * (z[0] + z[1]) / 2. + integratedList[-1]
            integratedList.append(integrated)
        return pd.Series(integratedList)

    def removeExtraneousSamples(self):
        """truncate self.df by removing ignored samples and zero pad at tail"""
        endIndex = 40000 + self.zeroPadLength
        self.df = self.df.truncate(self.ignoredSamples, endIndex, copy=False)
        self.df.reset_index(drop=True, inplace=True)
        logging.debug('df description after extraneous samples removed:')
        # self.printDfDesc()

    def butterHighpassFilter(self, inputColumn, outputColumn):
        """
        modeled after Butterworth bandpass code in scipy cookbook
        """
        b, a = self.butterPass('high')
        self.df[outputColumn] = lfilter(b, a, self.df[inputColumn])

    def convertMToCm(self, m):
        """
        convert values in meters to values in centimeters
        m: int or float holding distance in m
        """
        return m * 100

    def getStats(self, columnName):
        """
        get index of peak value and peak value itself
        (to be called after df has been clipped)
        columnName: string holding name of column in self.df
        return: list holding:
            1. int holding index of peak value
            2. float holding peak value
            3. float holding peak value rounded to four decimal places
        """

        minVal = self.df[columnName].min()
        maxVal = self.df[columnName].max()
        meanVal = self.df[columnName].mean()

        # get indexes of min and max values
        minValIndex = self.df.index[self.df[columnName] == minVal][0]
        maxValIndex = self.df.index[self.df[columnName] == maxVal][0]

        minPair = [minValIndex, minVal]
        maxPair = [maxValIndex, maxVal]

        if abs(minPair[1]) > abs(maxPair[1]):
            peakInfo = minPair
        else:
            peakInfo = maxPair

        peakInfo.append(round(peakInfo[1], 4))

        logging.debug('stats for {0}:{1}\n'.format(self.sensorCodeWithChannel, columnName))
        stats = 'min: {0}\nmax: {1}\nmean: {2}\n'.format(minVal, maxVal, meanVal)
        logging.debug(stats)
        return peakInfo

    def plotResultsGraph(self, canvasObject, column, titleSuffix, yLimit):
        """
        plot graph of data to given ResultsCanvas object (one of 24 graphs on one page)
        canvasObject: instance of ResultsCanvas class
        column: string holding name of column used as y data
        plotTitle: string holding title of plot
        yLimit: float holding value to be used to set range of plot along y-axis (from negative yLimit to yLimit)
        """
        plotTitle = self.sensorCodeWithChannel + ' ' + titleSuffix

        subplotPos = self.resultsSubplotDict[self.sensorCodeWithChannel]

        ax = canvasObject.figure.add_subplot(8, 3, subplotPos)

        plot = self.df.reset_index().plot(kind='line', x='index', y=column, color='gray', title=plotTitle, linewidth=0.25, ax=ax)

        ax.set_ylim(-yLimit, yLimit)
        ax.xaxis.set_visible(False)
        ax.xaxis.set_major_locator(plt.MaxNLocator(4))
        ax.get_legend().remove()

        # mark peak value and add text to plot
        x, y, yText = self.getStats(column)
        ax.plot(x, y, marker='o', color='red', markersize=2)
        ax.text(0.85, 0.85, '{0}'.format(yText), color='red', transform=ax.transAxes)

        # move this to Class constructor?
        canvasObject.figure.tight_layout()

    def plotComparisonGraph(self, canvasObject, yLimit):
        """
        plot displacement (for now) on a figure comparing displacements at different levels
        canvasObject: instance of ComparisonCanvas class
        yLimit: float holding value to be used to set range of plot along y-axis (from negative yLimit to yLimit)
        """
        subplotPos = self.comparisonSubplotDict[self.floor]
        ax = canvasObject.figure.add_subplot(4, 1, subplotPos)
        plot = self.df.reset_index().plot(kind='line', x='index', y='highpassed_displacement_cm', color='gray', linewidth=0.25, ax=ax)
        ax.set_ylim(-yLimit, yLimit)
        ax.xaxis.set_visible(False)
        ax.xaxis.set_major_locator(plt.MaxNLocator(4))
        if self.floor == '39':
            ax.set_title(canvasObject.windowTitle)
        ax.set_ylabel(self.sensorCodeWithChannel, rotation=0)
        ax.get_legend().remove()

        # mark peak value and add text to plot
        x, y, yText = self.getStats('highpassed_displacement_cm')
        ax.plot(x, y, marker='o', color='red', markersize=2)
        ax.text(0.8, 0.85, '{0}'.format(yText), color='red', transform=ax.transAxes)

        canvasObject.figure.tight_layout()


# subclass of QMainWindow to set up the portion of GUI
# to take information from user and serve as controller of program
class PrimaryUI(QMainWindow):
    """AccConvert's initial view for taking input from user."""
    def __init__(self):
        """View initializer."""
        super().__init__()

        # self.eventTimestamp is string (converted to pd.Timestamp when necessary)
        self.eventTimestamp = None
        self.eventTimestampReadable = None
        self.miniseedDir = None
        self.miniseedFileList = None
        self.miniseedFileCount = None
        self.workingBaseDir = None
        self.workingDir = None
        self.txtFileList = None
        self.txtFileCount = None
        self.pairedTxtFileList = []
        self.progress = QMessageBox(self)

        self.statsTable = StatsTable(self.eventTimestampReadable)
        self.offsetGResultsCanvas = ResultsCanvas('Acceleration (g)')
        self.bandpassedGResultsCanvas = ResultsCanvas('Bandpassed Acceleration (g)')
        self.velResultsCanvas = ResultsCanvas('Velocity (cm/s)')
        self.dispResultsCanvas = ResultsCanvas('Displacement (cm)')
        # order of following four lists must remain as is
        # get stats column names except for static columns
        self.statsColumnNames = self.statsTable.columnHeaders[-4:]
        self.conversionColumnNames = ['offset_g', 'bandpassed_g', 'detrended_velocity_cms', 'highpassed_displacement_cm']
        self.titleSuffixes = ['offset acceleration (g)', 'bandpassed acceleration (g)', 'detrended velocity (cm/s)', 'highpassed displacement (cm)']
        self.resultsCanvases = [self.offsetGResultsCanvas, self.bandpassedGResultsCanvas, self.velResultsCanvas, self.dispResultsCanvas]

        # self.statsColumnMaxValues will hold peak values in same order as self.conversionColumnNames
        self.statsColumnMaxValues = None

        self.NXcomparisonCanvas = ComparisonCanvas('N. Corner X-Dir (cm)')
        self.NYcomparisonCanvas = ComparisonCanvas('N. Corner Y-Dir (cm)')
        self.SXcomparisonCanvas = ComparisonCanvas('S. Corner X-Dir (cm)')
        self.SYcomparisonCanvas = ComparisonCanvas('S. Corner Y-Dir (cm)')

        # retain current order of self.comparisonCanvases
        self.comparisonCanvases = [self.NXcomparisonCanvas, self.NYcomparisonCanvas, self.SXcomparisonCanvas, self.SYcomparisonCanvas]
        self.allCanvases = self.resultsCanvases + self.comparisonCanvases
        self.comparisonPngNames = ['nx.png', 'ny.png', 'sx.png', 'sy.png']

        # Set some of main window's properties
        self.setWindowTitle('Accelerometer Data Conversion')
        self.setFixedSize(500, 250)
        # Set the central widget and the general layout
        self.generalLayout = QVBoxLayout()
        self.centralWidget = QWidget(self)
        self.setCentralWidget(self.centralWidget)
        self.centralWidget.setLayout(self.generalLayout)
        # Create the display and the buttons
        self.createTextInputFields()
        # self.createRadioButtons()
        self.createSubmitButton()

        self.eventField.textChanged.connect(self.enableSubmitButton)
        self.miniseedDirField.textChanged.connect(self.enableSubmitButton)
        self.workingBaseDirField.textChanged.connect(self.enableSubmitButton)

    def enableSubmitButton(self):
        """Allow click on submit button if all fields contain valid input"""
        if  self.isEventTimestampValid() and \
            self.isDirPathValid(self.miniseedDirField) and \
            self.isDirPathValid(self.workingBaseDirField):
                self.submitBtn.setEnabled(True)

    def setEventTimestamp(self):
        """Set event timestamp (string) based on user input"""
        logging.debug(self.eventField.text())
        self.eventTimestamp = self.eventField.text()

    def isEventTimestampValid(self):
        """
        Confirm event timestamp is entered in correct format
        return: boolean (True if valid)
        """
        regEx = QRegExp("[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{6}")
        timestampValidator = QRegExpValidator(regEx, self)
        result = timestampValidator.validate(self.eventField.text(), 0)
        # validate() returns tuple with 2 as first item if valid
        if result[0] == 2:
            return True
        else:
            return False

    def setMiniseedDir(self):
        """Set miniseed directory path based on user input"""
        self.miniseedDir = self.miniseedDirField.text()

    def setWorkingBaseDir(self):
        """Set base working directory path based on user input"""
        self.workingBaseDir = self.workingBaseDirField.text()

    def isDirPathValid(self, field):
        """
        Confirm that entered directory path exists
        field: name of field holding path entered by user
        return: boolean (True if path exists)
        """
        if os.path.exists(field.text()):
            return True
        else:
            return False

    def isWorkingDirWritable(self):
        """Return true if entered working directory is writable"""
        if os.access(os.path.dirname(self.workingBaseDirField.text()), os.W_OK):
            return True
        else:
            message = QMessageBox(QMessageBox.Critical, 'Invalid Input', 'Working directory is not writable. Please choose another location.', QMessageBox.Ok)
            message.exec_()
            return False

    def setMiniseedFileInfo(self):
        """
        Set: 
            -list of strings holding miniseed file names
            -variable holding integer with number of miniseed files
        """
        self.miniseedFileList = [f for f in os.listdir(self.miniseedDir) if f.endswith(".m")]
        self.miniseedFileCount = len(self.miniseedFileList)
        logging.debug('miniseed file count: {}'.format(self.miniseedFileCount))

    def isMiniseedCountValid(self):
        """Return true if number of miniseed files in miniseed directory is either 24 or 48"""
        if self.miniseedFileCount not in [24, 48]:
            message = QMessageBox(QMessageBox.Critical, 'Invalid Input', 'Miniseed directory must contain either 24 or 48 files with extension .m', QMessageBox.Ok)
            message.exec_()
            return False
        else:
            return True

    def setWorkingDir(self):
        """
        If not yet created, create working dir using event id/timestamp entered
        by user.
        """
        self.workingDir = os.path.join(self.workingBaseDir, self.eventTimestamp)

        if not os.path.isdir(self.workingDir):
            os.mkdir(self.workingDir)

    def timestampToUTC(self, eventTimestamp):
        """
        convert event timestamp from local Turkish time to UTC
        (will need to be edited if Turkey re-institutes daylight savings time,
        apparently DST is not expected for UTC at least through 2029)
        eventTimestamp: string holding event timestamp in local Turkish time (entered by user)
        return: UTCDateTime object holding timestamp in UTC
        """
        eventTimestamp = UTCDateTime(eventTimestamp)
        # subtract 3 hours from timestamp in local Turkish time (10800 seconds)
        eventTimestampUTC = eventTimestamp - 10800
        return eventTimestampUTC

    def getWindowBounds(self, eventTimestamp):
        """
        return start and end timestamps to be used as window boundaries
        eventTimestamp: UTCDateTime object holding timestamp in UTC
        return: tuple of UTCDateTime objects holding start and end times in UTC
        """
        startTime = eventTimestamp - 60
        endTime = startTime + 400
        return (startTime, endTime)

    def convertMiniseedToAscii(self):
        """
        Convert all miniseed files in miniseed directory to ascii files (TSPAIR format)
        """
        for f in self.miniseedFileList:
            mseedPath = os.path.join(self.miniseedDir, f)
            basename = f.rsplit(".m")[0]
            filename = basename + ".txt"
            outPath = os.path.join(self.workingDir, filename)
            stream = read(mseedPath)
            startTime, endTime = self.getWindowBounds(self.timestampToUTC(self.eventTimestamp))
            trimmedStream = stream.trim(startTime, endTime)
            try:
                trimmedStream.write(outPath, format='TSPAIR')
            except Exception as e:
                print('error converting miniseed to text file: {0}'.format(e))

    def createTextInputFields(self):
        """Create text input fields"""
        self.eventLabel = QLabel(self)
        self.eventLabel.setText('Timestamp of event in format "2020-01-11T163736"')
        self.miniseedDirLabel = QLabel(self)
        self.miniseedDirLabel.setText('Absolute path of directory holding miniseed files')
        self.workingBaseDirLabel = QLabel(self)
        self.workingBaseDirLabel.setText('Absolute path of base output directory\n(Report will be found here in new directory named with timestamp.)')

        self.eventField = QLineEdit(self)
        self.miniseedDirField = QLineEdit(self)
        self.workingBaseDirField = QLineEdit(self)

        self.generalLayout.addWidget(self.eventLabel)
        self.generalLayout.addWidget(self.eventField)
        self.generalLayout.addWidget(self.miniseedDirLabel)
        self.generalLayout.addWidget(self.miniseedDirField)
        self.generalLayout.addWidget(self.workingBaseDirLabel)
        self.generalLayout.addWidget(self.workingBaseDirField)

    def createRadioButtons(self):
        """Create radio buttons"""
        self.approachGroup = QButtonGroup(self.centralWidget)
        self.timePlain = QRadioButton('Time-domain conversion')
        self.timePlain.setChecked(True)
        # self.timeBaseline = QRadioButton('Time-domain with baseline correction')
        # self.freqCorrection = QRadioButton('Frequency-domain with correction filter')
        # self.freqPlain = QRadioButton('Frequency-domain without correction filter')

        self.approachGroup.addButton(self.timePlain)
        # self.approachGroup.addButton(self.timeBaseline)
        # self.approachGroup.addButton(self.freqCorrection)
        # self.approachGroup.addButton(self.freqPlain)

        self.generalLayout.addWidget(self.timePlain)
        # self.generalLayout.addWidget(self.timeBaseline)
        # self.generalLayout.addWidget(self.freqCorrection)
        # self.generalLayout.addWidget(self.freqPlain)

    def setTxtFileInfo(self):
        """Set list of sorted input text file paths and number of text files"""
        self.txtFileList = [os.path.join(self.workingDir, f) for f in os.listdir(self.workingDir)]
        self.txtFileList = sortFiles(self.txtFileList)
        self.txtFileCount = len(self.txtFileList)
        for path in self.txtFileList:
            logging.debug('txt file path: {0}'.format(path))

    def pairDeviceTxtFiles(self):
        """
        If seismic event spans two hours, create list of 24 two-item lists holding path pairs of miniseed files to be processed.
        Assume number of input miniseed files to be 24 (if event falls in single hour) or 48 (if event spans two hours)
        """
        if self.txtFileCount == 48:
            txtFileSensorCodeList = []
            for file in self.txtFileList:
                sensorCodeWithChannel = getSensorCodeInfo(file)[1]
                txtFileSensorCodeList.append((file, sensorCodeWithChannel))

            for t in txtFileSensorCodeList:
                logging.debug('txtFileSensorCodeList tuple: {}'.format(t))

            for c in SENSOR_CODES_WITH_CHANNELS:
                pairedList = [f for f in txtFileSensorCodeList if c in f]
                self.pairedTxtFileList.append(pairedList)

    def showProgress(self):
        """show progress message box to user after submit button clicked"""
        self.progress.setIcon(QMessageBox.Information)
        self.progress.setText("Processing acceleration data")
        self.progress.setWindowTitle("In Progress")
        # probably not necessarygi
        self.progress.setModal(False)
        self.progress.show()

    def updateStatsTable(self, conversionObject):
        """update row of stats table with max values at each of the (currently four) parameters"""
        # accRawPeakVal = conversionObject.accRawStats[2]
        accOffsetPeakVal = conversionObject.accOffsetStats[2]
        accBandpassedPeakVal = conversionObject.accBandpassedStats[2]
        velPeakVal = conversionObject.velStats[2]
        dispPeakVal = conversionObject.dispStats[2]

        self.statsTable.updateStatsDf(conversionObject.sensorCodeWithChannel, self.statsColumnNames[0], accOffsetPeakVal)
        self.statsTable.updateStatsDf(conversionObject.sensorCodeWithChannel, self.statsColumnNames[1], accBandpassedPeakVal)
        self.statsTable.updateStatsDf(conversionObject.sensorCodeWithChannel, self.statsColumnNames[2], velPeakVal)
        self.statsTable.updateStatsDf(conversionObject.sensorCodeWithChannel, self.statsColumnNames[3], dispPeakVal)

    def getStatsMaxValues(self):
        """
        get max values from each column of the stats table (called only once after final stats table is completely populated)
        (ensure that items of statsColumnNames and conversionColumnNames are in the same order)
        return: list holding max values of each column in stats table
        """
        columnMaxValues = []
        for column in self.statsColumnNames:
            columnMaxValues.append(self.statsTable.getColumnMax(column))
        print('max values of {0}:\n{1}'.format(self.statsColumnNames, columnMaxValues))
        return columnMaxValues

    def getPlotArgs(self):
        """
        return a list of tuples holding:
             string holding conversion column names
             string holding title suffix to be used for plot
             max value from each STATS column (which will be used to define range of ylimits of all plots for given parameter)
        """
        plotArgs = zip(self.resultsCanvases, self.conversionColumnNames, self.titleSuffixes, self.statsColumnMaxValues)
        return plotArgs

    def drawResultsPlots(self, conversionObject):
        """
        draw all (currently four) plots associated with given conversionObject
        conversionObject: instance of the Conversion class
        """
        plotArgs = self.getPlotArgs()
        for item in plotArgs:
            canvas, columnName, titleSuffix, maxVal = item
            # add 15% of maxVal to maxVal to get range of plots along y-axis
            yLimit = maxVal + maxVal * 0.15
            conversionObject.plotResultsGraph(canvas, columnName, titleSuffix, yLimit)

    def drawComparisonPlot(self, conversionObject):
        """
        add subplot of displacement to ComparisonCanvas if self.sensorCodeWithChannel meets criteria
        """
        displacementMaxVal = self.statsColumnMaxValues[-1]
        # add 15% of maxVal to maxVal to get range of plots along y-axis
        yLimit = displacementMaxVal + displacementMaxVal * 0.15
        if all(i in conversionObject.sensorCodeWithChannel for i in ['N', 'x']):
            conversionObject.plotComparisonGraph(self.NXcomparisonCanvas, yLimit)
        elif all(i in conversionObject.sensorCodeWithChannel for i in ['S', 'x']):
            conversionObject.plotComparisonGraph(self.SXcomparisonCanvas, yLimit)
        elif all(i in conversionObject.sensorCodeWithChannel for i in ['N', 'y']):
            conversionObject.plotComparisonGraph(self.NYcomparisonCanvas, yLimit)
        elif all(i in conversionObject.sensorCodeWithChannel for i in ['S', 'y']):
            conversionObject.plotComparisonGraph(self.SYcomparisonCanvas, yLimit)

        # B4 data to appear on the x or y canvases no matter what
        elif all(i in conversionObject.sensorCodeWithChannel for i in ['B', 'x']):
            conversionObject.plotComparisonGraph(self.SXcomparisonCanvas, yLimit)
            conversionObject.plotComparisonGraph(self.NXcomparisonCanvas, yLimit)
        elif all(i in conversionObject.sensorCodeWithChannel for i in ['B', 'y']):
            conversionObject.plotComparisonGraph(self.SYcomparisonCanvas, yLimit)
            conversionObject.plotComparisonGraph(self.NYcomparisonCanvas, yLimit)

    def getConversionObjectFromTwoTxtFiles(self, txtFilePair):
        """
        txtFilePair: list of tuples containing text file name (and sensor code channel)
        return: conversion object made from dataframe from combined text files
        """
        txtFilePair = sorted([item[0] for item in txtFilePair])
        p1 = ProcessedFromTxtFile(txtFilePair[0])
        df1 = p1.df
        p2 = ProcessedFromTxtFile(txtFilePair[1])
        df2 = p2.df
        df = pd.concat([df1, df2])
        df.reset_index(drop=True, inplace=True)
        return Conversion(df, p1.sensorCode, p1.sensorCodeWithChannel, self.eventTimestamp)

    def getConversionObjectFromOneTxtFile(self, txtFile):
        """
        txtFile: string holding name of text file produced from miniseed file
        return: conversion object made from dataframe produced from text file
        """
        p = ProcessedFromTxtFile(txtFile)
        df = p.df
        return Conversion(df, p.sensorCode, p.sensorCodeWithChannel, self.eventTimestamp)

    def showCanvases(self):
        for canvas in self.allCanvases:
            canvas.show()

    def saveResultsFiguresAsPdf(self):
        """save results figures to a single pdf"""
        pdfPath = os.path.join(self.workingDir, 'results.pdf')
        pdf = PdfPages(pdfPath)
        for canvas in self.resultsCanvases:
            pdf.savefig(canvas.figure)
        pdf.close()

    def saveComparisonFigures(self):
        """save comparison figures as individual png files"""
        comparisonCanvasDict = dict(zip(self.comparisonCanvases, self.comparisonPngNames))
        for canvas in self.comparisonCanvases:
            pngPath = os.path.join(self.workingDir, comparisonCanvasDict[canvas])
            canvas.figure.savefig(pngPath)

    def combineComparisonFigures(self):
        """combine comparison png files into single (one-page) pdf"""
        pdf = FPDF()
        pngFiles = [f for f in os.listdir(self.workingDir) if f in self.comparisonPngNames]
        pngPaths = [os.path.join(self.workingDir, f) for f in pngFiles]
        pdf.add_page()
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(140, 10, 'Unconfirmed preliminary results for event: {0} UTC+3'.format(self.eventTimestampReadable))
        for path in pngPaths:
            if 'nx' in path:
                x, y = (10, 17)
            elif 'ny' in path:
                x, y = (110, 17)
            elif 'sx' in path:
                x, y = (10, 156)
            elif 'sy' in path:
                x, y = (110, 156)
            pdf.image(path, x, y, h=140)
        pdf.output(os.path.join(self.workingDir, 'displacement_comparison.pdf'), "F")

    def combinePdfs(self):
        """combine all pdfs into single report.pdf"""
        pdfs = ['displacement_comparison.pdf', 'results.pdf', 'stats_table_all.pdf', 'stats_table_acc.pdf']
        pdfPaths = [os.path.join(self.workingDir, f) for f in pdfs]
        merger = PdfFileMerger()
        for pdf in pdfPaths:
            merger.append(pdf)

        merger.write(os.path.join(self.workingDir, 'report_{0}.pdf'.format(self.eventTimestamp)))
        merger.close()

    def getResults(self):
        """
        perform conversions for all datasets (24 datasets from 24 or 48 text files)
        call drawResultsPlots() to plot acceleration, velocity, and displacement for all datasets
        """
        if self.pairedTxtFileList:
            for pair in self.pairedTxtFileList:
                c = self.getConversionObjectFromTwoTxtFiles(pair)
                self.updateStatsTable(c)
            self.statsColumnMaxValues = self.getStatsMaxValues()

            for pair in self.pairedTxtFileList:
                c = self.getConversionObjectFromTwoTxtFiles(pair)
                self.drawResultsPlots(c)
                self.drawComparisonPlot(c)

        else:
            for txtFile in self.txtFileList:
                c = self.getConversionObjectFromOneTxtFile(txtFile)
                self.updateStatsTable(c)
            self.statsColumnMaxValues = self.getStatsMaxValues()

            for txtFile in self.txtFileList:
                c = self.getConversionObjectFromOneTxtFile(txtFile)
                self.drawResultsPlots(c)
                self.drawComparisonPlot(c)

        self.progress.close()
        self.showCanvases()
        
        seconds = time.time() - start_time
        print("--- {} minutes ---".format(seconds / 60.0))

        self.saveResultsFiguresAsPdf()
        self.saveComparisonFigures()
        self.combineComparisonFigures()
        self.statsTable.printTable()
        self.statsTable.tableToPdf(self.workingDir)
        self.statsTable.tableToPdf(self.workingDir, 'acceleration')
        self.combinePdfs()

    def processUserInput(self):
        self.setEventTimestamp()
        self.eventTimestampReadable = getReadableTimestamp(self.eventTimestamp)
        self.setMiniseedDir()
        self.setWorkingBaseDir()
        self.setMiniseedFileInfo()
        if not self.isMiniseedCountValid():
            return
        if not self.isWorkingDirWritable():
            return
        self.setWorkingDir()
        self.convertMiniseedToAscii()
        self.setTxtFileInfo()
        self.pairDeviceTxtFiles()
        self.showProgress()
        self.getResults()
        
    def createSubmitButton(self):
        """Create single submit button - default state is inactive"""
        self.submitBtn = QPushButton(self)
        self.submitBtn.setText("Submit")
        # using only plain time-domain approach now - add others later
        self.submitBtn.clicked.connect(self.processUserInput)
        self.generalLayout.addWidget(self.submitBtn)
        self.submitBtn.setEnabled(False)


# table holding peak values for acceleration, velocity, and displacement for each
# channel of each device (modeled after third-party report)
class StatsTable:
    def __init__(self, eventTimestampReadable):
        self.eventTimestampReadable = eventTimestampReadable
        self.columnHeaders = ['Ch', 'ID', 'Floor', 'Axis', 'Offset Acc (g)', 'Acc (g)', 'Vel (cm/s)', 'Disp (cm)']
        self.df = pd.DataFrame(columns=self.columnHeaders)

        self.populateStaticColumns()

    def populateStaticColumns(self):
        channels = [x for x in range(1, 25)]
        self.df['Ch'] = channels
        self.df['ID'] = SENSOR_CODES_WITH_CHANNELS
        floors = [getFloorCode(x) for x in SENSOR_CODES_WITH_CHANNELS]
        self.df['Floor'] = floors
        axes = [getAxis(x) for x in SENSOR_CODES_WITH_CHANNELS]
        self.df['Axis'] = axes

    def updateStatsDf(self, sensorCodeWithChannel, statsColumnName, value):
        """
        update stats dataframe where 'ID' equals sensorCodeWithChannel
        sensorCodeWithChannel: string holding sensor code with channel (from Conversion object)
        statsColumnName: string holding name of stats table dataframe column to be updated
        value: value to be set in statsDf (will come from stats of Conversion object)
        """
        self.df.loc[self.df['ID'] == sensorCodeWithChannel, statsColumnName] = value

    def getColumnMax(self, statsColumnName):
        """
        get maximum value in given column
        statsColumnName: string holding name of stats table dataframe column from which to find maximum value
        """
        return self.df[statsColumnName].max()

    def printTable(self):
        """print stats table to console"""
        print(self.df)

    def tableToPdf(self, workingDir, columns='all'):
        """
        convert stats table to pdf (via html)
        workingDir: string holding path to working directory (where pdf will be created)
        columns: string holding 'all' for all columns or 'acceleration' for bandpassed acceleration only
        """
        elements = []

        if columns == 'all':
            tableContent = self.df.to_numpy().tolist()
            tableContent.insert(0, self.columnHeaders)
            pdfFilename = 'stats_table_all.pdf'
        elif columns == 'acceleration':
            headers = ['Ch', 'ID', 'Floor', 'Axis', 'Acc (g)']
            tableContent = self.df[headers].to_numpy().tolist()
            tableContent.insert(0, headers)
            pdfFilename = 'stats_table_acc.pdf'
        
        # tableContent.insert(0, printedHeaders)

        tableLineLength = len(tableContent[0])
        tableLineComment = 'Unconfirmed preliminary results'
        tableLineList = [''] * (tableLineLength - 1)
        tableLineList.insert(0, tableLineComment)
        tableContent.insert(0, tableLineList)

        pdfFile = os.path.join(workingDir, pdfFilename)

        pdf = SimpleDocTemplate(
        pdfFile,
        pagesize=letter,
        rightMargin = 10,
        leftMargin = 28,
        topMargin = 5,
        bottomMargin = 5
        )

        # testing reportlab for table
        table = Table(tableContent, colWidths=[80, 80], rowHeights=24)
        primaryStyle = TableStyle([
            ('BACKGROUND', (0, 1), (6, 1), "#E3E3E3"),
            ('ALIGN', (0, 0), (0, 0), 'LEFT'),
            ('TEXTCOLOR', (0, 0), (-1, 0), "#000000"),
            ('ALIGN', (0, 1), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('FONTNAME', (0, 0), (-1, 0), 'Times-Bold'),
            ('FONTNAME', (0, 1), (-1, 1), 'Times-Bold'),
            ('FONTSIZE', (0, 1), (-1, 0), 10),
            ])

        table.setStyle(primaryStyle)

        numRows = len(tableContent)
        for i in range(1, numRows):
            if i >= 2:
                if i % 2 == 0:
                    color = "#FFFFFF"
                else:
                    color = "#F0F0F0"
                lineStyle = TableStyle([('BACKGROUND', (0, i), (-1, i), color)])
                table.setStyle(lineStyle)

        boxStyle = TableStyle([('BOX', (0,0), (-1,-1), 0.25, "#000000")])
        table.setStyle(boxStyle)

        headerElements = getReportHeader(self.eventTimestampReadable)
        for element in headerElements:
            elements.append(element)
        elements.append(table)

        pdf.build(elements)

        '''

        # replace blank lines in table template with table content
        with open(tableTemplate, 'r') as inFile:
            tableText = inFile.read().replace('insert table', html)

        # create html version of stats table
        htmlTable = os.path.join(workingDir, htmlFilename)
        with open(htmlTable, 'w+') as resultTable:
            resultTable.write(tableText)

        # testing html to pdf with PyQt5

        loader = QtWebEngineWidgets.QWebEngineView()
        loader.setZoomFactor(1)
        loader.page().pdfPrintingFinished.connect(
            lambda *args: print('finished:', args))
        #with open(resultTable, 'r') as htmlResults:
        #     content = htmlResults.read()
        loader.setHtml(tableText)
        print('setHtml() ran')
        #loader.page().printToPdf(pdfFile)

        def emitPdf(finished):
            print('value of finished var: {0}'.format(finished))
            print('emitPdf() entered')
            loader.show()
            loader.page().printToPdf(pdfFile)
            print('emitPdf() was run')

        loader.loadFinished.connect(emitPdf)
        print('load finished')

        
        # WeasyPrint will be installed on Linux, not Windows or MacOS
        try:
            # get WeasyPrint HTML object
            wpHtml = HTML(string=tableText)
            wpHtml.write_pdf(pdfFile)
        except:
            # read contents of html table and css style and assign to variables
            with open(htmlTable, 'r') as resultTable:
                tableString = resultTable.read()

            with open(tableStyle, 'r') as style:
                styleString = style.read()

            with open(pdfFile, 'w+b') as resultFile:
                pisa.CreatePDF(tableString, resultFile, default_css=styleString)
        '''

# Comparison Figure objects were going to be used to display four plots but ...
class ComparisonFigure(Figure):
    def __init__(self, title, width=14, height=20, dpi=100):
        Figure.__init__(self)
        self.title = title
        self.figsize = (width, height)
        self.dpi = dpi


class BaseCanvas(QMainWindow):
    def __init__(self, windowTitle, width=14, height=20, dpi=100):
        QMainWindow.__init__(self)
        self.windowTitle = windowTitle
        self.setWindowTitle(self.windowTitle)
        self.figure = Figure(figsize=(width, height), dpi=dpi)
        self.widget = QWidget()
        self.setCentralWidget(self.widget)
        self.vbox = QVBoxLayout()
        self.widget.setLayout(self.vbox)
        self.widget.layout().setContentsMargins(0, 0, 0, 0)
        self.widget.layout().setSpacing(0)

        self.canvas = FigureCanvas(self.figure)

        self.scroll = QScrollArea(self.widget)
        self.scroll.setWidget(self.canvas)

        self.nav = NavigationToolbar(self.canvas, self.widget)
        self.widget.layout().addWidget(self.nav)
        self.widget.layout().addWidget(self.scroll)

    # seems that use of QDesktopWidget() causes part of Navigation bar to turn black and/or not appear
    '''
    def setScreenLocation(self):
        """set location of results canvases"""
        availableGeom = QDesktopWidget().availableGeometry()
        screenGeom = QDesktopWidget().screenGeometry()

        widgetGeom = self.geometry()

        x = screenGeom.width() - widgetGeom.width()
        y = screenGeom.height() - widgetGeom.height()

        self.move(x, y)
    '''


# ComparisonCanvas objects used to display four plots
# wanted to show four ComparisonFigure objects (with four plots each) but seems that
# each FigureCanvas can only have one Figure object
class ComparisonCanvas(BaseCanvas):
    def __init__(self, windowTitle):
        BaseCanvas.__init__(self, windowTitle, width=4, height=7)
        self.setFixedSize(450, 800)


# ResultsCanvas objects used to display plots for all 24 devices/channels
# Class has one instance each of:
#    Figure (which can hold multiple subplots)
#    FigureCanvas (which holds the figure)
class ResultsCanvas(BaseCanvas):
    def __init__(self, windowTitle):
        BaseCanvas.__init__(self, windowTitle)
        self.setFixedSize(1470, 1000)


# Client code
def main():
    """Main function."""
    # Create an instance of QApplication
    convertacc = QApplication(sys.argv)

    # Show the application's GUI
    view = PrimaryUI()
    view.show()

    # Execute the program's main loop
    sys.exit(convertacc.exec_())