'''
AutoTester is the controlling software to automatically run water tests
Further info can be found at: https://robogardens.com/?p=928
This software is free for DIY, Nonprofit, and educational uses.
Copyright (C) 2017 - RoboGardens.com
	
Created on Aug 9, 2017

This module is the main server module which runs the tests and hosts the streaming video of the tester.

@author: Stephen Hayes
'''
import rpyc   # @UnresolvedImport
from TesterCore import Tester,getBasePath
import time
import atexit
import datetime
import threading
import cv2   # @UnresolvedImport
from http.server import BaseHTTPRequestHandler,HTTPServer
from socketserver import ThreadingMixIn
import numpy as np
import math
import traceback
from rpyc.utils.server import ThreadedServer   # @UnresolvedImport
import _pickle
import logging
import schedule    # @UnresolvedImport
import requests   # @UnresolvedImport
import os
import shutil
from ImageCheck import evaluateColor,evaluateColorBinary
from Alarms import sendMeasurementReport,sendReagentAlarm,sendFillAlarm,sendDispenseAlarm,sendEvaluateAlarm,sendUnableFillSyringes,sendUnableToRotateAlarm,sendCannotParkAlarm,sendOutOfLimitsAlarm,sendOutOfLimitsWarning
import sys
from skimage.color.rgb_colors import greenyellow
import random
from random import randint
import django
import platform

currentVersion='0.02'
remoteControlThreadRPYC=None
tester=None
letterSequenceCheck={'A':'B','B':'C','C':'D','D':'E','E':'F','F':'G','G':'H','H':'I','I':'J','J':'K','K':'L','L':'A'}
Mixerreactor='Mixerreactor'
Cleanreactor='Cleanreactor'
osmosewater='osmosewater'
tankwater='tankwater'
CentimeterToMove={'A':0,'B':3.7,'C':7.3,'D':11,'E':14.9,'F':18.6,'G':22.1,'H':25.7,'I':29.7,'J':33.3,'K':36.9,'L':40.5,'M':44.5,'Cleanreactor':47.9,'Mixerreactor':51.1}
destinationLetters='ABCDEFGHIJKLM'
airInSyringe=0.00 #was 0.07
syringeTolorance=0.03
rgb=255,255,255
PH='-'

def screenPresent(name):
	from subprocess import check_output
	var = str(check_output(["screen -ls; true"],shell=True))
	index=var.find(name)
	return index>-1

def runWebserverOld(tester,name):
	from subprocess import call
	call(["screen","-d","-m","-S",name,"python3", "/home/pi/AutoTesterv2/manage.py","runserver","0.0.0.0:" + str(tester.webPort),"--insecure"])            

def generateWebLaunchFile(tester):
	launchFile=tester.basePath + "/launchWebServer.sh"
	launchText="#!/bin/bash\nexport WORKON_HOME=$HOME/.virtualenvs\nexport VIRTUALENVWRAPPER_PYTHON=/usr/bin/python3\nsource /usr/local/bin/virtualenvwrapper.sh\nworkon "
	launchText = launchText + tester.virtualEnvironmentName + "\n"
	launchText=launchText + 'python ' + tester.basePath + 'manage.py runserver 0.0.0.0:' + str(tester.webPort) + ' --insecure >> /home/pi/Autolinetester/web.log 2>&1\n'
	f=open(launchFile,"w+")
	f.write(launchText)
	f.close()
	
def runWebServer(tester,name):
	from subprocess import call
	generateWebLaunchFile(tester)
	call(["screen","-d","-m","-S",name,"bash", "launchWebServer.sh"])   

def sleepUntilNextInterval(lastTime,intervalInSeconds):
	timeInterval=datetime.timedelta(seconds=intervalInSeconds)
	nextTime=lastTime+timeInterval
	while nextTime<datetime.datetime.now():
		nextTime+=timeInterval
	timeToSleep=(nextTime-datetime.datetime.now()).total_seconds()
	time.sleep(timeToSleep)
	return nextTime

def loadFeatureWindow(tester,featureName):
	if not tester.referenceMarkFound:
		return None
	try:
		feat=tester.featureList[featureName]
		feat.setTesterClipFromFeature(tester)
		return feat
	except:
		tester.debugLog.exception("Continuing...")
		return None
		
class TesterRemoteControl(rpyc.Service):
	def on_connect(self):
		# code that runs when a connection is created
		# (to init the serivce, if needed)
		self.tester=tester

	def on_disconnect(self):
		# code that runs when the connection has already closed
		# (to finalize the service, if needed)
		pass
	
	def exposed_testerOperation(self,operation):
		try:
			processWebCommand(tester,operation)
		except:
			tester.debugLog.exception("Continuing...")
	
def startHandler(threadName,operation): 
	tester.debugMessage('Thread: ' + threadName + ' started')
	operation.start() 
	
def videoGrabber():
	frameIntervalDelta=datetime.timedelta(milliseconds=1000/tester.framesPerSecond)
	frameIntervalSecs=frameIntervalDelta.microseconds/1000000
#    i=1
	tester.webcamInitialize()
	time.sleep(.1)
	nextTime=datetime.datetime.now()
	while True:
		try:
			if tester.suppressProcessing:
				try:
					imageLo=tester.grabFrame()
				except:
					tester.debugLog.exception("Continuing...")  
					imageLo=None                              
				if imageLo is None:
					time.sleep(.01)
				else:
					tester.videoLowResCaptureLock.acquire()
					tester.latestLowResImage=imageLo
					tester.videoLowResCaptureLock.notifyAll()
					tester.videoLowResCaptureLock.release()                
			else:
				currTime=datetime.datetime.now()
				if currTime>=nextTime:
					try:
						if tester.simulation:
							imageLo=tester.fakeFrame()
						else:
							imageLo=tester.grabFrame()
					except:
						tester.debugLog.exception("Continuing...")  
						imageLo=None                              
					if imageLo is None:
						time.sleep(.01)
					else:
						tester.videoLowResCaptureLock.acquire()
						tester.latestLowResImage=imageLo
						tester.videoLowResCaptureLock.notifyAll()
						tester.videoLowResCaptureLock.release()
	#                    tester.debugMessage('Grabbed low res frame')
	#                i+=1
					nextTime=nextTime+frameIntervalDelta
				else:
					timeRemainingUntilNextFrame=(nextTime-currTime).microseconds/1000000
					time.sleep(timeRemainingUntilNextFrame)
		except:
			tester.debugLog.exception("Continuing...")
			time.sleep(.1)

class TesterViewer(BaseHTTPRequestHandler):
	
	def do_GET(self):
		font = cv2.FONT_HERSHEY_SIMPLEX        
		if self.path.endswith('.mjpg'):
			self.send_response(200)
			self.send_header('Content-type','multipart/x-mixed-replace; boundary=--jpgboundary')
			self.end_headers()
			while tester.streamVideo:
				try:
					if tester.suppressProcessing:
						while tester.suppressProcessing:
							time.sleep(1)
							return
					tester.videoLowResCaptureLock.acquire()
					tester.videoLowResCaptureLock.wait()
					if tester.suppressProcessing:
						tester.videoLowResCaptureLock.release()
						jpg=tester.dummyBlackScreen
					else:
						imageCopy=tester.latestLowResImage.copy()
						tester.videoLowResCaptureLock.release()
						cv2.putText(imageCopy,'System Status: ' + tester.systemStatus,(10,25), font, .75,(255,255,255),2,cv2.LINE_AA)
						cv2.putText(imageCopy,'Last PH: ' + str(PH),(10,630), font, .75,(255,255,255),2,cv2.LINE_AA)
						x,y,w,h = 350,630,175,75
						cv2.rectangle(imageCopy, (x, 560), (x + w, y + h), (rgb), -1)
						if not tester.testStatus is None:
							try:
								cv2.putText(imageCopy,"Running Test: " + tester.currentTest,(20,55), font, .75,(255,255,255),2,cv2.LINE_AA)
								cv2.putText(imageCopy,tester.testStatus,(10,85), font, .75,(255,255,255),2,cv2.LINE_AA)                                
							except:
								tester.debugLog.exception("Error displaying test Status")

						if tester.showTraining and not tester.currentFeature is None:
							insertTrainingGraphic(tester,imageCopy)
						if tester.seriesRunning:
									cv2.putText(imageCopy,'Series Running',(200,115), font, .75,(255,255,255),2,cv2.LINE_AA)                                
						if tester.referenceMarkFound and tester.displayDot:
							cv2.line(imageCopy,(int(tester.avgCircleLeftMarkerCol),int(tester.avgCircleLeftMarkerRow)),(int(tester.avgCircleRightMarkerCol),int(tester.avgCircleRightMarkerRow)),(255,0,0),4)
						if tester.colorTable:
							try:
								colorTable=tester.colorTable.generateColorTableDisplay(tester,width=tester.colorTable.tableWidth,height=tester.colorTable.tableRowHeight)
								if not colorTable is None:
									showTableRows,showTableCols,showTableColors=colorTable.shape
									imageCopy[tester.colorTable.tableStartPosition:tester.colorTable.tableStartPosition+showTableRows,:showTableCols,:] =  colorTable
							except:
								traceback.print_exc()
	#                    r,jpg = cv2.imencode('.jpg',tester.maskGrey)
						r,jpg = cv2.imencode('.jpg',imageCopy)
					self.wfile.write(bytearray("--jpgboundary\r\n",'utf-8'))
					self.send_header('Content-type','image/jpeg')
					self.send_header('Content-length',str(len(jpg)))
					self.end_headers()
					self.wfile.write(bytearray(jpg))
					self.wfile.write(bytearray('\r\n','utf-8'))
				except:
