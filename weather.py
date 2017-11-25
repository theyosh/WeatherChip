# -*- coding: utf-8 -*-

'''
See Installation directory for installation dependencies

https://docs.getchip.com/chip.html#how-you-see-gpio
https://bbs.nextthing.co/t/reading-dht11-dht22-am2302-sensors/2383/78

'''

from bottle import Bottle, route, run, static_file, response

from threading import Thread
import subprocess
import os
import time
import rrdtool
import datetime
import time
import ConfigParser
import uuid

import netifaces
import netaddr
import socket
import urllib2
import multiprocessing

import logging
logger = logging.getLogger(__name__)

#from gevent import monkey, sleep
#monkey.patch_all()


def check_device(ipnumber):
  try:
    req = urllib2.Request('http://' + ipnumber + ':8080/api/info')
    response = urllib2.urlopen(req)
    return ipnumber

  except Exception, err:
    pass

  return None

class CHIPWeatherStationUtils():

  @staticmethod
  def to_fahrenheit(value):
    return float(value) * 9.0 / 5.0 + 32.0

  @staticmethod
  def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        return False

  @staticmethod
  def get_ip_number():
    for interface in netifaces.interfaces():
      if interface in ['lo','sit']:
        continue

      networkdata = netifaces.ifaddresses(interface)
      if netifaces.AF_INET in networkdata:
        for ip in networkdata[netifaces.AF_INET]:
          if 'addr' in ip and 'netmask' in ip and not ip['addr'].startswith('169'):
            return ip['addr']

    return False

  @staticmethod
  def get_network_ip_numbers():
    data = []
    for interface in netifaces.interfaces():
      if interface in ['lo','sit']:
        continue

      networkdata = netifaces.ifaddresses(interface)
      if netifaces.AF_INET in networkdata:
        for ip in networkdata[netifaces.AF_INET]:
          if 'addr' in ip and 'netmask' in ip and not ip['addr'].startswith('169'):
            try:
              iprange = netaddr.IPNetwork(ip['addr'] + '/' + ip['netmask'])
              for ipnumber in iprange.iter_hosts():
                data.append(str(ipnumber))
            except Exception, err:
              #print err
              pass

    return data

class CHIPWeatherStationConfig():

  def __init__(self):
    self.__defaults_file = 'defaults.cfg'
    self.__config_file = 'settings.cfg'

    self.__config = ConfigParser.SafeConfigParser()
    # Read defaults config file
    self.__config.readfp(open(self.__defaults_file))
    # Read new version number

    version = self.__get_config('system')['version']
    # Read custom config file
    self.__config.read(self.__config_file)
    # Update version number
    self.__config.set('system', 'version', str(version))

  def __save_config(self):
    '''Write terrariumPI config to settings.cfg file'''
    with open(self.__config_file, 'wb') as configfile:
      self.__config.write(configfile)

    return True

  def __get_config(self,section):
    '''Get terrariumPI config based on section. Return empty dict when not exists
    Keyword arguments:
    section -- section to read from the config'''

    config = {}
    if not self.__config.has_section(section):
      return config

    for config_part in self.__config.items(section):
      config[config_part[0]] = config_part[1]

    return config

  def get_version(self):
    return self.__get_config('system')['version']

  def get_uuid(self):
    sensorid = None
    if 'sensorid' in self.__get_config('system'):
      sensorid = self.__get_config('system')['sensorid']
    else:

      sensorid = str(uuid.uuid4())
      self.__config.set('system', 'sensorid', str(sensorid))
      self.__save_config()

    return sensorid

  def get_name(self):
    return self.__get_config('system')['name']

  def get_led_pin(self):
    return int(self.__get_config('system')['gpio_led'])

  def get_host_name(self):
    return self.__get_config('system')['hostname']

  def get_port_number(self):
    return self.__get_config('system')['portnumber']


