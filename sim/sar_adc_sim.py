import yaml
import numpy as np	
import matplotlib.pyplot as plt
from tqdm import tqdm

# Load parameters from YAML file
with open('adc_sim.yaml', 'r') as file:
  params = yaml.safe_load(file)

class CDAC:
  def __init__(self, resolution, sampling_frequency = 1e-9, positive_ref_voltage = 1, negative_ref_voltage = -1):
    # capacitor array setup, numbers (re-)calculated in 'build_capacitor_array'
    self.unit_capacitance      = params['CDAC']['unit_capacitance']
    self.use_radix             = params['CDAC']['use_radix']
    self.radix                 = params['CDAC']['radix']
    self.parasitic_capacitance = params['CDAC']['parasitic_capacitance']
    self.use_systematic_errors = params['CDAC']['use_systematic_errors']
    self.resolution            = resolution 
    self.array_size            = resolution - 1   
    self.capacitor_array_p     = np.zeros(self.array_size)
    self.capacitor_array_n     = np.zeros(self.array_size)
    self.total_capacitance_p   = 0  
    self.total_capacitance_n   = 0
    self.build_capacitor_array()

    # voltage swing and settling time
    self.settling_time         = params['CDAC']['settling_time']
    self.positive_ref_voltage  = positive_ref_voltage
    self.negative_ref_voltage  = negative_ref_voltage
    self.common_mode_voltage   = (positive_ref_voltage - negative_ref_voltage) / 2
    self.lsb_size = (self.positive_ref_voltage - self.negative_ref_voltage) / 2**resolution
    
    self.output_voltage_p = 0
    self.output_voltage_n = 0
    self.output_voltage_no_error_p = 0
    self.output_voltage_no_error_n = 0
    self.register_p = 0
    self.register_n = 0

    self.consumed_charge = 0

    self.use_settling_error  = params['CDAC']['use_settling_error']
    self.settling_time_error = np.exp(-1/(self.settling_time * sampling_frequency * (self.array_size + 1)))

  def update_parameters(self):   # update depending parameters after changes
    self.build_capacitor_array()
    self.lsb_size = (self.positive_ref_voltage - self.negative_ref_voltage) / 2**self.resolution
    self.common_mode_voltage = (self.positive_ref_voltage - self.negative_ref_voltage) / 2

  def build_capacitor_array(self):
    if self.use_radix:
      if self.radix != 2:
        # resize capacitor array size to the dynamic range of the nominal binary weighted capacitors
        self.array_size = int(np.ceil(self.array_size/np.log2(self.radix)))
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
    
    # np.set_printoptions(precision=2)
    # print('Cycles: ', self.array_size+1)  
    # print('Capacitor array: ', self.capacitor_array_p)
    # print('Total capacitance: ', self.total_capacitance_p)
    # print('capacitor_errors_weighted: ', capacitor_errors_weighted)

  def top_plate_sample(self, input_p, input_n):	
    # top plate sampling: DAC output voltage = input voltage
    self.output_voltage_no_error_p = input_p 
    self.output_voltage_no_error_n = input_n 
    self.output_voltage_p = input_p 
    self.output_voltage_n = input_n 
  
  def reset(self, do_calculate_energy = False):
    # init DAC register to mid-scale 0b01111...111
    register_p = 2**(self.array_size-1)-1
    register_n = 2**(self.array_size-1)-1 
    self.update(register_p, register_n, do_calculate_energy=do_calculate_energy)  
    # print('reset charge %e' % self.dac.consumed_charge)

  def update(self, register_p, register_n, do_calculate_energy = False): 
    # helper variables
    delta_backplane_voltage = self.positive_ref_voltage - self.negative_ref_voltage
    
    delta_output_voltage_p = 0
    delta_output_voltage_n = 0
    self.consumed_charge   = 0
    
    # calculate output voltage change induced by switched bottom plate voltages

    # broadcast implementation: slower than loop !!!
    # delta_register_array_p = np.array([int((register_p >> i) & 1) - int((self.register_p >> i) & 1) for i in range(self.array_size)], dtype='int')
    # delta_register_array_n = np.array([int((register_n >> i) & 1) - int((self.register_n >> i) & 1) for i in range(self.array_size)], dtype='int')
    # delta_output_voltage_p = np.sum(delta_register_array_p * self.capacitor_array_p/self.total_capacitance_p * delta_backplane_voltage)
    # delta_output_voltage_n = np.sum(delta_register_array_n * self.capacitor_array_n/self.total_capacitance_n * delta_backplane_voltage)

    for i in range(self.array_size):
      current_capacitor_p = self.capacitor_array_p[i]
      current_capacitor_n = self.capacitor_array_n[i]

      if   (register_p & (1 << i)) > (self.register_p & (1 << i)):
        delta_output_voltage_p += current_capacitor_p/self.total_capacitance_p * delta_backplane_voltage
      elif (register_p & (1 << i)) < (self.register_p & (1 << i)):
        delta_output_voltage_p -= current_capacitor_p/self.total_capacitance_p * delta_backplane_voltage

      if   (register_n & (1 << i)) > (self.register_n & (1 << i)):
        delta_output_voltage_n += current_capacitor_n/self.total_capacitance_n * delta_backplane_voltage
      elif (register_n & (1 << i)) < (self.register_n & (1 << i)):
        delta_output_voltage_n -= current_capacitor_n/self.total_capacitance_n * delta_backplane_voltage

    if do_calculate_energy:
      # calculate charge delivered from VREF supply dependent on output voltage change of the DAC:
      #   for positive output voltage change: change in DAC output voltage * summed capacitance connected to neg. VREF (GND)
      #   for negative output voltage change: change in DAC output voltage * summed capacitance connected to pos. VREF 

      for i in range(self.array_size):
        current_capacitor_p = self.capacitor_array_p[i]
        current_capacitor_n = self.capacitor_array_n[i]
        if   (delta_output_voltage_p > 0): # switch from neg. VREF (GND) to pos. VREF       
          if   (register_p & (1 << i) == 0):  # sum over capacitors connected to neg. VREF (GND)
            self.consumed_charge += current_capacitor_p * delta_output_voltage_p
        
        else: # negative delta_output_voltage, switch from pos. VREF to neg. VREF       
          if   (register_p & (1 << i) != 0):  # sum over capacitors connected to pos. VREF
            self.consumed_charge -= current_capacitor_p * delta_output_voltage_p

        if   (delta_output_voltage_n > 0): # switch from neg. VREF (GND) to pos. VREF       
          if   (register_n & (1 << i) == 0):  # sum over capacitors connected to neg. VREF
            self.consumed_charge += current_capacitor_n * delta_output_voltage_n

        else: # switch from pos. VREF to neg. VREF       
          if   (register_n & (1 << i) != 0):  # sum over capacitors connected to pos. VREF
            self.consumed_charge -= current_capacitor_n * delta_output_voltage_n
        
    # ideal output voltage
    self.output_voltage_no_error_p += delta_output_voltage_p
    self.output_voltage_no_error_n += delta_output_voltage_n  

    if self.use_settling_error:
      # update output voltage, including settling error
      self.output_voltage_p += delta_output_voltage_p * (1-self.settling_time_error)
      self.output_voltage_n += delta_output_voltage_n * (1-self.settling_time_error)
    else:   
      self.output_voltage_p = self.output_voltage_no_error_p
      self.output_voltage_n = self.output_voltage_no_error_n

    # update register
    self.register_p = register_p
    self.register_n = register_n

    return self.output_voltage_p-self.output_voltage_n

  def calculate_nonlinearity(self, do_plot = False):
    dnl_data = np.empty(2**self.array_size)
    inl_data = np.empty(2**self.array_size)
    dac_data = np.empty(2**self.array_size)
    reg_data = np.arange(2**self.array_size)

    mid_scale = 2**(self.array_size-1)
    
    self.top_plate_sample(0,0)

    for reg in reg_data:
      if (reg < mid_scale):
        dac_data[reg] = self.update(0, mid_scale - reg - 1) 
      else:
        dac_data[reg] = self.update(reg - mid_scale, 0)
    
    dnl_data    = np.diff(dac_data) - self.lsb_size
    dac_dnl_std = np.std(dnl_data)
    inl_data    = np.cumsum(dnl_data)
    dac_inl_std = np.std(inl_data)
  
    if do_plot:
      figure, plot = plt.subplots(3, 1)
      figure.suptitle('DAC Nonlinearity')
      plot[0].stairs(dac_data[:len(reg_data)-1], reg_data, baseline = None)
      #plot[0].set_xticks(range(0, self.bin_count,  self.bin_count>>3))
      plot[0].set_ylabel("Output voltage [V]")
      plot[0].grid(True)  
      plot[1].stairs(dnl_data[:len(reg_data)], reg_data, baseline = None, label = "DNL avg = %.3f" % dac_dnl_std)
      if dac_dnl_std < 0.001:
        plot[1].set_ylim(-1, 1)
      #plot10].set_xticks(range(0, self.bin_count,  self.bin_count>>3))
      plot[1].set_ylabel("DNL [LSB]")
      plot[1].legend()
      plot[1].grid(True)  
      plot[2].stairs(inl_data[:len(reg_data)-1], reg_data, baseline = None, label = "INL avg = %.3f" % dac_inl_std)
      if dac_inl_std < 0.001:
        plot[2].set_ylim(-1, 1)    
      #plot21].set_xticks(range(0, self.bin_count,  self.bin_count>>3))
      plot[2].set_ylabel("INL [LSB]")  
      plot[2].legend()
      plot[2].set_xlabel('Digital Output [ADU]')  
      plot[2].grid(True)        

    return dac_dnl_std, dac_inl_std    

