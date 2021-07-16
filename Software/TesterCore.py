'''
AutoTester is the controlling software to automatically run water tests
Further info can be found at: https://robogardens.com/?p=928
This software is free for DIY, Nonprofit, and educational uses.
Copyright (C) 2017 - RoboGardens.com
	
Created on Aug 9, 2017

This module is the interface towards the autotester physical hardware and the database.
The tester Class is the primary class representing the machine.

@author: Stephen Hayes
'''

import cv2   # @UnresolvedImport
import numpy as np
import math
import time
import os
from adafruit_motorkit import MotorKit
#import fisheye
#from FishEyeWrapper import FishEye,load_model
from ImageCheck import feature,colorSheet,swatch
import sys
import platform
import datetime
from datetime import datetime as dt
#from datetime import datetime, timedelta
import _pickle
import copy
import logging
from logging.handlers import RotatingFileHandler
import traceback
import django
from django.utils.timezone import activate
from django.utils.dateparse import parse_datetime
from django.utils import timezone
import pytz
import serial
from colormath.color_objects import LabColor, AdobeRGBColor, sRGBColor
from colormath.color_conversions import convert_color
from DFRobot_ADS1115 import ADS1115
from DFRobot_PH      import DFRobot_PH

try:
	from picamera.array import PiRGBArray   # @UnresolvedImport
	from picamera import PiCamera   # @UnresolvedImport
except:
	pass

currentVersion="0.04"

if platform.system()=='Windows':
	existsGPIO=False
	existsDisplay=True
	existsWebCam=True
else:
	import RPi.GPIO as GPIO   # @UnresolvedImport
	existsGPIO=True
	existsDisplay=False
	existsI2C=True
	existsWebCam=True
	
#PLUNG mark
KHSamplePumpEnableGPIO=27
KHSamplePumpStepGPIO=17
KHSamplePumpDirectionGPIO=23

#CAROUSEL mark
KHReagentPumpEnableGPIO=9
KHReagentPumpStepGPIO=10
KHReagentPumpDirectionGPIO=22

#AGITATOR mark
mainPumpEnableGPIO=6
mainPumpStepGPIO=5
mainPumpDirectionGPIO=11

ads1115 = ADS1115()
ph      = DFRobot_PH()

PHsamplesBetweenTest = 5
temperature	= 25.0

class testSequence:
	def __init__(self,name):
		self.testName=name

class reagent:
	def __init__(self,name):
		self.name=name