#                    tester.debugLog.exception("Continuing...")
					break                    
			tester.debugMessage('Connection aborted')
			while not tester.streamVideo:
				time.sleep(1)
			return
		if self.path.endswith('.html'):
			self.send_response(200)
			self.send_header('Content-type','text/html')
			self.end_headers()
			self.wfile.write('<html><head></head><body>')
			self.wfile.write('<img src="tester.mjpg"/>')
			self.wfile.write('</body></html>')
			return

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
	"""Handle requests in a separate thread."""

def videoStreamer():
	while tester.streamVideo:
		tester.debugMessage('Restarting Streaming Server')
		try:
			server = ThreadedHTTPServer(('', tester.videoStreamingPort), TesterViewer)
			tester.debugMessage("MJPG Server Started")
			server.serve_forever()
		except:
			tester.debugLog.exception("Closing Socket")
			server.socket.close()
			

def resetDripHistory(tester):
	tester.previousDripHeight=None
	tester.suppressProcessing=False
	tester.plungerSlow=False
	tester.plungerAbort=False
	tester.dripSamplesSoFar=0
	tester.samplesSinceLastDrop=0
	tester.dripSampleCount=0
	tester.dripTopList=[]
	tester.previousDripTopImage=None
	
def saveTopDripList(tester):
	fn="/home/pi/Images/DripTop/DT-" + datetime.datetime.now().strftime("%Y-%m-%d %H-%M-%S") + '-'
#    print('Saving Top Drip images')
	index=0
	for image in tester.dripTopList:
		saveFN=fn+str(index).zfill(4) + '.jpg'
		cv2.imwrite(saveFN,image)
		index+=1
	tester.dripTopList=[]

def testFillingMixer(tester):
	randomLevel=random.randint(4,7)
	tester.debugLog.info('Test filling mixer to level: ' + str(randomLevel))
	result=tester.MixerReactorPump(randomLevel)
	return result

def testMixerFill(tester,numCycles):
	testNum=0
	successCount=0
	failureCount=0
	while testNum<numCycles:
		result=testFillingMixer(tester)
		if result:
			tester.debugLog.info('Cycle completion: Success')
			successCount+=1
		else:
			tester.debugLog.info('Cycle completion: Failed')
			failureCount+=1
		testNum+=1
	tester.mainDrainPump(6)
	tester.debugLog.info('All test cycles completed. Success: ' + str(successCount) + ', Failures: ' + str(failureCount))            
	
def orientTester():
	tester.connectArduinoStepper()
	tester.connectArduinoSensor()
	tester.homingArduinoStepper()
	tester.infoMessage('Homing Arduino Stepper done')
	tester.systemStatus="Idle"
	tester.infoMessage('Orientation done!')

def cleanSyringe():
	tester.infoMessage('Move to CleaningReactor') 
	tester.testStatus='Move to CleaningReactor'
	TargetXas=CentimeterToMove[Cleanreactor]
	success=tester.XtoTargetReagent(TargetXas)
	if not success:
		tester.debugMessage('Unable to move to Cleanreactor')
		sendUnableToRotateAlarm(tester,reagentSlot,testName)
		return False

	success=tester.fillSyringes(airInSyringe)
	tester.infoMessage('Lower the Syringe in the CleaningReactor') 
	tester.testStatus='Lower the Syringe in the CleaningReactor'
	success=tester.lowerSyringesInCleanreactor()
	if not success:
		tester.debugMessage('Unable to lower the Syringe in the CleaningReactor')
		sendUnableToRotateAlarm(tester,ts.titrationSlot,testName)
		return False

	tester.osmoseCleanPump(6)

	tester.turnAgitator(2)

	tester.infoMessage('Get Osmose Water to flush the Syringe') 
	tester.testStatus='Get Osmose Water to flush the Syringe'
	success=tester.fillSyringes(0.8+airInSyringe)
	if not success:
		tester.debugMessage('Unable to get Osmose water')
		sendUnableFillSyringes(tester,ts.titrationSlot,testName)
		return False

	tester.infoMessage('Dose water') 
	tester.testStatus='Dose water'
	success=tester.doseSyringesLiquid()
	if not success:
		tester.debugMessage('Unable to dose the water')
		sendUnableFillSyringes(tester,ts.titrationSlot,testName)
		return False

	tester.infoMessage('Upper the Syringe out of the CleaningReactor') 
	tester.testStatus='Upper the Syringe out of the CleaningReactor'
	success=tester.UpperSyringes()
	if not success:
		tester.debugMessage('Unable to upper the Syringe out of the CleaningReactor')
		sendUnableToRotateAlarm(tester,ts.titrationSlot,testName)
		return False

	success=tester.fillSyringes(airInSyringe)
	tester.infoMessage('Lower the Syringe in the CleaningReactor') 
	tester.testStatus='Lower the Syringe in the CleaningReactor'
	success=tester.lowerSyringesInCleanreactor()
	if not success:
		tester.debugMessage('Unable to lower the Syringe in the CleaningReactor')
		sendUnableToRotateAlarm(tester,ts.titrationSlot,testName)
		return False

	tester.infoMessage('Get Osmose Water to flush the Syringe') 
	tester.testStatus='Get Osmose Water to flush the Syringe'
	success=tester.fillSyringes(0.8+airInSyringe)
	if not success:
		tester.debugMessage('Unable to get Osmose water')
		sendUnableFillSyringes(tester,ts.titrationSlot,testName)
		return False

	tester.infoMessage('Dose water') 
	tester.testStatus='Dose water'
	success=tester.doseSyringesLiquid()
	if not success:
		tester.debugMessage('Unable to dose the water')
		sendUnableFillSyringes(tester,ts.titrationSlot,testName)
		return False

	tester.turnAgitator(0)
	tester.cleanDrainPump(0)	

	tester.infoMessage('Upper the Syringe out of the CleaningReactor') 
	tester.testStatus='Upper the Syringe out of the CleaningReactor'
	success=tester.UpperSyringes()
	if not success:
		tester.debugMessage('Unable to upper the Syringe out of the CleaningReactor')
		sendUnableToRotateAlarm(tester,ts.titrationSlot,testName)
		return False

	time.sleep(2)
	tester.cleanDrainPumpOff()
	tester.turnAgitatorOff()

	tester.infoMessage('Get stuck liqued out of Syringe') 
	tester.testStatus='Get stuck liqued out of Syringe'
	success=tester.fillSyringes(0.8+airInSyringe)
	if not success:
		tester.debugMessage('Unable to get Osmose water')
		sendUnableFillSyringes(tester,ts.titrationSlot,testName)
		return False

	tester.infoMessage('Dose air') 
	tester.testStatus='Dose air'
	success=tester.doseSyringesLiquid()
	if not success:
		tester.debugMessage('Unable to dose the water')
		sendUnableFillSyringes(tester,ts.titrationSlot,testName)
		return False
	  
def cleanMixerReactor(tester):
	try:
		success=tester.UpperSyringes()
		TargetXas=CentimeterToMove[Mixerreactor]
		success=tester.XtoTargetReagent(TargetXas)
		tester.mainDrainPump(8)
		tester.turnAgitator(0)
		cleanCycle=0

		doubleCleanCycle=tester.calculateLastTest()
		if doubleCleanCycle==True:
			cleanCycle-=tester.mixerCleanCycles
			tester.infoMessage('Extra Cleaning the Mixer') 
			tester.testStatus='Extra Cleaning the Mixer'

		while cleanCycle<tester.mixerCleanCycles:
			time.sleep(.5)
			tester.MixerReactorPump(tester.mixerCleanML,tankwater)
			tester.mainDrainPump(12)
			cleanCycle+=1
		tester.turnAgitatorOff()
	except:
		tester.debugLog.exception("Failure cleaning Mixer")

