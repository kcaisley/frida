import numpy as np
import matplotlib

matplotlib.use("Agg")  # Use non-interactive backend
import matplotlib.pyplot as plt
from tqdm import tqdm
import os


class CDAC:
    def __init__(self, params, parent):
        self.parent = parent
        # dictionary with parameters
        self.params = params["CDAC"].copy()
        self.capacitor_array_p = np.zeros(self.params["array_size"])
        self.capacitor_array_n = np.zeros(self.params["array_size"])
        self.weights_array = np.zeros(self.params["array_size"])
        self.weights_sum = 0

        self.capacitance_sum_p = 0
        self.capacitance_sum_n = 0

        self.settling_time_error = 0

        self.output_voltage_p = 0
        self.output_voltage_n = 0
        self.register_p = 0
        self.register_n = 0
        self.consumed_charge = 0

    def update_parameters(self):  # FIXME: how is this even called at the beginning?
        self.build_capacitor_array()
        if self.params["settling_time"] > 0:
            self.settling_time_error = np.exp(  # Decaying exponential model (percent decay)
                -1
                / (
                    self.params["settling_time"]  # This is tau; the time constant
                    * self.parent.params["sampling_frequency"]
                    * (
                        self.params["array_size"] + 1
                    )  # This divides the sampling frequency to find the settling error
                )
            )
        else:
            self.settling_time_error = 0
        self.lsb_size = (
            self.params["positive_reference_voltage"]
            - self.params["negative_reference_voltage"]
        ) / (self.weights_sum)
        self.common_mode_voltage = (
            self.params["positive_reference_voltage"]
            - self.params["negative_reference_voltage"]
        ) / 2

    def reset(self, reset_value, do_calculate_energy=False):
        raise NotImplementedError

    def sample(self, input_p, input_n):
        raise NotImplementedError

    def update(self, register_p, register_n, do_calculate_energy=False):
        raise NotImplementedError

    def build_capacitor_array(self):
        raise NotImplementedError

    def calculate_nonlinearity(
        self, do_plot=False, values_per_bin=10
    ):  # FIXME: there is also an ADC top nonlinearity function?
        reg_data = np.arange(0, 2 ** (self.params["array_size"]), 1)
        dac_data = np.zeros(len(reg_data))
        dnl_data = np.zeros(len(reg_data) - 1)
        inl_data = np.zeros(len(reg_data))

        print("DAC array size %d" % self.params["array_size"])
        print("lsb size %e" % self.lsb_size)

        for reg in reg_data:
            self.reset(0)
            self.sample(0, 0)
            out_p, out_n = self.update(reg, 0)
            dac_data[reg] = out_p - out_n

        dnl_data = (np.diff(dac_data) - self.lsb_size) / self.lsb_size
        dac_dnl_std = np.std(dnl_data)
        inl_data = np.cumsum(dnl_data)
        dac_inl_std = np.std(inl_data)

        if do_plot:
            figure, plot = plt.subplots(3, 1, sharex=True)
            figure.suptitle("DAC Nonlinearity")
            plot[0].step(reg_data, dac_data, where="pre", label="DAC transfer function")
            # plot[0].set_xticks(range(reg_data[0], reg_data[len(reg_data)-1]+1,  self.params['array_size']//4))
            plot[0].set_ylabel("Output voltage [V]")
            plot[0].grid(True)
            plot[1].step(
                reg_data[:-1], dnl_data, where="post", label="DNL = %.3f" % dac_dnl_std
            )
            if dac_dnl_std < 0.0001:
                plot[1].set_ylim(-1, 1)
            plot[1].set_ylabel("DNL [LSB]")
            plot[1].legend(loc="upper right")
            plot[1].grid(True)
            plot[2].step(
                reg_data[:-1], inl_data, where="post", label="INL = %.3f" % dac_inl_std
            )
            if dac_inl_std < 0.0001:
                plot[2].set_ylim(-1, 1)
            plot[2].set_ylabel("INL [LSB]")
            plot[2].legend(loc="upper right")
            plot[2].set_xlabel("Digital code")
            plot[2].grid(True)

        return dac_dnl_std, dac_inl_std


