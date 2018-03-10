# -*- coding: utf-8 -*-
import os, time
from modules import cbpi
from modules.core.hardware import SensorActive
from modules.core.props import Property


# Retrieve list of sensor addresses
def get_sensors():
    try:
        arr = []
        for dirname in os.listdir('/sys/bus/w1/devices'):
            if (dirname.startswith("28") or dirname.startswith("10")):
                arr.append(dirname)
        return arr
    except:
        return []


# Get temperature for a sensor with a specific address
def get_temp(address):
    with open('/sys/bus/w1/devices/w1_bus_master1/%s/w1_slave' % address, 'r') as content_file:
        content = content_file.read()
        if (content.split('\n')[0].split(' ')[11] == "YES"):
            return float(content.split("=")[-1]) / 1000


@cbpi.sensor
class OneWireAdvanced(SensorActive):
    a_address = Property.Select("Sensor address", get_sensors())
    b_bias = Property.Number("Sensor bias", True, 0.0)
    c_update_interval = Property.Number("Update interval", True, 2.0)
    d_low_filter = Property.Number("Low value filter threshold", True, 0.0)
    e_high_filter = Property.Number("High value filter threshold", True, 100.0)
    g_alert = Property.Select("Alert when values filtered?", ["True", "False"])

    def get_unit(self):
        return "°C" if self.get_config_parameter("unit", "C") == "C" else "°F"

    def stop(self):
        pass

    def execute(self):
        address = self.a_address
        bias = float(self.b_bias)
        update_interval = float(self.c_update_interval)
        low_filter = float(self.d_low_filter)
        high_filter = float(self.e_high_filter)
        alert = bool(self.g_alert)

        # Error checking
        if update_interval <= 0.0:
            self.notify("OneWire Error", "Update interval must be positive", timeout=None, type="danger")
            raise ValueError("OneWire - Update interval must be positive")
        elif low_filter >= high_filter:
            self.notify("OneWire Error", "Low filter must be < high filter")
            raise ValueError("OneWire - Low filter must be < high filter")
        else:
            while self.is_running():
                waketime = time.time() + update_interval
                rawtemp = get_temp(address)
                if self.get_config_parameter("unit", "C") == "C":
                    temp = round(rawtemp + bias, 2)
                else:
                    temp = round((rawtemp * 9/5) + 32 + bias, 2)
                if rawtemp != None:
                    if low_filter < temp < high_filter:
                        self.data_received(temp)
                    elif alert:
                        self.notify("OneWire Warning", "%s reading of %s filtered" % (address, temp), time=update_interval*5, type="warning")
                        print("[%s] %s reading of %s filtered" % (waketime, address, temp))

                # Sleep until update required again
                if waketime <= time.time() + 0.25:
                    self.notify("OneWire Error", "Update interval is too short", timeout=None, type="danger")
                    raise ValueError("OneWire - Update interval is too short")
                else:
                    self.sleep(waketime - time.time())
