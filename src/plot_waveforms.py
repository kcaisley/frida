#!/usr/bin/env python3
"""
Waveform plotting script for SPICE simulation results
"""

import sys
import numpy as np
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend for batch processing
import matplotlib.pyplot as plt
from spicelib import *

def plot_waveforms():
    """
    Generate waveform plots from SPICE simulation data
    """
    # Read the raw file
    raw_data = RawRead('/home/kcaisley/frida/hdl/test_simple_complete.raw')
    
    # Get time vector and signals
    time = raw_data.get_trace('time').get_wave()
    a = raw_data.get_trace('v(a)').get_wave()
    b = raw_data.get_trace('v(b)').get_wave()  
    c = raw_data.get_trace('v(c)').get_wave()
    y1 = raw_data.get_trace('v(y1)').get_wave()
    y2 = raw_data.get_trace('v(y2)').get_wave()
    
    # Convert time to nanoseconds for better readability
    time_ns = time * 1e9
    
    print(f'Generating waveform plots from {len(time)} data points...')
    
    # Create figure with subplots
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10))
    fig.suptitle('SPICE Simulation Results - TSMC 65LP Test Circuit', 
                 fontsize=16, fontweight='bold')
    
    # Input signals subplot
    ax1.plot(time_ns, a, 'b-', linewidth=2.5, label='a')
    ax1.plot(time_ns, b, 'g-', linewidth=2.5, label='b') 
    ax1.plot(time_ns, c, 'r-', linewidth=2.5, label='c')
    ax1.set_ylabel('Voltage (V)', fontsize=13)
    ax1.set_title('Input Signals', fontsize=14, fontweight='bold')
    ax1.grid(True, alpha=0.3)
    ax1.legend(loc='upper right', fontsize=12)
    ax1.set_ylim(-0.2, 1.4)
    
    # Add voltage level indicators
    ax1.axhline(y=0.6, color='gray', linestyle='--', alpha=0.7, linewidth=1)
    ax1.axhline(y=1.2, color='gray', linestyle=':', alpha=0.7, linewidth=1)
    ax1.axhline(y=0.0, color='gray', linestyle=':', alpha=0.7, linewidth=1)
    
    # Add voltage level labels
    ax1.text(19.5, 0.6, 'Logic Threshold', fontsize=10, alpha=0.8)
    ax1.text(19.5, 1.2, 'VDD', fontsize=10, alpha=0.8)
    ax1.text(19.5, 0.0, 'VSS', fontsize=10, alpha=0.8)
    
    # Output signals subplot
    ax2.plot(time_ns, y1, 'm-', linewidth=2.5, label='y1 (AND)')
    ax2.plot(time_ns, y2, 'c-', linewidth=2.5, label='y2 (AOI21)')
    ax2.set_xlabel('Time (ns)', fontsize=13)
    ax2.set_ylabel('Voltage (V)', fontsize=13)
    ax2.set_title('Output Signals', fontsize=14, fontweight='bold')
    ax2.grid(True, alpha=0.3)
    ax2.legend(loc='upper right', fontsize=12)
    ax2.set_ylim(-0.2, 1.4)
    
    # Add voltage level indicators
    ax2.axhline(y=0.6, color='gray', linestyle='--', alpha=0.7, linewidth=1)
    ax2.axhline(y=1.2, color='gray', linestyle=':', alpha=0.7, linewidth=1)
    ax2.axhline(y=0.0, color='gray', linestyle=':', alpha=0.7, linewidth=1)
    
    # Highlight key transition points
    transition_times = [2.5, 5, 7.5, 10, 12.5, 15, 17.5, 20]
    for t in transition_times:
        if t <= 20:  # Only show lines within plot range
            ax1.axvline(x=t, color='orange', linestyle=':', alpha=0.4, linewidth=1)
            ax2.axvline(x=t, color='orange', linestyle=':', alpha=0.4, linewidth=1)
    
    # Add text annotations for logic functions
    ax1.text(0.02, 0.95, 'Input Stimulus:', transform=ax1.transAxes, 
             fontsize=11, fontweight='bold', verticalalignment='top',
             bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8))
    ax1.text(0.02, 0.85, 'a: PULSE(0→1.2V, 10ns period)', transform=ax1.transAxes, 
             fontsize=10, verticalalignment='top')
    ax1.text(0.02, 0.79, 'b: PULSE(0→1.2V, 10ns period, 2.5ns delay)', transform=ax1.transAxes, 
             fontsize=10, verticalalignment='top')
    ax1.text(0.02, 0.73, 'c: PULSE(0→1.2V, 4ns period, 1ns delay)', transform=ax1.transAxes, 
             fontsize=10, verticalalignment='top')
    
    ax2.text(0.02, 0.95, 'Logic Functions:', transform=ax2.transAxes, 
             fontsize=11, fontweight='bold', verticalalignment='top',
             bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8))
    ax2.text(0.02, 0.85, 'y1 = a ∧ b (AN2D0BWP7T)', transform=ax2.transAxes, 
             fontsize=10, verticalalignment='top')
    ax2.text(0.02, 0.79, 'y2 = ¬((a ∧ b) ∨ c) (AO21D0BWP7T)', transform=ax2.transAxes, 
             fontsize=10, verticalalignment='top')
    
    # Add process information
    ax2.text(0.98, 0.05, 'TSMC 65LP PDK\n1.2V Supply\nTypical Corner', 
             transform=ax2.transAxes, fontsize=10, 
             verticalalignment='bottom', horizontalalignment='right',
             bbox=dict(boxstyle="round,pad=0.3", facecolor="lightblue", alpha=0.8))
    
    # Adjust layout and save
    plt.tight_layout()
    plt.subplots_adjust(top=0.93)
    
    # Save high-quality plot
    output_file = '/home/kcaisley/frida/hdl/spice_waveforms.png'
    plt.savefig(output_file, dpi=200, bbox_inches='tight', 
                facecolor='white', edgecolor='none')
    print(f'High-resolution waveform plot saved as: {output_file}')
    
    # Also save as PDF
    pdf_file = '/home/kcaisley/frida/hdl/spice_waveforms.pdf'
    plt.savefig(pdf_file, bbox_inches='tight', 
                facecolor='white', edgecolor='none')
    print(f'Vector waveform plot saved as: {pdf_file}')
    
    # Print summary statistics
    print(f'\nWaveform Summary:')
    print(f'  Time range: {time_ns[0]:.1f} to {time_ns[-1]:.1f} ns')
    print(f'  Input ranges: a=[{a.min():.3f}, {a.max():.3f}]V, b=[{b.min():.3f}, {b.max():.3f}]V, c=[{c.min():.3f}, {c.max():.3f}]V')
    print(f'  Output ranges: y1=[{y1.min():.3f}, {y1.max():.3f}]V, y2=[{y2.min():.3f}, {y2.max():.3f}]V')
    
    plt.close()
    return output_file, pdf_file