class CDAC_BSS(CDAC):
    def __init__(self, params, parent):
        super().__init__(params, parent)
        self.update_parameters()

    def build_capacitor_array(self):
        """
        # The capacitor array can be constructed in three different ways:
        # 1. Use individual weights from the parameter file and 'array_size' as defined in the parameter file.
        # 2. Use binary weights (radix = 2) to construct the capacitor array and 'array_size' = resolution-1
        # 3. Use non binary weight (radix > 2) to construct the capacitor array and 'array_size' will be resized to the dynamic range of the nominal binary weighted capacitors
        """
        if self.params["use_individual_weights"]:
            # use individual weights from the parameter file, but only supports integers
            array_index_offset = (
                len(self.params["individual_weights"]) - self.params["array_size"]
            )
            self.weights_array = np.array(
                self.params["individual_weights"][
                    array_index_offset : array_index_offset + self.params["array_size"]
                ]
            )
            self.capacitor_array_p = (
                self.weights_array * self.params["unit_capacitance"]
            )
            self.capacitor_array_n = (
                self.weights_array * self.params["unit_capacitance"]
            )

        else:  # construct array according to given radix and desired resolution
            if self.params[
                "array_N_M_expansion"  # FIXME: I've deleted this option
            ]:  # If you want array size to be computed, instead of manually supplied
                self.params["array_size"] = (
                    self.parent.params["resolution"] - 1
                )  # for binary weighted capacitors
                if self.params["radix"] != 2:
                    # resize non-binary capacitor array size to match the dynamic range of a binary weighted capacitor array
                    self.params["array_size"] = int(
                        np.ceil(
                            self.params["array_size"] / np.log2(self.params["radix"])
                        )
                    )  # match *at least* the resolution of the radix 2 design

            # resize arrays
            self.capacitor_array_p = np.zeros(self.params["array_size"])
            self.capacitor_array_n = np.zeros(self.params["array_size"])
            self.weights_array = np.zeros(self.params["array_size"])

            # build capacitor array from given radix
            for i in range(self.params["array_size"]):
                self.capacitor_array_p[self.params["array_size"] - i - 1] = (
                    self.params["radix"] ** i * self.params["unit_capacitance"]
                )
                self.capacitor_array_n[self.params["array_size"] - i - 1] = (
                    self.params["radix"] ** i * self.params["unit_capacitance"]
                )
            self.weights_array = (
                self.capacitor_array_p / self.params["unit_capacitance"]
            )

        self.weights_sum = np.sum(self.weights_array)

        # add systematic errors
        if self.params["capacitor_mismatch_error"] > 0:
            for i in range(
                self.params["array_size"]
            ):  # error in percent/100   scaled with  sqrt(capacitance/unit capacitance)
                self.capacitor_array_p[i] += (
                    self.params["unit_capacitance"]
                    * np.random.normal(0, self.params["capacitor_mismatch_error"] / 100)
                    / np.sqrt(
                        self.capacitor_array_p[i] / self.params["unit_capacitance"]
                    )
                )
                self.capacitor_array_n[i] += (
                    self.params["unit_capacitance"]
                    * np.random.normal(0, self.params["capacitor_mismatch_error"] / 100)
                    / np.sqrt(
                        self.capacitor_array_n[i] / self.params["unit_capacitance"]
                    )
                )

        self.capacitance_sum_p = (
            sum(self.capacitor_array_p) + self.params["parasitic_capacitance"]
        )
        self.capacitance_sum_n = (
            sum(self.capacitor_array_n) + self.params["parasitic_capacitance"]
        )

        np.set_printoptions(precision=2)
        # Remove scattered prints - these are now in structured output

    def reset(self, reset_value, do_calculate_energy=False):
        register_p = reset_value  # 2**(self.params['array_size']-1)-1
        register_n = reset_value  # 2**(self.params['array_size']-1)-1
        self.update(register_p, register_n, do_calculate_energy=do_calculate_energy)
        # print('reset charge %e' % self.dac.consumed_charge)

    def sample(self, input_p, input_n):
        # top plate sampling: DAC output voltage = input voltage
        self.output_voltage_p = input_p
        self.output_voltage_n = input_n

    def update(self, register_p, register_n, do_calculate_energy=False):
        """
        Modeling note, which applies to all blocks:
        Class attributes are state internal to the block
        Input argument variables are changing values which are driven by other blocks
        Output return values model outputs which are driver to other blocks
        """
        delta_output_voltage_p = 0
        delta_output_voltage_n = 0
        self.consumed_charge = 0
        delta_backplane_voltage = (
            self.params["positive_reference_voltage"]
            - self.params["negative_reference_voltage"]
        )

        # calculate the contributions of the toggled capacitors to the output voltage change
        # Note that in real hardware, this would all happen simultaneously
        for i in range(self.params["array_size"]):
            current_capacitor_p = self.capacitor_array_p[i]
            current_capacitor_n = self.capacitor_array_n[i]
            reg_index = self.params["array_size"] - i - 1

            # If the incoming register value (at index i) is higher than the stored value, increase output
            if (register_p & (1 << reg_index)) > (self.register_p & (1 << reg_index)):
                delta_output_voltage_p += (
                    current_capacitor_p
                    / self.capacitance_sum_p
                    * delta_backplane_voltage
                )
            # vice-versa, decrease the output, Note how there is no case for the same value as this would maintain voltage.
            elif (register_p & (1 << reg_index)) < (self.register_p & (1 << reg_index)):
                delta_output_voltage_p -= (
                    current_capacitor_p
                    / self.capacitance_sum_p
                    * delta_backplane_voltage
                )

            if (register_n & (1 << reg_index)) > (self.register_n & (1 << reg_index)):
                delta_output_voltage_n += (
                    current_capacitor_n
                    / self.capacitance_sum_n
                    * delta_backplane_voltage
                )
            elif (register_n & (1 << reg_index)) < (self.register_n & (1 << reg_index)):
                delta_output_voltage_n -= (
                    current_capacitor_n
                    / self.capacitance_sum_n
                    * delta_backplane_voltage
                )

        if do_calculate_energy:
            # calculate the consumed charge =
            # delta_output_voltage * total capacitance connected to VREF (for negative delta_output_voltage) and
            # delta_output_voltage * total capacitance connected to GND  (for positive delta_output_voltage)

            # TODO: This can/should be simplified into just two cases, not two if-else
            # NOTE: Even though only one register bit has been updated, is it correct that we need to examine all caps?
            for i in range(self.params["array_size"]):
                current_capacitor_p = self.capacitor_array_p[i]
                current_capacitor_n = self.capacitor_array_n[i]
                reg_index = self.params["array_size"] - i - 1
                if delta_output_voltage_p > 0:
                    if (register_p & (1 << reg_index)) == 0:
                        self.consumed_charge += (
                            current_capacitor_p * delta_output_voltage_p
                        )
                else:
                    if (register_p & (1 << reg_index)) != 0:
                        self.consumed_charge -= (
                            current_capacitor_p * delta_output_voltage_p
                        )

                if delta_output_voltage_n > 0:
                    if (register_n & (1 << reg_index)) == 0:
                        self.consumed_charge += (
                            current_capacitor_n * delta_output_voltage_n
                        )
                else:
                    if (register_n & (1 << reg_index)) != 0:
                        self.consumed_charge -= (
                            current_capacitor_n * delta_output_voltage_n
                        )

        # ideal CDAC output voltage for reference
        self.output_voltage_p += delta_output_voltage_p
        self.output_voltage_n += delta_output_voltage_n

        # update register
        self.register_p = register_p
        self.register_n = register_n

        # add reference voltage noise, attenuated by the ratio of capacitance connected to VREF to total capacitance, correlated for n and p side
        # calculate total capacitance connected to VREF for each side
        capacitance_at_vref_p = 0
        capacitance_at_vref_n = 0
        for i in range(self.params["array_size"]):
            reg_index = self.params["array_size"] - i - 1
            if (self.register_p & (1 << reg_index)) != 0:
                capacitance_at_vref_p += self.capacitor_array_p[i]
            if (self.register_n & (1 << reg_index)) != 0:
                capacitance_at_vref_n += self.capacitor_array_n[i]

        voltage_noise_sample = np.random.normal(
            0, self.params["reference_voltage_noise"]
        )
        noise_p = voltage_noise_sample * capacitance_at_vref_p / self.capacitance_sum_p
        noise_n = voltage_noise_sample * capacitance_at_vref_n / self.capacitance_sum_n

        # calculate how much of the voltage step is resolved, as a voltage with same sign
        settling_error_p = delta_output_voltage_p * self.settling_time_error  #
        settling_error_n = delta_output_voltage_n * self.settling_time_error  #

        # add noise and subtract the unresolved voltage step
        return (self.output_voltage_p + noise_p - settling_error_p), (
            self.output_voltage_n + noise_n - settling_error_n
        )


