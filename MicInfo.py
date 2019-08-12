#!/usr/bin/env python3

import pyaudio
import os.path
p = pyaudio.PyAudio()
info = p.get_host_api_info_by_index(0)
numdevices = info.get('deviceCount')
os.system('clear')
for i in range(0, numdevices):
        if (p.get_device_info_by_host_api_device_index(0, i).get('maxInputChannels')) > 0:
            print("Input Device Index ", i, ":",
                  "Rate-", p.get_device_info_by_host_api_device_index(0, i).get('defaultSampleRate'),
                  ", Channels-", p.get_device_info_by_host_api_device_index(0, i).get('maxInputChannels'))
