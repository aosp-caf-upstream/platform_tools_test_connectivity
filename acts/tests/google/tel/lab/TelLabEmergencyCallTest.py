#/usr/bin/env python3.4
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
"""
Sanity tests for voice tests in telephony
"""
import time

from acts.controllers.anritsu_lib._anritsu_utils import AnritsuError
from acts.controllers.anritsu_lib.md8475a import CsfbType
from acts.controllers.anritsu_lib.md8475a import MD8475A
from acts.controllers.anritsu_lib.md8475a import VirtualPhoneAutoAnswer
from acts.controllers.anritsu_lib.md8475a import VirtualPhoneStatus
from acts.test_utils.tel.anritsu_utils import WAIT_TIME_ANRITSU_REG_AND_CALL
from acts.test_utils.tel.anritsu_utils import call_mo_setup_teardown
from acts.test_utils.tel.anritsu_utils import ims_mo_cs_teardown
from acts.test_utils.tel.anritsu_utils import call_mt_setup_teardown
from acts.test_utils.tel.anritsu_utils import set_system_model_1x
from acts.test_utils.tel.anritsu_utils import set_system_model_1x_evdo
from acts.test_utils.tel.anritsu_utils import set_system_model_gsm
from acts.test_utils.tel.anritsu_utils import set_system_model_lte_1x
from acts.test_utils.tel.anritsu_utils import set_system_model_lte_wcdma
from acts.test_utils.tel.anritsu_utils import set_system_model_wcdma
from acts.test_utils.tel.tel_defines import CALL_TEARDOWN_PHONE
from acts.test_utils.tel.tel_defines import DEFAULT_EMERGENCY_CALL_NUMBER
from acts.test_utils.tel.tel_defines import EMERGENCY_CALL_NUMBERS
from acts.test_utils.tel.tel_defines import RAT_FAMILY_CDMA2000
from acts.test_utils.tel.tel_defines import RAT_FAMILY_GSM
from acts.test_utils.tel.tel_defines import RAT_FAMILY_LTE
from acts.test_utils.tel.tel_defines import RAT_FAMILY_UMTS
from acts.test_utils.tel.tel_defines import RAT_1XRTT
from acts.test_utils.tel.tel_defines import NETWORK_MODE_CDMA
from acts.test_utils.tel.tel_defines import NETWORK_MODE_GSM_ONLY
from acts.test_utils.tel.tel_defines import NETWORK_MODE_GSM_UMTS
from acts.test_utils.tel.tel_defines import NETWORK_MODE_LTE_CDMA_EVDO
from acts.test_utils.tel.tel_defines import NETWORK_MODE_LTE_CDMA_EVDO_GSM_WCDMA
from acts.test_utils.tel.tel_defines import NETWORK_MODE_LTE_GSM_WCDMA
from acts.test_utils.tel.tel_defines import WAIT_TIME_IN_CALL
from acts.test_utils.tel.tel_defines import WAIT_TIME_IN_CALL_FOR_IMS
from acts.test_utils.tel.tel_test_utils import ensure_network_rat
from acts.test_utils.tel.tel_test_utils import ensure_phones_idle
from acts.test_utils.tel.tel_test_utils import toggle_airplane_mode
from acts.test_utils.tel.tel_test_utils import toggle_volte
from acts.test_utils.tel.tel_voice_utils import phone_idle_volte
from acts.test_utils.tel.TelephonyBaseTest import TelephonyBaseTest


