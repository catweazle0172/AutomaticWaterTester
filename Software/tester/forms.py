'''
AutoTester is the controlling software to automatically run water tests
Further info can be found at: https://robogardens.com/?p=928
This software is free for DIY, Nonprofit, and educational uses.
Copyright (C) 2017 - RoboGardens.com
    
Created on Aug 9, 2017

This module configures the autotester web forms for django.

@author: Stephen Hayes
'''

from django import forms
#from django.forms import modelformset_factory, Textarea

from .models import TestSchedule,TestDefinition,ReagentSetup,TesterExternal,CalibrationValues,MeasuredParameters

class ScheduleForm(forms.ModelForm):
    class Meta:
        model = TestSchedule
        exclude=()
#        widgets = {
#            'testToSchedule': Textarea(attrs={'cols': 80, 'rows': 20}),
#        }
    def __init__(self, *args, **kwargs):
        super(ScheduleForm, self).__init__(*args, **kwargs)
        if self.instance.id:
            self.fields['testToSchedule'].widget.attrs['readonly'] = True
            self.fields['hoursToRun'].help_text="Control Select for more than on hour"

class ReagentForm(forms.ModelForm):
    class Meta:
        model = ReagentSetup
        exclude=()
#        widgets = {
#            'testToSchedule': Textarea(attrs={'cols': 80, 'rows': 20}),
#        }
    def __init__(self, *args, **kwargs):
        super(ReagentForm, self).__init__(*args, **kwargs)
        if self.instance.id:
            self.fields['slotName'].widget.attrs['readonly'] = True
            self.fields['slotName'].label="Carousel Letter"
            self.fields['slotName'].help_text=None
            self.fields['slotName'].widget.attrs['title'] = "This is the carousel slot containing the reagent"
            self.fields['reagentName'].help_text=None
            self.fields['reagentName'].widget.attrs['title'] = "Human description of what the reagent is"
            self.fields['used'].help_text=None
            self.fields['used'].widget.attrs['title'] = "Is this reagent being used?"
            self.fields['hasAgitator'].help_text=None
            self.fields['hasAgitator'].widget.attrs['title'] = "If the syringe has an agitator magnet or not"
            self.fields['fluidRemainingInML'].help_text=None
            self.fields['fluidRemainingInML'].widget.attrs['title'] = "Amount of usable reagent left (set by machine)"
            self.fields['color'].help_text=None
            self.fields['color'].widget.attrs['title'] = "Human description of the color"
            self.fields['reagentInserted'].help_text=None
            self.fields['reagentInserted'].widget.attrs['title'] = "When the reagent was last replaced"
            
class TestDefinitionForm(forms.ModelForm):
    class Meta:
        model = TestDefinition
        exclude=()
#        widgets = {
#            'testToSchedule': Textarea(attrs={'cols': 80, 'rows': 20}),
#        }