class COMPARATOR:
    def __init__(self, params):
        # dictionary with parameters
        self.params = params["COMP"].copy()

    def compare(self, input_voltage_p, input_voltage_n):
        common_mode_offset_voltage = (
            (input_voltage_p + input_voltage_n)
            / 2
            * self.params["common_mode_dependent_offset_gain"]
        )
        noise_voltage = np.random.normal(0, self.params["threshold_voltage_noise"])
        return (
            input_voltage_p
            > input_voltage_n
            + self.params["offset_voltage"]
            + common_mode_offset_voltage
            + noise_voltage
        )


class SAR_ADC:
    def __init__(self, params):
        # dictionary with parameters
        self.params = params[
            "ADC"
        ].copy()  # need .copy() to make sure modifiying one won't also change the other
        self.sampling_frequency = self.params["sampling_frequency"]
        self.dac = CDAC_BSS(params, self)
        self.cycles = self.dac.params["array_size"] + 1
        self.clock_period = 1 / (self.sampling_frequency * self.cycles)
        self.redundancy = (
            self.cycles - self.params["resolution"]
        )  # FIXME: remove, not a useful metric. Won't break code.
        self.diff_input_voltage_range = (
            2
            * (  # FIXME: depends on parasitics... also CDAC update seems to have the same code?
                self.dac.params["positive_reference_voltage"]
                - self.dac.params["negative_reference_voltage"]
            )
        )
        self.lsb_size = (
            self.diff_input_voltage_range / 2 ** self.params["resolution"]
        )  # FIXME: this isn't true for non-binary??
        self.comparator = COMPARATOR(params)
        self.input_voltage_p = 0
        self.input_voltage_n = 0
        self.comp_result = []
        self.conversion_energy = 0
        self.midscale = 2 ** (
            self.params["resolution"] - 1
        )  # FIXME: this isn't true for non-binary, right?

        # performance metrics
        self.dnl = 0
        self.inl = 0
        self.enob = 0
        self.average_conversion_energy = 0
        self.fom = 0

    def update_parameters(self):  # FIXME: I think this is never called?
        self.dac.update_parameters()  # FIXME: This is also called in CDAC_BSS subclass?
        self.cycles = self.dac.params["array_size"] + 1
        self.clock_period = 1 / (self.sampling_frequency * self.cycles)
        self.redundancy = self.cycles - self.params["resolution"]
        self.diff_input_voltage_range = 2 * (
            self.dac.params["positive_reference_voltage"]
            - self.dac.params["negative_reference_voltage"]
        )
        self.lsb_size = self.diff_input_voltage_range / self.dac.weights_sum
        self.midscale = 2 ** (self.params["resolution"] - 1)
        self.dnl = 0
        self.inl = 0
        self.enob = 0
        self.average_conversion_energy = 0

    def print_parameter_list(self):
        # b = "\033[1m"
        # n = "\033[0m"
        parameters = ""
        parameters += "Design parameters\n"
        parameters += f" Resolution   {self.params['resolution']}\n"
        parameters += f" Sample freq. {self.sampling_frequency / 1.0e6:.0f} Msps\n"
        parameters += f" LSB size     {self.lsb_size / 1.0e-3:.3f} mV\n"
        parameters += f" Redundancy   {self.redundancy}\n"
        if not self.dac.use_individual_weights:
            parameters += f" DAC radix    {self.dac.radix:.1f}\n"
        parameters += f" DAC capacitor array size  {self.dac.params['array_size']}\n"
        parameters += f" DAC unit capacitance      {self.dac.params['unit_capacitance'] / 1e-15:.1f} fF\n"
        parameters += f" DAC parasitic capacitance {self.dac.params['parasitic_capacitance'] / 1e-15:.1f} fF\n"
        parameters += (
            f" DAC total capacitance     {self.dac.capacitance_sum_p / 1e-12:.2f} pF\n"
        )
        # TBD
        # if self.dac.use_systematic_errors:
        #   parameters += f" DAC systematic error {self.dac.settling_time_error:.2e}\n"
        parameters += f" DAC settling error        {self.dac.settling_time_error:.2e}\n"
        parameters += f" Comparator noise          {self.comparator.params['threshold_voltage_noise']:.2e}\n"
        parameters += f" Comparator offset         {self.params['comparator.offset_voltage']:.2e}\n"
        parameters += f" Reference noise           {self.dac.params['reference_voltage_noise']:.2e}\n"
        parameters += "Performance\n"
        parameters += f" DNL   {self.dnl:.2f}\n"
        parameters += f" INL   {self.inl:.2f}\n"
        parameters += f" ENOB  {self.enob:.2f}\n"
        parameters += f" FOM   {self.average_conversion_energy / self.params['resolution'] / 1e-12:.2e} pJ\n"
        return parameters

    # This function calculates the output value (i.e. 're-analog') from the array of comp outputs
    def calculate_result(self, comp_result, do_normalize_result=True):
        """
        Like the other functions starting with calculate_*, this function is non-physical
        in the sense that it just analyzes the data produced by the physical ADC hardware modeled by the other code.
        """

        # initialize result
        result = 0

        # accumulate weights to calculate the result
        for i in range(self.cycles - 1):
            if self.params["use_calibration"]:
                # Use real capacitor values available after (perfect) calibration
                # In the real world, we would try to find these values but it would be an impefect process
                result += (
                    (2 * comp_result[i] - 1)
                    * self.dac.capacitor_array_p[i]
                    / self.dac.params["unit_capacitance"]
                )
            else:
                # use ideal weights, ignoring the mismatch error of the real capacitors
                result += (2 * comp_result[i] - 1) * self.dac.weights_array[i]

            # DEBUGGING ONLY: note this print statement is too slow in a loop:
            # print('comp_result ', comp_result[i], ' weight ', self.dac.weights_array[i], ' result ', result)

        # add final comparison result
        result += comp_result[self.cycles - 1]

        # # alternative calculation (binary weighted capacitors only)
        # result += comp_result[0] * 2 * self.dac.weights_array[0]
        # result -= 2 * self.dac.weights_array[0] - 1
        # for i in range(1, self.cycles):
        #   # use ideal weights, ignoring the mismatch error of the real capacitors
        #   result += comp_result[i] * self.dac.weights_array[i-1]
        #   #print('comp_result ', comp_result[i], ' weight ', self.dac.weights_array[i-1], ' result ', result)

        if do_normalize_result:
            # correct for scaling factor with sub-binary weighted capacitors or multiple redundant conversions
            result *= (2 ** (self.params["resolution"] - 1) - 1) / (
                self.dac.weights_sum
            )  # ???
            result = int(np.round(result))
        return result

    def calculate_nonlinearity(self, do_plot=False, values_per_bin=10):
        """
        This function current has issues:
        - The max and min code aren't accounting for the case of non-binary
        - The number of codes...
        """
        # values_per_bin is now passed as parameter
        lower_excluded_bins = 4  # lower bound for DNL/INL calculation in LSB
        upper_excluded_bins = (
            4  # upper bound for DNL/INL calculation in LSB distance from full scale
        )

        # helper variables
        min_code = -(
            2 ** (self.params["resolution"] - 1)
        )  # FIXME: I thought this was wrong for binary, but now I realized it's right as long as it's re-analog codes
        max_code = (
            2 ** (self.params["resolution"] - 1) - 1  # FIXME: see above
        )
        num_codes = 2 ** self.params["resolution"]  # FIXME: see above
        lower_index_boundary = lower_excluded_bins
        upper_index_boundary = num_codes - upper_excluded_bins

        # data structures for DNL/INL calculation
        code_density_hist = np.empty(num_codes)
        bin_edges = []
        dnl_data = np.empty(num_codes)
        inl_data = np.empty(num_codes)
        adc_data = np.empty(num_codes * values_per_bin)

        # values are uniformly distributed within bin uniformly
        input_voltage_data = np.arange(
            -self.diff_input_voltage_range / 2,
            self.diff_input_voltage_range / 2,
            self.lsb_size / values_per_bin,
        )

        # do the conversions, assuming input codes have uniform density
        # Calculating DNL/INL - progress shown by tqdm
        for i in tqdm(range(len(input_voltage_data))):
            adc_data[i] = self.sample_and_convert(
                input_voltage_data[i] / 2.0, -input_voltage_data[i] / 2.0
            )

        # ADC data array - results now in structured output

        # calculate code density histogram
        code_density_hist, bin_edges = np.histogram(
            adc_data, bins=num_codes, range=(min_code, max_code)
        )
        code_density_hist = code_density_hist[lower_index_boundary:upper_index_boundary]
        bin_edges = bin_edges[lower_index_boundary:upper_index_boundary]
        average_bin_count = np.average(code_density_hist)

        # calculate differential nonlinearity, difference between expected ideal counts in a bit and 'measured' (ideally would be zero)
        dnl_data = (code_density_hist - average_bin_count) / average_bin_count
        dnl_data[:lower_index_boundary] = 0
        dnl_data[upper_index_boundary:] = 0
        dnl_sigma = np.std(dnl_data)

        # calculate integral(i.e. cumsum) nonlinearity
        inl_data = np.cumsum(dnl_data)
        inl_sigma = np.std(inl_data)
        self.dnl = dnl_sigma
        self.inl = inl_sigma
        # DNL/INL results now reported in structured output

        if do_plot:
            x_ticks = range(
                min_code, max_code + 10, 2 ** (self.params["resolution"] - 3)
            )
            plot_title = "ADC Nonlinearity"
            figure, plot = plt.subplots(4, 1, sharex=True, figsize=(10, 16))
            # figure.tight_layout()
            # figure.suptitle(plot_title)
            plot[0].title.set_text("ADC Transfer Function")
            plot[0].step(adc_data, input_voltage_data, where="pre")
            plot[0].set_xticks(x_ticks)
            plot[0].set_ylabel("Input voltage [V]")
            plot[0].grid(True)
            plot[1].title.set_text("Code Density")

            plot[1].step(
                bin_edges,
                code_density_hist,
                where="pre",
                label="Ideal bin count = %d" % values_per_bin,
            )
            plot[1].set_xticks(x_ticks)
            plot[1].set_ylabel("Counts per ADC code")
            plot[1].legend(loc="upper right")
            plot[1].grid(True)
            plot[2].title.set_text("Differential Nonlinearity")

            plot[2].step(
                bin_edges, dnl_data, where="post", label="DNL sigma = %.3f" % dnl_sigma
            )
            plot[2].set_ylim(-2, 2)
            plot[2].set_ylabel("DNL [LSB]")
            plot[2].legend(loc="upper right")
            plot[2].grid(True)
            plot[3].title.set_text("Integral Nonlinearity")
            plot[3].step(
                bin_edges, inl_data, where="post", label="INL sigma = %.3f" % inl_sigma
            )
            plot[3].set_ylim(-2, 2)
            plot[3].set_ylabel("INL [LSB]")
            plot[3].legend(loc="upper right")
            plot[3].set_xlabel("ADC code")
            plot[3].grid(True)

            return figure, plot

    def calculate_enob(self, do_plot=False, num_samples=1000):
        # return (snr - 1.76)/6.02
        frequency = 10e3
        amplitude = 0.55
        offset = 0
        # num_samples is now passed as parameter
        adc_gain = (
            self.diff_input_voltage_range / 2 / 2 ** self.params["resolution"]
        )  # FIXME: shouldn't this depend on parasitics. Does this really just depend on Cunit?
        adc_offset = 0

        time_array = np.arange(  # For 100ns sampling times, this means we have 1ms worth of capture
            start=0,
            stop=num_samples / self.sampling_frequency,
            step=1 / self.sampling_frequency,
        )
        input_voltage_array = np.empty(len(time_array))
        adc_data_array = np.empty(len(time_array))

        # sample sine wave
        # Calculating ENOB - progress shown by tqdm
        for i in tqdm(range(len(time_array))):  # Q: So one cycle of the sine wave?
            input_voltage = offset + amplitude * np.sin(
                2 * np.pi * frequency * time_array[i]
            )
            input_voltage_array[i] = input_voltage
            adc_data_array[i] = self.sample_and_convert(input_voltage, -input_voltage)

        # calculate residuals which represent the noise (in LSB)
        # Q: Assumes an ideal binary ADCs, so just ideal quantization noise.
        residual_array = input_voltage_array / adc_gain + adc_offset - adc_data_array
        # noise floor RMS
        noise_std = np.std(residual_array)
        noise_percent = noise_std / 2 ** self.params["resolution"] * 100
        # ENOB (ideal resolution minus noise gives effective resolution)
        self.enob = self.params["resolution"] - np.log10(
            noise_std * np.sqrt(12)
        )  # log10 is Decibels,
        # ENOB result now reported in structured output

        if do_plot:
            plot_title = "ENOB Calculation"
            figure, ax = plt.subplots(2, 1, sharex=True, figsize=(10, 8))
            figure.suptitle(plot_title)
            # Disabled to fit in the redundancy chart on the dashboard view
            # plot adc data
            # ax[0].plot(time_array, input_voltage_array, label="Input voltage")
            # ax[0].legend(loc="upper right")
            ax[0].stairs(
                adc_data_array[: len(time_array) - 1],
                time_array,
                baseline=False,
                label="ADC code",
            )
            ax[0].legend(loc="upper right")
            ax[0].grid(True)
            ax[1].plot(
                time_array,
                residual_array,
                label="Residuals [LSB]\n Noise std = %.3f\n ENOB = %.2f"
                % (noise_std, self.enob),
            )
            ax[1].legend(loc="upper right")
            ax[1].grid(True)
            ax[1].set_ylim(-6, 6)
            return figure, ax

    def calculate_conversion_energy(self, do_plot=False, samples_per_bin=1):
        # samples_per_bin is now passed as parameter
        common_mode_input_voltage = 0.0
        input_voltage_data = np.arange(
            -self.diff_input_voltage_range / 2,
            self.diff_input_voltage_range / 2,
            self.lsb_size / samples_per_bin,
        )
        conversion_energy_array = np.empty(len(input_voltage_data))
        adc_data = np.empty(2 ** self.params["resolution"] * samples_per_bin)
        conversion_energy_average = 0

        # Calculating conversion energy - progress shown by tqdm
        for i in tqdm(range(len(input_voltage_data))):
            adc_data[i] = self.sample_and_convert(
                input_voltage_data[i] / 2 + common_mode_input_voltage,
                -input_voltage_data[i] / 2 + common_mode_input_voltage,
                do_calculate_energy=True,
            )
            # This is the core of the algorithm. At every input voltage, it records the energy used
            # Inside sample_and_convert: reset() is run one, and update()
            conversion_energy_array[i] = self.conversion_energy
        conversion_energy_average = np.average(conversion_energy_array)

        self.fom = conversion_energy_average / self.params["resolution"]
        self.average_conversion_energy = conversion_energy_average
        # Conversion energy and FOM results now reported in structured output

        if do_plot:
            figure, ax = plt.subplots(2, 1, sharex=True, figsize=(10, 8))
            # figure.subplots_adjust(bottom=0.5)
            y_ticks = range(
                -(2 ** (self.params["resolution"] - 1)),
                2 ** (self.params["resolution"] - 1) + 1,
                2 ** (self.params["resolution"] - 3),
            )
            # figure.tight_layout()
            # figure.suptitle('ADC Transfer Function')
            ax[0].title.set_text("ADC Transfer Function")
            ax[0].step(input_voltage_data, adc_data)
            ax[0].set_ylabel("ADC code")
            ax[0].set_yticks(y_ticks)
            ax[0].grid(True)
            # plot[0].legend()
            ax[1].title.set_text("Conversion energy")
            ax[1].step(
                input_voltage_data,
                conversion_energy_array * 1e12,
                label="Conversion energy\n average = %.3f pJ"
                % (conversion_energy_average * 1e12),
            )
            ax[1].set_ylabel("Energy [pJ]")
            ax[1].set_xlabel("Diff. input voltage [V]")
            ax[1].grid(True)
            ax[1].legend(loc="upper right")
            return figure, ax

    # redundancy should express, if a bit decision error is made on bit i, what error should be expected by the end
    # a bit positions weight determines the error it can introduce, so you'd like to make sure each bit is not larger than the remaining sum of bits.
    # what we are actually calculating is the 'error tolerance range'. Think about settling error.
    # So it we can tolerate 12.5% of a bit position, this means that the weight of the remaining bits should be 12.5% larger than current bit.
    def calculate_redundancy(self, do_plot=False):
        weights = self.dac.weights_array.tolist()
        # Calculate the cumulative sum from the end, then subtract the current value
        self.redundancy = []
        step_ticks = []
        for i, value in enumerate(weights[:-1]):
            self.redundancy.append(
                (sum(weights[i + 1 :]) - weights[i]) / sum(weights[i:]) * 100
            )
            step_ticks.append(i)
        # Error tolerance array now summarized as scalar average in structured output

        if do_plot:
            figure, ax = plt.subplots(1, 1, figsize=(10, 8))
            figure.suptitle("Error Tolerance @ step [i] in percent [%]")
            ax.plot(step_ticks, self.redundancy, label="Error tolerance [%]")
            ax.set_xlabel("Conversion Step [i]")
            ax.set_ylabel("Error Tolerance [%]")
            ax.set_ylim(-35, 55)
            ax.grid(True)
            ax.legend(loc="upper right")

            return figure, ax

    def ideal_conversion(
        self, input_voltage_p, input_voltage_n
    ):  # FIXME: This isn't implemented for non-binary! It's coloring the chart RED!
        # NOTE: tHI
        # ideal conversion
        ideal_adc_code = int(
            np.round((input_voltage_p - input_voltage_n) / self.lsb_size - 0.5)
        )
        # invert MSB: this CDAC switching scheme uses MSB = 1 to indicate positive input voltage
        ideal_adc_code ^= 2 ** (self.params["resolution"] - 1)

        return ideal_adc_code

    def plot_transfer_function(self):
        samples_per_bin = 10  # Default value, can be overridden in function call
        common_mode_input_voltage = 0.6
        input_voltage_data = np.arange(
            -self.diff_input_voltage_range / 2,
            self.diff_input_voltage_range / 2,
            self.lsb_size / samples_per_bin,
        )
        input_voltage_data_lsb = np.empty(len(input_voltage_data))
        adc_data = np.empty(2 ** self.params["resolution"] * samples_per_bin)
        for i in tqdm(range(len(input_voltage_data))):
            adc_data[i] = self.sample_and_convert(
                input_voltage_data[i] / 2 + common_mode_input_voltage,
                -input_voltage_data[i] / 2 + common_mode_input_voltage,
            )
            # adc_data[i] = self.ideal_conversion(input_voltage_data[i]/2, -input_voltage_data[i]/2)
            # input_voltage_data_lsb[i] = self.ideal_conversion(input_voltage_data[i]/2, -input_voltage_data[i]/2)

        input_voltage_data_lsb = input_voltage_data / self.lsb_size + 0.5

        figure, ax = plt.subplots(2, 1, sharex=True)
        # y_ticks = range(0, 2**self.params['resolution']+10, 2**(self.params['resolution']-2))
        # y_ticks = range(-2**(self.params['resolution']-1), 2**(self.params['resolution']-1)+1, 2**(self.params['resolution']-2))
        figure.suptitle("ADC Transfer Function")
        ax[0].step(input_voltage_data, adc_data, label="ADC transfer function")
        ax[0].plot(
            input_voltage_data,
            input_voltage_data_lsb,
            "r--",
            label="Ideal transfer function",
        )
        ax[0].set_ylabel("ADC code")
        # plot[0].set_yticks(y_ticks)
        ax[0].grid(True)
        ax[0].legend(loc="upper right")
        ax[1].set_xlabel("Diff. input voltage [V]")
        ax[1].step(
            input_voltage_data, adc_data - input_voltage_data_lsb, label="Residuals"
        )
        ax[1].set_ylabel("Error [LSB]")
        ax[1].grid(True)
        ax[1].legend(loc="upper right")

    def compile_results(
        self,
        builddir=None,
        testcase="default",
        values_per_bin=10,
        num_samples=1000,
        samples_per_bin=1,
    ):
        # Create results directory if not specified
        if builddir is None:
            builddir = os.path.join(os.getcwd(), "results")

        # Ensure builddir exists
        os.makedirs(builddir, exist_ok=True)

        # Ensure builddir ends with /
        if not builddir.endswith("/"):
            builddir += "/"

        # Create unified output function
        markdown_lines = []

        def output_both(text, markdown_only=False):
            """Output text to both STDOUT and markdown report"""
            if not markdown_only:
                print(text)
            markdown_lines.append(text)

        # Helper function to format aligned tables for terminal
        def format_table_row(
            col1, col2, col3, col1_width=35, col2_width=15, col3_width=8
        ):
            """Format a table row with proper spacing for terminal alignment"""
            return f"| {col1:<{col1_width}} | {col2:<{col2_width}} | {col3:<{col3_width}} |"

        # Header information (markdown-only for report, plain for terminal)
        output_both("# SAR ADC Analysis Report: " + testcase, markdown_only=True)
        output_both("", markdown_only=True)
        output_both("## System Configuration", markdown_only=True)
        output_both("", markdown_only=True)
        output_both("| Parameter | Value | Unit |", markdown_only=True)
        output_both("|-----------|--------|------|", markdown_only=True)
        output_both("Simulation Type: Behavioral Model Only", markdown_only=True)
        output_both("", markdown_only=True)

        # Terminal header
        print(f"SAR ADC Analysis Report: {testcase}")
        print("=" * 60)
        print()

        # System parameters with aligned formatting
        print("System Configuration:")
        print("-" * 60)
        print(format_table_row("Parameter", "Value", "Unit"))
        print(format_table_row("-" * 35, "-" * 15, "-" * 8))

        # Collect all parameters including the scattered ones
        params_data = [
            ("Simulation Type", "Behavioral Model Only", ""),
            ("Resolution", self.params["resolution"], "bits"),
            ("Sample frequency", f"{self.sampling_frequency / 1.0e6:.3f}", "Msps"),
            ("LSB size", f"{self.lsb_size / 1.0e-3:.3f}", "mV"),
            ("Cycles", self.dac.params["array_size"] + 1, ""),
            ("DAC array size", self.dac.params["array_size"], "bits"),
            (
                "DAC unit capacitance",
                f"{self.dac.params['unit_capacitance'] / 1e-15:.3f}",
                "fF",
            ),
            (
                "DAC parasitic capacitance",
                f"{self.dac.params['parasitic_capacitance'] / 1e-15:.3f}",
                "fF",
            ),
            (
                "DAC total capacitance",
                f"{self.dac.capacitance_sum_p / 1e-12:.3f}",
                "pF",
            ),
            ("DAC weights array", str(self.dac.weights_array), ""),
            ("DAC weights sum", self.dac.weights_sum, ""),
            ("DAC settling error", f"{self.dac.settling_time_error / 100:.2f}", "%"),
            ("DAC switching strategy", self.dac.params["switching_strat"], ""),
            (
                "Comparator noise",
                f"{self.comparator.params['threshold_voltage_noise'] * 1000:.3f}",
                "mV",
            ),
            (
                "Comparator offset",
                f"{self.comparator.params['offset_voltage'] * 1000:.3f}",
                "mV",
            ),
            (
                "Reference positive voltage",
                f"{self.dac.params['positive_reference_voltage']:.1f}",
                "V",
            ),
            (
                "Reference negative voltage",
                f"{self.dac.params['negative_reference_voltage']:.1f}",
                "V",
            ),
            (
                "Reference voltage noise",
                f"{self.dac.params['reference_voltage_noise'] * 1000:.3f}",
                "mV",
            ),
        ]

        # Output parameters with aligned formatting for terminal and markdown table for report
        output_both("## System Parameters", markdown_only=True)
        output_both("", markdown_only=True)
        output_both("| Parameter | Value | Unit |", markdown_only=True)
        output_both("|-----------|--------|------|", markdown_only=True)

        for param, value, unit in params_data:
            # Terminal with aligned formatting
            print(format_table_row(param, str(value), unit))
            # Markdown for report
            output_both(f"| {param} | {value} | {unit} |", markdown_only=True)

        print()
        output_both("", markdown_only=True)

        # Analysis execution header
        print("Analysis Execution:")
        print("-" * 60)
        output_both("## Analysis Execution", markdown_only=True)
        output_both("", markdown_only=True)

        # Run analyses and collect results
        figure1, ax1 = self.calculate_nonlinearity(
            do_plot=True, values_per_bin=values_per_bin
        )
        plt.tight_layout()
        plot_path = f"{builddir}{testcase}_nonlinearity.png"
        plt.savefig(plot_path, dpi=300, bbox_inches="tight")
        plt.close()

        figure2, ax2 = self.calculate_conversion_energy(
            do_plot=True, samples_per_bin=samples_per_bin
        )
        plt.tight_layout()
        plot_path2 = f"{builddir}{testcase}_energy.png"
        plt.savefig(plot_path2, dpi=300, bbox_inches="tight")
        plt.close()

        figure3, ax3 = self.calculate_enob(do_plot=True, num_samples=num_samples)
        plt.tight_layout()
        plot_path3 = f"{builddir}{testcase}_enob.png"
        plt.savefig(plot_path3, dpi=300, bbox_inches="tight")
        plt.close()

        figure4, ax4 = self.calculate_redundancy(do_plot=True)
        plt.tight_layout()
        plot_path4 = f"{builddir}{testcase}_redundancy.png"
        plt.savefig(plot_path4, dpi=300, bbox_inches="tight")
        plt.close()

        # Calculate average redundancy for scalar summary
        avg_redundancy = (
            sum([x for x in self.redundancy if x > 0])
            / len([x for x in self.redundancy if x > 0])
            if any(x > 0 for x in self.redundancy)
            else 0
        )

        # Performance results with aligned formatting
        print()
        print("Analysis Results:")
        print("-" * 60)
        print(format_table_row("Parameter", "Value", "Unit"))
        print(format_table_row("-" * 35, "-" * 15, "-" * 8))

        results_data = [
            ("DNL", f"{self.dnl:.3f}", "LSB"),
            ("INL", f"{self.inl:.3f}", "LSB"),
            ("ENOB", f"{self.enob:.2f}", "bits"),
            ("Conversion Energy", f"{self.average_conversion_energy * 1e12:.3f}", "pJ"),
            (
                "FOM (energy/conversion)",
                f"{self.average_conversion_energy / self.params['resolution'] / 1e-12:.2f}",
                "pJ",
            ),
            ("Average Error Tolerance", f"{avg_redundancy:.1f}", "%"),
        ]

        # Terminal output
        for param, value, unit in results_data:
            print(format_table_row(param, value, unit))

        # Plot generation summary for terminal
        print()
        print("Generated Plots:")
        print("-" * 60)
        print(f"Nonlinearity analysis: {plot_path}")
        print(f"Energy analysis: {plot_path2}")
        print(f"ENOB analysis: {plot_path3}")
        print(f"Redundancy analysis: {plot_path4}")
        print()

        # Markdown-only sections for report
        output_both(f"Generated nonlinearity plot: {plot_path}", markdown_only=True)
        output_both(f"Generated energy analysis plot: {plot_path2}", markdown_only=True)
        output_both(f"Generated ENOB analysis plot: {plot_path3}", markdown_only=True)
        output_both(
            f"Generated redundancy analysis plot: {plot_path4}", markdown_only=True
        )
        output_both("", markdown_only=True)

        output_both("## Performance Results", markdown_only=True)
        output_both("", markdown_only=True)
        output_both("| Parameter | Value | Unit |", markdown_only=True)
        output_both("|-----------|--------|------|", markdown_only=True)

        for param, value, unit in results_data:
            output_both(f"| {param} | {value} | {unit} |", markdown_only=True)

        output_both("", markdown_only=True)

        # Analysis plots section for markdown
        output_both("## Analysis Plots", markdown_only=True)
        output_both("", markdown_only=True)
        output_both("### Nonlinearity Analysis", markdown_only=True)
        output_both(
            f"![Nonlinearity Analysis]({testcase}_nonlinearity.png)", markdown_only=True
        )
        output_both("", markdown_only=True)
        output_both("### Energy Analysis", markdown_only=True)
        output_both(f"![Energy Analysis]({testcase}_energy.png)", markdown_only=True)
        output_both("", markdown_only=True)
        output_both("### ENOB Analysis", markdown_only=True)
        output_both(f"![ENOB Analysis]({testcase}_enob.png)", markdown_only=True)
        output_both("", markdown_only=True)
        output_both("### Redundancy Analysis", markdown_only=True)
        output_both(
            f"![Redundancy Analysis]({testcase}_redundancy.png)", markdown_only=True
        )
        output_both("", markdown_only=True)
        output_both("---", markdown_only=True)
        output_both("*Generated by SAR ADC Behavioral Model*", markdown_only=True)

        # Write markdown file
        markdown_file = f"{builddir}{testcase}_report.md"
        with open(markdown_file, "w") as f:
            f.write("\n".join(markdown_lines))

        output_both(f"Report saved to: {markdown_file}")
        return markdown_file

    def sample_and_convert(
        self,
        input_voltage_p,
        input_voltage_n,
        do_calculate_energy=False,
        do_plot=False,
        do_normalize_result=True,
    ):
        """
        Perform a sample and conversion using switching of differential CDAC.
        Currently supports BSS and monotonic strategies. Assumes that:
            1. The CDAC is front side sampling, and back side switching
            2. The backside switches can only choose between two potentials
            3. There is one cap per switch, and vice versa.
        """

        # init arrays with DAC output voltages and comparator results
        dac_out_p = np.empty(self.dac.params["array_size"] + 1, dtype="float64")
        dac_out_n = np.empty(self.dac.params["array_size"] + 1, dtype="float64")
        self.comp_result = []
        self.conversion_energy = 0
        total_consumed_charge = 0
        # for annotation
        ideal_comp_result = []

        # init DAC register
        # NOTE: This essentially sets the switching strategy, but only covers cases where:
        #   - The CDAC is front side sampling, and back side switching
        #   - The backside switches can only choose between two potentials
        #   - There is one cap per switch, and

        allowed_switching_strats = {
            "monotonic",
            "bss",
        }  # FIXME: janky data validation. Do it better

        if self.dac.params["switching_strat"] == "monotonic":
            reset_value = (
                2 ** self.dac.params["array_size"] - 1
            )  # all 1's, so monotonic switching

        elif self.dac.params["switching_strat"] == "bss":
            reset_value = (
                2 ** (self.dac.params["array_size"] - 1) - 1
            )  # mid-scale, so BSS bidirectional single side switching

        else:
            raise ValueError(
                f"switching_strat wasn't one of the allowed values: {allowed_switching_strats}"
            )

        del allowed_switching_strats  # python doesn't need cleanup, but do it anyways?

        # reset_value = 0  # all 0's
        # reset_value = 0xff
        self.dac.reset(reset_value=reset_value, do_calculate_energy=do_calculate_energy)
        # total_consumed_charge += self.dac.consumed_charge

        # get initial DAC register setting
        temp_register_p = self.dac.register_p
        temp_register_n = self.dac.register_n

        # sample input voltage and append voltages to array
        self.dac.sample(input_voltage_p, input_voltage_n)

        # store first DAC output voltage set for plotting
        dac_out_p[0] = self.dac.output_voltage_p
        dac_out_n[0] = self.dac.output_voltage_n

        # do first comparison to set MSB (sign) bit
        self.comp_result.append(
            1
            if self.comparator.compare(
                self.dac.output_voltage_p, self.dac.output_voltage_n
            )
            else 0
        )

        for i in range(
            self.dac.params["array_size"]
        ):  # SAR loop, bidirectional single side switching (BSS)
            # update DAC register depending on the previous conversion
            if (
                reset_value & 1 << (self.dac.params["array_size"] - i - 1) == 0
            ):  # switch direction depends on the reset value of the DAC register
                if self.comp_result[i] == 1:
                    temp_register_n += 1 << (
                        self.dac.params["array_size"] - i - 1
                    )  # increment n-side
                else:
                    temp_register_p += 1 << (
                        self.dac.params["array_size"] - i - 1
                    )  # increment p-side

            else:  # all other bits
                if self.comp_result[i] == 1:
                    temp_register_p -= 1 << (
                        self.dac.params["array_size"] - i - 1
                    )  # decrement p-side
                else:
                    temp_register_n -= 1 << (
                        self.dac.params["array_size"] - i - 1
                    )  # decrement n-side

            # update DAC output voltage by one bit and append to array, return values include noise and settling error
            temp_dac_output_p, temp_dac_output_n = self.dac.update(
                temp_register_p,
                temp_register_n,
                do_calculate_energy=do_calculate_energy,
            )
            # consumed charge is added up here. Note that only one cap position is examined per iteration of this loop (non-physical)
            total_consumed_charge += self.dac.consumed_charge
            dac_out_p[i + 1] = temp_dac_output_p
            dac_out_n[i + 1] = temp_dac_output_n
            # print('  conversion %2d, reg_p %s, reg_n %s, dac_out_p %f, dac_out_n %f' % (i+1, format(self.dac.register_p, '#014b'), format(self.dac.register_n, '#014b'), self.dac.output_voltage_p, self.dac.output_voltage_n))

            # compare
            if self.comparator.compare(
                temp_dac_output_p, temp_dac_output_n
            ):  # comparator output = 1
                self.comp_result.append(1)
            else:  # comparator output = 0
                self.comp_result.append(0)

        # calculate result
        result = self.calculate_result(self.comp_result, do_normalize_result)

        # TODO: Check the expression below (which is essentially C*V*V)
        self.conversion_energy = total_consumed_charge * (
            self.dac.params["positive_reference_voltage"]
            - self.dac.params["negative_reference_voltage"]
        )

        # print('conversion energy %e [pJ]' % (self.conversion_energy * 1e12))

        if do_plot:
            # calculate error free conversion for annotation
            ideal_adc_code = self.ideal_conversion(input_voltage_p, input_voltage_n)
            # convert ideal code to array with comparison results
            for i in range(self.cycles):
                ideal_comp_result.append(
                    1 if ideal_adc_code & (1 << (self.cycles - i - 1)) else 0
                )
            # use calculate_result() to get the ideal result from the ideal comparison results
            ideal_result = self.calculate_result(
                ideal_comp_result
            )  # FIXME: Based on binary only model. Also this variable isn't used?'

            figure, plot = plt.subplots(1, 1)
            legend_title = (
                # "Diff input voltage [%.3f, %.3f] \nADC code = %s \nIdeal code = %s "
                # % (input_voltage_p, input_voltage_n, result, ideal_result)
                "Diff input voltage [%.3f, %.3f] \nADC code = %.2f"  # FIXME: Disable ideal result being added, as it's based on binary only model.
                % (input_voltage_p, input_voltage_n, result)
            )
            figure.suptitle("SAR Conversion")
            plot.stairs(
                dac_out_p, range(self.cycles + 1), baseline=False, label="p-side"
            )
            plot.stairs(
                dac_out_n, range(self.cycles + 1), baseline=False, label="n-side"
            )
            plot.set_ylabel("DAC Output Voltage [V]")
            plot.set_ylim(-1.5, 1.5)
            plot.set_xticks(range(0, self.cycles + 1, 1))
            plot.set_xlabel("Conversion Cycle")
            plot.legend(title=legend_title)
            plot.grid(True)
            for i in range(self.cycles):
                color = (
                    # "red" if self.comp_result[i] != ideal_comp_result[i] else "black"
                    "black"  # FIXME: The ideal comp result is based on binary-only code. FIX this!
                )
                plot.annotate(
                    self.comp_result[i], xy=(i + 0.5, 0), ha="center", color=color
                )

        return result
