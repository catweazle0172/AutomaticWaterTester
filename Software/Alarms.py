'''
AutoTester is the controlling software to automatically run water tests
Further info can be found at: https://robogardens.com/?p=928
This software is free for DIY, Nonprofit, and educational uses.
Copyright (C) 2017 - RoboGardens.com
    
Created on Aug 9, 2017

This module handles sending alarms and reports using the Telegram

@author: Stephen Hayes
'''
import datetime
import requests    # @UnresolvedImport


def telegram_bot_sendtext(message):
    from tester.models import TesterExternal,TesterProcessingParameters
    te=TesterExternal.objects.get(pk=1)

    send_text = 'https://api.telegram.org/bot' + (str(te.telegramBotToken)) + '/sendMessage?chat_id=' + (str(te.telegramChatID)) + '&parse_mode=Markdown&text=' + (str(message))

    response = requests.get(send_text)

    return response.json()

def sendMeasurementReport(tester,testRun,result):
    print('Measurement Report sent with ' + tester.testerName + ', ' + testRun + ',  %.2f' % result)
    message=('Measurement result from ' + tester.testerName + '\nWith result: ' + testRun + ' ' + (str(result))) 
    telegram_bot_sendtext(message)

def sendTestMeasurementReport(tester,testRun,testKey):
    print('Test Measurement Report sent with ' + tester.testerName + ', ' + testRun + ', This Was a Test')
    message=('Test Measurement Report sent with ' + tester.testerName + ', ' + testRun + ', This Was a Test')
    telegram_bot_sendtext(message)

def sendReagentAlarm(tester,reagent,remainingML):
    message=('From: ' + tester.testerName + '\nReagent in Slot ' + reagent + ' Low, Remaining ML: '+ (str(remainingML)))
    telegram_bot_sendtext(message)
    
def sendFillAlarm(tester,testBeingRun):
    sendAlarm(tester,'Error filling Mixing Cylinder',testBeingRun)   
    
def sendDispenseAlarm(tester,reagent,remainingML):
    sendAlarm(tester,'Unable to Dispense Drops for Slot ' + reagent ,'Remaining ML: '+ str(remainingML)) 

def sendEvaluateAlarm(tester,sequenceName):
    message=('Unable to Evaluate Samples for Test ' + sequenceName) 
    telegram_bot_sendtext(message)

def sendUnableToRotateAlarm(tester,slot,testName):
    sendAlarm(tester,'Unable to Rotate Carousel to Slot ' + slot,'Test: '+ testName) 

def sendUnableFillSyringes(tester,slot,testName):
    message=('From: ' + tester + '\nUnable to Fill Syringes by reagent:' + slot + ' For test: ' + testName)
    telegram_bot_sendtext(message)

def sendCannotParkAlarm(tester,testConcern):
    message=('From: ' + tester + '\nParking Failure' + testConcern)
    telegram_bot_sendtext(message)
    
def sendOutOfLimitsAlarm(tester,testName,results):
    message=('From: ' + tester + '\nWhat: Alarm\n Out of Limits' + testName + ' results: ' + (str(results))) 
    telegram_bot_sendtext(message)

def sendOutOfLimitsWarning(tester,testName,results):
    message=('From: ' + tester + '\nWhat: Warning\n Out of Limits' + testName + ' results: ' + (str(results))) 
    telegram_bot_sendtext(message)