class TelLabEmergencyCallTest(TelephonyBaseTest):

    # Used for all RATS other than LTE+VoLTE
    CELL_PARAM_FILE = 'C:\\MX847570\\CellParam\\ACTS\\2cell_param.wnscp'
    SIM_PARAM_FILE = 'C:\\MX847570\\SimParam\\ACTS\\2cell_param.wnssp'

    # Used for VoLTE Tests
    CELL_PARAM_FILE_FOR_VOLTE = \
        'C:\\MX847570\\CellParam\\ACTS\\LTE_VOLTE_CELL_PARAMETER.wnscp'
    SIM_PARAM_FILE_FOR_VOLTE = \
        'C:\\MX847570\\SimParam\\ACTS\\LTE_VOLTE_SIM_PARAMETER.wnssp'

    def __init__(self, controllers):
        TelephonyBaseTest.__init__(self, controllers)
        try:
            self.stress_test_number = int(self.user_params[
                "stress_test_number"])
            self.log.info("Executing {} calls per test in stress test mode".
                          format(self.stress_test_number))
        except KeyError:
            self.stress_test_number = 0
            self.log.info(
                "No 'stress_test_number' defined: running single iteration tests"
            )

        self.ad = self.android_devices[0]
        self.md8475a_ip_address = self.user_params[
            "anritsu_md8475a_ip_address"]

        setattr(self, 'emergency_call_number', DEFAULT_EMERGENCY_CALL_NUMBER)
        if 'emergency_call_number' in self.user_params:
            self.emergency_call_number = self.user_params[
                'emergency_call_number']
            self.log.info("Using provided emergency call number: {}".format(
                self.emergency_call_number))
        if not self.emergency_call_number in EMERGENCY_CALL_NUMBERS:
            self.log.warning("Unknown Emergency Number {}".format(
                self.emergency_call_number))

    def setup_class(self):
        try:
            self.anritsu = MD8475A(self.md8475a_ip_address, self.log)
        except AnritsuError:
            self.log.error("Error in connecting to Anritsu Simulator")
            return False
        return True

    def setup_test(self):
        ensure_phones_idle(self.log, self.android_devices)
        # get a handle to virtual phone
        self.virtualPhoneHandle = self.anritsu.get_VirtualPhone()
        toggle_airplane_mode(self.log, self.ad, True)
        return True

    def teardown_test(self):
        self.log.info("Stopping Simulation")
        self.anritsu.stop_simulation()
        toggle_airplane_mode(self.log, self.ad, True)
        return True

    def teardown_class(self):
        self.anritsu.disconnect()
        return True

    def _setup_emergency_call(self,
                              cell_param_file,
                              set_simulation_func,
                              simulation_param_file,
                              phone_setup_func,
                              phone_idle_func_after_registration=None,
                              is_ims_call=False,
                              is_wait_for_registration=True,
                              csfb_type=None,
                              srlte_csfb=None,
                              srvcc=False,
                              emergency_number=DEFAULT_EMERGENCY_CALL_NUMBER,
                              teardown_side=CALL_TEARDOWN_PHONE,
                              wait_time_in_call=WAIT_TIME_IN_CALL):
        try:
            # if load simumation parpameter file then no need to reset
            if simulation_param_file:
                self.anritsu.load_simulation_paramfile(simulation_param_file)
            else:
                self.anritsu.reset()
            # load cell parameter file after setting simulation parameters
            if cell_param_file:
                self.anritsu.load_cell_paramfile(cell_param_file)
            if set_simulation_func:
                set_simulation_func(self.anritsu, self.user_params)
            self.virtualPhoneHandle.auto_answer = (VirtualPhoneAutoAnswer.ON,
                                                   2)
            if csfb_type:
                self.anritsu.csfb_type = csfb_type
            if srlte_csfb == "lte_call_failure":
                self.anritsu.send_command("IMSPSAPAUTOANSWER 1,DISABLE")
            self.anritsu.start_simulation()
            iterations = 1
            if self.stress_test_number > 0:
                iterations = self.stress_test_number
            successes = 0
            for i in range(1, iterations + 1):
                if self.stress_test_number:
                    self.log.info("Running iteration {} of {}".format(
                        i, iterations))
                # FIXME: There's no good reason why this must be true;
                # I can only assume this was done to work around a problem
                self.ad.droid.telephonyToggleDataConnection(False)

                if phone_setup_func is not None:
                    if not phone_setup_func(self.ad):
                        self.log.error("phone_setup_func failed.")
                        continue
                if is_wait_for_registration:
                    self.anritsu.wait_for_registration_state()

                if phone_idle_func_after_registration:
                    if not phone_idle_func_after_registration(self.log,
                                                              self.ad):
                        continue

                time.sleep(WAIT_TIME_ANRITSU_REG_AND_CALL)
                if srlte_csfb or srvcc:
                    if not ims_mo_cs_teardown(
                            self.log, self.ad, self.anritsu, emergency_number,
                            CALL_TEARDOWN_PHONE, True, True, False,
                            WAIT_TIME_IN_CALL_FOR_IMS, WAIT_TIME_IN_CALL):
                        self.log.error(
                            "Phone {} Failed to make emergency call to {}"
                            .format(self.ad.serial, emergency_number))
                        continue
                else:
                    if not call_mo_setup_teardown(
                            self.log, self.ad, self.anritsu, emergency_number,
                            CALL_TEARDOWN_PHONE, True, WAIT_TIME_IN_CALL,
                            is_ims_call):
                        self.log.error(
                            "Phone {} Failed to make emergency call to {}"
                            .format(self.ad.serial, emergency_number))
                        continue
                successes += 1
                if self.stress_test_number:
                    self.log.info("Passed iteration {}".format(i))
            if self.stress_test_number:
                self.log.info("Total of {} successes out of {} attempts".
                              format(successes, iterations))
            return True if successes == iterations else False

        except AnritsuError as e:
            self.log.error("Error in connection with Anritsu Simulator: " +
                           str(e))
            return False
        except Exception as e:
            self.log.error("Exception during emergency call procedure: " + str(
                e))
            return False
        return True

    def _phone_setup_lte_wcdma(self, ad):
        return ensure_network_rat(
            self.log,
            ad,
            NETWORK_MODE_LTE_GSM_WCDMA,
            RAT_FAMILY_LTE,
            toggle_apm_after_setting=True)

    def _phone_setup_lte_1x(self, ad):
        return ensure_network_rat(
            self.log,
            ad,
            NETWORK_MODE_LTE_CDMA_EVDO,
            RAT_FAMILY_LTE,
            toggle_apm_after_setting=True)

    def _phone_setup_wcdma(self, ad):
        return ensure_network_rat(
            self.log,
            ad,
            NETWORK_MODE_GSM_UMTS,
            RAT_FAMILY_UMTS,
            toggle_apm_after_setting=True)

    def _phone_setup_gsm(self, ad):
        return ensure_network_rat(
            self.log,
            ad,
            NETWORK_MODE_GSM_ONLY,
            RAT_FAMILY_GSM,
            toggle_apm_after_setting=True)

    def _phone_setup_1x(self, ad):
        return ensure_network_rat(
            self.log,
            ad,
            NETWORK_MODE_CDMA,
            RAT_FAMILY_CDMA2000,
            toggle_apm_after_setting=True)

    def _phone_setup_airplane_mode(self, ad):
        return toggle_airplane_mode(self.log, ad, True)

    def _phone_setup_volte_airplane_mode(self, ad):
        toggle_volte(self.log, ad, True)
        return toggle_airplane_mode(self.log, ad, True)

    def _phone_setup_volte(self, ad):
        ad.droid.telephonyToggleDataConnection(True)
        toggle_volte(self.log, ad, True)
        return ensure_network_rat(
            self.log,
            ad,
            NETWORK_MODE_LTE_CDMA_EVDO_GSM_WCDMA,
            RAT_FAMILY_LTE,
            toggle_apm_after_setting=True)

    """ Tests Begin """

    @TelephonyBaseTest.tel_test_wrap
    def test_emergency_call_lte_wcdma_csfb_redirection(self):
        """ Test Emergency call functionality on LTE (CSFB to WCDMA).
            CSFB type is REDIRECTION

        Steps:
        1. Setup CallBox on LTE and WCDMA network, make sure DUT register on LTE network.
        2. Make an emergency call to 911. Make sure DUT CSFB to WCDMA.
        3. Make sure Anritsu receives the call and accept.
        4. Tear down the call.

        Expected Results:
        2. Emergency call succeed. DUT CSFB to WCDMA.
        3. Anritsu can accept the call.
        4. Tear down call succeed.

        Returns:
            True if pass; False if fail
        """
        return self._setup_emergency_call(
            self.CELL_PARAM_FILE,
            set_system_model_lte_wcdma,
            self.SIM_PARAM_FILE,
            self._phone_setup_lte_wcdma,
            emergency_number=self.emergency_call_number,
            csfb_type=CsfbType.CSFB_TYPE_REDIRECTION)

    @TelephonyBaseTest.tel_test_wrap
    def test_emergency_call_lte_wcdma_csfb_handover(self):
        """ Test Emergency call functionality on LTE (CSFB to WCDMA).
            CSFB type is HANDOVER

        Steps:
        1. Setup CallBox on LTE and WCDMA network, make sure DUT register on LTE network.
        2. Make an emergency call to 911. Make sure DUT CSFB to WCDMA.
        3. Make sure Anritsu receives the call and accept.
        4. Tear down the call.

        Expected Results:
        2. Emergency call succeed. DUT CSFB to WCDMA.
        3. Anritsu can accept the call.
        4. Tear down call succeed.

        Returns:
            True if pass; False if fail
        """
        return self._setup_emergency_call(
            self.CELL_PARAM_FILE,
            set_system_model_lte_wcdma,
            self.SIM_PARAM_FILE,
            self._phone_setup_lte_wcdma,
            emergency_number=self.emergency_call_number,
            csfb_type=CsfbType.CSFB_TYPE_HANDOVER)

    @TelephonyBaseTest.tel_test_wrap
    def test_emergency_call_lte_1x_csfb(self):
        """ Test Emergency call functionality on LTE (CSFB to 1x).

        Steps:
        1. Setup CallBox on LTE and CDMA 1X network, make sure DUT register on LTE network.
        2. Make an emergency call to 911. Make sure DUT CSFB to 1x.
        3. Make sure Anritsu receives the call and accept.
        4. Tear down the call.

        Expected Results:
        2. Emergency call succeed. DUT CSFB to 1x.
        3. Anritsu can accept the call.
        4. Tear down call succeed.

        Returns:
            True if pass; False if fail
        """
        return self._setup_emergency_call(
            self.CELL_PARAM_FILE,
            set_system_model_lte_1x,
            self.SIM_PARAM_FILE,
            self._phone_setup_lte_1x,
            emergency_number=self.emergency_call_number)

    @TelephonyBaseTest.tel_test_wrap
    def test_emergency_call_wcdma(self):
        """ Test Emergency call functionality on WCDMA

        Steps:
        1. Setup CallBox on WCDMA network, make sure DUT register on WCDMA network.
        2. Make an emergency call to 911.
        3. Make sure Anritsu receives the call and accept.
        4. Tear down the call.

        Expected Results:
        2. Emergency call succeed.
        3. Anritsu can accept the call.
        4. Tear down call succeed.

        Returns:
            True if pass; False if fail
        """
        return self._setup_emergency_call(
            self.CELL_PARAM_FILE,
            set_system_model_wcdma,
            self.SIM_PARAM_FILE,
            self._phone_setup_wcdma,
            emergency_number=self.emergency_call_number)

    @TelephonyBaseTest.tel_test_wrap
    def test_emergency_call_gsm(self):
        """ Test Emergency call functionality on GSM

        Steps:
        1. Setup CallBox on GSM network, make sure DUT register on GSM network.
        2. Make an emergency call to 911.
        3. Make sure Anritsu receives the call and accept.
        4. Tear down the call.

        Expected Results:
        2. Emergency call succeed.
        3. Anritsu can accept the call.
        4. Tear down call succeed.

        Returns:
            True if pass; False if fail
        """
        return self._setup_emergency_call(
            self.CELL_PARAM_FILE,
            set_system_model_gsm,
            self.SIM_PARAM_FILE,
            self._phone_setup_gsm,
            emergency_number=self.emergency_call_number)

    @TelephonyBaseTest.tel_test_wrap
    def test_emergency_call_1x(self):
        """ Test Emergency call functionality on CDMA 1X

        Steps:
        1. Setup CallBox on 1x network, make sure DUT register on 1x network.
        2. Make an emergency call to 911.
        3. Make sure Anritsu receives the call and accept.
        4. Tear down the call.

        Expected Results:
        2. Emergency call succeed.
        3. Anritsu can accept the call.
        4. Tear down call succeed.

        Returns:
            True if pass; False if fail
        """
        return self._setup_emergency_call(
            self.CELL_PARAM_FILE,
            set_system_model_1x,
            self.SIM_PARAM_FILE,
            self._phone_setup_1x,
            emergency_number=self.emergency_call_number)

    @TelephonyBaseTest.tel_test_wrap
    def test_emergency_call_1x_evdo(self):
        """ Test Emergency call functionality on CDMA 1X with EVDO

        Steps:
        1. Setup CallBox on 1x and EVDO network, make sure DUT register on 1x network.
        2. Make an emergency call to 911.
        3. Make sure Anritsu receives the call and accept.
        4. Tear down the call.

        Expected Results:
        2. Emergency call succeed.
        3. Anritsu can accept the call.
        4. Tear down call succeed.

        Returns:
            True if pass; False if fail
        """
        return self._setup_emergency_call(
            self.CELL_PARAM_FILE,
            set_system_model_1x_evdo,
            self.SIM_PARAM_FILE,
            self._phone_setup_1x,
            emergency_number=self.emergency_call_number)

    @TelephonyBaseTest.tel_test_wrap
    def test_emergency_call_1x_apm(self):
        """ Test Emergency call functionality on Airplane mode

        Steps:
        1. Setup CallBox on 1x network.
        2. Turn on Airplane mode on DUT. Make an emergency call to 911.
        3. Make sure Anritsu receives the call and accept.
        4. Tear down the call.

        Expected Results:
        2. Emergency call succeed.
        3. Anritsu can accept the call.
        4. Tear down call succeed.

        Returns:
            True if pass; False if fail
        """
        return self._setup_emergency_call(
            self.CELL_PARAM_FILE,
            set_system_model_1x,
            self.SIM_PARAM_FILE,
            self._phone_setup_airplane_mode,
            is_wait_for_registration=False,
            emergency_number=self.emergency_call_number)

    @TelephonyBaseTest.tel_test_wrap
    def test_emergency_call_wcdma_apm(self):
        """ Test Emergency call functionality on Airplane mode

        Steps:
        1. Setup CallBox on WCDMA network.
        2. Make an emergency call to 911.
        3. Make sure Anritsu receives the call and accept.
        4. Tear down the call.

        Expected Results:
        2. Emergency call succeed.
        3. Anritsu can accept the call.
        4. Tear down call succeed.

        Returns:
            True if pass; False if fail
        """
        return self._setup_emergency_call(
            self.CELL_PARAM_FILE,
            set_system_model_wcdma,
            self.SIM_PARAM_FILE,
            self._phone_setup_airplane_mode,
            is_wait_for_registration=False,
            emergency_number=self.emergency_call_number)

    @TelephonyBaseTest.tel_test_wrap
    def test_emergency_call_csfb_1x_lte_call_failure(self):
        """ Test Emergency call functionality,
        CSFB to CDMA1x after VoLTE call failure
        Ref: VzW LTE E911 test plan, 2.23, VZ_TC_LTEE911_7481
        Steps:
        1. Setup CallBox on VoLTE network with CDMA1x.
        2. Turn on DUT and enable VoLTE. Make an emergency call to 911.
        3. Make sure Anritsu IMS server does not answer the call
        4. The DUT requests CSFB to 1XCDMA and Anritsu accepts the call.
        4. Tear down the call.

        Expected Results:
        2. VoLTE Emergency call is made.
        3. Anritsu receive the call but does not answer.
        4. The 911 call CSFB to CDMA1x and answered successfully.
        4. Tear down call succeed.

        Returns:
            True if pass; False if fail
        """
        return self._setup_emergency_call(
            self.CELL_PARAM_FILE,
            set_system_model_lte_1x,
            self.SIM_PARAM_FILE_FOR_VOLTE,
            self._phone_setup_volte,
            phone_idle_volte,
            srlte_csfb="lte_call_failure",
            emergency_number=self.emergency_call_number,
            wait_time_in_call=WAIT_TIME_IN_CALL_FOR_IMS)

    @TelephonyBaseTest.tel_test_wrap
    def test_emergency_call_volte_1x(self):
        """ Test Emergency call functionality on VoLTE with CDMA1x
        Ref: VzW LTE E911 test plan, 2.24, VZ_TC_LTEE911_7482
        Steps:
        1. Setup CallBox on VoLTE network with CDMA1x.
        2. Turn on DUT and enable VoLTE. Make an emergency call to 911.
        3. Make sure Anritsu receives the call and accept.
        4. Tear down the call.

        Expected Results:
        2. Emergency call succeed.
        3. Anritsu can accept the call.
        4. Tear down call succeed.

        Returns:
            True if pass; False if fail
        """
        return self._setup_emergency_call(
            self.CELL_PARAM_FILE,
            set_system_model_lte_1x,
            self.SIM_PARAM_FILE_FOR_VOLTE,
            self._phone_setup_volte,
            phone_idle_volte,
            is_ims_call=True,
            emergency_number=self.emergency_call_number,
            wait_time_in_call=WAIT_TIME_IN_CALL_FOR_IMS)

    @TelephonyBaseTest.tel_test_wrap
    def test_emergency_call_volte(self):
        """ Test Emergency call functionality on VoLTE

        Steps:
        1. Setup CallBox on VoLTE network.
        2. Turn on DUT and enable VoLTE. Make an emergency call to 911.
        3. Make sure Anritsu receives the call and accept.
        4. Tear down the call.

        Expected Results:
        2. Emergency call succeed.
        3. Anritsu can accept the call.
        4. Tear down call succeed.

        Returns:
            True if pass; False if fail
        """
        return self._setup_emergency_call(
            self.CELL_PARAM_FILE_FOR_VOLTE,
            None,
            self.SIM_PARAM_FILE_FOR_VOLTE,
            self._phone_setup_volte,
            phone_idle_volte,
            is_ims_call=True,
            emergency_number=self.emergency_call_number,
            wait_time_in_call=WAIT_TIME_IN_CALL_FOR_IMS)

    @TelephonyBaseTest.tel_test_wrap
    def test_emergency_call_volte_apm(self):
        """ Test Emergency call functionality on VoLTE

        Steps:
        1. Setup CallBox on VoLTE network.
        2. Turn on Airplane mode on DUT. Make an emergency call to 911.
        3. Make sure Anritsu receives the call and accept.
        4. Tear down the call.

        Expected Results:
        2. Emergency call succeed.
        3. Anritsu can accept the call.
        4. Tear down call succeed.

        Returns:
            True if pass; False if fail
        """
        return self._setup_emergency_call(
            self.CELL_PARAM_FILE_FOR_VOLTE,
            None,
            self.SIM_PARAM_FILE_FOR_VOLTE,
            self._phone_setup_volte_airplane_mode,
            is_ims_call=True,
            is_wait_for_registration=False,
            emergency_number=self.emergency_call_number,
            wait_time_in_call=WAIT_TIME_IN_CALL_FOR_IMS)

    @TelephonyBaseTest.tel_test_wrap
    def test_emergency_call_no_sim_wcdma(self):
        """ Test Emergency call functionality with no SIM.

        Steps:
        1. Setup CallBox on WCDMA network.
        2. Make an emergency call to 911.
        3. Make sure Anritsu receives the call and accept.
        4. Tear down the call.

        Expected Results:
        2. Emergency call succeed.
        3. Anritsu can accept the call.
        4. Tear down call succeed.

        Returns:
            True if pass; False if fail
        """
        return self._setup_emergency_call(
            self.CELL_PARAM_FILE,
            set_system_model_wcdma,
            None,
            None,
            emergency_number=self.emergency_call_number,
            is_wait_for_registration=False)

    @TelephonyBaseTest.tel_test_wrap
    def test_emergency_call_no_sim_1x(self):
        """ Test Emergency call functionality with no SIM.

        Steps:
        1. Setup CallBox on 1x network.
        2. Make an emergency call to 911.
        3. Make sure Anritsu receives the call and accept.
        4. Tear down the call.

        Expected Results:
        2. Emergency call succeed.
        3. Anritsu can accept the call.
        4. Tear down call succeed.

        Returns:
            True if pass; False if fail
        """
        return self._setup_emergency_call(
            self.CELL_PARAM_FILE,
            set_system_model_1x,
            None,
            None,
            emergency_number=self.emergency_call_number,
            is_wait_for_registration=False)

    @TelephonyBaseTest.tel_test_wrap
    def test_emergency_call_no_sim_gsm(self):
        """ Test Emergency call functionality with no SIM.

        Steps:
        1. Setup CallBox on GSM network.
        2. Make an emergency call to 911.
        3. Make sure Anritsu receives the call and accept.
        4. Tear down the call.

        Expected Results:
        2. Emergency call succeed.
        3. Anritsu can accept the call.
        4. Tear down call succeed.

        Returns:
            True if pass; False if fail
        """
        return self._setup_emergency_call(
            self.CELL_PARAM_FILE,
            set_system_model_gsm,
            None,
            None,
            emergency_number=self.emergency_call_number,
            is_wait_for_registration=False)

    @TelephonyBaseTest.tel_test_wrap
    def test_emergency_call_no_sim_volte(self):
        """ Test Emergency call functionality with no SIM.

        Steps:
        1. Setup CallBox on VoLTE network.
        2. Make an emergency call to 911.
        3. Make sure Anritsu receives the call and accept.
        4. Tear down the call.

        Expected Results:
        2. Emergency call succeed.
        3. Anritsu can accept the call.
        4. Tear down call succeed.

        Returns:
            True if pass; False if fail
        """
        return self._setup_emergency_call(
            self.CELL_PARAM_FILE_FOR_VOLTE,
            None,
            self.SIM_PARAM_FILE_FOR_VOLTE,
            None,
            is_wait_for_registration=False,
            is_ims_call=True,
            emergency_number=self.emergency_call_number,
            wait_time_in_call=WAIT_TIME_IN_CALL_FOR_IMS)

    @TelephonyBaseTest.tel_test_wrap
    def test_emergency_call_no_sim_1x_ecbm(self):
        """ Test Emergency call functionality with no SIM.

        Steps:
        1. Setup CallBox on 1x network.
        2. Make an emergency call to 911.
        3. Make sure Anritsu receives the call and accept.
        4. Tear down the call.
        5. Make a call from Callbox to DUT.
        6. Verify DUT receive the incoming call.
        7. Answer on DUT, verify DUT can answer the call correctly.
        8. Hangup the call on DUT.

        Expected Results:
        2. Emergency call succeed.
        3. Anritsu can accept the call.
        4. Tear down call succeed.
        6. DUT receive incoming call.
        7. DUT answer the call correctly.
        8. Tear down call succeed.

        Returns:
            True if pass; False if fail
        """
        if not self._setup_emergency_call(
                self.CELL_PARAM_FILE,
                set_system_model_1x,
                None,
                None,
                emergency_number=self.emergency_call_number,
                is_wait_for_registration=False):
            self.log.error("Failed to make 911 call.")
            return False
        return call_mt_setup_teardown(self.log, self.ad,
                                      self.anritsu.get_VirtualPhone(), None,
                                      CALL_TEARDOWN_PHONE, RAT_1XRTT)

    """ Tests End """