class COMPARATOR:
  def __init__(self):
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
  def __init__(self):
    self.resolution = params['SAR_ADC']['resolution']
    self.sampling_frequency = params['SAR_ADC']['sampling_rate'] 
    self.positive_ref_voltage = params['SAR_ADC']['positive_reference_voltage']
    self.negative_ref_voltage = params['SAR_ADC']['negative_reference_voltage']
    self.dac = CDAC(sampling_frequency=self.sampling_frequency, resolution=self.resolution, positive_ref_voltage=self.positive_ref_voltage, negative_ref_voltage=self.negative_ref_voltage)  # for BSS, DAC array size must be number of ADC conversion cycles - 1
    self.cycles = self.dac.array_size + 1
    self.clock_period = 1/(self.sampling_frequency * self.cycles)
    self.redundancy = self.cycles - self.resolution
    self.diff_input_voltage_range = 2 * (self.positive_ref_voltage - self.negative_ref_voltage)
    self.lsb_size = self.diff_input_voltage_range / 2**self.resolution 
    self.comparator = COMPARATOR()
    self.input_voltage_p = 0
    self.input_voltage_n = 0
    self.comp_result = []
    self.conversion_energy = 0

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
    comp_out_no_error = []
  
    # init DAC register
    self.dac.reset(do_calculate_energy=do_calculate_energy)
    # total_consumed_charge += self.dac.consumed_charge
  
    # get initial DAC register setting
    temp_register_p = self.dac.register_p
    temp_register_n = self.dac.register_n
   
    # sample input voltage and append voltages to array
    self.dac.top_plate_sample(input_voltage_p, input_voltage_n)   

    # store first DAC output voltage set for plotting
    dac_out_p[0] = self.dac.output_voltage_p
    dac_out_n[0] = self.dac.output_voltage_n
  
    # do first comparison to set MSB (sign) bit
    if self.comparator.compare(self.dac.output_voltage_p, self.dac.output_voltage_n): # comparator output = 1
      self.comp_result.append(1)  
    else: # comparator output = 0
      self.comp_result.append(0)
    
    for i in range(self.dac.array_size):   # SAR loop, bidirectional single side switching (BSS)
      # print('conversion %2d, reg_p %s, reg_n %s, dac_out_p %f, dac_out_n %f' % (i+1, format(register_p, '#014b'), format(register_n, '#014b'), self.dac.output_voltage_p, self.dac.output_voltage_n))
      
      # update DAC register depending on the previous conversion
      if (i == 0): # first conversion switches MSB bit in opposite direction
        if self.comp_result[0] == 0:
          temp_register_p += 1 << (self.dac.array_size-1) # increment p-side
        else:
          temp_register_n += 1 << (self.dac.array_size-1) # increment n-side

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
      
      # compare
      if self.comparator.compare(self.dac.output_voltage_p, self.dac.output_voltage_n): # comparator output = 1
        self.comp_result.append(1)
      else: # comparator output = 0
        self.comp_result.append(0)
    
    # calculate result  
    result = self.calculate_result() 
    self.conversion_energy = total_consumed_charge * (self.dac.positive_ref_voltage - self.dac.negative_ref_voltage)
    # print('conversion energy %e [pJ]' % (self.conversion_energy * 1e12))
             
    if do_plot:
      # calculate error free conversion for annotation
      ideal_adc_code = self.ideal_conversion(input_voltage_p, input_voltage_n)
      for i in range(self.cycles):
        comp_out_no_error.append(1 if ideal_adc_code & (1 << (self.cycles - i -1)) else 0)

      figure, plot = plt.subplots(1, 1)
      legend_title = ('Diff input voltage [%.3f, %.3f] \nADC code = %s \nIdeal code = %s ' % (input_voltage_p, input_voltage_n, result, ideal_adc_code))
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
        color = 'red' if self.comp_result[i] != comp_out_no_error[i] else 'black'  
        plot.annotate(self.comp_result[i], xy=(i+0.5, 0), ha='center', color=color)

    return result

  def calculate_result(self):
    result = 0
    if (self.dac.use_radix):
      radix = self.dac.radix
    else:
      radix = 2
    for i in range(self.cycles):
      result += self.comp_result[i] * radix**(self.cycles-i-1)

    if (radix != 2):
      radix_scale_factor = (2**self.resolution-1) / ((radix**(self.cycles)-1)/(radix-1))
      result = result * radix_scale_factor
    return result

  def calculate_nonlinearity(self, do_plot = False):
    values_per_bin = 10 # number of values per bin for DNL/INL calculation
    lower_excluded_bins = 2  # lower bound for DNL/INL calculation in LSB
    upper_excluded_bins = 2  # upper bound for DNL/INL calculation in LSB distance from full scale

    # helper variables
    min_code  = 0 
    max_code  = 2**(self.resolution)-1
    num_codes = 2**self.resolution
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
    adc_offset  = 2**(self.resolution-1)

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
    residual_array = input_voltage_array/adc_gain + adc_offset - adc_data_array - 0.5
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
    ideal_adc_code = int(np.floor((input_voltage_p - input_voltage_n) / self.lsb_size))
    # signed to unsigned conversion
    ideal_adc_code += 2**(self.resolution-1)
    return ideal_adc_code

  def plot_transfer_function(self):
    samples_per_bin = 1
    common_mode_input_voltage = 0.3
    input_voltage_data = np.arange(-self.diff_input_voltage_range/2, self.diff_input_voltage_range/2, self.lsb_size/samples_per_bin)
    input_voltage_data_lsb = np.empty(len(input_voltage_data))
    adc_data = np.empty(2**self.resolution*samples_per_bin)
    for i in tqdm(range(len(input_voltage_data))):
      adc_data[i] = self.sample_and_convert_bss(input_voltage_data[i]/2+common_mode_input_voltage, -input_voltage_data[i]/2+common_mode_input_voltage) 
      #adc_data[i] = self.ideal_conversion(input_voltage_data[i]/2, -input_voltage_data[i]/2) 
      #input_voltage_data_lsb[i] = self.ideal_conversion(input_voltage_data[i]/2, -input_voltage_data[i]/2) 

    input_voltage_data_lsb = input_voltage_data / self.lsb_size + 2**(self.resolution-1)

    figure, plot = plt.subplots(2, 1, sharex=True)
    y_ticks = range(0, 2**self.resolution+10, 2**(self.resolution-3))
    figure.suptitle('ADC Transfer Function')
    plot[0].stairs(adc_data[:len(input_voltage_data)-1], input_voltage_data, baseline = None, label = 'ADC transfer function')
    plot[0].plot(input_voltage_data, input_voltage_data_lsb, 'r--', label = 'Ideal transfer function')
    plot[0].set_ylabel("ADC code")
    plot[0].set_yticks(y_ticks)
    plot[0].grid(True)  
    plot[0].legend()
    plot[0].set_xlabel('Diff. input voltage [V]')  
    plot[1].plot(input_voltage_data, input_voltage_data_lsb-adc_data, label='Residuals')
    plot[1].set_ylabel("ADC code")
    plot[1].grid(True)
    plot[1].legend()

