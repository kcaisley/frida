import yaml
import numpy as np	
import matplotlib.pyplot as plt
from tqdm import tqdm



class CDAC:
  def __init__(self, params):
    # capacitor array setup, numbers (re-)calculated in 'build_capacitor_array'
    self.unit_capacitance      = params['CDAC']['unit_capacitance']
    self.use_radix             = params['CDAC']['use_radix']
    self.radix                 = params['CDAC']['radix']
    self.parasitic_capacitance = params['CDAC']['parasitic_capacitance']
    self.use_systematic_errors = params['CDAC']['use_systematic_errors']
    self.resolution            = params['SAR_ADC']['resolution'] 
    
    self.total_capacitance_p   = 0  
    self.total_capacitance_n   = 0

    # voltage swing and settling time
    self.settling_time         = params['CDAC']['settling_time']
    self.positive_ref_voltage  = params['SAR_ADC']['positive_reference_voltage']
    self.negative_ref_voltage  = params['SAR_ADC']['negative_reference_voltage']
    
    self.output_voltage_p = 0
    self.output_voltage_n = 0
    self.output_voltage_no_error_p = 0
    self.output_voltage_no_error_n = 0
    self.register_p = 0
    self.register_n = 0
    self.consumed_charge = 0
    self.binary_range = 0

    self.update_parameters()
  
  def update_parameters(self):   # update depending parameters after changes
    self.array_size = self.resolution - 1   
    self.capacitor_array_p     = np.zeros(self.array_size)
    self.capacitor_array_n     = np.zeros(self.array_size)
    self.build_capacitor_array()
    self.use_settling_error  = params['CDAC']['use_settling_error']
    self.settling_time_error = np.exp(-1/(self.settling_time * params['SAR_ADC']['sampling_frequency'] * (self.array_size + 1)))
    self.lsb_size = (self.positive_ref_voltage - self.negative_ref_voltage) /(2**self.array_size)
    self.common_mode_voltage = (self.positive_ref_voltage - self.negative_ref_voltage) / 2

  def calculate_nonlinearity(self, do_plot = False):
    reg_data = np.arange(0, 2**(self.array_size), 1)
    dac_data = np.zeros(len(reg_data))
    dnl_data = np.zeros(len(reg_data)-1)
    inl_data = np.zeros(len(reg_data))

    print('DAC array size %d' % self.array_size)
    print('lsb size %e' % self.lsb_size)

    mid_scale = 0
    

    for reg in reg_data:
      self.reset(0)
      self.sample(0,0)
      dac_data[reg] = self.update(reg, 0) 

    
    dnl_data    = (np.diff(dac_data) - self.lsb_size) / self.lsb_size
    dac_dnl_std = np.std(dnl_data)
    inl_data    = np.cumsum(dnl_data)
    dac_inl_std = np.std(inl_data)
  
    if do_plot:
      figure, plot = plt.subplots(3, 1, sharex =	True)
      figure.suptitle('DAC Nonlinearity')
      plot[0].step(reg_data, dac_data, where = 'pre', label = 'DAC transfer function')
      #plot[0].set_xticks(range(reg_data[0], reg_data[len(reg_data)-1]+1,  self.array_size//4))
      plot[0].set_ylabel("Output voltage [V]")
      plot[0].grid(True)  
      plot[1].step(reg_data[:-1], dnl_data,  where = 'post', label = 'DNL = %.3f' % dac_dnl_std)
      if dac_dnl_std < 0.0001:
        plot[1].set_ylim(-1, 1)
      plot[1].set_ylabel("DNL [LSB]")
      plot[1].legend()
      plot[1].grid(True)  
      plot[2].step(reg_data[:-1], inl_data,  where = 'post', label = "INL = %.3f" % dac_inl_std)
      if dac_inl_std < 0.0001:
        plot[2].set_ylim(-1, 1)    
      plot[2].set_ylabel("INL [LSB]")  
      plot[2].legend()
      plot[2].set_xlabel('Digital code')  
      plot[2].grid(True)        

    return dac_dnl_std, dac_inl_std    