def osmoseCleanMixerReactor(tester):
	try:
		success=tester.UpperSyringes()
		TargetXas=CentimeterToMove[Mixerreactor]
		success=tester.XtoTargetReagent(TargetXas)
		tester.mainDrainPump(8)
		tester.turnAgitator(0)
		cleanCycle=0
		while cleanCycle<tester.mixerCleanCycles:
			time.sleep(.5)
			tester.MixerReactorPump(tester.mixerCleanML,osmosewater)
			tester.mainDrainPump(12)
			cleanCycle+=1
		tester.turnAgitatorOff()
	except:
		tester.debugLog.exception("Failure cleaning with Osmose Mixer")

def evaluateResults(tester,colorChartToUse):
	tester.videoLowResCaptureLock.acquire()
	tester.videoLowResCaptureLock.wait()
	imageCopy=tester.latestLowResImage.copy()
	tester.videoLowResCaptureLock.release()
	rs=evaluateColor(tester,imageCopy,colorChartToUse)
	if rs.valueAtSwatch<0:
		rs.valueAtSwatch=0
	tester.infoMessage('Result was: ' + str(rs.valueAtSwatch)) 
	return rs

def evaluateResultsBinary(tester,colorChartToUse):
	tester.videoLowResCaptureLock.acquire()
	tester.videoLowResCaptureLock.wait()
	imageCopy=tester.latestLowResImage.copy()
	tester.videoLowResCaptureLock.release()
	global rgb
	l,a,b,rgb=tester.measureArduinoSensor()
	rs=evaluateColorBinary(tester,imageCopy,colorChartToUse,l,a,b)
	if rs.valueAtSwatch<0:
		rs.valueAtSwatch=0
	tester.infoMessage('Result was: ' + str(rs.valueAtSwatch)) 
	return rs

def checkTestRange(tester,ts,results):
	alarmSent=False
	if not ts.tooLowAlarmThreshold is None:
		if results<=ts.tooLowAlarmThreshold:
			sendOutOfLimitsAlarm(tester,ts.testName,results)
			alarmSent=True
	if not ts.tooLowWarningThreshold is None and not alarmSent:
		if results<=ts.tooLowWarningThreshold:
			sendOutOfLimitsWarning(tester,ts.testName,results)
			alarmSent=True
	if not ts.tooHighAlarmThreshold is None and not alarmSent:
		if results>=ts.tooHighAlarmThreshold:
			sendOutOfLimitsAlarm(tester,ts.testName,results)
			alarmSent=True
	if not ts.tooHighWarningThreshold is None and not alarmSent:
		if results>=ts.tooHighWarningThreshold:
			sendOutOfLimitsWarning(tester,ts.testName,results)
			alarmSent=True        

def runTestStep(tester,testStepNumber,testName,waterVolInML,reagentSlot,agitateReagentSecs,agitateMixerSecs,AgitateSecsBetweenDrips,amountToDispense,thickLiquid,lastStep=False):
	try:
		tester.infoMessage('Check Syringe is up' )
		tester.testStatus='Check Syringe is up'
		success=tester.UpperSyringes()
		if not success:
			tester.debugMessage('Unable to upper the Syringe')
			sendUnableToRotateAlarm(tester,reagentSlot,testName)
			return False

		if waterVolInML>0:
			tester.infoMessage('Move to Mixerreactor') 
			tester.testStatus='Move to Mixerreactor'
			TargetXas=CentimeterToMove[Mixerreactor]
			success=tester.XtoTargetReagent(TargetXas)

			tester.infoMessage('Cleaning the Mixer') 
			tester.testStatus='Cleaning the Mixer'
			cleanMixerReactor(tester)
				
			tester.infoMessage('Filling the Mixing Cylinder') 
			tester.testStatus='Filling the Mixing Cylinder'
			fillResult=tester.MixerReactorPump(waterVolInML,tankwater)
			if not fillResult:
				tester.debugLog.info("Failure filling cylinder")
				sendFillAlarm(tester,testName)
				return False

			tester.calibrateArduinoSensor()

		cleanSyringeBeforeTest=tester.calculateLastTest()
		if cleanSyringeBeforeTest==True:
			cleanSyringe()

		tester.infoMessage('Move to Reagent ' + str(testStepNumber)) 
		tester.testStatus='Move to Reagent ' + str(testStepNumber)
		TargetXas=CentimeterToMove[reagentSlot]
		success=tester.XtoTargetReagent(TargetXas)
		if not success:
			tester.debugMessage('Unable to move to Reagent ' + str(testStepNumber))
			sendUnableToRotateAlarm(tester,reagentSlot,testName)
			return False

		if agitateReagentSecs>0:
			tester.infoMessage('Agitating the Reagent for ' + str(agitateReagentSecs) + ' secs.') 
			tester.testStatus='Agitating the Reagent for ' + str(agitateReagentSecs) + ' secs.'
			tester.turnAgitator(agitateReagentSecs)

		#success=tester.fillSyringes(airInSyringe) Oude voor lucht
		success=tester.fillSyringes(amountToDispense)
		tester.infoMessage('Lower the Syringe in the Reagent ' + str(testStepNumber)) 
		tester.testStatus='Lower the Syringe in the Reagent ' + str(testStepNumber)
		success=tester.lowerSyringesInReagent()
		if not success:
			tester.debugMessage('Unable to lower the Syringe in the reagent ' + str(testStepNumber))
			sendUnableToRotateAlarm(tester,reagentSlot,testName)
			return False

		tester.infoMessage('Get Reagent Liquid ' + str(testStepNumber)) 
		tester.testStatus='Get Reagent Liquid ' + str(testStepNumber)	


		success=tester.fillSyringes(airInSyringe) #Tijdelijk voor test om lucht in reagent glaasje te krijgen om vacuum te voorkomen.

		success=tester.fillSyringes(amountToDispense+airInSyringe+syringeTolorance)
		if not success:
			tester.debugMessage('Unable to get Reagent Liquid ' + str(testStepNumber))
			sendUnableFillSyringes(tester,reagentSlot,testName)
			return False

		if thickLiquid==True:
			tester.infoMessage('Wait for Thick Reagent ' + str(testStepNumber)) 
			tester.testStatus='Wait for Thick Reagent ' + str(testStepNumber)
			time.sleep(60)

		success=tester.fillSyringes(amountToDispense+airInSyringe)

		if thickLiquid==True:
			tester.infoMessage('Wait for Thick Reagent ' + str(testStepNumber)) 
			tester.testStatus='Wait for Thick Reagent ' + str(testStepNumber)
			time.sleep(10)

		tester.infoMessage('Upper the Syringe out of the Reagent ' + str(testStepNumber)) 
		tester.testStatus='Upper the Syringe out of the Reagent ' + str(testStepNumber)
		success=tester.UpperSyringes()
		if not success:
			tester.debugMessage('Unable to upper the Syringe out of the Reagent ' + str(testStepNumber))
			sendUnableToRotateAlarm(tester,reagentSlot,testName)
			return False

		tester.infoMessage('Move to Mixerreactor') 
		tester.testStatus='Move to Mixerreactor'
		TargetXas=CentimeterToMove[Mixerreactor]
		success=tester.XtoTargetReagent(TargetXas)
		if not success:
			tester.debugMessage('Unable to move to Mixerreactor ')
			sendUnableToRotateAlarm(tester,reagentSlot,testName)
			return False

		tester.infoMessage('Lower the Syringe in the Mixerreactor') 
		tester.testStatus='Lower the Syringe in the Mixerreactor'
		success=tester.lowerSyringesInMixerreactor()
		if not success:
			tester.debugMessage('Unable to lower the Syringe in the Mixerreactor')
			sendUnableToRotateAlarm(tester,reagentSlot,testName)
			return False

		if AgitateSecsBetweenDrips>0:
			tester.infoMessage('Dose Reagent Liquid ' + str(testStepNumber) + ' in steps') 
			tester.testStatus='Dose Reagent Liquid ' + str(testStepNumber) + ' in steps'
			mlToDispense=amountToDispense
			while True:
				if mlToDispense>0:
					success=tester.fillSyringes(mlToDispense)
					tester.turnAgitator(AgitateSecsBetweenDrips)
					mlToDispense-=0.01
				else:
					break
		else:
			tester.infoMessage('Dose Reagent Liquid ' + str(testStepNumber)) 
			tester.testStatus='Dose Reagent Liquid ' + str(testStepNumber)
			success=tester.doseSyringesLiquid()
			if not success:
				tester.debugMessage('Unable to dose Reagent Liquid ' + str(testStepNumber))
				sendUnableFillSyringes(tester,reagentSlot,testName)
				return False

		tester.infoMessage('Upper the Syringe out of the Mixerreactor') 
		tester.testStatus='Upper the Syringe out of the Mixerreactor'
		success=tester.UpperSyringes()
		if not success:
			tester.debugMessage('Unable to upper the Syringe out of the Mixerreactor')
			sendUnableToRotateAlarm(tester,reagentSlot,testName)
			return False

		if agitateMixerSecs>0:
			tester.infoMessage('Agitating the Mixerreactor for ' + str(agitateMixerSecs) + ' secs.') 
			tester.testStatus='Agitating the Mixerreactor for ' + str(agitateMixerSecs) + ' secs.'
			tester.turnAgitator(agitateMixerSecs)

		tester.saveNewReagentValue(reagentSlot,amountToDispense)

		if tester.lastReagentRemainingML<tester.reagentRemainingMLAlarmThresholdAutoTester and tester.reagentAlmostEmptyAlarmEnable:
			sendReagentAlarm(tester,reagentSlot,tester.lastReagentRemainingML)

		cleanSyringe()

		return True
	except:
		tester.debugLog.exception('Failure when running Test Step ' + str(testStepNumber))
		return False
	