if __name__ == "__main__":

  adc = SAR_ADC()
  # plot SAR iterations
  # adc.sample_and_convert_bss(-0.2, 0, do_plot=True, do_calculate_energy=True)
  # calculate conversion energy
  # adc.calculate_conversion_energy(do_plot=True)
  
  # plot transfer function
  # adc.plot_transfer_function()
  
  # adc.dac.use_radix = False 
  # adc.update_parameters()
  # print('binary weighted capacitors')
  # # calculate DNL/INL
  # adc.calculate_nonlinearity(do_plot=True)
  # # calculate ENOB
  # adc.calculate_enob()

  # adc.dac.use_radix = True
  # adc.dac.radix = 1.8
  # adc.update_parameters()
  # # print('non-binary weighted capacitors')
  # # calculate DNL/INL
  # adc.calculate_nonlinearity(do_plot=True)
  # # # calculate ENOB
  # adc.calculate_enob()


  # parametric ENOB calculation
  # adc.comparator.use_noise_error = True
  # for noise in np.arange(0, 10, 2):
  #   adc.comparator.noise_voltage = noise/1e3
  #   enob = adc.calculate_enob()
  #   print('noise %.3f [mV], ENOB %.2f' % (noise, enob))
  
  # CDAC only
  # dac = CDAC()
  # dac.calculate_nonlinearity(do_plot=True)

  adc.calculate_nonlinearity(do_plot=True)
  adc.calculate_enob()
  adc.calculate_conversion_energy()
  print(adc.print_parameter_list())
  plt.show()

