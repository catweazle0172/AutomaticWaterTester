'''
AutoTester is the controlling software to automatically run water tests
Further info can be found at: https://robogardens.com/?p=928
This software is free for DIY, Nonprofit, and educational uses.
Copyright (C) 2017 - RoboGardens.com
    
Created on Aug 9, 2017

This module receives commands from the Web interface and executes them.

@author: Stephen Hayes
'''

from AutoTester import  osmoseCleanMixerReactor,runTestSequence,loadFeatureWindow,evaluateResults,queueTestJob,CalibratePH
from TesterCore import Tester

from ImageCheck import swatch,colorSheet

from Alarms import sendTestMeasurementReport

def resetDisplayFlags(tester):
    tester.displayDot=False
    tester.showTraining=None
    tester.showSwatches=False
    tester.testStatus=None
    tester.colorTable=None
    
def shiftSwatches(tester,colorSheetName,lightingConditions,colShift,rowShift):
    swatchList=tester.colorSheetList[colorSheetName].swatchList
    for swatchNameAndCondition in swatchList:
        swatch=swatchList[swatchNameAndCondition]
#        if swatch.lightingConditions==lightingConditions:
        swatch.swatchULRow+=rowShift
        swatch.swatchULCol+=colShift
        swatch.swatchLRRow+=rowShift
        swatch.swatchLRCol+=colShift
    
def updateSwatch(tester,image,swatchRow,colorSheetName,newValue):
    try:
        swatch=tester.currentColorSheet.swatchList[str(swatchRow) + '/LED']
    except:
        tester.debugLog.exception('Swatch: ' + str(swatchRow) + ' Not found')
        return None   #The swatch may not exist
    swatch.colorSheetName=colorSheetName
    l,a,b=swatch.getAvgCIELabImage(tester,image)
    swatch.channel1=l
    swatch.channel2=a
    swatch.channel3=b
    swatch.lightingConditions='LED'
    if newValue == "Disable":
        swatch.enabled=False
        return swatch
    elif newValue=='':
        return swatch
    else:
        try:
            swatch.valueAtSwatch=float(newValue)
            return swatch
        except:                  
            tester.debugLog.exception("Invalid value for Value: " + str(swatchRow))
            return None
    
def saveSwatch(tester,swatchRow,newValue):
    cs=tester.currentColorSheet
    colorSheetName=cs.colorSheetName
    tester.videoLowResCaptureLock.acquire()
    tester.videoLowResCaptureLock.wait()
    imageCopy=tester.latestLowResImage.copy()
    tester.videoLowResCaptureLock.release()
    swatch=updateSwatch(tester,imageCopy,swatchRow,colorSheetName,newValue)
    try:
        print(colorSheetName)
        tester.saveColorSheetIntoDB(colorSheetName)
    except:
        tester.debugLog.exception("Unable to Save Swatch to Database")
    tester.colorTable=tester.currentColorSheet.generateColorTableDisplay(tester)
    print('Database updated with new Swatch')

def saveSet(tester,valueString):
    try:
        csParts=valueString.split(':')
        colorSheetName=csParts[0][2:]
        colorSheetItem=csParts[1][2:]
        colorSheetLighting=csParts[2][2:]
    except:
        tester.debugLog.exception("Error Parsing Clone Save String")
    try:
        cs=tester.colorSheetList[colorSheetName]
    except:
        cs=colorSheet(colorSheetName)
        tester.colorSheetList[colorSheetName]=cs
    cs.itemBeingMeasured=colorSheetItem
    tester.videoLowResCaptureLock.acquire()
    tester.videoLowResCaptureLock.wait()
    imageCopy=tester.latestLowResImage.copy()
    tester.videoLowResCaptureLock.release()
    i=1
    while i<=9:
        swatch=updateSwatch(tester,imageCopy,i,colorSheetName,colorSheetLighting,csParts)
        if not swatch is None:
            cs.swatchList[str(i) + '/' + colorSheetLighting]=swatch
        i+=1
    try:
#        print(colorSheetName)
        tester.saveColorSheetIntoDB(colorSheetName)
    except:
        tester.debugLog.exception("Unable to Save Cloned ColorString to Database")
    tester.colorTable=tester.currentColorSheet.generateColorTableDisplay(tester)
    print('Database updated with cloned swatches')