class Tester:
	CAMERATYPE_NONE=0
	CAMERATYPE_WEBCAM=1
	CAMERATYPE_PICAM=2    

	PRESENTATION_METRIC=0
	PRESENTATION_IMPERIAL=1
	
	def __init__(self, id):
		self.KHTester = True
		self.LineTester = False
		self.id = id
		self.simulation=(platform.system()=='Windows')
		self.basePath=getBasePath()
		self.webcam=None
		self.lowResImageGenerator=None
		self.measurementUnits=self.PRESENTATION_IMPERIAL
		if existsGPIO:
			GPIO.setmode(GPIO.BCM)
			GPIO.setwarnings(False)
			GPIO.setup(mainPumpEnableGPIO,GPIO.OUT)
			GPIO.setup(mainPumpStepGPIO,GPIO.OUT)
			GPIO.setup(mainPumpDirectionGPIO,GPIO.OUT)
			GPIO.setup(KHSamplePumpEnableGPIO,GPIO.OUT)
			GPIO.setup(KHSamplePumpStepGPIO,GPIO.OUT)
			GPIO.setup(KHSamplePumpDirectionGPIO,GPIO.OUT)
			GPIO.setup(KHReagentPumpEnableGPIO,GPIO.OUT)
			GPIO.setup(KHReagentPumpStepGPIO,GPIO.OUT)
			GPIO.setup(KHReagentPumpDirectionGPIO,GPIO.OUT)
			GPIO.output(mainPumpEnableGPIO,GPIO.HIGH)
			GPIO.output(mainPumpStepGPIO,GPIO.LOW)
			GPIO.output(mainPumpDirectionGPIO,GPIO.LOW)
			GPIO.output(KHSamplePumpEnableGPIO,GPIO.HIGH)
			GPIO.output(KHSamplePumpStepGPIO,GPIO.LOW)
			GPIO.output(KHSamplePumpDirectionGPIO,GPIO.LOW)
			GPIO.output(KHReagentPumpEnableGPIO,GPIO.HIGH)
			GPIO.output(KHReagentPumpStepGPIO,GPIO.LOW)
			GPIO.output(KHReagentPumpDirectionGPIO,GPIO.LOW)

		if self.KHTester is True:
			self.pca60 = MotorKit(address=0x60)
			self.pca60.motor2.throttle = 0
			self.pca60.motor4.throttle = 0

		if self.LineTester is True:
			self.pca61 = MotorKit(address=0x61)
			self.pca62 = MotorKit(address=0x62)
			self.pca62.motor3.throttle = 1		#Close valve Tank Water
			self.pca62.motor4.throttle = 1		#Close valve Osmose Water

		self.ArduinoStepper=False
		self.ArduinoSensor=False
		self.hommeArduinoStepper=False
		self.loadTesterFromDB()
		self.loadCalibrationValuesFromDB()
		self.loadProcessingParametersFromDB()
		self.loadStartupParametersFromDB()
		self.loadReagentsFromDB()
		self.testerLog=logging.getLogger('TesterLog')
		handler = RotatingFileHandler(self.basePath+ "Logs/tester.log", maxBytes=2000, backupCount=4)
		simpleFormatter = logging.Formatter('%(asctime)s - %(message)s')
		normalFormatter = logging.Formatter('%(asctime)s - %(threadName)s - %(message)s')
		handler.setFormatter(simpleFormatter)
		handler.setLevel(logging.INFO)
		self.testerLog.addHandler(handler)
		self.testerLog.setLevel(logging.INFO)
		self.debugLog=logging.getLogger('Debug')
		console = logging.StreamHandler()
		console.setLevel(logging.DEBUG)
		console.setFormatter(normalFormatter)
		self.debugLog.addHandler(console)
		handler2 = RotatingFileHandler(self.basePath+"Logs/debug.log", maxBytes=8000, backupCount=4)
		handler2.setFormatter(normalFormatter)
		handler2.setLevel(logging.INFO)
		self.debugLog.addHandler(handler2)
		self.debugLog.setLevel(logging.DEBUG)
		self.cameraType=self.getCameraType()
		self.undistortImage=False
		self.createDefaultBlackScreen()
		self.getCameraModel()
		self.videoLowResCaptureLock=None
		self.latestLowResImage=None
		self.streamVideo=True
		self.useImageForCalibration=False
		self.cameraCompensationTransformationMatrix=None
		self.testerScheduleRegenerate=True
		self.extruderFound=False
		self.showTraining=False
		self.captureImageLock=None
		self.currentLightingConditions='LED'
		self.lightingConditionToDisplay='LED'
		self.currentAvgColor=np.array([0,0,0])
		self.tooDark=False  
		self.infoMessage('Tester Engine version ' + currentVersion + ' loaded') 
		self.mainPumpEnabled=False
		self.KHSamplePumpEnabled=False
		self.KHReagentPumpEnabled=False
		self.displayDot=False
		self.avgGreenDotH=None
		self.avgGreenDotS=None
		self.avgGreenDotV=None
		self.avgRedDotH=None
		self.avgRedDotS=None
		self.avgRedDotV=None
		self.featureWindowULRow=0
		self.featureWindowULCol=0
		self.featureWindowLRRow=0
		self.featureWindowLRCol=0
		self.featureStepSize=1
		self.currentFeature=None
		self.loadTestDefinitionsFromDB()
		self.stopperState=None
		self.referenceMarkFound=False
		self.parked=True
		self.jiggleRepetitionPhotos=0  #Num of photos to take at different shifts.  If > 0 then clipping frame offset by up to + or - jiggleShiftMax
		self.jiggleShiftMax=5
		self.jigglePhoto=False  #Turns on only when training photos are to be taken
		self.seriesRunning=False
		self.lastReagentRemainingML=0
		self.lastReagentName=None
		self.suppressProcessing=False
		self.dripValueList=[]
		self.dripSamplesSoFar=0
		self.dripMinGap=4
		self.dripTopList=[]
		self.loadColorSheetsFromDB()
		self.currentColorSheet=None
		self.currentSwatch=None
		self.showSwatches=False
		self.colorTable=None
		self.runTestLock=None
		self.testStatus=None
		self.currentTest=None
		self.recordTestedImage=True
		self.abortJob=False
		self.resetJobSchedule=False
		self.diagnosticQueue=[]
		self.diagnosticLock=None
		self.systemStatus='Initializing'

		
	def getCameraModel(self):
		self.cameraModelFile=self.basePath + '/Calibrate/FisheyeUndistort-(' + self.lensType + ',' + str(self.cameraHeightLowRes) + ' x ' + str(self.cameraWidthLowRes) + ')-' + sys.version[0] + '.pkl'
		try:
			aggregateFishEyeModel=load_model(self.cameraModelFile)
			self.cameraFisheyeModel=aggregateFishEyeModel[0]
			self.cameraFisheyeExpansionFactor=aggregateFishEyeModel[1]
			self.infoMessage('Camera Model Loaded')
		except:
			self.cameraFisheyeModel=None
			self.infoMessage('Camera Model Not Found')
			self.cameraFisheyeExpansionFactor=self.defaultFisheyeExpansionFactor
		
	def debugMessage(self,message):
		try:
			if self.enableConsoleOutput:
				self.debugLog.debug(message)
		except:  #Might not have initialized yet
			print(message)
			
	def infoMessage(self,message):
		try:
			self.debugLog.info(message)
		except:  #Might not have initialized yet
			print(message)
			
	def loadTesterFromDB(self):
		from tester.models import TesterExternal
		te=TesterExternal.objects.get(pk=1)
		self.testerName=te.testerName
		self.testerVersion=te.testerVersion
		self.dbModelVersion=te.dbModelVersion
		self.virtualEnvironmentName=te.virtualEnvironmentName
		self.lensType=te.lensType
		self.cameraWidthLowRes=te.cameraWidthLowRes
		self.cameraHeightLowRes=te.cameraHeightLowRes
		self.tooDarkThreshold=te.tooDarkThreshold
		self.webPort=te.webPort
		self.videoStreamingPort=te.videoStreamingPort
		self.measurementUnits=te.measurementUnits
		self.pumpPurgeTimeSeconds=te.pumpPurgeTimeSeconds
		self.mixerCleanML=te.mixerCleanML
		self.mixerCleanCycles=te.mixerCleanCycles
		self.mixerCleanCyclesExtraAfterHours=te.mixerCleanCyclesExtraAfterHours
		self.reagentRemainingMLAlarmThresholdAutoTester=te.reagentRemainingMLAlarmThresholdAutoTester
		self.reagentRemainingMLAlarmThresholdKHTester=te.reagentRemainingMLAlarmThresholdKHTester
		self.reagentAlmostEmptyAlarmEnable=te.reagentAlmostEmptyAlarmEnable
		self.pauseInSecsBeforeEmptyingMixingChamber=te.pauseInSecsBeforeEmptyingMixingChamber
		self.telegramBotToken=te.telegramBotToken
		self.telegramChatID=te.telegramChatID
		self.sendMeasurementReports=te.sendMeasurementReports
		self.daysOfResultsToKeep=te.daysOfResultsToKeep
		self.enableConsoleOutput=te.enableConsoleOutput
		self.manageDatabases=te.manageDatabases

	def loadCalibrationValuesFromDB(self):
		from tester.models import CalibrationValues
		cv=CalibrationValues.objects.get(pk=1)
		self.calibrationMLAutotester=cv.calibrationMLAutotester
		self.calibrationMLKHSample=cv.calibrationMLKHSample
		self.calibraitonMLKHReagent=cv.calibraitonMLKHReagent

	def loadProcessingParametersFromDB(self):
		from tester.models import TesterProcessingParameters
		tpp=TesterProcessingParameters.objects.get(pk=1)
		self.framesPerSecond=tpp.framesPerSecond
		self.referenceCenterRow=tpp.defaultReferenceCenterRow
		self.referenceCenterCol=tpp.defaultReferenceCenterCol
		self.avgDotDistance=tpp.defaultAvgDotDistance
		self.defaultDotDistance=tpp.defaultAvgDotDistance
		self.skipOrientation=tpp.skipOrientation
		self.maxImageScalingWithoutAdjustment=tpp.maxImageScalingWithoutAdjustment
		self.minImageScalingWithoutAdjustment=tpp.minImageScalingWithoutAdjustment
		self.maxImageRotationWithoutAdjustment=tpp.maxImageRotationWithoutAdjustment
		self.minImageRotationWithoutAdjustment=tpp.minImageRotationWithoutAdjustment
		self.defaultFisheyeExpansionFactor=tpp.defaultFisheyeExpansionFactor
		self.gapTolerance=tpp.gapTolerance
		
	def loadStartupParametersFromDB(self):
		from tester.models import TesterStartupInfo
		tsi=TesterStartupInfo.objects.get(pk=1)
		self.seatedGap=tsi.seatedGap
		self.unseatedGap=tsi.unseatedGap
		
	def saveStartupParametersToDB(self):
		from tester.models import TesterStartupInfo
		tsi=TesterStartupInfo.objects.get(pk=1)
		tsi.seatedGap=self.seatedGap
		tsi.unseatedGap=self.unseatedGap
		tsi.save()
		
			
	def saveFeaturePosition(self,feat):                  
		from tester.models import TesterFeatureExternal
		testerToUpdate=TesterFeatureExternal.objects.get(featureName=feat.featureName)
		testerToUpdate.ulClipRowOffset=round(feat.ulClipRowOffset)
		testerToUpdate.ulClipColOffset=round(feat.ulClipColOffset)
		testerToUpdate.lrClipRowOffset=round(feat.lrClipRowOffset)
		testerToUpdate.lrClipColOffset=round(feat.lrClipColOffset)
		testerToUpdate.dlibPositionRowOffset=feat.dlibPositionRowOffset
		testerToUpdate.dlibPositionColOffset=feat.dlibPositionColOffset
		testerToUpdate.learnedWithReferenceDistance=feat.learnedWithReferenceDistance
		testerToUpdate.save()
		
	def loadTestDefinitionsFromDB(self):
		from tester.models import TestDefinition
		self.testSequenceList={}
		sequenceList=TestDefinition.objects.all()
		for seq in sequenceList:
			ts=testSequence(seq.testName)
			ts.enableTest=seq.enableTest
			ts.KHtestwithPHProbe=seq.KHtestwithPHProbe
			ts.waterVolInML=seq.waterVolInML
			ts.reagent1Slot=seq.reagent1Slot
			if not ts.reagent1Slot is None:
				ts.reagent1Slot=seq.reagent1Slot.slotName
			ts.reagent1AgitateSecs=seq.reagent1AgitateSecs
			ts.reagent1AgitateMixerSecs=seq.reagent1AgitateMixerSecs
			ts.reagent1AgitateSecsBetweenDrips=seq.reagent1AgitateSecsBetweenDrips
			ts.reagent1ThickLiquid=seq.reagent1ThickLiquid
			ts.reagent1Amount=seq.reagent1Amount
			ts.reagent2Slot=seq.reagent2Slot
			if not ts.reagent2Slot is None:
				ts.reagent2Slot=seq.reagent2Slot.slotName
			ts.reagent2AgitateSecs=seq.reagent2AgitateSecs
			ts.reagent2AgitateMixerSecs=seq.reagent2AgitateMixerSecs
			ts.reagent2AgitateSecsBetweenDrips=seq.reagent2AgitateSecsBetweenDrips
			ts.reagent2ThickLiquid=seq.reagent2ThickLiquid
			ts.reagent2Amount=seq.reagent2Amount
			ts.reagent3Slot=seq.reagent3Slot
			if not ts.reagent3Slot is None:
				ts.reagent3Slot=seq.reagent3Slot.slotName
			ts.reagent3AgitateSecs=seq.reagent3AgitateSecs
			ts.reagent3AgitateMixerSecs=seq.reagent3AgitateMixerSecs
			ts.reagent3AgitateSecsBetweenDrips=seq.reagent3AgitateSecsBetweenDrips
			ts.reagent3ThickLiquid=seq.reagent3ThickLiquid
			ts.reagent3Amount=seq.reagent3Amount
			ts.agitateMixtureSecs=seq.agitateMixtureSecs
			ts.delayBeforeReadingSecs=seq.delayBeforeReadingSecs
			ts.titrationSlot=seq.titrationSlot
			if not ts.titrationSlot is None:
				ts.titrationSlot=seq.titrationSlot.slotName
			ts.titrationAgitateSecs=seq.titrationAgitateSecs
			ts.titrationAgitateMixerSecs=seq.titrationAgitateMixerSecs
			ts.titrationTransition=seq.titrationTransition
			ts.titrationMaxAmount=seq.titrationMaxAmount
			ts.titrationFirstSkip=seq.titrationFirstSkip
			ts.colorChartToUse=seq.colorChartToUse
			if not ts.colorChartToUse is None:
				ts.colorChartToUse=seq.colorChartToUse.colorSheetName
			ts.lightAbsorptionTest=seq.lightAbsorptionTest
			if not ts.lightAbsorptionTest is None:
				ts.lightAbsorptionColor=seq.lightAbsorptionTest.LightAbsorptionColor
			ts.lightAbsorptionValue=seq.lightAbsorptionValue
			ts.lightAbsorptionResult=seq.lightAbsorptionResult
			ts.tooLowAlarmThreshold=seq.tooLowAlarmThreshold
			ts.tooLowWarningThreshold=seq.tooLowWarningThreshold
			ts.tooHighWarningThreshold=seq.tooHighWarningThreshold
			ts.tooHighAlarmThreshold=seq.tooHighAlarmThreshold
			ts.calctovalue=seq.calctovalue
			
			self.testSequenceList[ts.testName]=ts 
		
	def loadColorSheetsFromDB(self):
		from tester.models import ColorSheetExternal,SwatchExternal
		self.colorSheetList={}
		sheetList=ColorSheetExternal.objects.all()
		for csExternal in sheetList:
			cs=colorSheet(csExternal.colorSheetName)
			cs.itemBeingMeasured=csExternal.itemBeingMeasured
			cs.minPermissableValue=csExternal.minPermissableValue
			cs.maxPermissableValue=csExternal.maxPermissableValue
			self.colorSheetList[cs.colorSheetName]= cs
			swatchListExternal=SwatchExternal.objects.filter(colorSheetName__colorSheetName=cs.colorSheetName)
			for swatchExternal in swatchListExternal: 
				sw=swatch(cs.colorSheetName)
				sw.enabled=swatchExternal.enabled
				sw.swatchRow=swatchExternal.swatchRow
				sw.valueAtSwatch=swatchExternal.valueAtSwatch
				sw.lightingConditions=swatchExternal.lightingConditions.lightingConditionName
				sw.channel1=swatchExternal.channel1
				sw.channel2=swatchExternal.channel2
				sw.channel3=swatchExternal.channel3
				sw.swatchULRow=swatchExternal.swatchULRow
				sw.swatchULCol=swatchExternal.swatchULCol
				sw.swatchLRRow=swatchExternal.swatchLRRow
				sw.swatchLRCol=swatchExternal.swatchLRCol
				cs.swatchList[str(sw.swatchRow) + '/' + sw.lightingConditions]=sw
		
	def saveColorSheetIntoDB(self,colorSheetNameToDelete):
		from tester.models import ColorSheetExternal,SwatchExternal,LightingConditionsExternal
		ColorSheetExternal.objects.filter(colorSheetName=colorSheetNameToDelete).delete()
		cse=ColorSheetExternal()
		cs=self.colorSheetList[colorSheetNameToDelete]
		cse.colorSheetName=cs.colorSheetName
		cse.itemBeingMeasured=cs.itemBeingMeasured
		cse.minPermissableValue=cs.minPermissableValue
		cse.maxPermissableValue=cs.maxPermissableValue
		cse.save()
		lightingConditionsList=LightingConditionsExternal.objects.all()
		for lc in lightingConditionsList:
			lcName=lc.lightingConditionName
			floatValueSorted={}
			for swName in cs.swatchList:
				sw=cs.swatchList[swName]
				if sw.lightingConditions==lcName and sw.enabled:
					floatValueSorted[sw.valueAtSwatch]=sw
				rowIndex=1
			for swName in sorted(floatValueSorted):
				sw=floatValueSorted[swName]
				swe=SwatchExternal()
				swe.colorSheetName=ColorSheetExternal.objects.get(colorSheetName=colorSheetNameToDelete)
				swe.swatchRow=rowIndex
				swe.valueAtSwatch=sw.valueAtSwatch
				swe.lightingConditions=LightingConditionsExternal.objects.get(lightingConditionName=sw.lightingConditions)
				swe.channel1=sw.channel1
				swe.channel2=sw.channel2
				swe.channel3=sw.channel3
				swe.swatchULRow=sw.swatchULRow
				swe.swatchULCol=sw.swatchULCol
				swe.swatchLRRow=sw.swatchLRRow
				swe.swatchLRCol=sw.swatchLRCol
				swe.enabled=sw.enabled
				swe.save()
				rowIndex+=1
		#Rows got reordered so load up the swatches again
		cs.swatchList={}
		swatchListExternal=SwatchExternal.objects.filter(colorSheetName__colorSheetName=cs.colorSheetName)
		for swatchExternal in swatchListExternal: 
			sw=swatch(cs.colorSheetName)
			sw.enabled=swatchExternal.enabled
			sw.swatchRow=swatchExternal.swatchRow
			sw.valueAtSwatch=swatchExternal.valueAtSwatch
			sw.lightingConditions=swatchExternal.lightingConditions.lightingConditionName
			sw.channel1=swatchExternal.channel1
			sw.channel2=swatchExternal.channel2
			sw.channel3=swatchExternal.channel3
			sw.swatchULRow=swatchExternal.swatchULRow
			sw.swatchULCol=swatchExternal.swatchULCol
			sw.swatchLRRow=swatchExternal.swatchLRRow
			sw.swatchLRCol=swatchExternal.swatchLRCol
			cs.swatchList[str(sw.swatchRow) + '/' + sw.lightingConditions]=sw

		self.currentColorSheet=cs
	
	def makeResultStripDirectory(self):
		if os.path.isdir(self.basePath + '/tester/static/tester/resultstrips'):
			return
		else:
			os.mkdir(self.basePath + '/tester/static/tester/resultstrips') 
			   
	def saveTestResults(self,results,swatchResultList=None):
		try:
			from tester.models import TestResultsExternal
			tre=TestResultsExternal()
			tre.testPerformed=self.currentTest
			if results is None:
				tre.results=None
				tre.status='Failed'
			else:
				tre.status='Completed'
				tre.results=str(results)
			whenPerformed=timezone.now()
			tre.datetimePerformed=whenPerformed
			if not swatchResultList is None:
				tre.swatchFile='Strip-' + whenPerformed.strftime("%Y-%m-%d %H-%M-%S") + '.jpg'
			tre.save()
			if swatchResultList is None:
				return True
			sw=swatchResultList[0]
			swatchStrip=sw.generateSwatchResultList(swatchResultList)
			self.makeResultStripDirectory()
			saveName=self.basePath + '/tester/static/tester/resultstrips/Strip-' + whenPerformed.strftime("%Y-%m-%d %H-%M-%S") + '.jpg'
			cv2.imwrite(saveName,swatchStrip)
			return True
		except:
			traceback.print_exc()
			return False
		
	def removeOldRecords(self):
		removeRecordsOlderThan=timezone.now()-datetime.timedelta(days=self.daysOfResultsToKeep)
		print('Removing records older than: ' + str(removeRecordsOlderThan))
		try:
			from tester.models import TestResultsExternal
			oldRecords=TestResultsExternal.objects.filter(datetimePerformed__lte=removeRecordsOlderThan)
			for oldRecord in oldRecords:
				oldRecord.delete()
			self.makeResultStripDirectory()
			resultStripDirectory=self.basePath + '/tester/static/tester/resultstrips'
			fileList=os.listdir(resultStripDirectory)
			for file in fileList:
				if file[0:6]=='Strip-' and file[25:29]=='.jpg':
					dateString=file[6:25]
					fileDate=datetime.datetime.strptime(dateString,'%Y-%m-%d %H-%M-%S')
					if fileDate<removeRecordsOlderThan:
						os.remove(resultStripDirectory + '/' + file)
		except:
			traceback.print_exc()                        
		return
		
	def failureList(self,text):
		colSize=200
		listStruct=np.zeros((30,colSize,3),dtype=np.uint8)
		font = cv2.FONT_HERSHEY_SIMPLEX 
		cv2.putText(listStruct,text,(10,20), font, .7,(255,255,255),2,cv2.LINE_AA)
		return listStruct
	
	def saveTestSaveBadResults(self):
		try:
			from tester.models import TestResultsExternal
			tre=TestResultsExternal()
			tre.testPerformed=self.currentTest
			whenPerformed=timezone.now()
			tre.datetimePerformed=whenPerformed
			if self.abortJob:
				tre.status='Aborted'
			else:
				tre.status='Failed'
			tre.results=None
			tre.swatchFile='Strip-' + whenPerformed.strftime("%Y-%m-%d %H-%M-%S") + '.jpg'
			tre.save()
			errorStrip=self.failureList('Failure')
			self.makeResultStripDirectory()
			saveName=self.basePath + '/tester/static/tester/resultstrips/Strip-' + whenPerformed.strftime("%Y-%m-%d %H-%M-%S") + '.jpg'
			cv2.imwrite(saveName,errorStrip)
			return True
		except:
			traceback.print_exc()
			return False
		
	def loadReagentsFromDB(self):
		try:
			from tester.models import ReagentSetup
			self.reagentList={}
			reagentList=ReagentSetup.objects.all()
			for rs in reagentList:
				rg=reagent(name=rs.slotName)
				rg.hasAgitator=rs.hasAgitator
				rg.fluidRemainingInML=rs.fluidRemainingInML
				self.reagentList[rg.name]=rg
		except:
			traceback.print_exc()
			return False
		
	def saveNewReagentValue(self,reagent,amountToDispense):
		from tester.models import ReagentSetup
		remainingML=ReagentSetup.objects.get(slotName=reagent).fluidRemainingInML-amountToDispense
		reagentObj=ReagentSetup.objects.get(slotName=reagent)
		self.lastReagentRemainingML=round(remainingML,2)
		reagentObj.fluidRemainingInML=self.lastReagentRemainingML
		reagentObj.save()

	def inReagentPosition(self,reagent):
		from tester.models import ReagentSetup
		if ReagentSetup.objects.get(slotName=reagent).hasAgitator:
			self.tosyringetop=round(((self.maxPlungerDepthAgitator-ReagentSetup.objects.get(slotName=reagent).fluidRemainingInML)*int(-self.plungerStepsPerMM))+500,2)
		else:
			self.tosyringetop=round(((self.maxPlungerDepthNoAgitator-ReagentSetup.objects.get(slotName=reagent).fluidRemainingInML)*int(-self.plungerStepsPerMM))+500,2)

	def setCameraRotationMatrix(self,compensationDegrees,compensationScale,centerRow,centerCol):
		self.cameraCompensationTransformationMatrix = cv2.getRotationMatrix2D((centerRow,centerCol),compensationDegrees,compensationScale)                
