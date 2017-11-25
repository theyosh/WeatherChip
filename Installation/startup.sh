#!/bin/bash

mkdir -p /sys/kernel/config/device-tree/overlays/dht11
cat /home/chip/WeatherChip/Installation/dht11.dtbo > /sys/kernel/config/device-tree/overlays/dht11/dtbo
/home/chip/WeatherChip/Installation/NoIntDebounce

cd /home/chip/WeatherChip
screen -dmS WeatherChip python weather.py