def parseHome(tester,cmdOperation,cmdObject,cmdValue):
    try:
        if cmdOperation=='Abort':
            tester.abortJob=True
        else:
            print('Unknown HOME operation: ' + cmdOperation)                               
    except:
        tester.debugLog.exception("Error in HOME parsing")

def parseControl(tester,cmdOperation,cmdObject,cmdValue):
    try:
        if cmdOperation=='CalibrateMeasurement':
            tester.calibrateArduinoSensor()
        elif cmdOperation=='Measure':     
            tester.measureArduinoSensor()
        elif cmdOperation=='AgitatorOn':
            tester.turnAgitator(0)
        elif cmdOperation=='AgitatorOff':
            tester.turnAgitatorOff()
        elif cmdOperation=='CleanTankwater':
            cleanMixerReactor(tester)    
        elif cmdOperation=='CleanOsmoseWater':
            osmoseCleanMixerReactor(tester)               
        elif cmdOperation=='Fill5MLTankWater':
            tester.MixerReactorPump(5,'tankwater')
        elif cmdOperation=='Fill5MLOsmoseWater':
            tester.MixerReactorPump(5,'osmosewater')
        elif cmdOperation=='HomeSyringe':
            tester.homingArduinoStepper()
        elif cmdOperation=='UpSyringe':
            tester.UpperSyringes()
        elif cmdOperation=='MainDrainPump':
            tester.mainDrainPump(8)
        elif cmdOperation=='OsmoseCleanPump':
            tester.osmoseCleanPump(6)
        elif cmdOperation=='OsmoseCleanPump':
            tester.cleanDrainPump(8)  

        else:
            print('Unknown CONTROL operation: ' + cmdOperation) 
    except:                  
 
       tester.debugLog.exception("Error in CONTROL parsing")

def parseCalibrate(tester,cmdOperation,cmdObject,cmdValue):
    try:
        if cmdOperation=='DoseAutoTester':
            tester.loadCalibrationValuesFromDB()
            tester.calibrateAutoTesterPump()
        elif cmdOperation=='DoseKHSample':
            tester.loadCalibrationValuesFromDB()
            tester.calibrateKHSamplePump()
        elif cmdOperation=='DoseKHReagent':
            tester.loadCalibrationValuesFromDB()
            tester.calibrateKHReagentPump()
        elif cmdOperation=='CalPH4':
            CalibratePH(tester)
        elif cmdOperation=='CalPH7':
            CalibratePH(tester)
        elif cmdOperation=='UPDATE':
            tester.calculateCalibrationValues()
            tester.loadCalibrationValuesFromDB()
        else:                     
            print('Unknown CALIBRATION operation: ' + cmdOperation)                   
    except:
        tester.debugLog.exception("Error in CALIBRATION parsing")
        
def queueDiagnosticTest(tester,cmdOperation,cmdObject):
    tester.diagnosticLock.acquire()
    tester.diagnosticQueue.append([cmdOperation,cmdObject])
    tester.diagnosticLock.release()

def parseDiagnostics(tester,cmdOperation,cmdObject,cmdValue):
    try:
        if cmdOperation=="Dispense5":
            dispenseDrops(tester,5)
        elif cmdOperation=='ConsoleOn':
            tester.enableConsoleOutput=True
        elif cmdOperation=='ConsoleOff':
            tester.enableConsoleOutput=False
        elif cmdOperation=='Snapshot':
            takeSnapshot(tester)
        elif cmdOperation=='Carousel Diagnostic':
            queueDiagnosticTest(tester,cmdOperation,5)                   
        elif cmdOperation=='Plunger Diagnostic':
            queueDiagnosticTest(tester,cmdOperation,5)                   
        elif cmdOperation=='Dispense Diagnostic':
            queueDiagnosticTest(tester,cmdOperation,5)                   
        elif cmdOperation=='Fill Mixer Diagnostic':
            queueDiagnosticTest(tester,cmdOperation,5)                   
        else:
            print('Unknown DIAGNOSTIC operation: ' + cmdOperation)
    except:                  
        tester.debugLog.exception("Error in DIAGNOSTIC parsing")
        
