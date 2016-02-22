#!/usr/bin/env python3.4
#
#   Copyright 2016 - The Android Open Source Project
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

from builtins import str

import time
import traceback

from acts.controllers import android
from acts.controllers.adb import AdbProxy
from acts.controllers.adb import is_port_available
from acts.controllers.adb import get_available_host_port
from acts.controllers.fastboot import FastbootProxy
from acts.controllers.event_dispatcher import EventDispatcher
from acts.logger import LoggerProxy
from acts.signals import ControllerError
from acts.utils import exe_cmd

def create(configs, logger):
    if configs == []:
        ads = get_all_instances()
    elif not configs:
        return []
    elif isinstance(configs[0], str):
        # Configs is a list of serials.
        ads = get_instances(configs, logger)
    else:
        # Configs is a list of dicts.
        ads = get_instances_with_configs(configs, logger)
    connected_ads = list_adb_devices()
    for ad in ads:
        if ad.serial not in connected_ads:
            raise DoesNotExistError(("Android device %s is specified in config"
                                     " but is not attached.") % ad.serial)
        try:
            ad.get_droid()
            ad.ed.start()
        except:
            # This exception is logged here to help with debugging under py2,
            # because "exception raised while processing another exception" is
            # only printed under py3.
            msg = "Failed to start sl4a on %s" % ad.serial
            logger.exception(msg)
            raise ControllerError(msg)
    return ads

def destroy(ads):
    for ad in ads:
        try:
            ad.terminate_all_sessions()
        except:
            pass

class AndroidDeviceError(Exception):
    pass

class DoesNotExistError(AndroidDeviceError):
    """Raised when something that does not exist is referenced.
    """

def _parse_device_list(device_list_str, key):
    """Parses a byte string representing a list of devices. The string is
    generated by calling either adb or fastboot.

    Args:
        device_list_str: Output of adb or fastboot.
        key: The token that signifies a device in device_list_str.

    Returns:
        A list of android device serial numbers.
    """
    clean_lines = str(device_list_str, 'utf-8').strip().split('\n')
    results = []
    for line in clean_lines:
        tokens = line.strip().split('\t')
        if len(tokens) == 2 and tokens[1] == key:
            results.append(tokens[0])
    return results

def list_adb_devices():
    """List all android devices connected to the computer that are detected by
    adb.

    Returns:
        A list of android device serials. Empty if there's none.
    """
    out = AdbProxy().devices()
    return _parse_device_list(out, "device")

def list_fastboot_devices():
    """List all android devices connected to the computer that are in in
    fastboot mode. These are detected by fastboot.

    Returns:
        A list of android device serials. Empty if there's none.
    """
    out = FastbootProxy().devices()
    return _parse_device_list(out, "fastboot")

def get_instances(serials, logger=None):
    """Create AndroidDevice instances from a list of serials.

    Args:
        serials: A list of android device serials.
        logger: A logger to be passed to each instance.

    Returns:
        A list of AndroidDevice objects.
    """
    results = []
    for s in serials:
        results.append(AndroidDevice(s, logger=logger))
    return results

def get_instances_with_configs(configs, logger=None):
    """Create AndroidDevice instances from a list of json configs.

    Each config should have the required key-value pair "serial".

    Args:
        configs: A list of dicts each representing the configuration of one
            android device.
        logger: A logger to be passed to each instance.

    Returns:
        A list of AndroidDevice objects.
    """
    results = []
    for c in configs:
        try:
            serial = c.pop("serial")
        except KeyError:
            raise ControllerError(('Requried value "serial" is missing in '
                'AndroidDevice config %s.') % c)
        ad = AndroidDevice(serial, logger=logger)
        ad.load_config(c)
        results.append(ad)
    return results