#        print('Col: ' + str(centerCol) + ', Row: ' + str(centerRow))
		
	def grabFrame(self):
		if not existsWebCam:
			return False
		if self.cameraType==self.CAMERATYPE_PICAM:
			lowResImage=None
			rotLowResImage=None
			if self.lowResImageGenerator==None:
				self.webcam.resolution=(self.cameraHeightLowRes,self.cameraWidthLowRes)
				self.lowResArray=PiRGBArray(self.webcam)
				self.lowResImageGenerator = self.webcam.capture_continuous(self.lowResArray,format='bgr',use_video_port=True)
			for frame in self.lowResImageGenerator:
				lowResImage=frame.array
				self.lowResArray.truncate(0)
				if self.undistortImage: 
					rot90image=np.rot90(lowResImage)
					if not self.cameraCompensationTransformationMatrix is None:
						width,height,channels=rot90image.shape
						rot90image = cv2.warpAffine(rot90image, self.cameraCompensationTransformationMatrix,(height,width),flags=cv2.INTER_LINEAR)                                            
					rotLowResImage=self.imageUndistort(rot90image)
				else:    
					rotLowResImage=np.rot90(lowResImage)
				break
			return rotLowResImage
		else:
			return None,None
		
	def fakeFrame(self):  #Used for simulation on windows computer
		if self.cameraType==self.CAMERATYPE_NONE:
			simulationImageFN=self.basePath + 'Simulation/NoCameraImage-' + str(self.cameraHeightLowRes) + 'x' + str(self.cameraWidthLowRes) + '.jpg'
		else:    
			simulationImageFN=self.basePath + 'Simulation/SimulationImage-' + str(self.cameraHeightLowRes) + 'x' + str(self.cameraWidthLowRes) + '.jpg'
		simulationImage=cv2.imread(simulationImageFN)
		return simulationImage
		
	def getCameraType(self):
		if self.simulation:
			return self.CAMERATYPE_NONE
		try:
			camera=PiCamera()
			self.infoMessage('Picam found')
			camera.close()
			self.infoMessage('Camera type is picamera')
			return self.CAMERATYPE_PICAM
		except:
