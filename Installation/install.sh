#!/bin/bash

apt update
apt -y install python python-bottle python-rrdtool python-netifaces python-netaddr screen

# More info at: https://bbs.nextthing.co/t/reading-dht11-dht22-am2302-sensors/2383/85

sudo mkdir -p /lib/modules/4.4.13-ntc-mlc/kernel/drivers/iio/humidity/
sudo cp dht11.ko /lib/modules/4.4.13-ntc-mlc/kernel/drivers/iio/humidity/
sudo depmod
