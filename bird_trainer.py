#!/usr/bin/env python3

def train_bird(Name):
    #Import necessary modules
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
    
    #Block an Error Message
    import warnings
    warnings.simplefilter("ignore", DeprecationWarning) #it doesn't like my using np.fromstring, but its fine 
    
    #Define a bird statemachine object
    #Create a new machine class (CustomStateMachine) which includes the timeout functionality
    @add_state_features(Timeout)
    class CustomStateMachine(Machine):
        pass

    #Create a class of machines for our birds
    class Bird(CustomStateMachine):

        #Define the structure of the state machine
        def __init__(self, Name):

            #Enumerate States and timed exit conditions
            states = [
                {'name': 'Initial'},  
                {'name': 'Acclimation', 'timeout': 300,  'on_timeout': 'Begin'},
                {'name': 'ITI',         'timeout': 100,  'on_timeout': 'Trial_Start'},
                {'name': 'Trial',       'timeout': 20,   'on_timeout': 'Trial_End',   'on_enter': 'Trial_Toggle', 'on_exit': 'Trial_Toggle'}, 
                {'name': 'DataLog'}
            ]

            #Enumerate Transitions
            transitions = [
                {'trigger': 'Initialize',  'source': 'Initial',        'dest': 'Acclimation'},
                {'trigger': 'Begin',       'source': 'Acclimation',    'dest': 'ITI'},
                {'trigger': 'Trial_Start', 'source': 'ITI',            'dest': 'Trial'},
                {'trigger': 'Trial_End',   'source': 'Trial',          'dest': 'ITI',         'after': 'Track_Performance'},
                {'trigger': 'Song',        'source': 'Trial',          'dest':  None,         'before': 'Reward'},
                {'trigger': 'End',         'source': ['ITI', 'Trial'], 'dest': 'DataLog',     'after': 'Log_Performance'}
            ]

            #Define the initialization of the machine with the above properties
            Machine.__init__(self, states = states, \
                             transitions = transitions, \
                             initial = 'Initial', \
                             ignore_invalid_triggers=True)

            #Initialize the hardware and data recording
            self.Set_Name(Name)
            self.Set_Last_Reward() #Initialize the reward buffer 
            self.Init_GPIO() #Initialeze the solenoid valve
            self.Init_Performance() #Intialize performance tracking
            self.Initialize() #Move into acclimation

        #Define the functions required for reward and external tracking
        #Initialize the solenoid valve as a digital "LED" (binary states)
        def Init_GPIO(self):
            self.reward_solenoid = gpiozero.LED(24)
            self.reward_LED = gpiozero.LED(23)
            self.trial_LED = gpiozero.LED(22)
            self.trial_SmartTint = gpiozero.LED(27)

        def Reward(self): 
            #Deliver the reward
            self.reward_solenoid.on()
            self.reward_LED.on()

            time.sleep(0.2) #length of this sleep determines size of water reward

            self.reward_solenoid.off()
            self.reward_LED.off()

            #Log the reward
            self.trial_data = self.trial_data + 1

        def Set_Last_Reward(self, Reward_Time = 0): #Units are seconds, see usage in the audio callback below
            self.Reward_Time = Reward_Time

        def Trial_Toggle(self): #Chnages the state of the trial LED for external tracking
            self.trial_LED.toggle()
            self.trial_SmartTint.toggle()


        #Define the functions to record performance
        def Set_Name(self, Name):
            self.name = Name

        def Init_Performance(self): #Creates the necessary variables
            self.session_data = [] #Vector of rewards given in trials of a single session. First entry is first trial
            self.trial_data = 0 #Holding variable to count rewards in the current trial

            self.data_path = Path('Data_Logs/' + self.name + '.csv') #build path to the data log file
            self.datetime = str(datetime.now())#Get the date and time the session began

        def Track_Performance(self):
            self.session_data.append(self.trial_data) #Store the last trial's performance
            self.trial_data = 0 #Reset the trial data variable for the next trial

        def Log_Performance(self):
            #Calculate the fraction of trials in which there was at least 1 reward given
            fraction_sung = sum(w>0 for w in self.session_data) / len(self.session_data)

            #Determine if a data_log exists for this animal
            if self.data_path.is_file():
                #Get the number of rows to determine what session # we are on
                with open(str(self.data_path), "rt") as data_log:
                    reader = csv.reader(data_log)
                    session_num = sum(1 for row in reader) #Since the first row is a header, I don't need to add 1

                #Add animal ID, datetime, session #, and fraction of sung trials to the session data
                self.session_data = [self.name, self.datetime, session_num, fraction_sung] + self.session_data

                #Write the session_data into the data log as a new row
                with open(str(self.data_path), "a") as data_log:
                    writer = csv.writer(data_log, lineterminator ='\n')
                    writer.writerow(self.session_data)

            else: #if its the first data point we need to first write in the header and then the data
                #Set session #
                session_num = 1

                #create the header
                header = ['Animal ID', 'Session Datetime', 'Session Number', 'Fraction Sung Trials'] \
                + list(range(1,len(self.session_data)+1))

                #Add animal ID, datetime, session #, and fraction of sung trials to the session data
                self.session_data = [self.name, self.datetime, session_num, fraction_sung] + self.session_data

                #write in the header and the data
                with open(str(self.data_path), "w") as data_log:
                    writer = csv.writer(data_log, lineterminator ='\n')
                    writer.writerow(header)
                    writer.writerow(self.session_data)
                    
 
    #Set up the audiostream
    #Pyaudio stream parameters
    form_1      = pyaudio.paInt16 #16-bit resolution on the mic
    chans       = 1 #1 channel
    samp_rate   = 44100 #44.1kHz sampling rate
    chunk       = 2^13 #2^13 samples for buffer
    record_secs = 3330 #seconds to record, same as desired session length including acclimation
    dev_index   = 2 #device index found by p.get_device_info_by_index(ii)

    #Song detection parameters
    song_window       = 1 #Number of seconds which a song event should occupy
    trigger_threshold = 1.7 #Power ratio threshold
    trigger_fraction  = .5 #Fraction of measurments within song_window that must be above threshold to trigger 
    reward_buffer     = 3 #Reward can't be triggered within this many seconds of a previous reward 
    
    #Define the audio ocallback function
    def callback(in_data, frame_count, time_info, status):    
        chunk_data = np.fromstring(in_data, np.int16) #convert the audio data from a string to an array
        dfft = abs(np.fft.rfft(chunk_data)) #perform fft

        power_rats.append(sum(dfft[1:]) / (dfft[0]+1)) #determine power_ratio
        time_stamps.append(time_info['input_buffer_adc_time']) #add timestamp

        #trim the power_rats and timestamp vectors to only include data from the last song_window
        trim = True
        idx = 0
        while trim:
            if ((time_stamps[-1]-song_window) >= time_stamps[idx]) :
                idx = idx+1
            else:
                del power_rats[0:idx]
                del time_stamps[0:idx]
                trim = False

        #Trigger Condition for Song detection
        #If more than trigger_fraction of chunks within the last song_window have a power ratio >= trigger_threshold
        #AND if its been more than reward_buffer since the last time
        if ((sum(r > trigger_threshold for r in power_rats) / len(power_rats) >= trigger_fraction) and \
            (time_stamps[-1] >= (bird.Reward_Time + reward_buffer))): 

            bird.Song() #Trigger the FSM reward
            bird.Set_Last_Reward(time_stamps[-1]) #Sets the current timestamp as the last reward

        return (in_data, pyaudio.paContinue) #necessary so the stream doesn't crash
    
    #Define the necessary variables
    power_rats=[] #vector of power ratios
    time_stamps=[] #corresponding vector of time stamps
    
    #Init pyaudio
    p = pyaudio.PyAudio()

    #create pyaudio stream
    stream = p.open(format             = form_1, \
                    rate               = samp_rate, \
                    channels           = chans, \
                    input_device_index = dev_index, \
                    input              = True, \
                    output             = False, \
                    frames_per_buffer  = chunk, \
                    stream_callback    = callback)

    #Clear the console vomit generated by pyaudio
    os.system('clear')
    
    #start the pyaudio stream
    bird = Bird(Name)
    stream.start_stream()
    time.sleep(record_secs) #Keep the current thread active during recording
    
    #Kill the stream and end the session
    stream.stop_stream() 
    stream.close()
    p.terminate()
    
    bird.End()


#We need to read the birds name off of the command line
#Import the requirements from getopts
import sys
import getopt

#Give the user some help if they need it
def usage():
  print ('Usage: '+sys.argv[0]+' -n <Bird_Name>')

#Predefine the name variable
Bird_Name = 'NotABird_Blah_Blah_Blah'

#Read in the name with getopt, offer help
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

#Train the bird
train_bird(Bird_Name)