def getDirectReadResults(tester,ts,sequenceName):
	testSucceeded=True
	results=None
	tester.colorTable=tester.colorSheetList[ts.colorChartToUse].generateColorTableDisplay(tester)        
	if ts.agitateMixtureSecs>0:
		success=tester.UpperSyringes()
		TargetXas=CentimeterToMove[Mixerreactor]
		success=tester.XtoTargetReagent(TargetXas)
		tester.testStatus='Agitating the Mixture for ' + str(ts.agitateMixtureSecs) + ' secs.'
		tester.turnAgitator(ts.agitateMixtureSecs)
	global rgb
	l,a,b,rgb=tester.measureArduinoSensor()

	timeRemaining=ts.delayBeforeReadingSecs-ts.agitateMixtureSecs
	while timeRemaining>0:
		tester.testStatus='Waiting ' + str(timeRemaining) + ' secs before reading mixture.'
		time.sleep(1)
		timeRemaining-=1
	try:
		rs=evaluateResults(tester,ts.colorChartToUse)
		results=rs.valueAtSwatch
		tester.testStatus='Test results are: %.2f' % results
		tester.saveTestResults(results,swatchResultList=[rs])
		tester.infoMessage('Completed Test ' + sequenceName + ', Results were: %.2f' % results)
		if tester.sendMeasurementReports and not tester.telegramBotToken is None:
			
			sendMeasurementReport(tester,sequenceName,results)
	except:
		testSucceeded=False
		sendEvaluateAlarm(tester,sequenceName)
		tester.debugLog.exception("Failure evaluating")
	checkTestRange(tester,ts,results)
	
	l,a,b,rgb=tester.measureArduinoSensor()

	time.sleep(tester.pauseInSecsBeforeEmptyingMixingChamber)

	if testSucceeded:
		tester.testStatus='Result was: %.2f' % results + ' - Emptying chamber'
	else:
		tester.testStatus='Test Failed'
	tester.mainDrainPump(6)
	return results

