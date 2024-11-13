import yaml
import numpy as np	
import matplotlib.pyplot as plt
from tqdm import tqdm

# Load parameters from YAML file
with open('adc_sim.yaml', 'r') as file:
  params = yaml.safe_load(file)

class CDAC:
  def __init__(self, array_size, clock_period = 1e-9):
    # capacitor array setup
    self.array_size            = array_size
    self.unit_capacitance      = np.array(params['CDAC']['unit_capacitance'])
    self.capacitor_array_p     = np.zeros(self.array_size)
    self.capacitor_array_n     = np.zeros(self.array_size)
    self.use_radix             = params['CDAC']['use_radix']
    self.radix                 = params['CDAC']['radix']
    self.parasitic_capacitance = params['CDAC']['parasitic_capacitance']
    self.use_systematic_errors = params['CDAC']['use_systematic_errors']
    self.total_capacitance_p = 0  # calculated in 'build_capacitor_array'
    self.total_capacitance_n = 0
    self.build_capacitor_array(use_systematic_errors=self.use_systematic_errors)

    # voltage swing and settling time
    self.settling_time         = params['CDAC']['settling_time']
    self.positive_ref_voltage  = params['CDAC']['positive_reference_voltage']
    self.negative_ref_voltage  = params['CDAC']['negative_reference_voltage']
    self.common_mode_voltage   = params['CDAC']['common_mode_voltage']
    self.lsb_size = (self.positive_ref_voltage - self.negative_ref_voltage) / 2**self.array_size
    
    self.output_voltage_p = 0
    self.output_voltage_n = 0
    self.output_voltage_no_error_p = 0
    self.output_voltage_no_error_n = 0
    self.register_p = 0
    self.register_n = 0

    self.use_settling_error  = params['CDAC']['use_settling_error']
    self.settling_time_error = np.exp(-clock_period/self.settling_time)

  def build_capacitor_array(self, use_systematic_errors):
    if self.use_radix:
      for i in range(self.array_size):
        self.capacitor_array_p[i] = params['CDAC']['radix']**i * self.unit_capacitance
        self.capacitor_array_n[i] = params['CDAC']['radix']**i * self.unit_capacitance
    else:
      self.capacitor_array_p = params['CDAC']['capacitor_weights'][:self.array_size] * self.unit_capacitance
      self.capacitor_array_n = params['CDAC']['capacitor_weights'][:self.array_size] * self.unit_capacitance

    if use_systematic_errors:
      capacitor_errors_absolute = np.array(params['CDAC']['capacitor_systematic_errors'][:self.array_size]) / 100 * self.unit_capacitance
      capacitor_errors_weighted = capacitor_errors_absolute / np.sqrt(params['CDAC']['capacitor_weights'][:self.array_size])

      self.capacitor_array_p += capacitor_errors_weighted
      self.capacitor_array_n -= capacitor_errors_weighted

    self.total_capacitance_p = sum(self.capacitor_array_p) + self.parasitic_capacitance
    self.total_capacitance_n = sum(self.capacitor_array_n) + self.parasitic_capacitance
    
    # np.set_printoptions(precision=2)
    # print('Capacitor array: ', self.capacitor_array_p)
    # print('capacitor_errors_weighted: ', capacitor_errors_weighted)

  def top_plate_sample(self, input_p, input_n):	
    # top plate sampling: DAC output voltage = input voltage
    self.output_voltage_no_error_p = input_p 
    self.output_voltage_no_error_n = input_n 
    self.output_voltage_p = input_p 
    self.output_voltage_n = input_n 

  def update(self, register_p, register_n):
    # helper variables

    delta_backplane_voltage = self.positive_ref_voltage - self.negative_ref_voltage
        
    delta_output_voltage_p = 0
    delta_output_voltage_n = 0
    
    # calculate output voltage change induced by switched bottom plate voltages
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

  def compare(self, input_voltage_p, input_voltage_n):
    if self.use_offset_error:
      common_mode_offset_voltage = (input_voltage_p + input_voltage_n)/2 * self.common_mode_dependent_offset_gain
      return input_voltage_p > input_voltage_n + self.offset_voltage + common_mode_offset_voltage
    else:
      return input_voltage_p > input_voltage_n