class CHIPWeatherStationLEDIndicator():

  def __init__(self, pin):
    self.__active = False
    self.__base_pin = None
    self.__scan_pin_base()

    if self.__base_pin is not None:
      self.pin = self.__base_pin + pin
      self.__init_gpio()
      self.off()
    else:
      logger.error('GPIO is not available!')
      print 'ERROR, no GPIO available!'

  def __scan_pin_base(self):
    self.__base_pin =  subprocess.Popen('grep -l pcf8574a /sys/class/gpio/*/*label | grep -o "[0-9]*"',
                                      shell=True,
                                      stdout=subprocess.PIPE).communicate()[0].strip()

    if CHIPWeatherStationUtils.is_number(self.__base_pin):
      self.__base_pin = int(self.__base_pin)

  def __init_gpio(self):
    # Open GPIO pin
    if os.path.isfile('/sys/class/gpio/gpio' + str(self.pin) + '/value'):
      self.close()

    subprocess.Popen('echo ' + str(self.pin) + ' > /sys/class/gpio/export',shell=True,stdout=subprocess.PIPE)
    # Set direction to OUT going
    subprocess.Popen('echo out > /sys/class/gpio/gpio' + str(self.pin) + '/direction',shell=True,stdout=subprocess.PIPE)
    # Force output closed by default
    subprocess.Popen('echo 1 > /sys/class/gpio/gpio' + str(self.pin) + '/active_low',shell=True,stdout=subprocess.PIPE)

    self.__active = True

  def on(self):
    if self.__active:
      subprocess.Popen('echo 1 > /sys/class/gpio/gpio' + str(self.pin) + '/value',shell=True,stdout=subprocess.PIPE)

  def off(self):
    if self.__active:
      subprocess.Popen('echo 0 > /sys/class/gpio/gpio' + str(self.pin) + '/value',shell=True,stdout=subprocess.PIPE)

  def close(self):
    subprocess.Popen('echo ' + str(self.pin) + ' > /sys/class/gpio/unexport',shell=True,stdout=subprocess.PIPE)

class CHIPWeatherStationCPUSensor():

  def __init__(self):
    self.__cpu_temp = 0.0
    self.__last_update = 0.0
    self.__update_time_out = 60.0
    self.__update()

  def __update(self):
    now = time.time()
    if now - self.__last_update > self.__update_time_out:
      cpu_temp = subprocess.Popen('/usr/sbin/axp209 --temperature',
                                   shell=True,
                                   stdout=subprocess.PIPE).communicate()[0].strip()

      if 'oC' in cpu_temp:
        self.__cpu_temp = float(cpu_temp.replace('oC','').strip())
        self.__last_update = now

  def get_temperature(self):
    self.__update()
    return self.__cpu_temp

class CHIPWeatherStationSensor():

  def __init__(self):
    self.__last_temp_update = 0.0
    self.__last_hum_update = 0.0
    self.__update_time_out = 60.0

    self.__temperature = 0.0
    self.__humidity = 0.0
    self.__sensor_path = None
    self.__scan_sensor()
    self.__update()

  def __scan_sensor(self):
    self.__sensor_path = subprocess.Popen('grep -l humidity_sensor /sys/bus/iio/devices/iio:device*/name',
                                         shell=True,
                                         stdout=subprocess.PIPE).communicate()[0].strip().replace('/name','')

    if self.__sensor_path == '':
      self.__sensor_path = None

  def __update(self):
    now = time.time()
    if self.__sensor_path is None:
      return False

    if now - self.__last_hum_update > self.__update_time_out:
      for attempt in xrange(0,3):
        try:
          if os.path.isfile(self.__sensor_path + '/in_humidityrelative_input'):
            with open(self.__sensor_path + '/in_humidityrelative_input') as sensor:
              self.__humidity = sensor.read()

            self.__humidity = int(self.__humidity.strip())
            self.__last_hum_update = now
            break
        except IOError, err:
          pass

        time.sleep(1)

    if now - self.__last_temp_update > self.__update_time_out:
      for attempt in xrange(0,3):
        try:
          if os.path.isfile(self.__sensor_path + '/in_temp_input'):
            with open(self.__sensor_path + '/in_temp_input') as sensor:
              self.__temperature = sensor.read()

            self.__temperature = int(self.__temperature.strip())
            self.__last_temp_update = now
            break
        except IOError, err:
          pass

        time.sleep(1)

  def get_temperature(self):
    self.__update()
    return float(self.__temperature) / 1000

  def get_humidity(self):
    self.__update()
    return float(self.__humidity) / 1000