class TesterForm(forms.ModelForm):
    class Meta:
        model = TesterExternal
        exclude=('lensType','fisheyeExpansionFactor','cameraWidthLowRes','cameraHeightLowRes', \
                 'tooDarkThreshold','measurementUnits','pumpPurgeTimeSeconds','pauseInSecsBeforeEmptyingMixingChamber')

    def __init__(self, *args, **kwargs):
        super(TesterForm, self).__init__(*args, **kwargs)
        if self.instance.id:
            self.fields['testerName'].label="Name of the Tester"
            self.fields['testerName'].widget.attrs['title'] = "This is the name of the AutoTester.  It will be sent in notifications"
            self.fields['testerVersion'].label="Software Version"
            self.fields['testerVersion'].widget.attrs['title'] = "This is the software version"
            self.fields['testerVersion'].widget.attrs['readonly'] = True
            self.fields['dbModelVersion'].label="Database Version"
            self.fields['dbModelVersion'].widget.attrs['title'] = "This is the version of the database"
            self.fields['dbModelVersion'].widget.attrs['readonly'] = True
            self.fields['virtualEnvironmentName'].label="Virtual Environment Name"
            self.fields['virtualEnvironmentName'].widget.attrs['title'] = "The name of the virtual environment that the program runs under"
            self.fields['webPort'].label="WebServer Port"
            self.fields['webPort'].widget.attrs['title'] = "Port that the WebServer Listens On, Must be >1000"
            self.fields['videoStreamingPort'].label="Video Streaming Port"
            self.fields['videoStreamingPort'].widget.attrs['title'] = "Port that the Video from the AutoTester is streamed to.  Must be >1000"
            self.fields['mixerCleanML'].label="ML to Clean the Mixer"
            self.fields['mixerCleanML'].widget.attrs['title'] = "How many ML to clean the mixer for each flush cycle"
            self.fields['mixerCleanCycles'].label="Mixer Cleaning Cycles"
            self.fields['mixerCleanCycles'].widget.attrs['title'] = "How many times to clean the mixer at the beginning of each test"
            self.fields['mixerCleanCyclesExtraAfterHours'].label="Clean Mixer extra after hour"
            self.fields['mixerCleanCyclesExtraAfterHours'].widget.attrs['title'] = "Give 2 more cleaning cycles after last test hours ago"
            self.fields['reagentRemainingMLAlarmThresholdAutoTester'].label="Reagent Low Threshold AutoTester"
            self.fields['reagentRemainingMLAlarmThresholdAutoTester'].widget.attrs['title'] = "A reagent is considered low when this many usable ML remain at AutoTester"
            self.fields['reagentRemainingMLAlarmThresholdKHTester'].label="Reagent Low Threshold KH Tester"
            self.fields['reagentRemainingMLAlarmThresholdKHTester'].widget.attrs['title'] = "A reagent is considered low when this many usable ML remain at KH Tester"
            self.fields['reagentAlmostEmptyAlarmEnable'].label="Send Reagent Low Alarms"
            self.fields['reagentAlmostEmptyAlarmEnable'].widget.attrs['title'] = "Check if you want AutoTester to notify you when a reagent is low"
            self.fields['sendMeasurementReports'].label="Enable Measurement Reports"
            self.fields['sendMeasurementReports'].widget.attrs['title'] = "Check if you want a notification each time a test is run"
            self.fields['telegramBotToken'].label="Telegram Bot Token"
            self.fields['telegramBotToken'].widget.attrs['title'] = "Set the Telegram Bot Token for sending alarms or reports"
            self.fields['telegramChatID'].label="Telegram Chat ID"
            self.fields['telegramChatID'].widget.attrs['title'] = "Set the Telegram Chat ID for sending alarms or reports"
            self.fields['daysOfResultsToKeep'].label="Days of Historical Results to Keep"
            self.fields['daysOfResultsToKeep'].widget.attrs['title'] = "Enter number of days of old results to keep"
            self.fields['enableConsoleOutput'].label="Enable Console Output"
            self.fields['enableConsoleOutput'].widget.attrs['title'] = "Checking this will cause a verbose stream to be displayed on the SSH program console"
            self.fields['manageDatabases'].label="Manage Databases"
            self.fields['manageDatabases'].widget.attrs['title'] = "Checking this and restarting will give access to the internal databases.  Caution in making changes"

class CalibrationForm(forms.ModelForm):
    class Meta:
        model = CalibrationValues
        exclude=()
#        widgets = {
#            'testToSchedule': Textarea(attrs={'cols': 80, 'rows': 20}),
#        }
    def __init__(self, *args, **kwargs):
        super(CalibrationForm, self).__init__(*args, **kwargs)
        if self.instance.id:
            self.fields['calibrationMLAutotester'].label="Total ML AutoTester"
            self.fields['calibrationMLAutotester'].widget.attrs['title'] = "Total dosed liquid in ML Autotester"
            self.fields['calibrationMLKHSample'].label="Total ML KH Sample Water"
            self.fields['calibrationMLKHSample'].widget.attrs['title'] = "Total dosed liquid in ML KH Sample Water"
            self.fields['calibraitonMLKHReagent'].label="Total ML KH Reagent"
            self.fields['calibraitonMLKHReagent'].widget.attrs['title'] = "Total dosed liquid in ML KH Reagent"

class MeasuredParametersForm(forms.ModelForm):
    class Meta:
        model = MeasuredParameters
        exclude=()
#        widgets = {
#            'testToSchedule': Textarea(attrs={'cols': 80, 'rows': 20}),
#        }
    def __init__(self, *args, **kwargs):
        super(MeasuredParametersForm, self).__init__(*args, **kwargs)
        if self.instance.id:
            self.fields['R'].label="Red"
            self.fields['R'].widget.attrs['title'] = "Red"
            self.fields['G'].label="Green"
            self.fields['G'].widget.attrs['title'] = "Green"
            self.fields['B'].label="Blue"
            self.fields['B'].widget.attrs['title'] = "Blue"
            self.fields['abR'].label="Arbsorption Red"
            self.fields['abR'].widget.attrs['title'] = "Arbsorption Red"
            self.fields['abG'].label="Arbsorption Green"
            self.fields['abG'].widget.attrs['title'] = "Arbsorption Green"
            self.fields['abB'].label="Arbsorption Blue"
            self.fields['abB'].widget.attrs['title'] = "Arbsorption Blue"
            self.fields['labL'].label="labL"
            self.fields['labL'].widget.attrs['title'] = "labL"
            self.fields['labA'].label="labA"
            self.fields['labA'].widget.attrs['title'] = "labA"
            self.fields['labB'].label="labB"
            self.fields['labB'].widget.attrs['title'] = "labB"