class CDAC_BSS(CDAC):
  def __init__(self, params):
    super().__init__(params)

  def build_capacitor_array(self):
      if self.use_radix:
        if self.radix != 2:
          # resize capacitor array size to the dynamic range of the nominal binary weighted capacitors
          self.array_size = int(np.round(self.array_size/np.log2(self.radix)))
          self.capacitor_array_p = np.zeros(self.array_size)
          self.capacitor_array_n = np.zeros(self.array_size)
  
        for i in range(self.array_size):
          self.capacitor_array_p[i] = self.radix**i * self.unit_capacitance
          self.capacitor_array_n[i] = self.radix**i * self.unit_capacitance
      else:
        self.array_size = self.resolution - 1 
        self.capacitor_array_p = np.array(params['CDAC']['capacitor_weights'][:self.array_size]) * self.unit_capacitance
        self.capacitor_array_n = np.array(params['CDAC']['capacitor_weights'][:self.array_size]) * self.unit_capacitance


      if self.use_systematic_errors:
        capacitor_errors_absolute = np.array(params['CDAC']['capacitor_systematic_errors'][:self.array_size]) / 100 * self.unit_capacitance
        capacitor_errors_weighted = capacitor_errors_absolute / np.sqrt(params['CDAC']['capacitor_weights'][:self.array_size])

        self.capacitor_array_p += capacitor_errors_weighted
        self.capacitor_array_n -= capacitor_errors_weighted

      self.total_capacitance_p = sum(self.capacitor_array_p) + self.parasitic_capacitance
      self.total_capacitance_n = sum(self.capacitor_array_n) + self.parasitic_capacitance
      # non-triviel scaling factor for non radix 2
      self.binary_range = self.total_capacitance_p / self.unit_capacitance
  
      # np.set_printoptions(precision=2)
      # print('Cycles: ', self.array_size+1)  
      # print('Capacitor array: ', self.capacitor_array_p)
      # print('Total capacitance: ', self.total_capacitance_p)
      # print('DAC binary range %d' % self.binary_range)  
      
  def reset(self, reset_value, do_calculate_energy = False):
    register_p = reset_value # 2**(self.array_size-1)-1
    register_n = reset_value # 2**(self.array_size-1)-1 
    self.update(register_p, register_n, do_calculate_energy=do_calculate_energy)  
    # print('reset charge %e' % self.dac.consumed_charge)

  def sample(self, input_p, input_n):	
    # top plate sampling: DAC output voltage = input voltage
    self.output_voltage_no_error_p = input_p 
    self.output_voltage_no_error_n = input_n 
    self.output_voltage_p = input_p 
    self.output_voltage_n = input_n 
  
  def update(self, register_p, register_n, do_calculate_energy=False):
    delta_backplane_voltage = self.positive_ref_voltage - self.negative_ref_voltage
    delta_output_voltage_p = 0
    delta_output_voltage_n = 0
    self.consumed_charge = 0

    for i in range(self.array_size):
      current_capacitor_p = self.capacitor_array_p[i]
      current_capacitor_n = self.capacitor_array_n[i]

      if (register_p & (1 << i)) > (self.register_p & (1 << i)):
        delta_output_voltage_p += current_capacitor_p / self.total_capacitance_p * delta_backplane_voltage 
      elif (register_p & (1 << i)) < (self.register_p & (1 << i)):
        delta_output_voltage_p -= current_capacitor_p / self.total_capacitance_p * delta_backplane_voltage 

      if (register_n & (1 << i)) > (self.register_n & (1 << i)):
        delta_output_voltage_n += current_capacitor_n / self.total_capacitance_n * delta_backplane_voltage 
      elif (register_n & (1 << i)) < (self.register_n & (1 << i)):
        delta_output_voltage_n -= current_capacitor_n / self.total_capacitance_n * delta_backplane_voltage

    if do_calculate_energy:
      for i in range(self.array_size):
        current_capacitor_p = self.capacitor_array_p[i]
        current_capacitor_n = self.capacitor_array_n[i]
        if delta_output_voltage_p > 0:
          if (register_p & (1 << i)) == 0:
            self.consumed_charge += current_capacitor_p * delta_output_voltage_p
        else:
          if (register_p & (1 << i)) != 0:
            self.consumed_charge -= current_capacitor_p * delta_output_voltage_p

        if delta_output_voltage_n > 0:
          if (register_n & (1 << i)) == 0:
            self.consumed_charge += current_capacitor_n * delta_output_voltage_n
        else:
          if (register_n & (1 << i)) != 0:
            self.consumed_charge -= current_capacitor_n * delta_output_voltage_n

    self.output_voltage_no_error_p += delta_output_voltage_p
    self.output_voltage_no_error_n += delta_output_voltage_n

    if self.use_settling_error:
      self.output_voltage_p += delta_output_voltage_p * (1 - self.settling_time_error)
      self.output_voltage_n += delta_output_voltage_n * (1 - self.settling_time_error)
    else:
      self.output_voltage_p = self.output_voltage_no_error_p
      self.output_voltage_n = self.output_voltage_no_error_n

    self.register_p = register_p
    self.register_n = register_n

    return self.output_voltage_p - self.output_voltage_n