class CHIPWeatherStationDatabase():

  def __init__(self,config):
    self.__config = config
    self.__data_file = 'data.rrd'
    if not os.path.isfile(self.__data_file):
      self.__create_rrd_database()

  def __create_rrd_database(self):
    rrdtool.create( self.__data_file,
                    '--start', 'N',
                    '--step', '60',
                    'DS:cputemp:GAUGE:600:U:U',
                    'DS:temp:GAUGE:600:U:U',
                    'DS:humidity:GAUGE:600:U:U',
                    'RRA:AVERAGE:0.5:1:' + str( 60 * 24 ),
                    'RRA:MIN:0.5:1:' + str( 60 * 24 ),
                    'RRA:MAX:0.5:1:' + str( 60 * 24 ),
                    'RRA:AVERAGE:0.5:60:168',
                    'RRA:MIN:0.5:60:168',
                    'RRA:MAX:0.5:60:168',
                    'RRA:AVERAGE:0.5:' + str( 60 * 24 ) + ':365',
                    'RRA:MIN:0.5:' + str( 60 * 24 ) + ':365',
                    'RRA:MAX:0.5:' + str( 60 * 24 ) + ':365')

  def update(self, cputemp, temp, humidity):
    try:
      ret = rrdtool.update(self.__data_file, 'N:%s:%s:%s' % (cputemp,
                                                             temp,
                                                             humidity));
    except Exception, err:
      pass


  def create_graphs(self):
    for sched in ['daily' , 'weekly', 'monthly']:
      if sched == 'weekly':
        period = 'w'
      elif sched == 'daily':
        period = 'd'
      elif sched == 'monthly':
        period = 'm'

      ret = rrdtool.graph('web/%s.png' %(sched),

                          '--slope-mode',
                          '--start',
                          '-1%s' %(period),
                          '--title=CHIP Weather Station %s graph' % sched,
                          '--vertical-label=Measurement',
                          '--watermark=Dongle ID %s, software version %s, last update %s' % (self.__config.get_uuid(),
                                                                                             self.__config.get_version(),
                                                                                             datetime.datetime.now().strftime('%d-%m-%Y %H:%M:%S')),
                          '-w 500',
                          '-h 150',
                          '-A',

                          '--border=0',
                          '--color=BACK#000000',
                          '--color=CANVAS#FFFFFF20',
                          '--color=GRID#FFFFFF20',
                          '--color=MGRID#adadad',
                          '--color=FONT#FFFFFF',
                          '--color=FRAME#FFFFFF20',
                          '--color=ARROW#FFFFFF',

                          'COMMENT:' + '{:<30}'.format(''),
                          'COMMENT:' + '{:<10}'.format('Current'),
                          'COMMENT:' + '{:<10}'.format('Maximum'),
                          'COMMENT:' + '{:<10}'.format('Average'),
                          'COMMENT:Minimum\l',

                          'DEF:Humidity=' + self.__data_file + ':humidity:AVERAGE',
                          'AREA:Humidity#0000FF60:' + '{:<28}'.format('Humidity in %'),
                          'LINE2:Humidity#0000FF',
                          'GPRINT:Humidity:LAST:%6.2lf%%' +  '{:<3}'.format(''),
                          'GPRINT:Humidity:MAX:%6.2lf%%' +  '{:<3}'.format(''),
                          'GPRINT:Humidity:AVERAGE:%6.2lf%%' +  '{:<3}'.format(''),
                          'GPRINT:Humidity:MIN:%6.2lf%%\l',

                          'DEF:Temperature=' + self.__data_file + ':temp:AVERAGE',
                          'LINE2:Temperature#00FF0080:' + '{:<28}'.format('Temperature in C'),
                          'GPRINT:Temperature:LAST:%6.2lfC' +  '{:<3}'.format(''),
                          'GPRINT:Temperature:MAX:%6.2lfC' +  '{:<3}'.format(''),
                          'GPRINT:Temperature:AVERAGE:%6.2lfC' +  '{:<3}'.format(''),
                          'GPRINT:Temperature:MIN:%6.2lfC\l',

                          'DEF:CPUTemperature=' + self.__data_file + ':cputemp:AVERAGE',
                          'LINE2:CPUTemperature#FF000080:' + '{:<28}'.format('CPU Temperature in C'),
                          'GPRINT:CPUTemperature:LAST:%6.2lfC' +  '{:<3}'.format(''),
                          'GPRINT:CPUTemperature:MAX:%6.2lfC' +  '{:<3}'.format(''),
                          'GPRINT:CPUTemperature:AVERAGE:%6.2lfC' +  '{:<3}'.format(''),
                          'GPRINT:CPUTemperature:MIN:%6.2lfC\l'
                          )

