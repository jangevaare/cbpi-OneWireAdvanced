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
    c_update_interval = Property.Number("Update interval", True, 5.0)
    d_low_filter = Property.Number("Low value filter threshold", True, 0.0)
    e_high_filter = Property.Number("High value filter threshold", True, 100.0)
    f_notify = Property.Select("Notifications", ["True", "False"])
    g_notification_timeout = Property.Number("Notification duration", True, 5000, description="Notification duration in milliseconds")

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
        notify = bool(self.f_notify)
        notification_timeout = float(self.g_notification_timeout)

        # Error checking
        if notification_timeout <= 0.0:
            cbpi.notify("OneWire Error", "Notification timeout must be positive", timeout=None, type="danger")
            raise ValueError("OneWire - Notification timeout must be positive")
        elif update_interval <= 0.0:
            cbpi.notify("OneWire Error", "Update interval must be positive", timeout=None, type="danger")
            raise ValueError("OneWire - Update interval must be positive")
        elif low_filter >= high_filter:
            cbpi.notify("OneWire Error", "Low filter must be < high filter", timeout=None, type="danger")
            raise ValueError("OneWire - Low filter must be < high filter")
        else:
            while self.is_running():
                waketime = time.time() + update_interval
                rawtemp = get_temp(address)
                if rawtemp != None:
                    if self.get_config_parameter("unit", "C") == "C":
                        temp = round(rawtemp + bias, 2)
                    else:
                        temp = round((rawtemp * 9/5) + 32 + bias, 2)
                    if low_filter < temp < high_filter:
                        self.data_received(temp)
                    else:
                        if notify:
                            cbpi.notify("OneWire Warning", "%s reading of %s filtered" % (address, temp), timeout=notification_timeout, type="warning")
                        cbpi.app.logger.info("[%s] %s reading of %s filtered" % (waketime, address, temp))

                # Sleep until update required again
                if waketime <= time.time():
                    if notify:
                        cbpi.notify("OneWire Warning", "Reading of %s could not complete within update interval" % (address), timeout=notification_timeout, type="warning")
                    cbpi.app.logger.info("[%s] reading of %s could not complete within update interval" % (waketime, address))
                else:
                    self.sleep(waketime - time.time())

    @classmethod
    def init_global(self):
        try:
            call(["modprobe", "w1-gpio"])
            call(["modprobe", "w1-therm"])
        except Exception as e:
            pass