def create_interactive_plot():
    """
    Create an interactive version using PyQt5 backend
    """
    try:
        matplotlib.use('Qt5Agg')  # Switch to interactive backend
        import matplotlib.pyplot as plt
        
        # Read the raw file
        raw_data = RawRead('/home/kcaisley/frida/hdl/test_simple_complete.raw')
        
        # Get signals
        time = raw_data.get_trace('time').get_wave() * 1e9  # Convert to ns
        a = raw_data.get_trace('v(a)').get_wave()
        b = raw_data.get_trace('v(b)').get_wave()  
        c = raw_data.get_trace('v(c)').get_wave()
        y1 = raw_data.get_trace('v(y1)').get_wave()
        y2 = raw_data.get_trace('v(y2)').get_wave()
        
        # Create interactive plot
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))
        fig.suptitle('SPICE Waveforms - Interactive View (PyQt5)', fontsize=14)
        
        ax1.plot(time, a, 'b-', linewidth=2, label='a')
        ax1.plot(time, b, 'g-', linewidth=2, label='b')
        ax1.plot(time, c, 'r-', linewidth=2, label='c')
        ax1.set_ylabel('Voltage (V)')
        ax1.set_title('Input Signals')
        ax1.grid(True, alpha=0.3)
        ax1.legend()
        
        ax2.plot(time, y1, 'm-', linewidth=2, label='y1 (AND)')
        ax2.plot(time, y2, 'c-', linewidth=2, label='y2 (AOI21)')
        ax2.set_xlabel('Time (ns)')
        ax2.set_ylabel('Voltage (V)')
        ax2.set_title('Output Signals')
        ax2.grid(True, alpha=0.3)
        ax2.legend()
        
        plt.tight_layout()
        print('Launching interactive plot window (PyQt5)...')
        print('Close the plot window to continue.')
        plt.show()
        
    except Exception as e:
        print(f'Interactive plot failed: {e}')
        print('Static plots were generated successfully.')

if __name__ == '__main__':
    # Generate static plots first
    png_file, pdf_file = plot_waveforms()
    
    # Optionally create interactive plot
    if len(sys.argv) > 1 and sys.argv[1] == '--interactive':
        create_interactive_plot()
    else:
        print('\nTo view interactive plot, run: python3 hdl/plot_waveforms.py --interactive')