# Our liberty file is in units of ns, so we must use the same here

current_design adc

# Create clocks for sequencing signals
create_clock -name seq_init -period 100 -waveform {0 5} [get_ports seq_init]
create_clock -name seq_samp -period 100 -waveform {0 5} [get_ports seq_samp]
create_clock -name seq_comp -period 5 [get_ports seq_comp]
create_clock -name seq_update -period 5 [get_ports seq_update]

# Set clock uncertainties
set_clock_uncertainty 0.05 [all_clocks]