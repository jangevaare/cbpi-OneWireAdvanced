# -*- coding: utf-8 -*-
import os, time, subprocess
from modules import cbpi
from modules.core.hardware import SensorActive
from modules.core.props import Property


def ifelse_celcius(x, y):
    if cbpi.get_config_parameter("unit", "C") == "C":
        return x
    else:
        return y


def get_sensors():
    try:
        arr = []
        for dirname in os.listdir('/sys/bus/w1/devices'):
            if (dirname.startswith("28") or dirname.startswith("10")):
                arr.append(dirname)
        return arr
    except:
        return []


def set_precision(precision, address):
    if not 9 <= precision <= 12:
        raise ValueError("The given sensor precision '{0}' is out of range (9-12)".format(precision))
    exitcode = subprocess.call("echo {0} > /sys/bus/w1/devices/{1}/w1_slave".format(precision, address), shell=True)
    if exitcode != 0:
        raise UserWarning("Failed to change resolution to {0} bit. You might have to be root to change the precision".format(precision))


def get_temp(address):
    attempts = 0
    temp = 9999
    # Bitbang the 1-wire interface.
    try:
        s = subprocess.check_output('cat /sys/bus/w1/devices/%s/w1_slave' % address, shell=True).strip()
        lines = s.split('\n')
        line0 = lines[0].split()
        if line0[-1] == 'YES':  # CRC check was good.
            line1 = lines[1].split()
            temp = float(line1[-1][2:])/1000
    except:
        pass
    return temp


# Property descriptions
bias_description = "Sensor bias may be positive or negative."

alpha_description = "The parameter α determines the relative weighting of temperature readings in an exponential moving average. α must be >0 and <=1. At α=1, all weight is placed on the current reading. T_i = α*t_i + (1-α)*T_i-1)"

precision_description_C = "DS18B20 sensors can be set to provide 9 bit (0.5°C, 93.75ms conversion), 10 bit (0.25°C, 187.5ms conversion), 11 bit (0.125°C, 375 ms conversion), or 12 bit precision (0.0625°C, 750ms conversion)."

precision_description_F = "DS18B20 sensors can be set to provide 9 bit (0.9°F, 93.75ms conversion), 10 bit (0.45°F, 187.5ms conversion), 11 bit (0.225°F, 375 ms conversion), or 12 bit precision (0.1125°F, 750ms conversion)."

low_filter_description = "Values below the low value filter threshold will be ignored. Units automatically selected."

high_filter_description = "Values above the high value filter threshold will be ignored. Units automatically selected."


@cbpi.sensor
class OneWireAdvanced(SensorActive):
    a_address = Property.Select("Address", get_sensors())
    b_bias = Property.Number(ifelse_celcius("Bias (°C)", "Bias (°F)"), True, 0.0, description=bias_description)
    b_alpha = Property.Number("Exponential moving average parameter (α)", True, 1.0, description=alpha_description)
    c_precision = Property.Select("Precision (bits)", [9,10,11,12], description=ifelse_celcius(precision_description_C, precision_description_F))
    c_update_interval = Property.Number("Update interval (ms)", True, 5000)
    d_low_filter = Property.Number(ifelse_celcius("Low value filter threshold (°C)", "Low value filter threshold (°F)"), True, ifelse_celcius(0,32), description = low_filter_description)
    e_high_filter = Property.Number(ifelse_celcius("High value filter threshold (°C)", "High value filter threshold (°F)"), True, ifelse_celcius(100,212), description = high_filter_description)
    f_notify1 = Property.Select("Notify when values filtered?", ["True", "False"])
    f_notify2 = Property.Select("Notify when reading did not complete within update interval?", ["True", "False"])
    g_notification_timeout = Property.Number("Notification duration (ms)", True, 5000, description="Notification duration in milliseconds")

    def get_unit(self):
        return ifelse_celcius("°C", "°F")

    def stop(self):
        pass

    def execute(self):
        address = self.a_address
        bias = float(self.b_bias)
        alpha = float(self.b_alpha)
        precision = int(self.c_precision)
        update_interval = float(self.c_update_interval)/1000.0
        low_filter = float(self.d_low_filter)
        high_filter = float(self.e_high_filter)
        notify1 = bool(self.f_notify1)
        notify2 = bool(self.f_notify2)
        notification_timeout = float(self.g_notification_timeout)

        # Error checking
        if not 0.0 < alpha <= 1.0:
            cbpi.notify("OneWire Error", "α must be >0 and <= 1", timeout=None, type="danger")
            raise ValueError("OneWire - α must be >0 and <= 1")
        elif notification_timeout <= 0.0:
            cbpi.notify("OneWire Error", "Notification timeout must be positive", timeout=None, type="danger")
            raise ValueError("OneWire - Notification timeout must be positive")
        elif update_interval <= 0.0:
            cbpi.notify("OneWire Error", "Update interval must be positive", timeout=None, type="danger")
            raise ValueError("OneWire - Update interval must be positive")
        elif low_filter >= high_filter:
            cbpi.notify("OneWire Error", "Low filter must be < high filter", timeout=None, type="danger")
            raise ValueError("OneWire - Low filter must be < high filter")
        else:
            # Set precision in volatile SRAM
            try:
                set_precision(precision, address)
            except:
                cbpi.notify("OneWire Warning", "Could not change precision of %s, may have insufficient permissions" % address, timeout=None, type="warning")
                cbpi.app.logger.info("[%s] Could not change precision of %s, may have insufficient permissions" % (time.time(), address))

            # Initialize previous value for exponential moving average
            last_temp = None

            # Running loop
            while self.is_running():
                waketime = time.time() + update_interval
                current_temp = get_temp(address)
                if current_temp != None:
                    # A temperature of 85 is a communication error code
                    if current_temp == 85.0:
                        cbpi.notify("OneWire Warning", "Communication error with %s detected" % address, timeout=notification_timeout, type="warning")
                        cbpi.app.logger.info("[%s] Communication error with %s detected" % (waketime, address))
                    # Proceed with valid temperature readings
                    else:
                        # Convert current temp and add bias if necessary
                        if self.get_config_parameter("unit", "C") == "C":
                            current_temp = current_temp + bias
                        else:
                            current_temp = (current_temp * 9/5) + 32 + bias

                        # Check if temp is within filter limits
                        if low_filter < current_temp < high_filter:
                            if last_temp != None:
                                exp_temp = current_temp*alpha + last_temp*(1.0-alpha)
                                self.data_received(round(exp_temp, 3))
                                last_temp = exp_temp
                            else:
                                self.data_received(round(current_temp, 3))
                                last_temp = current_temp
                        else:
                            cbpi.app.logger.info("[%s] %s reading of %s filtered" % (waketime, address, round(current_temp, 3)))
                            if notify1:
                                cbpi.notify("OneWire Warning", "%s reading of %s filtered" % (address, round(current_temp, 3)), timeout=notification_timeout, type="warning")

                # Sleep until update required again
                if waketime <= time.time():
                    cbpi.app.logger.info("[%s] reading of %s could not complete within update interval" % (waketime, address))
                    if notify2:
                        cbpi.notify("OneWire Warning", "Reading of %s could not complete within update interval" % (address), timeout=notification_timeout, type="warning")
                else:
                    self.sleep(waketime - time.time())

    @classmethod
    def init_global(self):
        try:
            call(["modprobe", "w1-gpio"])
            call(["modprobe", "w1-therm"])
        except:
            pass
