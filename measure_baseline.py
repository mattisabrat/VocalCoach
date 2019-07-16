#!/usr/bin/env python3

#Imports
from transitions import Machine
from transitions.extensions.states import add_state_features, Timeout
import time
import numpy as np
import pyaudio
from omxplayer.player import OMXPlayer
from pathlib import Path
import csv
import os.path
from datetime import datetime
import gpiozero
import configparser

#Block an Error Message
import warnings
warnings.simplefilter("ignore", DeprecationWarning) #it doesn't like my using np.fromstring, but its fine
    

#Read in the settings from the config
config = configparser.ConfigParser()
config.read('config.ini')

#Stream Parameters
chans       =  int(config.get('Stream_Parameters', 'channels')) #number channel
samp_rate   =  int(config.get('Stream_Parameters', 'sample_rate')) #44.1kHz sampling rate
chunk       =  int(config.get('Stream_Parameters', 'chunk')) #samples for buffer
dev_index   =  int(config.get('Stream_Parameters', 'device_index')) #device index found by p.get_device_info_by_index(ii)


#Define callback
def callback(in_data, frame_count, time_info, status):    
    chunk_data = np.fromstring(in_data, np.int16) #convert the audio data from a string to an array
    dfft = abs(np.fft.rfft(chunk_data)) #perform fft
    power_rats.append(sum(dfft[1:]) / (dfft[0]+1)) #determine power_ratio

    return (in_data, pyaudio.paContinue) #necessary so the stream doesn't crash


#Define the necessary variables
power_rats=[] #vector of power ratios

#Init pyaudio
p = pyaudio.PyAudio()

#create pyaudio stream
stream = p.open(format             = pyaudio.paInt16, \
                rate               = samp_rate, \
                channels           = chans, \
                input_device_index = dev_index, \
                input              = True, \
                output             = False, \
                frames_per_buffer  = chunk, \
                stream_callback    = callback)

#Clear the console vomit generated by pyaudio
os.system('clear')

#Make the measurement
stream.start_stream()
time.sleep(2) #Keep the current thread active during recording

#Kill the stream and end the session
stream.stop_stream() 
stream.close()
p.terminate()

#Calculate baseline stats
power_rat_mean = np.average(power_rats)
power_rat_std  = np.std(power_rats)
power_rat_90   = np.quantile(power_rats, .9)

print(power_rat_mean)
print(power_rat_std)
print(power_rat_90)

#Write the power_rat_90 value into the config file
config.set('Detection_Parameters', 'power_rat_90', str(power_rat_90))
with open('config.ini', 'w+') as configfile:
    config.write(configfile)