def runTitration(tester,ts,sequenceName):
	global rgb
	l,a,b,rgb=tester.measureArduinoSensor()

	try:
		if ts.agitateMixtureSecs>0:
			success=tester.UpperSyringes()
			TargetXas=CentimeterToMove[Mixerreactor]
			success=tester.XtoTargetReagent(TargetXas)
			tester.infoMessage('Agitating the Mixerreactor for ' + str(ts.agitateMixtureSecs) + ' secs.') 
			tester.testStatus='Agitating the Mixerreactor for ' + str(ts.agitateMixtureSecs) + ' secs.'
			tester.turnAgitator(ts.agitateMixtureSecs)

		tester.infoMessage('Move to Titration Reagent ' + str(ts.titrationSlot)) 
		tester.testStatus='Move to Titration Reagent ' + str(ts.titrationSlot)
		TargetXas=CentimeterToMove[ts.titrationSlot]
		success=tester.XtoTargetReagent(TargetXas)
		if not success:
			tester.debugMessage('Unable to move to Titration Reagent ' + str(ts.titrationSlot))
			sendUnableToRotateAlarm(tester,ts.titrationSlot,testName)
			return False

		if ts.titrationAgitateSecs>0:
			tester.infoMessage('Agitating the Titration Reagent for ' + str(ts.titrationAgitateSecs) + ' secs.') 
			tester.testStatus='Agitating the Titration Reagent for ' + str(ts.titrationAgitateSecs) + ' secs.'
			tester.turnAgitator(ts.titrationAgitateSecs)

		tester.infoMessage('Get Reagent Liquid ' + str(ts.titrationSlot)) 
		tester.testStatus='Get Reagent Liquid ' + str(ts.titrationSlot)
		if ts.titrationMaxAmount>1:
			titrationfirstamount=1
			titrationsecondamount=ts.titrationMaxAmount-1

			#success=tester.fillSyringes(airInSyringe) Oude voor lucht
			success=tester.fillSyringes(titrationfirstamount)

			tester.infoMessage('Lower the Syringe in the Reagent ' + str(ts.titrationSlot)) 
			tester.testStatus='Lower the Syringe in the Reagent ' + str(ts.titrationSlot)
			success=tester.lowerSyringesInReagent()
			if not success:
				tester.debugMessage('Unable to lower the Syringe in the reagent ' + str(ts.titrationSlot))
				sendUnableToRotateAlarm(tester,ts.titrationSlot,testName)
				return False

			success=tester.fillSyringes(airInSyringe) #Tijdelijk voor test om lucht in reagent glaasje te krijgen om vacuum te voorkomen.

			success=tester.fillSyringes(titrationfirstamount+airInSyringe+syringeTolorance)
			success=tester.fillSyringes(titrationfirstamount+airInSyringe)
			amountToDispense=1
			amountToDose=amountToDispense
		
		else:
			#success=tester.fillSyringes(airInSyringe) Oude voor lucht
			success=tester.fillSyringes(ts.titrationMaxAmount)

			tester.infoMessage('Lower the Syringe in the Reagent ' + str(ts.titrationSlot)) 
			tester.testStatus='Lower the Syringe in the Reagent ' + str(ts.titrationSlot)
			success=tester.lowerSyringesInReagent()
			if not success:
				tester.debugMessage('Unable to lower the Syringe in the reagent ' + str(ts.titrationSlot))
				sendUnableToRotateAlarm(tester,ts.titrationSlot,testName)
				return False

			success=tester.fillSyringes(airInSyringe) #Tijdelijk voor test om lucht in reagent glaasje te krijgen om vacuum te voorkomen.
			success=tester.fillSyringes(ts.titrationMaxAmount+airInSyringe+syringeTolorance)
			success=tester.fillSyringes(ts.titrationMaxAmount+airInSyringe)
			titrationsecondamount=0
			amountToDispense=ts.titrationMaxAmount
			amountToDose=amountToDispense

		if not success:
			tester.debugMessage('Unable to get Reagent Liquid ' + str(ts.titrationSlot))
			sendUnableFillSyringes(tester,ts.titrationSlot,testName)
			return False
	
		tester.infoMessage('Upper the Syringe out of the Reagent ' + str(ts.titrationSlot)) 
		tester.testStatus='Upper the Syringe out of the Reagent ' + str(ts.titrationSlot)
		success=tester.UpperSyringes()
		if not success:
			tester.debugMessage('Unable to upper the Syringe out of the Reagent ' + str(ts.titrationSlot))
			sendUnableToRotateAlarm(tester,ts.titrationSlot,testName)
			return False

		tester.infoMessage('Move to Mixerreactor') 
		tester.testStatus='Move to Mixerreactor'
		TargetXas=CentimeterToMove[Mixerreactor]
		success=tester.XtoTargetReagent(TargetXas)
		if not success:
			tester.debugMessage('Unable to move to Mixerreactor ')
			sendUnableToRotateAlarm(tester,ts.titrationSlot,testName)
			return False

		remainingWaitTime=ts.delayBeforeReadingSecs-ts.titrationAgitateSecs
		if remainingWaitTime>0:
			tester.infoMessage('Waiting for ' + str(remainingWaitTime) + ' secs before beginning titration.') 
			tester.testStatus='Waiting for ' + str(remainingWaitTime) + ' secs before beginning titration.'
			time.sleep(remainingWaitTime)

		tester.infoMessage('Lower the Syringe in the Mixerreactor') 
		tester.testStatus='Lower the Syringe in the Mixerreactor'
		success=tester.lowerSyringesInMixerreactor()
		if not success:
			tester.debugMessage('Unable to lower the Syringe in the Mixerreactor')
			sendUnableToRotateAlarm(tester,ts.titrationSlot,testName)
			return False

		dispenseCount=0
		firstpass=0
		triggerpoint=0
		colorResultsList=[]
		testSucceeded=False

		if ts.titrationFirstSkip>0.01:
			TitronFirstSkipdose=1-ts.titrationFirstSkip
			success=tester.fillSyringes(TitronFirstSkipdose+airInSyringe)
			amountToDose-=ts.titrationFirstSkip
			dispenseCount+=ts.titrationFirstSkip

		while dispenseCount<=amountToDispense:
			success=tester.fillSyringes(amountToDose+airInSyringe)
			tester.testStatus='Processing with dispense = ' + str(round(dispenseCount,2))
			if ts.titrationAgitateMixerSecs>0:
				tester.turnAgitator(ts.titrationAgitateMixerSecs)
			time.sleep(0.5)
			rs=evaluateResultsBinary(tester,ts.colorChartToUse)
			rs.swatchDropCount=round(dispenseCount,2)
			colorResultsList.append(rs)
			print('Observed Value = ' + str(rs.valueAtSwatch))
			if rs.valueAtSwatch>=ts.titrationTransition:
				testSucceeded=True
				firstpass+=1
				if firstpass==1:
					triggerpoint=dispenseCount
				break	
			amountToDose-=0.01
			dispenseCount+=0.01
		print('Exited')

		if titrationsecondamount>0.01 and testSucceeded==False:
			tester.infoMessage('Upper the Syringe' )
			tester.testStatus='Upper the Syringe'
			success=tester.UpperSyringes()
			if not success:
				tester.debugMessage('Unable to upper the Syringe')
				sendUnableToRotateAlarm(tester,reagentSlot,testName)
				return False

			tester.infoMessage('Move to CleaningReactor') 
			tester.testStatus='Move to CleaningReactor'
			TargetXas=CentimeterToMove[Cleanreactor]
			success=tester.XtoTargetReagent(TargetXas)
			if not success:
				tester.debugMessage('Unable to move to CleaningReactor')
				sendUnableToRotateAlarm(tester,ts.titrationSlot,testName)
				return False

			tester.infoMessage('Lower the Syringe in the CleaningReactor') 
			tester.testStatus='Lower the Syringe in the CleaningReactor'
			success=tester.lowerSyringesInCleanreactor()
			if not success:
				tester.debugMessage('Unable to lower the Syringe in the CleaningReactor')
				sendUnableToRotateAlarm(tester,ts.titrationSlot,testName)
				return False

			tester.osmoseCleanPump(6)

			tester.turnAgitator(2)

			tester.infoMessage('Get Osmose Water to flush the Syringe') 
			tester.testStatus='Get Osmose Water to flush the Syringe'
			success=tester.fillSyringes(0.1)
			if not success:
				tester.debugMessage('Unable to get Osmose water')
				sendUnableFillSyringes(tester,ts.titrationSlot,testName)
				return False

			tester.infoMessage('Dose water') 
			tester.testStatus='Dose water'
			success=tester.doseSyringesLiquid()
			if not success:
				tester.debugMessage('Unable to dose the water')
				sendUnableFillSyringes(tester,ts.titrationSlot,testName)
				return False

			tester.turnAgitator(0)
			tester.cleanDrainPump(0)

			tester.infoMessage('Upper the Syringe out of the CleaningReactor') 
			tester.testStatus='Upper the Syringe out of the CleaningReactor'
			success=tester.UpperSyringes()
			if not success:
				tester.debugMessage('Unable to upper the Syringe out of the CleaningReactor')
				sendUnableToRotateAlarm(tester,ts.titrationSlot,testName)
				return False

			tester.cleanDrainPumpOff()
			tester.turnAgitatorOff()

			tester.infoMessage('Move to Titration Reagent ' + str(ts.titrationSlot)) 
			tester.testStatus='Move to Titration Reagent ' + str(ts.titrationSlot)
			TargetXas=CentimeterToMove[ts.titrationSlot]
			success=tester.XtoTargetReagent(TargetXas)
			if not success:
				tester.debugMessage('Unable to move to Titration Reagent ' + str(ts.titrationSlot))
				sendUnableToRotateAlarm(tester,ts.titrationSlot,testName)
				return False

			if ts.titrationAgitateSecs>0:
				tester.infoMessage('Agitating the Titration Reagent for ' + str(ts.titrationAgitateSecs) + ' secs.') 
				tester.testStatus='Agitating the Titration Reagent for ' + str(ts.titrationAgitateSecs) + ' secs.'
				tester.turnAgitator(ts.titrationAgitateSecs/2)

			#success=tester.fillSyringes(airInSyringe) Oude voor lucht
			success=tester.fillSyringes(titrationsecondamount)

			tester.infoMessage('Lower the Syringe in the Reagent ' + str(ts.titrationSlot)) 
			tester.testStatus='Lower the Syringe in the Reagent ' + str(ts.titrationSlot)
			success=tester.lowerSyringesInReagent()
			if not success:
				tester.debugMessage('Unable to lower the Syringe in the reagent ' + str(ts.titrationSlot))
				sendUnableToRotateAlarm(tester,ts.titrationSlot,testName)
				return False

			success=tester.fillSyringes(airInSyringe) #Tijdelijk voor test om lucht in reagent glaasje te krijgen om vacuum te voorkomen.
				
			tester.infoMessage('Get Reagent Liquid ' + str(ts.titrationSlot)) 
			tester.testStatus='Get Reagent Liquid ' + str(ts.titrationSlot)
			success=tester.fillSyringes(titrationsecondamount+airInSyringe+syringeTolorance)
			success=tester.fillSyringes(titrationsecondamount+airInSyringe)
			amountToDose=titrationsecondamount	
			if not success:
				tester.debugMessage('Unable to get Reagent Liquid ' + str(ts.titrationSlot))
				sendUnableToRotateAlarm(tester,ts.titrationSlot,testName)
				return False

			tester.infoMessage('Upper the Syringe' )
			tester.testStatus='Upper the Syringe'
			success=tester.UpperSyringes()
			if not success:
				tester.debugMessage('Unable to upper the Syringe')
				sendUnableToRotateAlarm(tester,reagentSlot,testName)
				return False

			tester.infoMessage('Move to Mixerreactor') 
			tester.testStatus='Move to Mixerreactor'
			TargetXas=CentimeterToMove[Mixerreactor]
			success=tester.XtoTargetReagent(TargetXas)
			if not success:
				tester.debugMessage('Unable to move to Mixerreactor ')
				sendUnableToRotateAlarm(tester,ts.titrationSlot,testName)
				return False

			tester.infoMessage('Lower the Syringe in the Mixerreactor') 
			tester.testStatus='Lower the Syringe in the Mixerreactor'
			success=tester.lowerSyringesInMixerreactor()
			if not success:
				tester.debugMessage('Unable to lower the Syringe in the Mixerreactor')
				sendUnableToRotateAlarm(tester,ts.titrationSlot,testName)
				return False

			while dispenseCount<=ts.titrationMaxAmount:
				success=tester.fillSyringes(amountToDose+airInSyringe)
				tester.testStatus='Processing with dispense = ' + str(round(dispenseCount,2))
				if ts.titrationAgitateMixerSecs>0:
					tester.turnAgitator(ts.titrationAgitateMixerSecs)
				time.sleep(0.5)
				rs=evaluateResultsBinary(tester,ts.colorChartToUse)
				rs.swatchDropCount=round(dispenseCount,2)
				colorResultsList.append(rs)
				print('Observed Value = ' + str(rs.valueAtSwatch))
				if rs.valueAtSwatch>=ts.titrationTransition:
					testSucceeded=True
					firstpass+=1
					if firstpass==1:
						triggerpoint=dispenseCount
					break

				amountToDose-=0.01
				dispenseCount+=0.01
			print('Exited')

		tester.infoMessage('Upper the Syringe' )
		tester.testStatus='Upper the Syringe'
		success=tester.UpperSyringes()
		if not success:
			tester.debugMessage('Unable to upper the Syringe')
			sendUnableToRotateAlarm(tester,reagentSlot,testName)
			return False

		try:
			if testSucceeded:
				convertdripstovalue=triggerpoint*ts.calctovalue
				results=round(convertdripstovalue,2)
				tester.testStatus=('Test results are: ' + str(round(convertdripstovalue,2)) + ', Used ML:' + str(round(triggerpoint,2)))
				tester.saveTestResults(results,swatchResultList=colorResultsList)
				tester.infoMessage('Completed Test ' + sequenceName + ', Results were: ' + str(round(convertdripstovalue,2)) + ', Used ML:' + str(round(triggerpoint,2)))
				if tester.sendMeasurementReports and not tester.telegramBotToken is None:
					sendMeasurementReport(tester,sequenceName,results)
				checkTestRange(tester,ts,results)
			elif dispenseCount>ts.titrationMaxAmount:
				results=None
				tester.saveTestResults(results,swatchResultList=colorResultsList)
				sendEvaluateAlarm(tester,sequenceName)
				tester.debugLog.exception("Max ML dispensed before hitting transition")
			else:
				sendEvaluateAlarm(tester,sequenceName)
				tester.debugLog.exception("Failure evaluating")                
		except:
			testSucceeded=False
			sendEvaluateAlarm(tester,sequenceName)
			tester.debugLog.exception("Failure evaluating")

		time.sleep(tester.pauseInSecsBeforeEmptyingMixingChamber)

		tester.infoMessage('Move to CleaningReactor') 
		tester.testStatus='Move to CleaningReactor'
		TargetXas=CentimeterToMove[Cleanreactor]
		success=tester.XtoTargetReagent(TargetXas)
		if not success:
			tester.debugMessage('Unable to move to CleaningReactor')
			sendUnableToRotateAlarm(tester,ts.titrationSlot,testName)
			return False

		if amountToDose>0.02:
			tester.infoMessage('Lower the Syringe in the CleaningReactor') 
			tester.testStatus='Lower the Syringe in the CleaningReactor'
			success=tester.lowerSyringesInCleanreactor()
			if not success:
				tester.debugMessage('Unable to lower the Syringe in the CleaningReactor')
				sendUnableToRotateAlarm(tester,ts.titrationSlot,testName)
				return False

			tester.osmoseCleanPump(6)

			tester.turnAgitator(0)

			amountToDose-=0.01
			success=tester.fillSyringes(amountToDose+airInSyringe)
			time.sleep(1)

			tester.cleanDrainPump(0)

			tester.infoMessage('Upper the Syringe out of the CleaningReactor') 
			tester.testStatus='Upper the Syringe out of the CleaningReactor'
			success=tester.UpperSyringes()
			if not success:
				tester.debugMessage('Unable to upper the Syringe out of the CleaningReactor')
				sendUnableToRotateAlarm(tester,ts.titrationSlot,testName)
				return False

			time.sleep(2)
			tester.cleanDrainPumpOff()
			tester.turnAgitatorOff()

			tester.infoMessage('Move to Titration Reagent ' + str(ts.titrationSlot)) 
			tester.testStatus='Move to Titration Reagent ' + str(ts.titrationSlot)
			TargetXas=CentimeterToMove[ts.titrationSlot]
			success=tester.XtoTargetReagent(TargetXas)
			if not success:
				tester.debugMessage('Unable to move to Titration Reagent ' + str(ts.titrationSlot))
				sendUnableToRotateAlarm(tester,ts.titrationSlot,testName)
				return False

			tester.infoMessage('Lower the Syringe in the Reagent ' + str(ts.titrationSlot)) 
			tester.testStatus='Lower the Syringe in the Reagent ' + str(ts.titrationSlot)
			success=tester.lowerSyringesInReagentForReturnLiquid()
			if not success:
				tester.debugMessage('Unable to lower the Syringe in the reagent ' + str(ts.titrationSlot))
				sendUnableToRotateAlarm(tester,ts.titrationSlot,testName)
				return False

			tester.infoMessage('Dose Reagent Liquid ' +  str(ts.titrationSlot)) 
			tester.testStatus='Dose Reagent Liquid ' +  str(ts.titrationSlot)
			success=tester.doseSyringesLiquid()
			if not success:
				tester.debugMessage('Unable to dose Reagent Liquid ' +  str(ts.titrationSlot))
				sendUnableFillSyringes(tester,ts.titrationSlot,testName)
				return False

			tester.infoMessage('Upper the Syringe' )
			tester.testStatus='Upper the Syringe'
			success=tester.UpperSyringes()
			if not success:
				tester.debugMessage('Unable to upper the Syringe')
				sendUnableToRotateAlarm(tester,reagentSlot,testName)
				return False

			tester.infoMessage('Move to CleaningReactor') 
			tester.testStatus='Move to CleaningReactor'
			TargetXas=CentimeterToMove[Cleanreactor]
			success=tester.XtoTargetReagent(TargetXas)
			if not success:
				tester.debugMessage('Unable to move to CleaningReactor')
				sendUnableToRotateAlarm(tester,ts.titrationSlot,testName)
				return False

		cleanSyringe()

		tester.saveNewReagentValue(ts.titrationSlot,dispenseCount)

		if tester.lastReagentRemainingML<tester.reagentRemainingMLAlarmThresholdAutoTester and tester.reagentAlmostEmptyAlarmEnable:
			sendReagentAlarm(tester,ts.titrationSlot,tester.lastReagentRemainingML)
		return results
	except:
		time.sleep(1)
		tester.mainDrainPump(6)

		tester.debugLog.exception('Failure when running Titration Step')
		return None