def get_all_instances(include_fastboot=False, logger=None):
    """Create AndroidDevice instances for all attached android devices.

    Args:
        include_fastboot: Whether to include devices in bootloader mode or not.
        logger: A logger to be passed to each instance.

    Returns:
        A list of AndroidDevice objects each representing an android device
        attached to the computer.
    """
    if include_fastboot:
        serial_list = list_adb_devices() + list_fastboot_devices()
        return get_instances(serial_list, logger=logger)
    return get_instances(list_adb_devices(), logger=logger)

def filter_devices(ads, func):
    """Finds the AndroidDevice instances from a list that match certain
    conditions.

    Args:
        ads: A list of AndroidDevice instances.
        func: A function that takes an AndroidDevice object and returns True
            if the device satisfies the filter condition.

    Returns:
        A list of AndroidDevice instances that satisfy the filter condition.
    """
    results = []
    for ad in ads:
        if func(ad):
            results.append(ad)
    return results

def get_device(ads, **kwargs):
    """Finds a unique AndroidDevice instance from a list that has specific
    attributes of certain values.

    Example:
        get_device(android_devices, label="foo", phone_number="1234567890")
        get_device(android_devices, model="angler")

    Args:
        ads: A list of AndroidDevice instances.
        kwargs: keyword arguments used to filter AndroidDevice instances.

    Returns:
        The target AndroidDevice instance.

    Raises:
        AndroidDeviceError is raised if none or more than one device is
        matched.
    """
    def _get_device_filter(ad):
        for k, v in kwargs.items():
            if not hasattr(ad, k):
                return False
            elif getattr(ad, k) != v:
                return False
        return True
    filtered = filter_devices(ads, _get_device_filter)
    if not filtered:
        raise AndroidDeviceError(("Could not find a target device that matches"
                                  " condition: %s.") % kwargs)
    elif len(filtered) == 1:
        return filtered[0]
    else:
        serials = [ad.serial for ad in filtered]
        raise AndroidDeviceError("More than one device matched: %s" % serials)

