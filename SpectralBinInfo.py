#!/usr/bin/env/python3

#Imports
import numpy as np
import configparser

#Read values
config = configparser.ConfigParser()
config.read('config.ini')
chunk       =  int(config.get('Stream_Parameters', 'chunk')) 
samp_rate   =  int(config.get('Stream_Parameters', 'sample_rate')) 

def bin_data(chunk, rate):
    period = 1/rate
    freq = np.fft.rfftfreq(n = chunk, d=period)
    n_bins = len(freq)
    freq_spacing = freq[1]-freq[0]
    return([n_bins, freq_spacing])

bins = bin_data(chunk, samp_rate)
print(chunk, 'samples per chunk at ', samp_rate, 'Hz resolve')
print(bins[0], 'bins with centers separated by ', bins[1],'Hz')