class COMPARATOR:
  def __init__(self, params):
    self.use_offset_error = params['COMPARATOR']['use_offset_error']  
    self.offset_voltage   = params['COMPARATOR']['offset_voltage']
    self.common_mode_dependent_offset_gain  = params['COMPARATOR']['common_mode_dependent_offset_gain']
    self.use_noise_error  = params['COMPARATOR']['use_noise_error']
    self.noise_voltage    = params['COMPARATOR']['noise_voltage']

  def compare(self, input_voltage_p, input_voltage_n):
    if self.use_offset_error:
      common_mode_offset_voltage = (input_voltage_p + input_voltage_n)/2 * self.common_mode_dependent_offset_gain
    else:
      common_mode_offset_voltage = 0

    if self.use_noise_error:
      noise_voltage = np.random.normal(0, self.noise_voltage)
    else:
      noise_voltage = 0

    return input_voltage_p > input_voltage_n + self.offset_voltage + common_mode_offset_voltage + noise_voltage

class SAR_ADC:
  def __init__(self, params):
    self.resolution = params['SAR_ADC']['resolution']
    self.sampling_frequency = params['SAR_ADC']['sampling_frequency'] 
    self.positive_ref_voltage = params['SAR_ADC']['positive_reference_voltage']
    self.negative_ref_voltage = params['SAR_ADC']['negative_reference_voltage']
    self.dac = CDAC_BSS(params) 
    self.cycles = self.dac.array_size + 1
    self.clock_period = 1/(self.sampling_frequency * self.cycles)
    self.redundancy = self.cycles - self.resolution
    self.diff_input_voltage_range = 2 * (self.positive_ref_voltage - self.negative_ref_voltage)
    self.lsb_size = self.diff_input_voltage_range / 2**self.resolution 
    self.comparator = COMPARATOR(params)
    self.input_voltage_p = 0
    self.input_voltage_n = 0
    self.comp_result = []
    self.conversion_energy = 0
    self.midscale = 2**(self.resolution-1) 

    # performance metrics
    self.dnl  = 0
    self.inl  = 0
    self.enob = 0
    self.average_conversion_energy = 0
    self.fom = 0

  def update_parameters(self):  # update depending parameters after changes 
    self.dac.update_parameters()
    self.cycles = self.dac.array_size + 1
    self.clock_period = 1/(self.sampling_frequency * self.cycles)
    self.redundancy = self.cycles - self.resolution
    self.diff_input_voltage_range = 2 * (self.positive_ref_voltage - self.negative_ref_voltage)
    self.lsb_size = self.diff_input_voltage_range / 2**self.resolution 
    self.midscale = 2**(self.resolution-1) 
    self.dnl  = 0
    self.inl  = 0
    self.enob = 0
    self.average_conversion_energy = 0   

  def print_parameter_list(self):
    b = "\033[1m"
    n = "\033[0m"
    parameters = ""
    parameters += b+"Design parameters\n"+n
    parameters += f" Resolution   {self.resolution}\n"
    parameters += f" Sample freq. {self.sampling_frequency/1.0e6:.0f} Msps\n"
    parameters += f" LSB size     {self.lsb_size/1.0e-3:.3f} mV\n"
    parameters += f" Redundancy   {self.redundancy}\n"
    if self.dac.use_radix:
      parameters += f" DAC radix    {self.dac.radix:.1f}\n"
    parameters += f" DAC capacitor array size  {self.dac.array_size}\n"
    parameters += f" DAC unit capacitance      {self.dac.unit_capacitance/1e-15:.1f} fF\n"
    parameters += f" DAC parasitic capacitance {self.dac.parasitic_capacitance/1e-15:.1f} fF\n"
    parameters += f" DAC total capacitance     {self.dac.total_capacitance_p/1e-12:.2f} pF\n"
    # TBD
    # if self.dac.use_systematic_errors:
    #   parameters += f" DAC systematic error {self.dac.settling_time_error:.2e}\n"    
    if self.dac.use_settling_error:
      parameters += f" DAC settling error        {self.dac.settling_time_error:.2e}\n"
    if self.comparator.use_noise_error:
      parameters += f" Comparator noise          {self.comparator.noise_voltage:.2e}\n"
    if self.comparator.use_offset_error:
      parameters += f" Comparator offset         {self.comparator.offset_voltage:.2e}\n"
    parameters += b+"Performance\n"+n
    parameters += f" DNL   {self.dnl:.2f}\n"
    parameters += f" INL   {self.inl:.2f}\n"
    parameters += f" ENOB  {self.enob:.2f}\n"
    parameters += f" FOM   {self.average_conversion_energy / self.resolution / 1e-12:.2e} pJ\n"
    return parameters
     
  def sample_and_convert_bss(self, input_voltage_p, input_voltage_n, do_calculate_energy = False,  do_plot = False):	
    # init arrays with DAC output voltages and comparator results
    dac_out_p = np.empty(self.dac.array_size + 1, dtype='float64')
    dac_out_n = np.empty(self.dac.array_size + 1, dtype='float64')
    self.comp_result = []
    self.conversion_energy = 0
    total_consumed_charge = 0
    # for annotation
    ideal_comp_result = []
  
    # init DAC register
    reset_value = 2**(self.dac.array_size-1)-1 # mid-scale
    # reset_value = 2**self.dac.array_size-1  # all 1's  
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
    self.comp_result.append(1 if self.comparator.compare(self.dac.output_voltage_p, self.dac.output_voltage_n) else 0)  
    
    for i in range(self.dac.array_size):   # SAR loop, bidirectional single side switching (BSS)
      
      # update DAC register depending on the previous conversion
      if (reset_value &  1 << (self.dac.array_size-i-1) == 0): # switch direction depends on the reset value of the DAC register
        if self.comp_result[i] == 1:
          temp_register_n += 1 << (self.dac.array_size-i-1) # increment n-side
        else:
          temp_register_p += 1 << (self.dac.array_size-i-1) # increment p-side

      else: # all other bits
        if self.comp_result[i] == 1:
          temp_register_p -= 1 << (self.dac.array_size-i-1) # decrement p-side
        else:
          temp_register_n -= 1 << (self.dac.array_size-i-1) # decrement n-side
   
      # update DAC output voltage and append to array
      self.dac.update(temp_register_p, temp_register_n, do_calculate_energy = do_calculate_energy)
      total_consumed_charge += self.dac.consumed_charge
      dac_out_p[i+1] = self.dac.output_voltage_p
      dac_out_n[i+1] = self.dac.output_voltage_n
      # print('  conversion %2d, reg_p %s, reg_n %s, dac_out_p %f, dac_out_n %f' % (i+1, format(self.dac.register_p, '#014b'), format(self.dac.register_n, '#014b'), self.dac.output_voltage_p, self.dac.output_voltage_n))
      
      # compare
      if self.comparator.compare(self.dac.output_voltage_p, self.dac.output_voltage_n): # comparator output = 1
        self.comp_result.append(1)
      else: # comparator output = 0
        self.comp_result.append(0)
    
    # calculate result  
    result = self.calculate_result(self.comp_result) 
    self.conversion_energy = total_consumed_charge * (self.dac.positive_ref_voltage - self.dac.negative_ref_voltage)
    # print('conversion energy %e [pJ]' % (self.conversion_energy * 1e12))
             
    if do_plot:
      # calculate error free conversion for annotation
      ideal_adc_code = self.ideal_conversion(input_voltage_p, input_voltage_n)
      # convert ideal code to array with comparison results
      for i in range(self.cycles):
        ideal_comp_result.append(1 if ideal_adc_code & (1 << (self.cycles - i -1)) else 0)
      # use calculate_result() to get the ideal result from the ideal comparison results
      ideal_result = self.calculate_result(ideal_comp_result) 

      figure, plot = plt.subplots(1, 1)
      legend_title = ('Diff input voltage [%.3f, %.3f] \nADC code = %s \nIdeal code = %s ' % (input_voltage_p, input_voltage_n, result, ideal_result))
      figure.suptitle('SAR Conversion')
      plot.stairs(dac_out_p, range(self.cycles+1), baseline = False, label = "p-side")
      plot.stairs(dac_out_n, range(self.cycles+1), baseline = False, label = "n-side")
      plot.set_ylabel("DAC Output Voltage [V]")
      plot.set_ylim(-1.5, 1.5)    
      plot.set_xticks(range(0, self.cycles + 1, 1))
      plot.set_xlabel("Conversion Cycle")
      plot.legend(title=legend_title)
      plot.grid(True)  
      for i in range(self.cycles):
        color = 'red' if self.comp_result[i] != ideal_comp_result[i] else 'black'  
        plot.annotate(self.comp_result[i], xy=(i+0.5, 0), ha='center', color=color)

    return result

  def calculate_result(self, comp_result):
    result = 0  # initialize result

    if (self.dac.use_radix):
      radix = self.dac.radix
    else:
      radix = 2

    # calculate absolute value of result
    for i in range(self.cycles):
      result += (2*comp_result[i]-1) * radix**(self.cycles-i-2)    
    
    result += 0.5  # round to nearest integer
       
    # result -= radix**(self.cycles-1)  # convert to signed value
    # result *= self.lsb_size # convert to voltage

    if (radix != 2):
      radix_scale_factor = 2**(self.resolution-1) / self.dac.binary_range
      result = result * radix_scale_factor
    return (result)

  def calculate_nonlinearity(self, do_plot = False):
    values_per_bin = 100 # number of values per bin for DNL/INL calculation
    lower_excluded_bins = 2  # lower bound for DNL/INL calculation in LSB
    upper_excluded_bins = 2  # upper bound for DNL/INL calculation in LSB distance from full scale

    # helper variables
    min_code  = - 2**(self.resolution-1) # 0 
    max_code  =   2**(self.resolution-1)-1# 2**(self.resolution)-1
    num_codes =   2**self.resolution
    lower_index_boundary = lower_excluded_bins
    upper_index_boundary = num_codes - upper_excluded_bins
    
    # data structures for DNL/INL calculation
    code_density_hist = np.empty(num_codes)
    bin_edges = []
    dnl_data = np.empty(num_codes)
    inl_data = np.empty(num_codes)
    adc_data = np.empty(num_codes * values_per_bin)
    input_voltage_data = np.arange(-self.diff_input_voltage_range/2, self.diff_input_voltage_range/2, self.lsb_size/values_per_bin)

     # do the conversions
    print('Calculating DNL/INL ...')
    for i in tqdm(range(len(input_voltage_data))):
      adc_data[i] = self.sample_and_convert_bss(input_voltage_data[i]/2.0, -input_voltage_data[i]/2.0) 

    #print('adc_data ', adc_data)

    # calculate code density histogram
    code_density_hist, bin_edges = np.histogram(adc_data, bins = num_codes, range = (min_code, max_code))   
    code_density_hist = code_density_hist[lower_index_boundary:upper_index_boundary]
    bin_edges         = bin_edges[lower_index_boundary:upper_index_boundary+1]
    average_bin_count = np.average(code_density_hist)

    # calculate differential nonlinearity
    dnl_data = (code_density_hist - average_bin_count) / average_bin_count
    dnl_data[:lower_index_boundary] = 0
    dnl_data[upper_index_boundary:] = 0
    dnl_sigma = np.std(dnl_data)

    # calculate integral nonlinearity 
    inl_data = np.cumsum(dnl_data)
    inl_sigma = np.std(inl_data)

    
    if do_plot:
      x_ticks = range(min_code, max_code+10, 2**(self.resolution-3))
      plot_title = 'ADC Nonlinearity \n (settling error = %s, systematic errors = %s, offset error = %s)' % (self.dac.use_settling_error, self.dac.use_systematic_errors, self.comparator.use_offset_error) 
      figure, plot = plt.subplots(3, 1, sharex=True,)
      figure.suptitle(plot_title)
      plot[0].stairs(code_density_hist, bin_edges, baseline = None)
      plot[0].set_xticks(x_ticks)
      plot[0].set_ylabel("Code density")
      plot[0].grid(True)  
      plot[1].stairs(dnl_data, bin_edges, baseline = None, label = "DNL sigma = %.3f" % dnl_sigma)
      plot[1].set_ylim(-2, 2)
      plot[1].set_ylabel("DNL [LSB]")
      plot[1].legend()
      plot[1].grid(True)  
      plot[2].stairs(inl_data, bin_edges, baseline = None, label = "INL sigma = %.3f" % inl_sigma)
      plot[2].set_ylim(-2, 2)    
      plot[2].set_ylabel("INL [LSB]")  
      plot[2].legend()
      plot[2].set_xlabel('ADC code')  
      plot[2].grid(True)        
    
    self.dnl = dnl_sigma
    self.inl = inl_sigma       

  def calculate_enob(self, do_plot = False):
    # return (snr - 1.76)/6.02
    frequency   = 1e4
    amplitude   = 0.59
    offset      = 0
    num_samples = 10000
    adc_gain    = self.diff_input_voltage_range / 2 / 2**self.resolution
    adc_offset  = 0

    time_array          = np.arange(start=0, stop=num_samples/self.sampling_frequency, step=1/self.sampling_frequency)
    input_voltage_array = np.empty(len(time_array))
    adc_data_array      = np.empty(len(time_array))

    # sample sine wave
    print('Calculating ENOB ...')
    for i in tqdm(range(len(time_array))):
      input_voltage = offset + amplitude*np.sin(2*np.pi*frequency*time_array[i])
      input_voltage_array[i] = input_voltage
      adc_data_array[i] = self.sample_and_convert_bss(input_voltage,  -input_voltage)

    # calculate residuals which represent the noise (in LSB)
    residual_array = input_voltage_array/adc_gain + adc_offset - adc_data_array 
    # noise floor RMS
    noise_std = np.std(residual_array)
    noise_percent = noise_std/2**self.resolution * 100
    # ENOB
    enob = self.resolution - np.log10(noise_std*np.sqrt(12))

    
    if do_plot:
      plot_title = 'ENOB Calculation\n (settling error = %s, systematic errors = %s, offset error = %s)' % (self.dac.use_settling_error, self.dac.use_systematic_errors, self.comparator.use_offset_error) 
      figure, plot = plt.subplots(3, 1, sharex=True)
      figure.suptitle(plot_title)    
      # plot adc data
      plot[0].plot(time_array, input_voltage_array, label = 'Input voltage')
      plot[0].legend()
      plot[1].stairs(adc_data_array[:len(time_array)-1], time_array, baseline = False, label = 'ADC code')
      plot[1].legend()
      plot[2].plot(time_array, residual_array, label = 'Residuals [LSB]\n Noise std = %.3f\n ENOB = %.2f' % (noise_std, enob))
      plot[2].legend()
      print('ENOB %.2f' % enob)
    
    self.enob = enob
    return enob

  def calculate_conversion_energy(self, do_plot = False):
    samples_per_bin = 1
    common_mode_input_voltage = 0.0
    input_voltage_data = np.arange(-self.diff_input_voltage_range/2, self.diff_input_voltage_range/2, self.lsb_size/samples_per_bin)
    conversion_energy_array = np.empty(len(input_voltage_data))
    adc_data = np.empty(2**self.resolution*samples_per_bin)
    conversion_energy_average = 0

    print('Calculating conversion energy ...')
    for i in tqdm(range(len(input_voltage_data))):
      adc_data[i] = self.sample_and_convert_bss(input_voltage_data[i]/2+common_mode_input_voltage, -input_voltage_data[i]/2+common_mode_input_voltage, do_calculate_energy=True) 
      conversion_energy_array[i] = self.conversion_energy
    conversion_energy_average = np.average(conversion_energy_array)
  
    if do_plot:
      figure, plot = plt.subplots(2, 1, sharex=True)
      y_ticks = range(0, 2**self.resolution+10, 2**(self.resolution-3))
      figure.suptitle('ADC Transfer Function')
      plot[0].stairs(adc_data[:len(input_voltage_data)-1], input_voltage_data, baseline = None, label = 'ADC transfer function')
      plot[0].set_ylabel("ADC code")
      plot[0].set_yticks(y_ticks)
      plot[0].grid(True)  
      plot[0].legend()
      plot[1].plot(input_voltage_data, conversion_energy_array * 1e12, label='Conversion energy\n average = %.3f pJ' % (conversion_energy_average * 1e12))  
      plot[1].set_ylabel("Energy [pJ]")
      plot[1].set_xlabel('Diff. input voltage [V]')  
      plot[1].grid(True)
      plot[1].legend()

      print('conversion energy average P[pJ] %e' % (conversion_energy_average * 1e12))
      print('FOM[pJ] %e' % (conversion_energy_average / adc.resolution * 1e12))

    self.fom = conversion_energy_average / adc.resolution
    self.average_conversion_energy = conversion_energy_average

  def ideal_conversion(self, input_voltage_p, input_voltage_n): 
    # ideal conversion
    ideal_adc_code = int(np.round((input_voltage_p - input_voltage_n) / self.lsb_size - 0.5)) 
    # invert MSB: this CDAC switching scheme uses MSB = 1 to indicate positive input voltage
    ideal_adc_code ^= 2**(self.resolution-1) 

    return ideal_adc_code

  def plot_transfer_function(self):
    samples_per_bin = 100
    common_mode_input_voltage = 0.6
    input_voltage_data = np.arange(-self.diff_input_voltage_range/2, self.diff_input_voltage_range/2, self.lsb_size/samples_per_bin)
    input_voltage_data_lsb = np.empty(len(input_voltage_data))
    adc_data = np.empty(2**self.resolution*samples_per_bin)
    for i in tqdm(range(len(input_voltage_data))):
      adc_data[i] = self.sample_and_convert_bss(input_voltage_data[i]/2+common_mode_input_voltage, -input_voltage_data[i]/2+common_mode_input_voltage) 
      #adc_data[i] = self.ideal_conversion(input_voltage_data[i]/2, -input_voltage_data[i]/2) 
      # input_voltage_data_lsb[i] = self.ideal_conversion(input_voltage_data[i]/2, -input_voltage_data[i]/2) 

    input_voltage_data_lsb = input_voltage_data / self.lsb_size + 0.5

    figure, plot = plt.subplots(2, 1, sharex=True)
   # y_ticks = range(0, 2**self.resolution+10, 2**(self.resolution-2))
   # y_ticks = range(-2**(self.resolution-1), 2**(self.resolution-1)+1, 2**(self.resolution-2))
    figure.suptitle('ADC Transfer Function')
    plot[0].step(input_voltage_data, adc_data, label = 'ADC transfer function')
    plot[0].plot(input_voltage_data, input_voltage_data_lsb, 'r--', label = 'Ideal transfer function')
    plot[0].set_ylabel("ADC code")
    #plot[0].set_yticks(y_ticks)
    plot[0].grid(True)  
    plot[0].legend()
    plot[1].set_xlabel('Diff. input voltage [V]')  
    plot[1].step(input_voltage_data, adc_data-input_voltage_data_lsb, label='Residuals')
    plot[1].set_ylabel("Error [LSB]")
    plot[1].grid(True)
    plot[1].legend()