class SAR_ADC:
  def __init__(self):
    self.resolution = params['SAR_ADC']['resolution']
    self.cycles = self.resolution + params['SAR_ADC']['redundancy']
    self.clock_period = 1/(params['SAR_ADC']['sampling_rate'] * self.cycles)
    self.dac = CDAC(clock_period=self.clock_period, array_size=self.cycles-1)  # for BSS, DAC array size must be number of ADC conversion cycles - 1
    self.diff_input_voltage_range = 2 * (self.dac.positive_ref_voltage - self.dac.negative_ref_voltage)
    self.lsb_size = self.diff_input_voltage_range / 2**self.resolution
    self.comparator = COMPARATOR()
    self.input_voltage_p = 0
    self.input_voltage_n = 0
    self.register_p = 0 
    self.register_n = 0
    self.comp_result = []

  def include_errors(self, use_settling_error = False, use_systematic_errors = False, use_dac_offset_error = False):
    # capacitor array mismatch
    if use_systematic_errors:
      self.dac.build_capacitor_array(use_systematic_errors=True, use_radix=False)
    else:
      self.dac.build_capacitor_array(use_systematic_errors=False, use_radix=True)
        # DAC settling time error
    self.dac.use_settling_error = use_settling_error
    # comparator offset error
    self.comparator.use_offset_error = use_dac_offset_error
      
  def sample_and_convert_bss(self, input_voltage_p, input_voltage_n, do_plot = False):	
    # init arrays with DAC output voltages and comparator results
    dac_out_p = []
    dac_out_n = []
    self.comp_result = []
    # for annotation
    comp_out_no_error = []
  
    # init DAC register to mid-scale 0b01111...111
    self.register_p = 2**(self.dac.array_size-1)-1
    self.register_n = 2**(self.dac.array_size-1)-1 
    self.dac.update(self.register_p, self.register_n)   # init DAC register
    self.dac.update(self.register_p, self.register_n)   # 2nd init DAC register to suppress settling time error for MSB comparison
   
    # sample input voltage and append voltages to array
    self.dac.top_plate_sample(input_voltage_p, input_voltage_n)   
    dac_out_p.append(self.dac.output_voltage_p)
    dac_out_n.append(self.dac.output_voltage_n)
  
    # do first comparison to set MSB (sign) bit
    if self.comparator.compare(self.dac.output_voltage_p, self.dac.output_voltage_n): # comparator output = 1
      self.comp_result.append(0)  # opposite direction
    else: # comparator output = 0
      self.comp_result.append(1)
    
    for i in range(self.dac.array_size):   # SAR loop, bidirectional single side switching (BSS)
      # print('conversion %2d, reg_p %s, reg_n %s, dac_out_p %f, dac_out_n %f' % (i+1, format(self.register_p, '#014b'), format(self.register_n, '#014b'), self.dac.output_voltage_p, self.dac.output_voltage_n))
      
      # update DAC register depending on the previous conversion
      if (i == 0): # first conversion switches MSB bit in opposite direction
        if self.comp_result[0] == 1:
          self.register_p += 1 << (self.dac.array_size-1) # increment p-side
        else:
          self.register_n += 1 << (self.dac.array_size-1) # increment n-side

      else: # all other bits
        if self.comp_result[i] == 1:
          self.register_p -= 1 << (self.dac.array_size-i-1) # decrement p-side
        else:
          self.register_n -= 1 << (self.dac.array_size-i-1) # decrement n-side
   
      # update DAC output voltage and append to array
      self.dac.update(self.register_p, self.register_n)
      dac_out_p.append(self.dac.output_voltage_p)
      dac_out_n.append(self.dac.output_voltage_n)
      
      # compare
      if self.comparator.compare(self.dac.output_voltage_p, self.dac.output_voltage_n): # comparator output = 1
        self.comp_result.append(1)
      else: # comparator output = 0
        self.comp_result.append(0)
    
    # calculate result  
    result = self.calculate_result() 
        
    # calculate error free conversion for annotation
    ideal_adc_code = int((input_voltage_p - input_voltage_n) / self.lsb_size )
    # ideal conversion bits
    for i in range(self.cycles):
      comp_out_no_error.append(1 if ideal_adc_code & (1 << (self.cycles - i -1)) else 0)
   
    if do_plot:
      figure, plot = plt.subplots(1, 1)
      legend_title = ('Diff input voltage [%.3f, %.3f] \nADC code = %s \nIdeal code = %s ' % (input_voltage_p, input_voltage_n, result, ideal_adc_code))
      figure.suptitle('SAR Conversion')
      plot.stairs(dac_out_p, range(self.cycles+1), label = "p-side")
      plot.stairs(dac_out_n, range(self.cycles+1), label = "n-side")
      # plo0[1].axhline(y=input_voltage_p-input_voltage_n, color='red', linestyle='--')
      plot.set_ylabel("DAC Output Voltage [V]")
      plot.set_ylim(-1.5, 1.5)    
      plot.set_xticks(range(0, self.cycles + 1, 1))
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
      result += self.comp_result[i] * radix**(self.cycles - i -1)
    # fix sign bit
    if result >= 2**(self.resolution-1):
      result = result - 2**self.resolution 
    return result

  def calculate_nonlinearity(self, do_plot = False):
    values_per_bin = 100 # number of values per bin for DNL/INL calculation
    lower_excluded_bins = 10  # lower bound for DNL/INL calculation in LSB
    upper_excluded_bins = 10  # upper bound for DNL/INL calculation in LSB distance from full scale

    # helper variables
    min_code = -2**(self.resolution-1)
    max_code =  2**(self.resolution-1)-1
    num_codes = 2**self.resolution
    lower_index_boundary = lower_excluded_bins
    upper_index_boundary = num_codes - upper_excluded_bins
    
    # data structures for DNL/INL calculation
    code_density_hist = []#np.zeros(2**self.cycles)
    bin_edges = []
    dnl_data = np.empty(num_codes)
    inl_data = np.empty(num_codes)
    adc_data = np.empty(num_codes * values_per_bin)
    input_voltage_data = np.arange(-self.diff_input_voltage_range/2, self.diff_input_voltage_range/2, self.lsb_size/values_per_bin)

     # do the conversions
    for i in tqdm(range(num_codes * values_per_bin)):
      adc_data[i] = self.sample_and_convert_bss(input_voltage_data[i]/2, -input_voltage_data[i]/2) 

    # calculate code density histogram
    code_density_hist, bin_edges = np.histogram(adc_data, bins = num_codes)   
    code_density_hist = code_density_hist[lower_index_boundary:upper_index_boundary]
    bin_edges         = bin_edges[lower_index_boundary:upper_index_boundary+1]
    average_bin_count = np.average(code_density_hist)

    # calculate differential nonlinearity
    dnl_data = (code_density_hist - average_bin_count) / average_bin_count
    dnl_data[:lower_index_boundary] = 0
    dnl_data[upper_index_boundary:] = 0
    dnl_sigma = np.std(dnl_data)

    # calculate integral nonlinearity INL
    inl_data = np.cumsum(dnl_data)
    inl_sigma = np.std(inl_data)

    x_ticks = range(-2**(self.resolution-1), 2**(self.resolution-1)+1, 2**(self.resolution-3))
    
    if do_plot:
      plot_title = 'ADC Nonlinearity \n (settling error = %s, systematic errors = %s, offset error = %s)' % (self.dac.use_settling_error, self.dac.use_systematic_errors, self.comparator.use_offset_error) 
      figure, plot = plt.subplots(3, 1, sharex=True,)
      figure.suptitle(plot_title)
      plot[0].stairs(code_density_hist, bin_edges, baseline = None)
      plot[0].set_xticks(x_ticks)
      plot[0].set_ylabel("Code density")
      plot[0].grid(True)  
      plot[1].stairs(dnl_data, bin_edges, baseline = None, label = "DNL sigma = %.3f" % dnl_sigma)
      plot[1].set_ylim(-1, 1)
      plot[1].set_ylabel("DNL [LSB]")
      plot[1].legend()
      plot[1].grid(True)  
      plot[2].stairs(inl_data, bin_edges, baseline = None, label = "INL sigma = %.3f" % inl_sigma)
      plot[2].set_ylim(-1, 1)    
      plot[2].set_ylabel("INL [LSB]")  
      plot[2].legend()
      plot[2].set_xlabel('ADC code')  
      plot[2].grid(True)        

    return dnl_sigma, inl_sigma        

  def plot_transfer_function(self):
    input_voltage_data = np.arange(-self.diff_input_voltage_range/2, self.diff_input_voltage_range/2 + self.lsb_size, self.lsb_size)
    adc_data = np.empty(2**self.resolution)
    for i in range(2**self.resolution):
      adc_data[i] = self.sample_and_convert_bss(input_voltage_data[i]/2, -input_voltage_data[i]/2) 

    figure, plot = plt.subplots(1, 1)
    figure.suptitle('ADC Transfer Function')
    plot.stairs(adc_data, input_voltage_data, baseline = None)
    plot.set_ylabel("ADC code")
    plot.grid(True)  
    plot.set_xlabel('Diff. input voltage [V]')  


if __name__ == "__main__":

  adc = SAR_ADC()
  # plot SAR iterations
  adc.sample_and_convert_bss(1.1, 0, do_plot=True)
  # plot transfer function
  adc.plot_transfer_function()
  # calculate DNL/INL
  adc.calculate_nonlinearity(do_plot=True)
  
  # CDAC only
  # dac = CDAC()
  # dac.calculate_nonlinearity(do_plot=True)

  plt.show()