def runKHTest(tester,ts,sequenceName):
	PHmin = 6.5
	PHmax = 9
	PHStartSlowReagentDose = 5.8
	PHreachpoint = 4.5
	reagentDoseFastAmount = 0.50
	reagentDoseSlowAmount = 0.05
	testSucceeded=None


	#tester.infoMessage('Start KH Tester') 
	#tester.testStatus='Start KH Tester'
	#mixing Reagent in Bottle
	tester.infoMessage('Mix Reagent Bottle') 
	tester.testStatus='Mix Reagent Bottle'
	tester.mixerReagentBottleMotorCommand(ts.titrationAgitateSecs)
	tester.infoMessage('Mix Jar') 
	tester.testStatus='Mix Jar'
	tester.mixerJarMotorCommand(2)
	#empty Mixer Jar
	tester.infoMessage('Empty jar back to tank') 
	tester.testStatus='Empty jar back to tank'
	tester.sampleWaterPumpCommand(-ts.waterVolInML)
	tester.infoMessage('Empty jar to drain') 
	tester.testStatus='Empty jar to drain'
	tester.drainPumpCommand(25)
	#fill mixer Jar
	tester.infoMessage('Fill jar with tank water') 
	tester.testStatus='Fill jar with tank water'
	tester.sampleWaterPumpCommand(ts.waterVolInML)
	tester.mixerJarMotorCommand(5)
	#check PH is ok
	global PH
	PH = tester.read_ph()
	print('PH now in Jar: ' + str(PH))
	#tester.infoMessage('PH in Jar ' + str(PH)) 
	#tester.testStatus='PH in Jar ' + str(PH)
	doseTotalReagent=0

	if PH<PHmin or PH>PHmax:
		print ('test failed because PH out of start range')
		testSucceeded=False

	tester.mixerJarMotorCommandManual(0.55)
	tester.infoMessage('Dose first reagent amount') 
	tester.testStatus='Dose first reagent amount'
	tester.reagentPumpCommand(ts.titrationFirstSkip)
	doseTotalReagent+=ts.titrationFirstSkip

	while doseTotalReagent<=ts.titrationMaxAmount and testSucceeded==None:
		tester.infoMessage('Dosed ' + str(doseTotalReagent) + 'ML') 
		tester.testStatus='Dosed ' + str(doseTotalReagent) + 'ML'
		if PH>PHStartSlowReagentDose:
			#Mixer motor
			tester.reagentPumpCommand(reagentDoseFastAmount)
			doseTotalReagent+=reagentDoseFastAmount
			PH = tester.read_ph()

		if PH<=PHStartSlowReagentDose:
			#Mixer motor
			tester.reagentPumpCommand(reagentDoseSlowAmount)
			doseTotalReagent+=reagentDoseSlowAmount
			PH = tester.read_ph()
			if PH <= PHreachpoint:
				print ('Test passed with total reagent used' + str(doseTotalReagent))
				testSucceeded=True
				break

		if doseTotalReagent>=ts.titrationMaxAmount:
			testSucceeded=False

	tester.mixerJarMotorCommandManual(0)
	
	if testSucceeded is True:
		KHValue = round((doseTotalReagent*ts.calctovalue),2)
		tester.infoMessage('Result was: '+ str(KHValue) + 'KH')
		tester.testStatus='Result was: '+ str(KHValue) + 'KH'
		sendMeasurementReport(tester,sequenceName,KHValue)
	else:
		KHValue = None
		sendEvaluateAlarm(tester,sequenceName)



	tester.infoMessage('Empty jar to drain') 
	tester.testStatus='Empty jar to drain'
	tester.drainPumpCommand(60)

	#Fill Mixer Jar, for keeping the PH probe wet
	tester.infoMessage('Fill jar with tank water') 
	tester.testStatus='Fill jar with tank water'
	tester.sampleWaterPumpCommand(ts.waterVolInML)
	tester.mixerJarMotorCommand(5)

	PH = tester.read_ph()
	print('PH now after test in Jar: ' + str(PH))

	tester.saveNewReagentValue(ts.titrationSlot,doseTotalReagent)

	if tester.lastReagentRemainingML<tester.reagentRemainingMLAlarmThresholdKHTester and tester.reagentAlmostEmptyAlarmEnable:
		sendReagentAlarm(tester,ts.titrationSlot,tester.lastReagentRemainingML)

	return KHValue

