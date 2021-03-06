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
    import configparser
    
    #Block an Error Message
    import warnings
    warnings.simplefilter("ignore", DeprecationWarning) #it doesn't like my using np.fromstring, but its fine
    
    #Read in the config file
    config = configparser.ConfigParser()
    config.read('config.ini')
    
    #Expiramental parameters
    Acclimation = int(config.get('Expiramental_Parameters', 'acclimation')) #length of acclimation (s)
    ITI = int(config.get('Expiramental_Parameters', 'ITI')) #length of ITI (s)
    Trial = int(config.get('Expiramental_Parameters', 'trial')) #length of Trial (s)
    record_secs =  int(config.get('Expiramental_Parameters', 'total_length')) #length of whole session (s)     

    
    #Stream Parameters
    chans       =  int(config.get('Stream_Parameters', 'channels')) #number channel
    samp_rate   =  int(config.get('Stream_Parameters', 'sample_rate')) #44.1kHz sampling rate
    chunk       =  int(config.get('Stream_Parameters', 'chunk')) #samples for buffer
    dev_index   =  int(config.get('Stream_Parameters', 'device_index')) #device index found by p.get_device_info_by_index(ii)
    
    #Detection Parameters
    song_window       = float(config.get('Detection_Parameters', 'song_window')) #Number of seconds which a song event should occupy
    power_rat_90      = float(config.get('Detection_Parameters', 'power_rat_90')) #Power ratio threshold
    trigger_fraction  = float(config.get('Detection_Parameters', 'trigger_fraction')) #Fraction of measurments within song_window that must be above threshold to trigger 
    reward_buffer     = float(config.get('Detection_Parameters', 'reward_buffer')) #Reward can't be triggered within this many seconds of a previous reward 

    #Define a bird statemachine object
    #Create a new machine class (CustomStateMachine) which includes the timeout functionality
    @add_state_features(Timeout)
    class CustomStateMachine(Machine):
        pass

    #Create a class of machines for our birds
    class Bird(CustomStateMachine):

        #Define the structure of the state machine
        def __init__(self, Name, Acclimation, ITI, Trial):

            #Initialize the hardware and data recording
            self.Set_Name(Name) #Sets the name
            self.Set_Experiment(Acclimation, ITI, Trial) #sets the experimental paradigm
            self.Set_Last_Reward() #Initialize the reward buffer 
            self.Init_GPIO() #Initialize the solenoid valve, LEDs, and smartscreen
            self.Init_Performance() #Intialize performance tracking

            
            #Enumerate States and timed exit conditions
            states = [
                {'name': 'Initial'},  
                {'name': 'Acclimation', 'timeout': self.Acclimation,     'on_timeout': 'Begin'},
                {'name': 'ITI',         'timeout': self.ITI,             'on_timeout': 'Trial_Start'},
                {'name': 'Trial',       'timeout': self.Trial,           'on_timeout': 'Trial_End',   'on_enter': 'Trial_Toggle', 'on_exit': 'Trial_Toggle'}, 
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

            #Lets Start
            self.Set_Name(Name) #Sets the name (again, it has to be twice, I think it needs to get passed into the Machine.__init__, but idk and idc.
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
            time.sleep(0.8)
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

        def Set_Experiment(self, Acclimation, ITI, Trial):
            self.Acclimation = Acclimation
            self.ITI = ITI
            self.Trial = Trial

        def Init_Performance(self): #Creates the necessary variables
            self.session_data = [] #Vector of rewards given in trials of a single session. First entry is first trial
            self.trial_data = 0 #Holding variable to count rewards in the current trial

            self.data_path = Path('Data_Logs/' + self.name + '.csv') #build path to the data log file
            self.datetime = str(datetime.now())#Get the date and time the session began

            #Make sure that Data_Logs/ exists, otherwise make it
            if (not os.path.exists(os.getcwd() + '/Data_Logs/')):
                os.makedirs(os.getcwd() + '/Data_Logs/')

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
                with open(str(self.data_path), "w+") as data_log:
                    writer = csv.writer(data_log, lineterminator ='\n')
                    writer.writerow(header)
                    writer.writerow(self.session_data)

                        
    #Define the audio ocallback function
    def callback(in_data, frame_count, time_info, status):    
        chunk_data = np.fromstring(in_data, np.int16) #convert the audio data from a string to an array
        dfft = abs(np.fft.rfft(chunk_data)) #perform fft

        power_rats.append(sum(dfft[1:]) / (dfft[0]+1)) #determine power_ratio
        #print(power_rats[-1])
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
        #If more than trigger_fraction of chunks within the last song_window have a power ratio >= power_rat_90
        #AND if its been more than reward_buffer since the last time
        if ((sum(r > power_rat_90 for r in power_rats) / len(power_rats) >= trigger_fraction) and \
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
    
    #start the pyaudio stream
    bird = Bird(Name, Acclimation, ITI, Trial)
    time.sleep(2) #allow time for init, otherwise bird not defined first instance of the callback
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