#            traceback.print_exc()
			self.infoMessage('No camera found')
			self.systemStatus="Stopped - No Camera Found"
			self.simulation=True
			return self.CAMERATYPE_NONE
			
	def webcamInitialize(self):
		if self.cameraType==self.CAMERATYPE_PICAM:
			self.webcam=PiCamera()
			self.webcam.rotation=180
			self.webcam.framerate = self.framesPerSecond  
			self.webcam.resolution=(self.cameraHeightLowRes,self.cameraWidthLowRes)
			time.sleep(.1)
			return True 
		else:
			return None      
		
	def webcamRelease(self):
		if self.cameraType==self.CAMERATYPE_PICAM:
			if self.webcam==None:
				return
			else:
				self.webcam.close()
				self.webcam=None
				return
		else:
			return

	def createDefaultBlackScreen(self):
		font = cv2.FONT_HERSHEY_SIMPLEX        
		blackScreen=np.zeros((100,100),dtype=np.uint8)
		cv2.putText(blackScreen,"Video",(10,20), font, .50,(255,255,255),2,cv2.LINE_AA)
		cv2.putText(blackScreen,"Disabled",(10,40), font, .50,(255,255,255),2,cv2.LINE_AA)
		cv2.putText(blackScreen,"during",(10,60), font, .50,(255,255,255),2,cv2.LINE_AA)
		cv2.putText(blackScreen,"Dispense",(10,80), font, .50,(255,255,255),2,cv2.LINE_AA)
		r,jpg = cv2.imencode('.jpg',blackScreen)
		self.dummyBlackScreen=jpg        
			
	def imageUndistort(self,image):
		height,width,colors=image.shape
		if self.cameraFisheyeModel==None:
			self.debugMessage('Cannot undistort image because camera model does not exist, returning distorted image')
			return image
		else:
			Rmat=np.array([[1.,0.,0.],[0.,1.,0.],[0.,0.,self.cameraFisheyeExpansionFactor]])
			dst = self.cameraFisheyeModel.undistort(image, undistorted_size=(width, height),R=Rmat)
			return dst

	def mainDrainPump(self,sec):
		self.pca61.motor2.throttle = 1
		self.MainDrainPumpOn=True
		time.sleep(sec)
		self.pca61.motor2.throttle = 0
		self.MainDrainPumpOn=False
		return

	def osmoseCleanPump(self,sec):
		self.pca61.motor3.throttle = 1
		self.cleanPumpOn=True
		time.sleep(sec)
		self.pca61.motor3.throttle = 0
		self.cleanPumpOn=False
		return

	def cleanDrainPump(self,sec):
		if sec==0:
			self.pca61.motor4.throttle = 1
			self.cleanDrainPumpOn=True
			return
		else: 	
			self.pca61.motor4.throttle = 1
			self.cleanDrainPumpOn=True
			time.sleep(sec)
			self.pca61.motor4.throttle = 0
			self.cleanDrainPumpOn=False
			return
			
	def cleanDrainPumpOff(self):
		self.pca61.motor4.throttle = 0
		self.cleanDrainPumpOn=False
		return

	def turnAgitator(self,sec):
		if sec==0:
			self.pca61.motor1.throttle = 0.3
			time.sleep(0.1)
			self.pca61.motor1.throttle = 0.2
			self.agitatorOn=True
			return
		else: 	
			self.pca61.motor1.throttle = 0.3
			self.agitatorOn=True
			time.sleep(0.1)
			self.pca61.motor1.throttle = 0.2
			time.sleep(sec)
			self.pca61.motor1.throttle = 0
			self.agitatorOn=False
			return

	def turnAgitatorOff(self):
		self.pca61.motor1.throttle = 0
		self.agitatorOn=False
		return

	def calibrateAutoTesterPump(self):
		RampUpTimeDelay = 0.005
		self.pca62.motor3.throttle = 0		#Open valve Tank Water
		self.pca62.motor4.throttle = 1		#Close valve Osmose Water
		if not self.mainPumpEnabled:
			GPIO.output(mainPumpEnableGPIO,GPIO.LOW)
			time.sleep(.0005)
			self.mainPumpEnabled=True

		GPIO.output(mainPumpDirectionGPIO,GPIO.LOW)
		stepCountThisPump=0
		stepDelay=.0001
		stepsToPump=65000
		print (stepsToPump)

		while stepCountThisPump<stepsToPump:
			GPIO.output(mainPumpStepGPIO,GPIO.HIGH)
			time.sleep(stepDelay)
			GPIO.output(mainPumpStepGPIO,GPIO.LOW)
			time.sleep(stepDelay)
			stepCountThisPump+=1

			if RampUpTimeDelay > 0.0001:
				RampUpTimeDelay-=0.0001
				time.sleep(RampUpTimeDelay)

		self.mainPumpEnabled=False     
		GPIO.output(mainPumpEnableGPIO,GPIO.HIGH)
		self.pca62.motor3.throttle = 1		#Close valve Tank Water
		self.pca62.motor4.throttle = 1		#Close valve Osmose Water
		return True  

	def calibrateKHSamplePump(self):
		RampUpTimeDelay = 0.01
		if not self.KHSamplePumpEnabled:
			GPIO.output(KHSamplePumpEnableGPIO,GPIO.LOW)
			time.sleep(.0005)
			self.KHSamplePumpEnabled=True

		GPIO.output(KHSamplePumpDirectionGPIO,GPIO.LOW)
		stepCountThisPump=0
		stepDelay=.00001
		stepsToPump=940000
		print (stepsToPump)

		while stepCountThisPump<stepsToPump:
			GPIO.output(KHSamplePumpStepGPIO,GPIO.HIGH)
			time.sleep(stepDelay)
			GPIO.output(KHSamplePumpStepGPIO,GPIO.LOW)
			time.sleep(stepDelay)
			stepCountThisPump+=1

			if RampUpTimeDelay > 0.0001:
				RampUpTimeDelay-=0.0001
				time.sleep(RampUpTimeDelay)

		self.KHSamplePumpEnabled=False     
		GPIO.output(KHSamplePumpEnableGPIO,GPIO.HIGH)
		return True

	def calibrateKHReagentPump(self):
		RampUpTimeDelay = 0.01
		if not self.KHReagentPumpEnabled:
			GPIO.output(KHReagentPumpEnableGPIO,GPIO.LOW)
			time.sleep(.0005)
			self.KHReagentPumpEnabled=True

		GPIO.output(KHReagentPumpDirectionGPIO,GPIO.LOW)
		stepCountThisPump=0
		stepDelay=.00001
		stepsToPump=260000
		print (stepsToPump)

		while stepCountThisPump<stepsToPump:
			GPIO.output(KHReagentPumpStepGPIO,GPIO.HIGH)
			time.sleep(stepDelay)
			GPIO.output(KHReagentPumpStepGPIO,GPIO.LOW)
			time.sleep(stepDelay)
			stepCountThisPump+=1

			if RampUpTimeDelay > 0.0001:
				RampUpTimeDelay-=0.0001
				time.sleep(RampUpTimeDelay)

		self.KHReagentPumpEnabled=False     
		GPIO.output(KHReagentPumpEnableGPIO,GPIO.HIGH)
		return True  

	def MixerReactorPump(self,ml,water):
		RampUpTimeDelay = 0.005
		if water is 'tankwater':
			self.pca62.motor3.throttle = 0		#Open valve Tank Water
			self.pca62.motor4.throttle = 1		#Close valve Osmose Water
			stepsfor1ml=int(65000 / self.calibrationMLAutotester)
		elif water is 'osmosewater':
			self.pca62.motor3.throttle = 1		#Close valve Tank Water
			self.pca62.motor4.throttle = 0		#Open valve Osmose Water
			stepsfor1ml=int((65000 / self.calibrationMLAutotester)/1.5)
		if not self.mainPumpEnabled:
			GPIO.output(mainPumpEnableGPIO,GPIO.LOW)
			time.sleep(.0005)
			self.mainPumpEnabled=True
		if ml>0:
			GPIO.output(mainPumpDirectionGPIO,GPIO.LOW)
			stepIncrement=1
		else:
			GPIO.output(mainPumpDirectionGPIO,GPIO.HIGH)
			stepIncrement=-1

		stepCountThisPump=0
		stepDelay=.000025

		stepsToPump=ml*stepsfor1ml
		print (stepsToPump)

		while stepCountThisPump<stepsToPump:
			GPIO.output(mainPumpStepGPIO,GPIO.HIGH)
			time.sleep(stepDelay)
			GPIO.output(mainPumpStepGPIO,GPIO.LOW)
			time.sleep(stepDelay)
			stepCountThisPump+=1

			if RampUpTimeDelay > 0.0001:
				RampUpTimeDelay-=0.0001
				time.sleep(RampUpTimeDelay)
  
		GPIO.output(mainPumpEnableGPIO,GPIO.HIGH)
		self.mainPumpEnabled=False
		self.pca62.motor3.throttle = 1		#Close valve Tank Water
		self.pca62.motor4.throttle = 1		#Close valve Osmose Water
		return True  

	def sampleWaterPumpCommand(self,ml):
		RampUpTimeDelay = 0.01
		if not self.KHSamplePumpEnabled:
			GPIO.output(KHSamplePumpEnableGPIO,GPIO.LOW)
			time.sleep(.0005)
			self.KHSamplePumpEnabled=True
		if ml>0:
			GPIO.output(KHSamplePumpDirectionGPIO,GPIO.LOW)
		else:
			GPIO.output(KHSamplePumpDirectionGPIO,GPIO.HIGH)
			ml*=-1

		stepCountThisPump=0
		stepDelay=.00001
		stepsfor1ml=int(940000 / self.calibrationMLKHSample)
		stepsToPump=ml*stepsfor1ml
		print (stepsToPump)	

		while stepCountThisPump<stepsToPump:
			GPIO.output(KHSamplePumpStepGPIO,GPIO.HIGH)
			time.sleep(stepDelay)
			GPIO.output(KHSamplePumpStepGPIO,GPIO.LOW)
			time.sleep(stepDelay)
			stepCountThisPump+=1

			if RampUpTimeDelay > 0.0001:
				RampUpTimeDelay-=0.0001
				time.sleep(RampUpTimeDelay)

		GPIO.output(KHSamplePumpEnableGPIO,GPIO.HIGH)
		self.KHSamplePumpEnabled=False
		return True  

	def reagentPumpCommand(self,ml):
		RampUpTimeDelay = 0.01
		if not self.KHReagentPumpEnabled:
			GPIO.output(KHReagentPumpEnableGPIO,GPIO.LOW)
			time.sleep(.0005)
			self.KHReagentPumpEnabled=True
		if ml>0:
			GPIO.output(KHReagentPumpDirectionGPIO,GPIO.LOW)

		stepCountThisPump=0
		stepDelay=.00002
		stepsfor1ml=int(260000 / self.calibraitonMLKHReagent)
		stepsToPump=ml*stepsfor1ml
		print (stepsToPump)

		while stepCountThisPump<stepsToPump:
			GPIO.output(KHReagentPumpStepGPIO,GPIO.HIGH)
			time.sleep(stepDelay)
			GPIO.output(KHReagentPumpStepGPIO,GPIO.LOW)
			time.sleep(stepDelay)
			stepCountThisPump+=1

			if RampUpTimeDelay > 0.0001:
				RampUpTimeDelay-=0.0001
				time.sleep(RampUpTimeDelay)

		GPIO.output(KHReagentPumpEnableGPIO,GPIO.HIGH)
		self.KHReagentPumpEnabled=False
		return True  
			                    
	def getID(self):
		return self.testerName
	
	def printDetectionParameters(self):
		print('Detection parameter settings:')
	
	def quit(self):
		if self.simulation:
			return
		GPIO.cleanup()
		
	def addJobToQueue(self,jobToQueue):
		from tester.models import JobExternal,TestDefinition
		newJob=JobExternal()
		newJob.jobToRun=TestDefinition.objects.get(testName=jobToQueue)
		newJob.save()
	
	def anyMoreJobs(self):
		from tester.models import JobExternal
		jobsQueued=JobExternal.objects.filter(jobStatus='Queued')
		for job in jobsQueued:
			if job.timeStamp<=timezone.now():
				return True
		return False
	
	def getNextJob(self):
		from tester.models import JobExternal,TestResultsExternal
		jobsQueued=JobExternal.objects.filter(jobStatus='Queued')
		for job in jobsQueued:
			if job.timeStamp<=timezone.now():
				if not job.jobToRun.enableTest:
					self.infoMessage('Job ' + job.jobToRun.testName + ' skipped since test disabled')
					skippedTest=TestResultsExternal()
					skippedTest.testPerformed=job.jobToRun.testName
					skippedTest.status='Skipped'
					skippedTest.datetimePerformed=timezone.now()
					skippedTest.save()
					job.delete()
				else:
					job.jobStatus='Running'
					job.save()                
					return job.jobToRun.testName
		return None

	def clearRunningJobs(self):
		from tester.models import JobExternal
		JobExternal.objects.filter(jobStatus='Running').delete()
		
	def getJobDaysText(self,testName):
		from tester.models import TestSchedule
		try:
			test=TestSchedule.objects.get(testToSchedule=testName)
			return test.daysToRun
		except:
			return 'Never'
		
	def getHoursToRunList(self,testName):
		from tester.models import TestSchedule
		hourList=[]
		try:
			test=TestSchedule.objects.get(testToSchedule=testName)
			for timeOfDay in test.hoursToRun.all():
				timeSegs=str(timeOfDay).split(':')
				hourList.append(str(timeSegs[0] + ':' + timeSegs[1]))
		except:
			pass
		return hourList

	def connectArduinoStepper(self):
		self.arduinostepper=serial.Serial('/dev/ttyUSB0', 9600, timeout=.1)
		time.sleep(2)
		self.ArduinoStepper=True
		return

	def connectArduinoSensor(self):
		self.arduinosensor=serial.Serial('/dev/ttyACM0', 9600, timeout=.1)
		time.sleep(2)
		self.ArduinoSensor=True
		self.arduinosensor.write(str.encode("[2, 10]" + '\n'))
		time.sleep(0.2)
		self.arduinosensor.readline() 
		time.sleep(0.2)
		self.arduinosensor.write(str.encode("[13]" + '\n')) # set CMD_SET_MODE_COLOR_SPECIFIC
		time.sleep(0.2)
		self.arduinosensor.readline() 
		time.sleep(0.2)
		return

	def homingArduinoStepper(self):
		self.arduinostepper.write(str.encode('$H' + '\n'))
		while True:
			if "error: Expected command letter" in str(self.arduinostepper.readline()): 
				self.hommeArduinoStepper=True
				break
		else: 
			print ('homing is calibrating')
			time.sleep(2)
		return

	def XtoTargetReagent(self,TargetXas):
		self.arduinostepper.write(str.encode('X' + str(TargetXas) + '\n'))
		time.sleep(2)
		while True: 
			self.arduinostepper.write(str.encode("?" + '\n'))
			self.arduinostepper.flushInput() 
			time.sleep(0.2)
			grbl_out = str(self.arduinostepper.readline()) 

			grbl_out_strip = grbl_out.strip()
			grbl_out_split = grbl_out_strip.split (',',4)

			status, xas, yas, zas, unkown = grbl_out_split
			statuscorrect = status.replace('<', '')
			xascorrect = xas.replace('MPos:', '')

			#print(statuscorrect)
			#print(xascorrect)
			#print(yas)
			#print(zas)

			if (round(float(xascorrect),2)) == float(TargetXas):
				return True

	def lowerSyringesInReagent(self):
		self.arduinostepper.write(str.encode('Z55' + '\n'))
		time.sleep(2)
		while True: 
			self.arduinostepper.write(str.encode("?" + '\n'))
			self.arduinostepper.flushInput() 
			time.sleep(0.2)
			grbl_out = str(self.arduinostepper.readline()) 

			grbl_out_strip = grbl_out.strip()
			grbl_out_split = grbl_out_strip.split (',',4)

			status, xas, yas, zas, unkown = grbl_out_split
			
			if float(zas) == float(55):
				return True

	def fillSyringes(self,amountToDispense):
		self.arduinostepper.write(str.encode('Y' + str(int(amountToDispense*100)) + '\n'))
		time.sleep(2)
		while True: 
			self.arduinostepper.write(str.encode("?" + '\n'))
			self.arduinostepper.flushInput() 
			time.sleep(0.2)
			grbl_out = str(self.arduinostepper.readline()) 

			grbl_out_strip = grbl_out.strip()
			grbl_out_split = grbl_out_strip.split (',',4)

			status, xas, yas, zas, unkown = grbl_out_split

			if (round(float(yas),1)) == int(amountToDispense*100):
				return True

	def UpperSyringes(self):
		self.arduinostepper.write(str.encode('Z0' + '\n'))
		time.sleep(2)
		while True: 
			self.arduinostepper.write(str.encode("?" + '\n'))
			self.arduinostepper.flushInput() 
			time.sleep(0.2)
			grbl_out = str(self.arduinostepper.readline()) 

			grbl_out_strip = grbl_out.strip()
			grbl_out_split = grbl_out_strip.split (',',4)

			status, xas, yas, zas, unkown = grbl_out_split
			
			if float(zas) == float(0):
				return True      

	def doseSyringesLiquid(self):
		self.arduinostepper.write(str.encode('Y0' + '\n'))
		time.sleep(2)
		while True: 
			self.arduinostepper.write(str.encode("?" + '\n'))
			self.arduinostepper.flushInput() 
			time.sleep(0.2)
			grbl_out = str(self.arduinostepper.readline()) 

			grbl_out_strip = grbl_out.strip()
			grbl_out_split = grbl_out_strip.split (',',4)

			status, xas, yas, zas, unkown = grbl_out_split
			
			if float(yas) == float(0):
				return True

	def lowerSyringesInMixerreactor(self):
		self.arduinostepper.write(str.encode('Z40' + '\n'))
		time.sleep(2)
		while True: 
			self.arduinostepper.write(str.encode("?" + '\n'))
			self.arduinostepper.flushInput() 
			time.sleep(0.2)
			grbl_out = str(self.arduinostepper.readline()) 

			grbl_out_strip = grbl_out.strip()
			grbl_out_split = grbl_out_strip.split (',',4)

			status, xas, yas, zas, unkown = grbl_out_split
			
			if float(zas) == float(40):
				return True

	def lowerSyringesInReagentForReturnLiquid(self):
		self.arduinostepper.write(str.encode('Z15' + '\n'))
		time.sleep(2)
		while True: 
			self.arduinostepper.write(str.encode("?" + '\n'))
			self.arduinostepper.flushInput() 
			time.sleep(0.2)
			grbl_out = str(self.arduinostepper.readline()) 

			grbl_out_strip = grbl_out.strip()
			grbl_out_split = grbl_out_strip.split (',',4)

			status, xas, yas, zas, unkown = grbl_out_split
			
			if float(zas) == float(15):
				return True

	def lowerSyringesInCleanreactor(self):
		self.arduinostepper.write(str.encode('Z45' + '\n'))
		time.sleep(2)
		while True: 
			self.arduinostepper.write(str.encode("?" + '\n'))
			self.arduinostepper.flushInput() 
			time.sleep(0.2)
			grbl_out = str(self.arduinostepper.readline()) 

			grbl_out_strip = grbl_out.strip()
			grbl_out_split = grbl_out_strip.split (',',4)

			status, xas, yas, zas, unkown = grbl_out_split
			
			if float(zas) == float(45):
				return True

	def calibrateArduinoSensor(self):
		self.arduinosensor.write(str.encode("[5]" + '\n')) # Calibrate Red
		time.sleep(0.1)
		self.arduinosensor.readline()
		time.sleep(0.2)
		self.arduinosensor.write(str.encode("[6]" + '\n')) # Calibrate Green
		time.sleep(0.1)
		self.arduinosensor.readline()
		time.sleep(0.2)
		self.arduinosensor.write(str.encode("[7]" + '\n')) # Calibrate Blue
		time.sleep(0.1)
		self.arduinosensor.readline()
		time.sleep(0.2)
		self.arduinosensor.write(str.encode("[8]" + '\n')) # Calibrate White
		time.sleep(0.1)
		self.arduinosensor.readline()
		return

	def measureArduinoSensor(self):
		self.arduinosensor.write(str.encode("[9]" + '\n')) #Measure Red
		time.sleep(0.1)
		Rarduinovalue=self.arduinosensor.readline()
		time.sleep(0.2)
		self.arduinosensor.write(str.encode("[10]" + '\n')) #Measure Green
		time.sleep(0.1)
		Garduinovalue=self.arduinosensor.readline()
		time.sleep(0.2)
		self.arduinosensor.write(str.encode("[11]" + '\n')) #Measure Blue
		time.sleep(0.1)
		Barduinovalue=self.arduinosensor.readline()

		Rvalue = float(Rarduinovalue[-16:-3])
		Gvalue = float(Garduinovalue[-16:-3])
		Bvalue = float(Barduinovalue[-16:-3])

		if (Rvalue > 1):
			Rvalue=1

		if (Gvalue > 1):
			Gvalue=1

		if (Bvalue > 1):
			Bvalue=1

		R255=255-(Rvalue*255)
		G255=255-(Gvalue*255)
		B255=255-(Bvalue*255)

		bgr255=(B255,G255,R255)
		
		print (bgr255)

		Rvalue1 = (1-Rvalue)
		Gvalue1 = (1-Gvalue)
		Bvalue1 = (1-Bvalue)

		rgb=sRGBColor(Rvalue1,Gvalue1,Bvalue1)
		lab = convert_color(rgb, LabColor)

		from tester.models import MeasuredParameters
		MeasureInfoFromDB=MeasuredParameters.objects.get(pk=1)
		MeasureInfoFromDB.R=R255
		MeasureInfoFromDB.G=G255
		MeasureInfoFromDB.B=B255
		MeasureInfoFromDB.abR=Rvalue
		MeasureInfoFromDB.abG=Gvalue
		MeasureInfoFromDB.abB=Bvalue
		MeasureInfoFromDB.labL=lab.lab_l
		MeasureInfoFromDB.labA=lab.lab_a
		MeasureInfoFromDB.labB=lab.lab_b
		MeasureInfoFromDB.save()

		return lab.lab_l,lab.lab_a,lab.lab_b,bgr255,Rvalue,Gvalue,Bvalue

	def calculateLastTest(self):
		from tester.models import TestResultsExternal
		lastTestResult=TestResultsExternal.objects.last()

		lastTestResultWithExtraTime=lastTestResult.datetimePerformed + datetime.timedelta(hours=self.mixerCleanCyclesExtraAfterHours)
		if lastTestResultWithExtraTime <= dt.now():
			return True

	def readLastKHTestResult(self,sequenceName):
		from tester.models import TestResultsExternal
		KHTests=TestResultsExternal.objects.filter(testPerformed=sequenceName)
		LastKHTest=KHTests.last()
		LastKHValue=LastKHTest.results
		LastKHTime=LastKHTest.datetimePerformed
		return LastKHValue,LastKHTime

	def drainPumpCommand(self,sec):
		self.pca60.motor1.throttle = 1
		time.sleep(sec)
		self.pca60.motor1.throttle = 0

	def mixerJarMotorCommand(self,sec):
		self.pca60.motor4.throttle = 0.5
		time.sleep(sec)
		self.pca60.motor4.throttle = 0

	def mixerJarMotorCommandManual(self,speed):
		self.pca60.motor4.throttle = speed

	def mixerReagentBottleMotorCommand(self,sec):
		self.pca60.motor2.throttle = 0.5
		time.sleep(sec)
		self.pca60.motor2.throttle = 0

	def read_ph(self):
		temperature=25
		ads1115.setAddr_ADS1115(0x4A)
		ads1115.setGain(0x00)
		ph.begin()
		PHTOTAL = 0
		stepx=0
		while stepx < PHsamplesBetweenTest:
			time.sleep(1)
			adc0 = ads1115.readVoltage(0)
			PHTOTAL+=ph.readPH(adc0['r'],temperature)
			stepx+=1
		phresult=round(PHTOTAL/PHsamplesBetweenTest,2)
		return phresult

	def calibratePH(self):
		ph.begin()
		ads1115.setAddr_ADS1115(0x4A)
		ads1115.setGain(0x00)
		adc0 = ads1115.readVoltage(0)
		print ("A0:%dmV "%(adc0['r']))
		ph.calibration(adc0['r'])

def getBasePath():
	programPath=os.path.realpath(__file__)
	programPathForwardSlash=programPath.replace('\\','/')
	programPathList=programPathForwardSlash.split('/')
	numPathSegments=len(programPathList)
	basePath=''
	pathSegment=0
	while pathSegment<numPathSegments-1:
		basePath+=programPathList[pathSegment] + '/'
		pathSegment+=1
#    print(basePath)
	return basePath
			
		
if __name__ == '__main__':
	basePath=getBasePath()
	sys.path.append(os.path.abspath(basePath))
	os.environ['DJANGO_SETTINGS_MODULE'] = 'AutoTesterv2.settings'
	django.setup()
	a=Tester(1)