def parseClickString(tester,cmdObject,cmdValue):
    #The Syntax of the click value string is:  'x-Coord,y-Coord,value
    clickParts=cmdObject.split(',')
    try:
        xCoord=int(clickParts[0])
        yCoord=int(clickParts[1])
        swatchValue=float(cmdValue)
        return xCoord,yCoord,swatchValue
    except:
        return -1,-1,-1       

def parseSwatch(tester,cmdOperation,cmdObject,cmdValue):
    tester.showSwatches=True
    try:
        tester.featureStepSize=float(cmdObject)
    except:
        pass
    try:
        if cmdOperation=='SetSheet':
            try:
                tester.currentColorSheet=tester.colorSheetList[cmdObject]
                tester.currentColorSheet.loadSwatchesImage(tester,-1,-1,-1)              
            except:
                tester.debugLog.exception("Bad colorSheet")
        elif cmdOperation=='Click':
            xCoord,yCoord,swatchValue=parseClickString(tester,cmdObject,cmdValue)
            try:
                tester.currentColorSheet.loadSwatchesImage(tester,xCoord,yCoord,swatchValue)
            except:
                pass
        elif cmdOperation=='Reload':
            tester.loadColorSheetsFromDB()
        elif cmdOperation=='ShowTable':
            tester.colorTable=tester.currentColorSheet
        else:
            print('Unknown SWATCH operation: ' + cmdOperation)                               
    except:
        tester.debugLog.exception("Error in SWATCH parsing")

def parseAlarms(tester,cmdOperation,cmdObject,cmdValue):
    try:
        if cmdOperation=='testTelegram':
            sendTestMeasurementReport(tester,'Telegram Test',cmdObject)                    
        else:
            print('Unknown ALARMS operation: ' + cmdOperation)                               
    except:
        tester.debugLog.exception("Error in ALARMS parsing")

def parseSchedule(tester,cmdOperation,cmdObject,cmdValue):
    try:
        if cmdOperation=='reloadSchedules':
            tester.resetJobSchedule=True
        else:
            print('Unknown SCHEDULE operation: ' + cmdOperation)                               
    except:
        tester.debugLog.exception("Error in SCHEDULE parsing")

def parseReload(tester,cmdOperation,cmdObject,cmdValue):
    try:
        if cmdOperation=='TestDefs':
            tester.loadTestDefinitionsFromDB()
        elif cmdOperation=='Reagents':
            tester.loadReagentsFromDB()
        else:
            print('Unknown RELOAD operation: ' + cmdOperation)                               
    except:
        tester.debugLog.exception("Error in SCHEDULE parsing")

def processWebCommand(tester,commandString):
    resetDisplayFlags(tester)
    print('Command String Received: ' + str(commandString))
#    if tester.simulation:
#        return
    cmdParts=commandString.split('/')
    cmdCategory=None
    cmdOperation=None
    cmdObject=None
    cmdValue=None
    try:
        cmdCategory=cmdParts[0]
        cmdOperation=cmdParts[1]
        cmdObject=cmdParts[2]
        cmdValue=cmdParts[3]
    except:
        pass
    if cmdCategory=='Home':
        parseHome(tester,cmdOperation,cmdObject,cmdValue)
    elif cmdCategory=='OPERATE':
        parseOperate(tester,cmdOperation,cmdObject,cmdValue)
    elif cmdCategory=='CONTROL':
        parseControl(tester,cmdOperation,cmdObject,cmdValue)
    elif cmdCategory=='SWATCH':
        parseSwatch(tester,cmdOperation,cmdObject,cmdValue)
    elif cmdCategory=='DIAGNOSTIC':
        parseDiagnostics(tester,cmdOperation,cmdObject,cmdValue)
    elif cmdCategory=='CALIBRATE':
        parseCalibrate(tester,cmdOperation,cmdObject,cmdValue)
    elif cmdCategory=='ALARMS':
        parseAlarms(tester,cmdOperation,cmdObject,cmdValue)
    elif cmdCategory=='SCHEDULE':
        parseSchedule(tester,cmdOperation,cmdObject,cmdValue)
    elif cmdCategory=='RELOAD':
        parseReload(tester,cmdOperation,cmdObject,cmdValue)
    elif cmdCategory=='CLEAR':
        pass
    else:
        tester.debugLog.info('Unknown category in web command string: ' + commandString)        

if __name__ == '__main__':
    pass