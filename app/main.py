from typing import List, Optional
import requests

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response

from pydantic import BaseModel

from midiutil import MIDIFile
from pydub import AudioSegment
import os
import subprocess

from io import BytesIO
import base64

app = FastAPI()

class HeadSoupMusicRequest(BaseModel):
    activityTypeId: str
    timings: List[float]
    tags: Optional[List[str]]
    uid: str
    activityId: str

@app.get("/")
def read_root():
    return "odserve is happy to serve you"

@app.post("/music")
async def handle_music_req(request: HeadSoupMusicRequest):
    subprocess.run("rm *.wav; rm *.mp3; rm *.mid", shell=True)
    try:
        # url = "http://odcore:8080/midijson"
        url = "http://localhost:8080/midijson"

        print("forwarding fuegodata", request, "to", url)
        response = requests.post(url, json=request.model_dump())
        if response.status_code == 200:
            print("POST request successful!")
        else:
            print("POST request failed with status code:", response.status_code)

        data = response.json()
        response_timings = data['timings']
        timings_list = [float(timing) for timing in response_timings]

        # create midi file from response
        midiJSONDataArray = data['midiJSONData']
        write_midi_file(midiJSONDataArray)
        # create audio file from MIDI file
        render_to_audio()
        # encode audio for response
        audio_file = "master.mp3"
        audio = AudioSegment.from_mp3(audio_file)
        audio_data = BytesIO()
        audio.export(audio_data, format="mp3")
        audio_data.seek(0)
        audio_base64 = base64.b64encode(audio_data.getvalue()).decode()

        response_data = {
            "audio": audio_base64,
            "durations": timings_list,
        }

        return response_data
    
    except Exception as e:
        return {"error": str(e)}, 500

def write_midi_file(midiJSONDataArray):
    for deviceIdx, deviceData in enumerate(midiJSONDataArray):
        print("DEVICE ENUMERATION")
        mf = MIDIFile(16)

        programChangeData = deviceData['programChangeData']
        midiNoteEvents = deviceData['midiNoteEvents']
        print("midiNoteEvents", len(midiNoteEvents))
        ccData = deviceData['ccData']
        tempoData = deviceData['tempoData']

        if programChangeData:
            for programChange in programChangeData:
                channelNumber = programChange['channelNumber'] 
                bankNumber = programChange['bankNumber']
                patchNumber = programChange['patchNumber']
                clockPosition = programChange['clockPosition']
                patchName = programChange['patchName']
                print(clockPosition, channelNumber, bankNumber, patchNumber, patchName)

                midiChannel = channelNumber % 16
                midiTime = clockPosition / 24

                controllerNumber = 0   # bank select controller number
                trackNumber = midiChannel
                mf.addControllerEvent(trackNumber, midiChannel, midiTime, controllerNumber, bankNumber)
                mf.addProgramChange(trackNumber, midiChannel, midiTime, patchNumber)

        if midiNoteEvents:
            for midiNotEvent in midiNoteEvents:
                noteNumber = midiNotEvent['noteNumber']
                noteLength = midiNotEvent['noteLength']
                noteVelocity = midiNotEvent['noteVelocity']
                channelNumber = midiNotEvent['channelNumber']
                clockPosition = midiNotEvent['clockPosition']
                # print("noteEvent", noteNumber)whats

                midiChannel = channelNumber % 16
                midiNoteLength = noteLength / 24 #PPQ from aa-core
                midiTime = clockPosition / 24

                trackNumber = midiChannel
                # print("note", trackNumber, midiChannel, noteNumber, midiTime, midiNoteLength, noteVelocity)

                mf.addNote(trackNumber, midiChannel, noteNumber, midiTime, midiNoteLength, noteVelocity)

        if ccData:
            for cc in ccData:
                clockPosition = cc['clockPosition']
                channelNumber = cc['channelNumber']
                ccNumber = cc['ccNumber']
                ccValue = cc['ccValue']

                midiChannel = channelNumber % 16
                midiTime = clockPosition / 24

                trackNumber = midiChannel
                mf.addControllerEvent(trackNumber, midiChannel, midiTime, ccNumber, ccValue)

        if tempoData:
            for tempo in tempoData:
                clockPosition = tempo['clockPosition']
                tempoBPM = tempo['tempoBPM']
                print("tempo", clockPosition, tempoBPM)

                midiTime = clockPosition / 24

                track = 0
                mf.addTempo(track, 0, tempoBPM)

        filename = "midi-output-{}.mid".format(deviceIdx)
        # print("writing", filename)
        with open(filename, 'wb') as outf: 
            mf.writeFile(outf)

def render_to_audio():
    fluidCmdTemplate = "fluidsynth ../FluidR3_GM.sf2 {} --fast-render={}"

    #homebrew
    print("USING NORMALIZE (macOS Homebrew)")
    normalizeCmdTemplate = "normalize {}"
    #app-get
    # print("USING NORMALIZE-AUDIO (linux app-get)")
    # normalizeCmdTemplate = "normalize-audio {}"

    directory = "."

    files = os.listdir()
    for file in files:
        if file.endswith(".mid"):
            input_file = os.path.join(directory, file)
            rendered_file = os.path.join(directory, f"{os.path.splitext(file)[0]}_rendered.wav")

            fluid_command = fluidCmdTemplate.format(input_file, rendered_file)
            subprocess.run(fluid_command, shell=True)

            normalize_command = normalizeCmdTemplate.format(rendered_file)
            subprocess.run(normalize_command, shell=True)

    files = os.listdir()
    audiofiles = list(filter(lambda f: f.endswith(".wav"), files))
    flaggedlist = list(map(lambda s: "-i " + s, audiofiles))
    count = len(flaggedlist)
    flaggedstring = ' '.join(flaggedlist)
    mix_command = "ffmpeg " + flaggedstring + f" -filter_complex '[0:a][1:a]amix=inputs={count}:duration=first, equalizer=f=100:width_type=h:width=50:g=10, compand=attacks=0:points=-80/-900|-45/-15|0/-3|20/-3:gain=5' master.mp3 -loglevel error"
    subprocess.run(mix_command, shell=True)