if __name__ == "__main__":

  # Load parameters from YAML file
  with open('adc_sim.yaml', 'r') as file:
    params = yaml.safe_load(file)

  adc = SAR_ADC(params)
 
  # below code blocks can be individually used for visualization and debugging

  # plot SAR iterations 
  # adc.sample_and_convert_bss(  0.000, 0.0, do_plot=True, do_calculate_energy=True)
  
  # calculate conversion energy
  # adc.calculate_conversion_energy(do_plot=True)
  
  # plot transfer function
  # adc.plot_transfer_function()
  
  # calculate DNL/INL
  # adc.calculate_nonlinearity(do_plot=True)
  
  # CDAC only
  # dac = CDAC_BSS(params)
  # dac.calculate_nonlinearity(do_plot=True)

  # here starts the quantification of the performance metrices

  # compare binary and non-binary weighted capacitors 
  adc.dac.use_radix = False 
  adc.update_parameters()
  print('binary weighted capacitors')
  adc.calculate_nonlinearity(do_plot=True)
  adc.calculate_enob()
  print(adc.print_parameter_list())
 
  adc.dac.use_radix = True
  adc.dac.radix = 1.8
  adc.update_parameters()
  print('non-binary weighted capacitors')
  adc.calculate_nonlinearity(do_plot=True)
  adc.calculate_enob()
  print(adc.print_parameter_list())

  # parametric ENOB calculation
  # adc.comparator.use_noise_error = True
  # for noise in np.arange(0, 10, 2):
  #   adc.comparator.noise_voltage = noise/1e3
  #   enob = adc.calculate_enob()
  #   print('noise %.3f [mV], ENOB %.2f' % (noise, enob))
 
 
  # print(adc.print_parameter_list())
  plt.show()

