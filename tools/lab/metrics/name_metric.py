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

import metric


class NameMetric(metric.Metric):

    COMMAND = 'hostname'
    # Fields for response dictionary
    NAME = 'name'

    def gather_metric(self):
        """Returns the name of system

        Returns:
            A dict with the following fields:
              name: a string representing the system's hostname

        """
        # Run shell command
        result = self._shell.run(self.COMMAND).stdout
        # Example stdout:
        # android1759-test-server-14
        response = {
            self.NAME: result,
        }
        return response