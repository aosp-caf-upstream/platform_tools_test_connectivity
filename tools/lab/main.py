#!/usr/bin/env python
#
#   Copyright 2017 - The Android Open Source Project
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

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import argparse
import sys

from metrics.adb_hash_metric import AdbHashMetric
from metrics.cpu_metric import CpuMetric
from metrics.disk_metric import DiskMetric
from metrics.name_metric import NameMetric
from metrics.network_metric import NetworkMetric
from metrics.ram_metric import RamMetric
from metrics.uptime_metric import UptimeMetric
from metrics.usb_metric import UsbMetric
from metrics.verify_metric import VerifyMetric
from reporters.logger_reporter import LoggerReporter
from runner import InstantRunner


class RunnerFactory(object):
    _reporter_constructor = {
        'logger': lambda: [LoggerReporter()],
    }

    _metric_constructor = {
        'usb_io': lambda param: [UsbMetric()],
        'disk': lambda param: [DiskMetric()],
        'uptime': lambda param: [UptimeMetric()],
        'verify_devices':
            lambda param: [VerifyMetric(), AdbHashMetric()],
        'ram': lambda param: [RamMetric()],
        'cpu': lambda param: [CpuMetric()],
        'network': lambda param: [NetworkMetric(param)],
        'hostname': lambda param: [NameMetric()],
        'all': lambda param: [DiskMetric(), UptimeMetric(),
                              AdbHashMetric(), RamMetric(), CpuMetric(),
                              NameMetric(), UsbMetric(), NetworkMetric()]
    }

    @classmethod
    def create(cls, arguments):
        """ Creates the Runner Class that will take care of gather metrics
        and determining how to report those metrics.

        Args:
            arguments: The arguments passed in through command line, a dict.

        Returns:
            Returns a Runner that was created by passing in a list of
            metrics and list of reporters.
        """
        arg_dict = arguments
        metrics = []
        reporters = []

        rep_list = arg_dict.pop('reporter')
        if rep_list is not None:
            for rep_type in rep_list:
                reporters += cls._reporter_constructor[rep_type]()
        else:
            # If no reporter specified, default to logger.
            reporters += [LoggerReporter()]

        # Check keys and values to see what metrics to include.
        for key in arg_dict:
            val = arg_dict[key]
            if val is not None:
                metrics += cls._metric_constructor[key](val)

        return InstantRunner(metrics, reporters)


def _argparse():
    parser = argparse.ArgumentParser(
        description='Tool for getting lab health of android testing lab',
        prog='Lab Health')

    parser.add_argument(
        '-v',
        '--version',
        action='version',
        version='%(prog)s v0.1.0',
        help='specify version of program')
    parser.add_argument(
        '-i',
        '--usb-io',
        action='store_true',
        default=None,
        help='display recent USB I/O')
    parser.add_argument(
        '-u',
        '--uptime',
        action='store_true',
        default=None,
        help='display uptime of current lab station')
    parser.add_argument(
        '-d',
        '--disk',
        choices=['size', 'used', 'avail', 'percent'],
        nargs='*',
        help='display the disk space statistics')
    parser.add_argument(
        '-ra',
        '--ram',
        action='store_true',
        default=None,
        help='display the current RAM usage')
    parser.add_argument(
        '-c',
        '--cpu',
        action='count',
        default=None,
        help='display the current CPU usage as percent')
    parser.add_argument(
        '-vd',
        '--verify-devices',
        action='store_true',
        default=None,
        help=('verify all devices connected are in \'device\' mode, '
              'environment variables set properly, '
              'and hash of directory is correct'))
    parser.add_argument(
        '-r',
        '--reporter',
        choices=['logger'],
        nargs='+',
        help='choose the reporting method needed')
    parser.add_argument(
        '-p',
        '--program',
        choices=['python', 'adb', 'fastboot', 'os', 'kernel'],
        nargs='*',
        help='display the versions of chosen programs (default = all)')
    parser.add_argument(
        '-n',
        '--network',
        nargs='*',
        default=None,
        help='retrieve status of network')
    parser.add_argument(
        '-a',
        '--all',
        action='store_true',
        default=None,
        help='Display every metric available')
    parser.add_argument(
        '-hn',
        '--hostname',
        action='store_true',
        default=None,
        help='Display the hostname of the current system')

    return parser


def main():
    parser = _argparse()

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(1)

    r = RunnerFactory().create(vars(parser.parse_args()))
    r.run()


if __name__ == '__main__':
    main()
