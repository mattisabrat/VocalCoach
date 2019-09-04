#!/usr/bin/env/python3

#--------------------------------------------------------------
#Provides a ~20uL water reward every 2min and flashes the reward LED.
#This is just to esatblish the valence of the reward lixit on the first day of water restriction.
#Also records video.
#--------------------------------------------------------------

#import
import gpiozero
import time
import picamera
import os
import sys
import getopt
import datetime as dt

#quick front end
def usage():
  print ('Usage: '+sys.argv[0]+' -n <Bird_Name>')

Bird_Name = 'NotABird_Blah_Blah_Blah'

#Read in args to get the bird name
try:
    opts, args = getopt.getopt(sys.argv[1:], 'n:h', ['--name', '--help'])
except getopt.GetoptError:
    usage()
    sys.exit(2)
    
for opt, arg in opts:
    if opt in ('-h', '--help'):
        usage()
        sys.exit(2)
    elif opt in ('-n', '--name'):
        Bird_Name = str(arg)
    else:
        usage()
        sys.exit(2)

#Double check the user input a name
if (Bird_Name == 'NotABird_Blah_Blah_Blah'):
    usage()
    sys.exit(2)

#Make an the output directory
if (not os.path.exists(os.getcwd() + '/Data_Logs/'+Bird_Name)):
    os.makedirs(os.getcwd() + '/Data_Logs/'+Bird_Name)

#define the reward pins
reward_solenoid = gpiozero.LED(24)
reward_LED      = gpiozero.LED(23)

#Threaded_Recorder class
class Threaded_Recorder:
    #init
    def __init__(self, resolution, framerate, rec_length, video_path):
        self.camera                     = picamera.PiCamera()
        self.camera.resolution          = resolution
        self.camera.framerate           = framerate
        self.camera.annotate_background = picamera.Color('Black')
        self.camera.annotate_text       = dt.datetime.now().strftime('%H:%M:%S:%f')
        self.rec_length                 = rec_length
        self.video_path                 = video_path
        self.period                     = 1/framerate
        
    #Record
    def record_video(self):
        self.camera.start_recording(self.video_path +'.h264')
        self.start = dt.datetime.now()
        while (dt.datetime.now() - self.start).seconds < (self.rec_length + 5):
            self.camera.annotate_text = dt.datetime.now().strftime('%H:%M:%S:%f')
            self.camera.wait_recording(self.period)
        self.camera.stop_recording()


threaded_rec = Threaded_Recorder(resolution = (640, 480),
                                 framerate  = 20,
                                 rec_length = 1,
                                 video_path = 'Data_Logs/'+Bird_Name+'/'+Bird_Name+'_E')
time.sleep(0.2)
threaded_rec.record_video()
start_time = dt.datetime.now()
while (dt.datetime.now()-start_time).total_seconds() < 10:
    time.sleep(9)
    reward_solenoid.on()
    reward_LED.on()

    time.sleep(0.2)
    reward_solenoid.off()

    time.sleep(0.8)
    