def CalibratePH(tester):
	waitTime = 120
	while waitTime >= 1: 
		waitTime-=1
		tester.infoMessage('Wait ' + str(waitTime) + ' Sec') 
		tester.systemStatus='Wait ' + str(waitTime) + ' Sec'
		time.sleep(1)
	result=tester.calibratePH()
	if result is True:
		message = 'Passed'
	else:
		message = 'Failed'
	tester.infoMessage('Calibration ' + str(message)) 
	tester.systemStatus='Calibration ' + str(message)
	global PH
	PH = tester.read_ph()
	print('PH now: ' + str(PH))
	time.sleep(10)
	tester.systemStatus="Idle"
	return


def runTestSequence(tester,sequenceName):
	from tester.models import ReagentSetup
	tester.systemStatus="Running Test"
	tester.abortJob=False
	results=None
	tester.infoMessage('Running Test ' + sequenceName) 
	tester.currentTest=sequenceName
	testSucceeded=None
	try:
		ts=tester.testSequenceList[sequenceName]
		
		if ts.KHtestwithPHProbe:
			if not ts.titrationSlot is None:
				if (ReagentSetup.objects.get(slotName=ts.titrationSlot).fluidRemainingInML)<tester.reagentRemainingMLAlarmThresholdKHTester:
					sendReagentAlarm(tester,ts.titrationSlot,ReagentSetup.objects.get(slotName=ts.titrationSlot).fluidRemainingInML)
					tester.infoMessage('KH Reagent to low to start test')
					testSucceeded=False

				if not testSucceeded is False and not tester.abortJob:
					results=runKHTest(tester,ts,sequenceName)
					tester.saveTestResults(results,None)
					if results is None:
						testSucceeded=False

		else:

			numSteps=0
			tester.homingArduinoStepper()
			if not ts.reagent1Slot is None:
				numSteps+=1
				if (ReagentSetup.objects.get(slotName=ts.reagent1Slot).fluidRemainingInML)<tester.reagentRemainingMLAlarmThresholdAutoTester:
					tester.infoMessage('Reagent 1 to low to start test')
					sendReagentAlarm(tester,ts.reagent1Slot,ReagentSetup.objects.get(slotName=ts.reagent1Slot).fluidRemainingInML)
					testSucceeded=False
			if not ts.reagent2Slot is None:
				numSteps+=1
				if (ReagentSetup.objects.get(slotName=ts.reagent2Slot).fluidRemainingInML)<tester.reagentRemainingMLAlarmThresholdAutoTester:
					tester.infoMessage('Reagent 2 to low to start test')
					sendReagentAlarm(tester,ts.reagent2Slot,ReagentSetup.objects.get(slotName=ts.reagent2Slot).fluidRemainingInML)
					testSucceeded=False
			if not ts.reagent3Slot is None:
				numSteps+=1
				if (ReagentSetup.objects.get(slotName=ts.reagent3Slot).fluidRemainingInML)<tester.reagentRemainingMLAlarmThresholdAutoTester:
					sendReagentAlarm(tester,ts.reagent3Slot,ReagentSetup.objects.get(slotName=ts.reagent3Slot).fluidRemainingInML)
					tester.infoMessage('Reagent 3 to low to start test')
					testSucceeded=False
			if not ts.titrationSlot is None:
				numSteps+=1
				if (ReagentSetup.objects.get(slotName=ts.titrationSlot).fluidRemainingInML)<tester.reagentRemainingMLAlarmThresholdAutoTester:
					sendReagentAlarm(tester,ts.titrationSlot,ReagentSetup.objects.get(slotName=ts.titrationSlot).fluidRemainingInML)
					tester.infoMessage('Titration to low to start test')
					testSucceeded=False

			if not testSucceeded is False:
				if not ts.reagent1Slot is None and ts.reagent1Amount>0:
					success=runTestStep(tester,1,sequenceName,ts.waterVolInML,ts.reagent1Slot,ts.reagent1AgitateSecs,ts.reagent1AgitateMixerSecs,ts.reagent1AgitateSecsBetweenDrips,ts.reagent1Amount,ts.reagent1ThickLiquid,lastStep=numSteps==1)
					testSucceeded=success
					if success and not ts.reagent2Slot is None and ts.reagent2Amount>0 and not tester.abortJob:
						success=runTestStep(tester,2,sequenceName,0,ts.reagent2Slot,ts.reagent2AgitateSecs,ts.reagent2AgitateMixerSecs,ts.reagent2AgitateSecsBetweenDrips,ts.reagent2Amount,ts.reagent2ThickLiquid,lastStep=numSteps==2)
						testSucceeded=success
						if success and not ts.reagent3Slot is None and ts.reagent3Amount>0  and not tester.abortJob:
							success=runTestStep(tester,3,sequenceName,0,ts.reagent3Slot,ts.reagent3AgitateSecs,ts.reagent3AgitateMixerSecs,ts.reagent3AgitateSecsBetweenDrips,ts.reagent3Amount,ts.reagent3ThickLiquid,lastStep=numSteps==3)
							testSucceeded=success
				if testSucceeded and not tester.abortJob:
					if ts.titrationSlot is None:
						results=getDirectReadResults(tester,ts,sequenceName)
						if results is None:
							testSucceeded=False
					else:
						results=runTitration(tester,ts,sequenceName)
						if results is None:
							testSucceeded=False
				else:
					tester.saveTestSaveBadResults()
		
				if not tester.anyMoreJobs():
					if testSucceeded:
						tester.testStatus='Result was: %.2f' % results + ' - Cleaning the Mixer'
						print('Result was: %.2f' % results + ' - Cleaning the Mixer')
					else:
						tester.testStatus='Test Failed'
						print('Test Failed')

				osmoseCleanMixerReactor(tester)

				time.sleep(1)

				tester.homingArduinoStepper()
				tester.infoMessage('System Parked') 
		if testSucceeded is False or None:
			tester.testStatus='Test Failed'
		else:
			tester.testStatus='Done: Last Results: %.2f' % results
		tester.colorTable=None
	except:
		tester.debugLog.exception('Failure when running Test')
	tester.turnAgitatorOff()
	tester.systemStatus="Idle"
	global rgb
	rgb=255,255,255
	return testSucceeded

def dailyMaintenance():
	tester.removeOldRecords()
				
def alarmMonitor():
	alarmCheckIntervalInSeconds=60
	lastWakeupTime=datetime.datetime.now()
	alarmCheckInterval=datetime.timedelta(seconds=alarmCheckIntervalInSeconds)
	nextalarmCheck=lastWakeupTime+alarmCheckInterval
	while True:
		lastWakeupTime=sleepUntilNextInterval(lastWakeupTime,alarmCheckIntervalInSeconds)
		if datetime.datetime.now()>nextalarmCheck:
			nextalarmCheck=nextalarmCheck+alarmCheckInterval
			try:
				time.sleep(100)
			except:
				tester.debugLog.exception("Continuing...")
				time.sleep(1)
				
def queueTestJob(tester,jobToQueue):
	print('Running job: ' + jobToQueue)
	tester.runTestLock.acquire()
	tester.addJobToQueue(jobToQueue)
	tester.runTestLock.release()
	
def runTestFromQueue():    
	while True:
		try:
			moreToDo=tester.anyMoreJobs()
			if moreToDo and tester.systemStatus=='Idle':
				tester.runTestLock.acquire()
				nextJobToRun=tester.getNextJob()
				tester.runTestLock.release()
				if nextJobToRun is None:
					time.sleep(10)
				else:
					if tester.simulation:
						print('Would have runTestSequence for ' + nextJobToRun)
					else:
						runTestSequence(tester,nextJobToRun)
					tester.abortJob=False
					tester.clearRunningJobs() 
			else:
				time.sleep(10)
		except:
			tester.debugLog.exception("Error in Test Runner...")
			time.sleep(10)
			
