import mmap, os, sys, time, tty, termios, select
import tomli, argparse, traceback

import xdg
from xdg import xdg_config_home

import influxdb_client
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

from .pysimapi.simapi import types

obj1 = None
obj2 = None

def isData():
    return select.select([sys.stdin], [], [], 0) == ([sys.stdin], [], [])

def get_mapped_object(name):
    if sys.platform == "win32":
        map_name = u"Local\\%s" % name
        if not check_file_is_mapped_file(map_name, 2048):
            raise FileNotFoundError('FileMapping \'%s\' does not exist.'%(map_name))
        _obj = types[name].from_buffer(mmap.mmap(-1, ctypes.sizeof(types[name]), map_name))
    else:

        with open('/dev/shm/%s' % name, 'r+b') as f:
            _obj = types[name].from_buffer(mmap.mmap(f.fileno(), 0))
    return _obj


def initRF2():
    return get_mapped_object("rFactor2SMMP_Telemetry")


def mapRF2(sessionName, lap, prevlap, obj1, client):
 # 3 different measurements
 # Car Info, Session Info, Telemetery

  bucket="Sessions"
  lap = obj1.mVehicles[0].mLapNumber
  car = (
    Point("Car")
    # session name and lap will be tags
    .tag("lap", obj1.mVehicles[0].mLapNumber)
    .tag("session", sessionName)
    .field("overheating", obj1.mVehicles[0].mOverheating)
    .field("fuel", obj1.mVehicles[0].mFuel)
    .field("frontLeftWear", obj1.mVehicles[0].mWheels[0].mWear)
    .field("frontRightWear", obj1.mVehicles[0].mWheels[0].mWear)
    .field("rearLeftWear", obj1.mVehicles[0].mWheels[0].mWear)
    .field("rearRightWear", obj1.mVehicles[0].mWheels[0].mWear)
  )

  telem = (
    Point("Performance")
    # session name and lap will be tags
    .tag("lap", obj1.mVehicles[0].mLapNumber+1)
    .tag("session", sessionName)
    .field("throttle", obj1.mVehicles[0].mUnfilteredThrottle)
    .field("brake", obj1.mVehicles[0].mUnfilteredBrake)
    .field("speed", abs(obj1.mVehicles[0].mLocalVel.z * 3.6))
    .field("rpms", obj1.mVehicles[0].mEngineRPM)
    .field("gear", obj1.mVehicles[0].mGear)
    .field("steering", obj1.mVehicles[0].mUnfilteredSteering)
  )

  write_api = client.write_api(write_options=SYNCHRONOUS)
  write_api.write(bucket=bucket, org="aurorasmirk@mailfence.com", record=telem)

  if (prevlap != lap):
      prevlap=lap
      write_api.write(bucket=bucket, org="aurorasmirk@mailfence.com", record=car)
  return lap, prevlap

def initAC1():
    return get_mapped_object("acpmf_physics")
def initAC2():
    return get_mapped_object("acpmf_graphics")

def mapAC(sessionName, lap, prevlap, obj1, obj2, client):
 # 3 different measurements
 # Car Info, Session Info, Telemetery

  bucket="Sessions"
  point = (
    Point("performance")
    # session name and lap will be tags
    .tag("lap", obj2.completedLaps+1)
    .tag("session", sessionName)
    .field("throttle", obj1.gas)
    .field("brake", obj1.brake)
    .field("fuel", obj1.fuel)
    .field("speed", obj1.speedKmh)
    .field("rpms", obj1.rpms)
    .field("gear", obj1.gear)
    .field("steering", obj1.steerAngle)
  )
  write_api = client.write_api(write_options=SYNCHRONOUS)
  write_api.write(bucket=bucket, org="aurorasmirk@mailfence.com", record=point)
  return lap, prevlap

def main():  # pragma: no cover

    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--sim')
    parser.add_argument('-n', '--name')
    parser.add_argument('-v', dest='verbose', action='store_true')
    args = parser.parse_args()

    if args.sim == "ac":
        print("Using Assetto Corsa")
        obj1 = initAC1()
        obj2 = initAC2()
    else:
        print("Using RFactor2")
        obj1 = initRF2()
    
    configdir=os.path.join(xdg_config_home(),"sim_telem_monitor")
    with open(os.path.join(configdir,"monitor.toml"), mode="rb") as fp:
        config = tomli.load(fp)
    
    token = config["influxdatabase"]["token"]
    org   = config["influxdatabase"]["org"]
    url   = config["influxdatabase"]["url"]
    client = influxdb_client.InfluxDBClient(url=url, token=token, org=org)
    bucket="Sessions"

    sessionName="Session"
    sessionName=args.name

    # Needs to be slightly different on win32
    # https://stackoverflow.com/questions/2408560/non-blocking-console-input
    print("Press q to exit")
    old_settings = termios.tcgetattr(sys.stdin)
    try:
        tty.setcbreak(sys.stdin.fileno())
        lap = 0
        prevlap = 0
        while True:
            
            if args.sim == "ac":
                mapAC(sessionName, lap, prevlap, obj1, obj2, client)
            else:
                mapRF2(sessionName, lap, prevlap, obj1, client)
            
            if isData():
                c = sys.stdin.read(1)
                if c == '\x71':         # x1b is ESC # x71 is q
                    break
            time.sleep(1/4)

    except:
        traceback.print_exc()

    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)