class CHIPWeatherStationEngine():

  def __init__(self):
    self.__config = CHIPWeatherStationConfig()
    self.__database = CHIPWeatherStationDatabase(self.__config)
    self.__temp_hum_sensor = CHIPWeatherStationSensor()
    self.__cpu_sensor = CHIPWeatherStationCPUSensor()
    self.__status_led = CHIPWeatherStationLEDIndicator(self.__config.get_led_pin())

    self.__ip = CHIPWeatherStationUtils.get_ip_number()

    self.__engine = Thread(target = self.__engine_loop,)
    self.__engine.daemon = True
    self.__engine.start()

    self.__sensor_scan_progress = None

#    self.scan_sensors()

  def __engine_loop(self):
    while True:
      self.__status_led.on()
      self.__database.update(self.__cpu_sensor.get_temperature(),
                           self.__temp_hum_sensor.get_temperature(),
                           self.__temp_hum_sensor.get_humidity())
      self.__database.create_graphs()
      self.__status_led.off()
      print 'Done updating. CPU: %f, Temp: %f, Humidity: %f. Scan process %f%%. Next update in 30 seconds' % (self.__cpu_sensor.get_temperature(),
                                                                                            self.__temp_hum_sensor.get_temperature(),
                                                                                            self.__temp_hum_sensor.get_humidity(),
                                                                                            self.get_scan_status())
      time.sleep(30)

  def __scan_sensors(self):
    iplist = CHIPWeatherStationUtils.get_network_ip_numbers()
    counter = 0.0
    total = float(len(iplist))

    self.__sensor_scan_progress = 0.0
    print 'Start sensor scanning (%s) ...' % total
    pool = multiprocessing.Pool(10)
    for device in pool.imap_unordered(check_device, iplist):
      counter += 1.0
      self.__sensor_scan_progress = (counter / total ) * 100
      if device is not None:
        print device

    self.__sensor_scan_progress = None

  def scan_sensors(self):
    if not self.is_scanning():
      timeout = 3
      socket.setdefaulttimeout(timeout)
      Thread(target=self.__scan_sensors).start()

  def get_scan_status(self):
    return self.__sensor_scan_progress if self.__sensor_scan_progress is not None else -1

  def get_uuid(self):
    return self.__config.get_uuid()

  def get_version(self):
    return self.__config.get_version()

  def get_name(self):
    return self.__config.get_name()

  def get_ip_number(self):
    return self.__ip

  def get_temperature(self):
    return self.__temp_hum_sensor.get_temperature()

  def get_humidity(self):
    return self.__temp_hum_sensor.get_humidity()

  def is_scanning(self):
    return self.get_scan_status() >= 0.0;

  def cleanup(self):
    print 'Cleanup....'
    self.__status_led.off()
    self.__status_led.close()

class CHIPWeatherStationWebServer(Bottle):

  def __init__(self, host = '::', port = 8080):
    self.__engine = CHIPWeatherStationEngine()
    self.__host = host
    self.__port = port
    self.__set_routes()

  def __api_call(self,url):
    if 'info' == url:
      return {'uuid' : self.__engine.get_uuid(),
              'name' : self.__engine.get_name(),
              'ip': self.__engine.get_ip_number(),
              'scanning' : self.__engine.is_scanning(),
              'uptime': 0,
              'version' : self.__engine.get_version()}

    elif 'temperature' == url:
      return {'uuid' : self.__engine.get_uuid(),
              'value' : self.__engine.get_temperature()}

    elif 'humidity' == url:
      return {'uuid' : self.__engine.get_uuid(),
              'value' : self.__engine.get_humidity()}


  def __set_routes(self):
    @route('/')
    def index():
      return '<meta http-equiv="refresh" content="0;index.html"/>'

    @route('/api/<url:path>')
    def callback(url):
      response.set_header('Access-Control-Allow-Origin', '*')
      return self.__api_call(url)

    @route('/<path:re:.*>')
    def callback(path):
      return static_file(path,root='web')

  def cleanup(self):
    self.__engine.cleanup()

  def start_server(self):
    run(host=self.__host,
        port=self.__port,
        debug=True,
        reloader=False,
        quiet=False)

if __name__  == "__main__":
  CHIPWeatherStation = CHIPWeatherStationWebServer()
  try:
    CHIPWeatherStation.start_server()
  except KeyboardInterrupt:
    print 'KILL KILL KILL'
  finally:
    CHIPWeatherStation.cleanup()