def clearJobSchedules():
	schedule.clear()
	
def setJobSchedules(testName):
	daysToRun=tester.getJobDaysText(testName)
	tester.infoMessage('Days to run for ' + testName + ' was ' + daysToRun)
	if daysToRun=='Never':
		return
	for hour in tester.getHoursToRunList(testName):
		print('Adding schedule for ' + testName + ' on ' + daysToRun + ' at ' + hour)
		if daysToRun=='Everyday':
			schedule.every().day.at(hour).do(queueTestJob,tester,testName).tag(testName)
		elif daysToRun=='2day':
			schedule.every(2).days.at(hour).do(queueTestJob,tester,testName).tag(testName)
		elif daysToRun=='3day':
			schedule.every(3).days.at(hour).do(queueTestJob,tester,testName).tag(testName)
		elif daysToRun=='4day':
			schedule.every(4).days.at(hour).do(queueTestJob,tester,testName).tag(testName)
		elif daysToRun=='5day':
			schedule.every(5).days.at(hour).do(queueTestJob,tester,testName).tag(testName)
		elif daysToRun=='10day':
			schedule.every(10).days.at(hour).do(queueTestJob,tester,testName).tag(testName)
		elif daysToRun=='14day':
			schedule.every(14).days.at(hour).do(queueTestJob,tester,testName).tag(testName)
		elif daysToRun=='21day':
			schedule.every(21).days.at(hour).do(queueTestJob,tester,testName).tag(testName)
		elif daysToRun=='28day':
			schedule.every(28).days.at(hour).do(queueTestJob,tester,testName).tag(testName)
		elif daysToRun=='Sunday':
			schedule.every().sunday.at(hour).do(queueTestJob,tester,testName).tag(testName)
		elif daysToRun=='Monday':
			schedule.every().sunday.at(hour).do(queueTestJob,tester,testName).tag(testName)
		elif daysToRun=='Tuesday':
			schedule.every().sunday.at(hour).do(queueTestJob,tester,testName).tag(testName)
		elif daysToRun=='Wednesday':
			schedule.every().sunday.at(hour).do(queueTestJob,tester,testName).tag(testName)
		elif daysToRun=='Thursday':
			schedule.every().sunday.at(hour).do(queueTestJob,tester,testName).tag(testName)
		elif daysToRun=='Friday':
			schedule.every().sunday.at(hour).do(queueTestJob,tester,testName).tag(testName)
		elif daysToRun=='Saturday':
			schedule.every().sunday.at(hour).do(queueTestJob,tester,testName).tag(testName)

def resetJobSchedules():
	clearJobSchedules()
	for ts in tester.testSequenceList:
		try:
			setJobSchedules(ts) 
		except:
			pass 
	schedule.every().day.at('22:09').do(dailyMaintenance).tag('Maintenance')

def testerJobScheduler():
	resetJobSchedules()
	while True:
		if tester.resetJobSchedule:
			tester.resetJobSchedule=False
			resetJobSchedules()
		schedule.run_pending()
		time.sleep(10) 
		
def runDiagnosticTest(diagnosticTest):
	tester.systemStatus="Running Diagnostic"
	if diagnosticTest[0]=='Carousel Diagnostic':
		stepsToRun=diagnosticTest[1]
		tester.debugLog.info("Starting Carousel Diagnostic for " + str(stepsToRun) + ' movements')
		testRotation(tester,int(stepsToRun))
		tester.debugLog.info("Carousel Diagnostic test completed - see Debug log for results")
	elif diagnosticTest[0]=='Plunger Diagnostic':
		stepsToRun=diagnosticTest[1]
		tester.debugLog.info("Starting Plunger Diagnostic for " + str(stepsToRun) + ' open/close cycles')
		testPlunger(tester,int(stepsToRun))
		tester.debugLog.info("Plunger Diagnostic test completed - see Debug log for results")
	elif diagnosticTest[0]=='Dispense Diagnostic':
		stepsToRun=diagnosticTest[1]
		tester.debugLog.info("Starting Drop Dispensing Diagnostic for " + str(stepsToRun) + ' cycles')
		testDispensing(tester,int(stepsToRun))
		tester.debugLog.info("Drop Dispense Diagnostic test completed - see Debug log for results")
	elif diagnosticTest[0]=='Fill Mixer Diagnostic':
		stepsToRun=diagnosticTest[1]
		tester.debugLog.info("Starting Mixer Fill Diagnostic for " + str(stepsToRun) + ' cycles')
		testMixerFill(tester,int(stepsToRun))
		tester.debugLog.info("Mixer Fill Diagnostic test completed - see Debug log for results")
	else:
		try:
			print('Unknown diagnostic test ' + diagnosticTest[0])
		except:
			traceback.print_exc()   
	tester.systemStatus="Idle"
			 
def testerDiagnostics(): 
	while True:
		tester.diagnosticLock.acquire()
		diagnosticQueueItemCount=len(tester.diagnosticQueue)
		if diagnosticQueueItemCount >0 and tester.systemStatus=="Idle":
			nextDiagnostic=tester.diagnosticQueue[0]
			tester.diagnosticQueue=tester.diagnosticQueue[1:]
			tester.diagnosticLock.release()
			runDiagnosticTest(nextDiagnostic)
		else:
			tester.diagnosticLock.release()
		time.sleep(10)
				 
def exit_handler():
	global remoteControlThreadRPYC
	tester.debugMessage('Done')
	remoteControlThreadRPYC.close()
	tester.webcamRelease()
	
if __name__ == '__main__':
	from WebCmdHandler import processWebCommand
	basePath=getBasePath()
	sys.path.append(os.path.abspath(basePath))
	os.environ['DJANGO_SETTINGS_MODULE'] = 'AutoTesterv2.settings'
	django.setup()
	tester=Tester(1)
	if tester.manageDatabases:
		adminToUse=tester.basePath + 'tester/databaseAdminFull.py'
	else:
		adminToUse=tester.basePath + 'tester/databaseAdminEmpty.py'
	adminToReplace=tester.basePath + 'tester/databaseAdmin.py'
	try:
		fin=open(adminToUse,'r')
		text=fin.read()
		fin.close()
		fout=open(adminToReplace,'w+')
		fout.write(text)
		fout.close()
	except:
		tester.infoMessage('Admin update failed')
	testerWebName='TesterWeb'
	if platform.system()!='Windows':
		if screenPresent(testerWebName):
			tester.infoMessage('Web port already active, so not relaunched')
		else:
			tester.infoMessage('Web port not active, so launching webserver on port: ' + str(tester.webPort))
			runWebServer(tester,testerWebName)
	tester.videoLowResCaptureLock=threading.Condition()
	tester.runTestLock=threading.Lock()
	tester.diagnosticLock=threading.Lock()
	tester.testerLog.info('Feeded Server Threaded Started')
	remoteControlThreadRPYC = ThreadedServer(TesterRemoteControl, port = 18861)
	atexit.register(exit_handler)
	remoteControlThread=threading.Thread(target=startHandler,args=('Remote Control',remoteControlThreadRPYC))
	remoteControlThread.start()
	videoGrabberThread=threading.Thread(target=videoGrabber,name='Video Grabber',args=())
	videoGrabberThread.start()
	tester.infoMessage('Thread: ' + videoGrabberThread.getName() + ' started')
	videoStreamerThread=threading.Thread(target=videoStreamer,name='Video Streamer',args=())
	videoStreamerThread.start()
	tester.infoMessage('Thread: ' + videoStreamerThread.getName() + ' started')
	orientTesterThread=threading.Thread(target=orientTester,name='Orient Tester',args=())
	orientTesterThread.start()
	tester.infoMessage('Thread: ' + orientTesterThread.getName() + ' started')
	runTestFromQueueThread=threading.Thread(target=runTestFromQueue,name='Run Test',args=())
	runTestFromQueueThread.start()
	tester.infoMessage('Thread: ' + runTestFromQueueThread.getName() + ' started')
	testerJobSchedulerThread=threading.Thread(target=testerJobScheduler,name='Job Scheduler',args=())
	testerJobSchedulerThread.start()
	tester.infoMessage('Thread: ' + testerJobSchedulerThread.getName() + ' started')
	testerDiagnosticsThread=threading.Thread(target=testerDiagnostics,name='Diagnostics',args=())
	testerDiagnosticsThread.start()
	tester.infoMessage('Thread: ' + testerDiagnosticsThread.getName() + ' started')
	tester.infoMessage('Tester Server version ' + currentVersion + ' loaded') 