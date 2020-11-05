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
	
mainPumpEnableGPIO=27
mainPumpStepGPIO=17
mainPumpDirectionGPIO=23

relay1GPIO=9
relay2GPIO=11
relay3GPIO=5
relay4GPIO=6

ledGPIO=13
agitateGPIO=19
shakerGPIO=26
temppumpGPIO=21

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
			GPIO.setup(relay1GPIO,GPIO.OUT)
			GPIO.setup(relay2GPIO,GPIO.OUT)
			GPIO.setup(relay3GPIO,GPIO.OUT)
			GPIO.setup(relay4GPIO,GPIO.OUT)
			GPIO.setup(ledGPIO,GPIO.OUT)
			GPIO.setup(agitateGPIO,GPIO.OUT)
			GPIO.setup(shakerGPIO,GPIO.OUT)
			GPIO.setup(temppumpGPIO,GPIO.OUT)
			GPIO.output(mainPumpEnableGPIO,GPIO.HIGH)
			GPIO.output(mainPumpStepGPIO,GPIO.LOW)
			GPIO.output(mainPumpDirectionGPIO,GPIO.LOW)
			GPIO.output(relay1GPIO,GPIO.HIGH)
			GPIO.output(relay2GPIO,GPIO.HIGH)
			GPIO.output(relay3GPIO,GPIO.HIGH)
			GPIO.output(relay4GPIO,GPIO.HIGH)
			GPIO.output(ledGPIO,GPIO.LOW)
			GPIO.output(agitateGPIO,GPIO.LOW)
			GPIO.output(shakerGPIO,GPIO.LOW)
			GPIO.output(temppumpGPIO,GPIO.LOW)
		self.ledOn=False
		self.ArduinoStepper=False
		self.ArduinoSensor=False
		self.hommeArduinoStepper=False
		self.mainPumpOn=False
		self.mainDrainPumpOn=False
		self.cleanPumpOn=False
		self.cleanDrainPumpOn=False
		self.valveForOsmoseOn=False
		self.agitatorOn=False
		self.shakerOn=False
		self.tempPumpOn=False
		self.loadTesterFromDB()
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
		self.mainPumpStepsPerMM=200*2*34/12 #Stepper Motor Steps, 1/4 steps, 34 tooth outer gear, 12 tooth inner gear
		self.mmToRaiseFromOpenToFullyClosed=5
		self.mainPumpSteps=None
		self.mainPumpStepping=False
		self.mainPumpMoving=False
		self.previousLeftStopperPosition=None
		self.stopperMovement=None
		self.moveCarouselLock=None
		self.carouselSeriesLock=None
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
		self.flashLights()
		
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
		from tester.models import TesterExternal,TesterProcessingParameters
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
		self.stepsFor1ML=te.stepsFor1ML
		self.reagentRemainingMLAlarmThreshold=te.reagentRemainingMLAlarmThreshold
		self.reagentAlmostEmptyAlarmEnable=te.reagentAlmostEmptyAlarmEnable
		self.pauseInSecsBeforeEmptyingMixingChamber=te.pauseInSecsBeforeEmptyingMixingChamber
		self.telegramBotToken=te.telegramBotToken
		self.telegramChatID=te.telegramChatID
		self.sendMeasurementReports=te.sendMeasurementReports
		self.daysOfResultsToKeep=te.daysOfResultsToKeep
		self.enableConsoleOutput=te.enableConsoleOutput
		self.manageDatabases=te.manageDatabases
		
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
			ts.colorChartToUse=seq.colorChartToUse.colorSheetName
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
		reagentObj.fluidRemainingInML=remainingML
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
		
	def turnLedOn(self):
		if self.simulation:
			self.ledOn=True
			return
		if existsGPIO:
			GPIO.output(ledGPIO,GPIO.HIGH)
		self.ledOn=True
		return
			
	def turnLedOff(self):
		if self.simulation:
			self.ledOn=False
			return
		if existsGPIO:
			GPIO.output(ledGPIO,GPIO.LOW)
		self.ledOn=False
		return
	
	def flashLights(self):
		self.turnLedOn()
		time.sleep(.5)
		self.turnLedOff()
		time.sleep(.5)
		self.turnLedOn()
		time.sleep(.5)
		self.turnLedOff()
		time.sleep(.5)
		self.turnLedOn()
		time.sleep(.5)
		self.turnLedOff()
		
	def turnMainPumpOn(self):
		if self.simulation:
			self.tempPumpOn=True
			return
		if existsGPIO:
			GPIO.output(temppumpGPIO,GPIO.HIGH)
		self.tempPumpOn=True
		return
			
	def turnMainPumpOff(self):
		if self.simulation:
			self.tempPumpOn=False
			return
		if existsGPIO:
			GPIO.output(temppumpGPIO,GPIO.LOW)
		self.tempPumpOn=False
		return

	def turnMainDrainPumpOn(self):
		if self.simulation:
			self.mainDrainPumpOn=True
			return
		if existsGPIO:
			GPIO.output(relay1GPIO,GPIO.LOW)
		self.MainDrainPumpOn=True
		return
			
	def turnMainDrainPumpOff(self):
		if self.simulation:
			self.mainDrainPumpOn=False
			return
		if existsGPIO:
			GPIO.output(relay1GPIO,GPIO.HIGH)
		self.MainDrainPumpOn=False
		return        

	def turnCleanPumpOn(self):
		if self.simulation:
			self.cleanPumpOn=True
			return
		if existsGPIO:
			GPIO.output(relay2GPIO,GPIO.LOW)
		self.cleanPumpOn=True
		return
			
	def turnCleanPumpOff(self):
		if self.simulation:
			self.cleanPumpOn=False
			return
		if existsGPIO:
			GPIO.output(relay2GPIO,GPIO.HIGH)
		self.cleanPumpOn=False
		return 

	def turnCleanDrainPumpOn(self):
		if self.simulation:
			self.cleanDrainPumpOn=True
			return
		if existsGPIO:
			GPIO.output(relay3GPIO,GPIO.LOW)
		self.cleanDrainPumpOn=True
		return
			
	def turnCleanDrainPumpOff(self):
		if self.simulation:
			self.cleanDrainPumpOn=False
			return
		if existsGPIO:
			GPIO.output(relay3GPIO,GPIO.HIGH)
		self.cleanDrainPumpOn=False
		return

	def turnValveForOsmoseOn(self):
		if self.simulation:
			self.valveForOsmoseOn=True
			return
		if existsGPIO:
			GPIO.output(relay4GPIO,GPIO.LOW)
		self.valveForOsmoseOn=True
		return

	def turnValveForOsmoseOff(self):
		if self.simulation:
			self.valveForOsmoseOn=False
			return
		if existsGPIO:
			GPIO.output(relay4GPIO,GPIO.HIGH)
		self.valveForOsmoseOn=False
		return

	def turnAgitatorOn(self):
		if self.simulation:
			self.agitatorOn=True
			return
		if existsGPIO:
			GPIO.output(agitateGPIO,GPIO.HIGH)
		self.agitatorOn=True
		return

	def turnAgitatorOff(self):
		if self.simulation:
			self.agitatorOn=False
			return
		if existsGPIO:
			GPIO.output(agitateGPIO,GPIO.LOW)
		self.agitatorOn=False
		return

	def turnShakerOn(self):
		if self.simulation:
			self.shakerOn=True
			return
		if existsGPIO:
			GPIO.output(shakerGPIO,GPIO.HIGH)
		self.shakerOn=True
		return

	def turnShakerOff(self):
		if self.simulation:
			self.shakerOn=False
			return
		if existsGPIO:
			GPIO.output(shakerGPIO,GPIO.LOW)
		self.shakerOn=False
		return
	
	def fillMixingReactor(self,ml):
		if self.simulation:
			self.mainPumpEnabled=True
			return

		time.sleep(.5)

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
		stepDelay=.0002
        
		stepsToPump=self.stepsFor1ML*ml
		self.mainPumpStepping=True
		print (stepsToPump)

		while stepCountThisPump<stepsToPump:

			GPIO.output(mainPumpStepGPIO,GPIO.HIGH)

			time.sleep(stepDelay)
			GPIO.output(mainPumpStepGPIO,GPIO.LOW)
			time.sleep(stepDelay)
			stepCountThisPump+=1

		self.mainPumpEnabled=False     

		GPIO.output(mainPumpEnableGPIO,GPIO.HIGH)
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
		
		Rvalue1 = (1-Rvalue)
		Gvalue1 = (1-Gvalue)
		Bvalue1 = (1-Bvalue)

		rgb=sRGBColor(Rvalue1,Gvalue1,Bvalue1)
		lab = convert_color(rgb, LabColor)
		return lab.lab_l,lab.lab_a,lab.lab_b

	def calculateLastTest(self):
		from tester.models import TestResultsExternal
		lastTestResult=TestResultsExternal.objects.last()

		lastTestResultWithExtraTime=lastTestResult.datetimePerformed + datetime.timedelta(hours=self.mixerCleanCyclesExtraAfterHours)
		if lastTestResultWithExtraTime <= dt.now():
			return True


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