class AndroidDevice:
    """Class representing an android device.

    Each object of this class represents one Android device in ACTS, including
    handles to adb, fastboot, and sl4a clients. In addition to direct adb
    commands, this object also uses adb port forwarding to talk to the Android
    device.

    Attributes:
        serial: A string that's the serial number of the Androi device.
        h_port: An integer that's the port number for adb port forwarding used
            on the computer the Android device is connected
        d_port: An integer  that's the port number used on the Android device
            for adb port forwarding.
        log: A LoggerProxy object used for the class's internal logging.
        adb: An AdbProxy object used for interacting with the device via adb.
        fastboot: A FastbootProxy object used for interacting with the device
            via fastboot.
    """

    def __init__(self, serial="", host_port=None, device_port=8080,
                 logger=None):
        self.serial = serial
        self.h_port = host_port
        self.d_port = device_port
        self.log = LoggerProxy(logger)
        self._droid_sessions = {}
        self._event_dispatchers = {}
        self.adb = AdbProxy(serial)
        self.fastboot = FastbootProxy(serial)
        if not self.is_bootloader:
            self.root_adb()

    def __del__(self):
        if self.h_port:
            self.adb.forward("--remove tcp:%d" % self.h_port)

    @property
    def is_bootloader(self):
        """True if the device is in bootloader mode.
        """
        return self.serial in list_fastboot_devices()

    @property
    def is_adb_root(self):
        """True if adb is running as root for this device.
        """
        return "root" in self.adb.shell("id -u").decode("utf-8")

    @property
    def model(self):
        """The Android code name for the device.
        """
        # If device is in bootloader mode, get mode name from fastboot.
        if self.is_bootloader:
            out = self.fastboot.getvar("product").strip()
            # "out" is never empty because of the "total time" message fastboot
            # writes to stderr.
            lines = out.decode("utf-8").split('\n', 1)
            if lines:
                tokens = lines[0].split(' ')
                if len(tokens) > 1:
                    return tokens[1].lower()
            return None
        out = self.adb.shell('getprop | grep ro.build.product')
        model = out.decode("utf-8").strip().split('[')[-1][:-1].lower()
        if model == "sprout":
            return model
        else:
            out = self.adb.shell('getprop | grep ro.product.name')
            model = out.decode("utf-8").strip().split('[')[-1][:-1].lower()
            return model

    @property
    def droid(self):
        """The first sl4a session initiated on this device. None if there isn't
        one.
        """
        try:
            session_id = sorted(self._droid_sessions)[0]
            return self._droid_sessions[session_id][0]
        except IndexError:
            return None

    @property
    def ed(self):
        """The first event_dispatcher instance created on this device. None if
        there isn't one.
        """
        try:
            session_id = sorted(self._event_dispatchers)[0]
            return self._event_dispatchers[session_id]
        except IndexError:
            return None

    @property
    def droids(self):
        """A list of the active sl4a sessions on this device.

        If multiple connections exist for the same session, only one connection
        is listed.
        """
        keys = sorted(self._droid_sessions)
        results = []
        for k in keys:
            results.append(self._droid_sessions[k][0])
        return results

    @property
    def eds(self):
        """A list of the event_dispatcher objects on this device.

        The indexing of the list matches that of the droids property.
        """
        keys = sorted(self._event_dispatchers)
        results = []
        for k in keys:
            results.append(self._event_dispatchers[k])
        return results

    def load_config(self, config):
        """Add attributes to the AndroidDevice object based on json config.

        Args:
            config: A dictionary representing the configs.

        Raises:
            ControllerError is raised if the config is trying to overwrite an
            existing attribute.
        """
        for k, v in config.items():
            if hasattr(self, k):
                raise ControllerError(("Attempting to set existing attribute "
                    "%s on %s") % (k, self.serial))
            setattr(self, k, v)

    def root_adb(self):
        """Change adb to root mode for this device.
        """
        if not self.is_adb_root:
            self.adb.root()
            self.adb.wait_for_device()
            self.adb.remount()
            self.adb.wait_for_device()

    def get_droid(self, handle_event=True):
        """Create an sl4a connection to the device.

        Return the connection handler 'droid'. By default, another connection
        on the same session is made for EventDispatcher, and the dispatcher is
        returned to the caller as well.
        If sl4a server is not started on the device, try to start it.

        Args:
            handle_event: True if this droid session will need to handle
                events.

        Returns:
            droid: Android object used to communicate with sl4a on the android
                device.
            ed: An optional EventDispatcher to organize events for this droid.

        Examples:
            Don't need event handling:
            >>> ad = AndroidDevice()
            >>> droid = ad.get_droid(False)

            Need event handling:
            >>> ad = AndroidDevice()
            >>> droid, ed = ad.get_droid()
        """
        if not self.h_port or not is_port_available(self.h_port):
            self.h_port = get_available_host_port()
        self.adb.tcp_forward(self.h_port, self.d_port)
        try:
            droid = self.start_new_session()
        except:
            self.adb.start_sl4a()
            droid = self.start_new_session()
        if handle_event:
            ed = self.get_dispatcher(droid)
            return droid, ed
        return droid

    def get_dispatcher(self, droid):
        """Return an EventDispatcher for an sl4a session

        Args:
            droid: Session to create EventDispatcher for.

        Returns:
            ed: An EventDispatcher for specified session.
        """
        ed_key = self.serial + str(droid.uid)
        if ed_key in self._event_dispatchers:
            if self._event_dispatchers[ed_key] is None:
                raise AndroidDeviceError("EventDispatcher Key Empty")
            self.log.debug(("Returning existing key %s for event dispatcher!"
                ) % ed_key)
            return self._event_dispatchers[ed_key]
        event_droid = self.add_new_connection_to_session(droid.uid)
        ed = EventDispatcher(event_droid)
        self._event_dispatchers[ed_key] = ed
        return ed

    def start_new_session(self):
        """Start a new session in sl4a.

        Also caches the droid in a dict with its uid being the key.

        Returns:
            An Android object used to communicate with sl4a on the android
                device.

        Raises:
            SL4AException: Something is wrong with sl4a and it returned an
            existing uid to a new session.
        """
        droid = android.Android(port=self.h_port)
        if droid.uid in self._droid_sessions:
            raise android.SL4AException(("SL4A returned an existing uid for a "
                "new session. Abort."))
        self._droid_sessions[droid.uid] = [droid]
        return droid

    def add_new_connection_to_session(self, session_id):
        """Create a new connection to an existing sl4a session.

        Args:
            session_id: UID of the sl4a session to add connection to.

        Returns:
            An Android object used to communicate with sl4a on the android
                device.

        Raises:
            DoesNotExistError: Raised if the session it's trying to connect to
            does not exist.
        """
        if session_id not in self._droid_sessions:
            raise DoesNotExistError("Session %d doesn't exist." % session_id)
        droid = android.Android(cmd='continue', uid=session_id,
            port=self.h_port)
        return droid

    def terminate_session(self, session_id):
        """Terminate a session in sl4a.

        Send terminate signal to sl4a server; stop dispatcher associated with
        the session. Clear corresponding droids and dispatchers from cache.

        Args:
            session_id: UID of the sl4a session to terminate.
        """
        if self._droid_sessions and (session_id in self._droid_sessions):
            for droid in self._droid_sessions[session_id]:
                droid.closeSl4aSession()
                droid.close()
            del self._droid_sessions[session_id]
        ed_key = self.serial + str(session_id)
        if ed_key in self._event_dispatchers:
            self._event_dispatchers[ed_key].clean_up()
            del self._event_dispatchers[ed_key]

    def terminate_all_sessions(self):
        """Terminate all sl4a sessions on the AndroidDevice instance.

        Terminate all sessions and clear caches.
        """
        if self._droid_sessions:
            session_ids = list(self._droid_sessions.keys())
            for session_id in session_ids:
                try:
                    self.terminate_session(session_id)
                except:
                    msg = "Failed to terminate session %d." % session_id
                    self.log.exception(msg)
                    self.log.error(traceback.format_exc())
            if self.h_port:
                self.adb.forward("--remove tcp:%d" % self.h_port)
                self.h_port = None

    def run_iperf_client(self, server_host, extra_args=""):
        """Start iperf client on the device.

        Return status as true if iperf client start successfully.
        And data flow information as results.

        Args:
            server_host: Address of the iperf server.
            extra_args: A string representing extra arguments for iperf client,
                e.g. "-i 1 -t 30".

        Returns:
            status: true if iperf client start successfully.
            results: results have data flow information
        """
        out = self.adb.shell("iperf3 -c {} {}".format(server_host, extra_args))
        clean_out = str(out,'utf-8').strip().split('\n')
        if "error" in clean_out[0].lower():
            return False, clean_out
        return True, clean_out

    def wait_for_boot_completion(self):
        """Waits for the device to boot up.

        Returns:
            True if the device successfully finished booting, False otherwise.
        """
        timeout = time.time() + 60*15 # wait for 15 minutes
        while True:
            out = self.adb.shell("getprop sys.boot_completed")
            completed = out.decode('utf-8').strip()
            if completed == '1':
                return True
            if time.time() > timeout:
                return False
            time.sleep(5)

    def reboot(self):
        """Reboots the device.

        Terminate all sl4a sessions, reboot the device, wait for device to
        complete booting, and restart an sl4a session.

        This is a blocking method.

        This is probably going to print some error messages in console. Only
        use if there's no other option.

        Example:
            droid, ed = ad.reboot()

        Returns:
            An sl4a session with an event_dispatcher.

        Raises:
            AndroidDeviceError is raised if waiting for completion timed
            out.
        """
        if self.is_bootloader:
            self.fastboot.reboot()
            return
        self.terminate_all_sessions()
        self.adb.reboot()
        time.sleep(5)
        if not self.wait_for_boot_completion():
            raise AndroidDeviceError("Reboot timed out on %s." % self.serial)
        self.root_adb()
        droid, ed = self.get_droid()
        ed.start()
        return droid, ed
