#!/usr/bin/env python3
"""
Interactive waveform viewer for Spectre simulation results.
Usage: python plot_waveforms.py <design_name>
Example: python plot_waveforms.py samp_tgate
"""

import sys
from pathlib import Path
import matplotlib
matplotlib.use('TkAgg')  # Use TkAgg backend for better remote session support
import matplotlib.pyplot as plt
from spicelib.raw.raw_read import RawRead

class WaveformViewer:
    def __init__(self, design_name):
        self.design_name = design_name
        self.results_dir = Path("results") / design_name
        self.raw_files = sorted(self.results_dir.glob("*.raw"))

        if not self.raw_files:
            print(f"ERROR: No .raw files found in {self.results_dir}")
            sys.exit(1)

        self.current_file_idx = 0
        self.current_raw = None
        self.visible_traces = []
        self.fig, self.ax = None, None

        # Load first file
        self.load_file(0)

    def load_file(self, idx):
        """Load a specific raw file by index"""
        if idx < 0 or idx >= len(self.raw_files):
            print(f"Invalid file index: {idx}")
            return

        self.current_file_idx = idx
        raw_file = self.raw_files[idx]
        print(f"\nLoading: {raw_file.name}")

        try:
            # Read all traces from the file
            # Spectre .raw files use ngspice binary format (headers are auto-corrected by run_simulations.py)
            self.current_raw = RawRead(str(raw_file), traces_to_read='*', dialect='ngspice', verbose=False)
            trace_names = self.current_raw.get_trace_names()

            # By default, show all voltage traces (skip time/frequency axis)
            if trace_names:
                self.visible_traces = [t for t in trace_names[1:] if t.lower() not in ['time', 'frequency']]

            print(f"Loaded {len(trace_names)} traces, plotting {len(self.visible_traces)} by default")

        except Exception as e:
            print(f"ERROR loading {raw_file}: {e}")
            print("Hint: If you see header format errors, re-run 'make sim' to regenerate .raw files")
            sys.exit(1)

    def plot(self):
        """Plot the current waveforms"""
        if self.fig is None:
            self.fig, self.ax = plt.subplots(figsize=(12, 6))
            plt.subplots_adjust(bottom=0.15)

        self.ax.clear()

        if not self.visible_traces:
            self.ax.text(0.5, 0.5, 'No traces to display\nUse "add <trace>" to add traces',
                        ha='center', va='center', transform=self.ax.transAxes)
        else:
            # Get the x-axis (time or frequency)
            x = self.current_raw.get_axis()

            # Plot each visible trace
            for trace_name in self.visible_traces:
                try:
                    y = self.current_raw.get_wave(trace_name)
                    self.ax.plot(x, y, label=trace_name, alpha=0.8)
                except Exception as e:
                    print(f"Warning: Could not plot {trace_name}: {e}")

        self.ax.set_xlabel(self.current_raw.get_trace_names()[0])
        self.ax.set_ylabel('Value')
        self.ax.set_title(f"{self.raw_files[self.current_file_idx].name}")
        self.ax.grid(True, alpha=0.3)

        if self.visible_traces:
            self.ax.legend(loc='best', fontsize=8)

        plt.draw()

    def show_status(self):
        """Display current status and available commands"""
        print("\n" + "="*70)
        print(f"Current file: [{self.current_file_idx+1}/{len(self.raw_files)}] {self.raw_files[self.current_file_idx].name}")
        print(f"Visible traces: {len(self.visible_traces)}")
        print("-"*70)

        all_traces = self.current_raw.get_trace_names()
        print(f"Available traces ({len(all_traces)}):")
        for i, trace in enumerate(all_traces):
            visible = "✓" if trace in self.visible_traces else " "
            print(f"  [{visible}] {i}: {trace}")

        print("-"*70)
        print("Commands:")
        print("  <number>        - Switch to file number (1-{})".format(len(self.raw_files)))
        print("  add <trace>     - Add trace by name or index")
        print("  rm <trace>      - Remove trace by name or index")
        print("  clear           - Remove all traces")
        print("  all             - Show all traces")
        print("  list            - Show this status")
        print("  files           - List all available files")
        print("  quit/q/exit     - Exit viewer")
        print("="*70)

    def list_files(self):
        """List all available raw files"""
        print("\n" + "="*70)
        print(f"Available files ({len(self.raw_files)}):")
        for i, f in enumerate(self.raw_files):
            marker = ">" if i == self.current_file_idx else " "
            print(f"{marker} {i+1}: {f.name}")
        print("="*70)

    def add_trace(self, trace_ref):
        """Add a trace to the visible list"""
        all_traces = self.current_raw.get_trace_names()

        # Try to parse as index
        try:
            idx = int(trace_ref)
            if 0 <= idx < len(all_traces):
                trace_name = all_traces[idx]
            else:
                print(f"Invalid trace index: {idx}")
                return
        except ValueError:
            # Treat as trace name
            trace_name = trace_ref
            if trace_name not in all_traces:
                print(f"Trace '{trace_name}' not found")
                return

        if trace_name not in self.visible_traces:
            self.visible_traces.append(trace_name)
            print(f"Added: {trace_name}")
        else:
            print(f"Already visible: {trace_name}")

    def remove_trace(self, trace_ref):
        """Remove a trace from the visible list"""
        all_traces = self.current_raw.get_trace_names()

        # Try to parse as index
        try:
            idx = int(trace_ref)
            if 0 <= idx < len(all_traces):
                trace_name = all_traces[idx]
            else:
                print(f"Invalid trace index: {idx}")
                return
        except ValueError:
            trace_name = trace_ref

        if trace_name in self.visible_traces:
            self.visible_traces.remove(trace_name)
            print(f"Removed: {trace_name}")
        else:
            print(f"Not visible: {trace_name}")

    def run(self):
        """Main interactive loop"""
        # Show initial plot
        plt.ion()  # Enable interactive mode
        self.plot()
        self.show_status()
        plt.show(block=False)

        # Interactive command loop
        while True:
            try:
                cmd = input("\n> ").strip()

                if not cmd:
                    continue

                # Parse command
                parts = cmd.split(maxsplit=1)
                cmd_name = parts[0].lower()
                cmd_arg = parts[1] if len(parts) > 1 else None

                # Handle commands
                if cmd_name in ['quit', 'q', 'exit']:
                    print("Exiting...")
                    break

                elif cmd_name == 'list':
                    self.show_status()

                elif cmd_name == 'files':
                    self.list_files()

                elif cmd_name == 'add':
                    if cmd_arg:
                        self.add_trace(cmd_arg)
                        self.plot()
                    else:
                        print("Usage: add <trace_name_or_index>")

                elif cmd_name == 'rm':
                    if cmd_arg:
                        self.remove_trace(cmd_arg)
                        self.plot()
                    else:
                        print("Usage: rm <trace_name_or_index>")

                elif cmd_name == 'clear':
                    self.visible_traces.clear()
                    print("Cleared all traces")
                    self.plot()

                elif cmd_name == 'all':
                    all_traces = self.current_raw.get_trace_names()
                    self.visible_traces = [t for t in all_traces[1:]]
                    print(f"Showing all {len(self.visible_traces)} traces")
                    self.plot()

                elif cmd_name.isdigit():
                    # Switch to file by number (1-indexed for user)
                    file_idx = int(cmd_name) - 1
                    if 0 <= file_idx < len(self.raw_files):
                        self.load_file(file_idx)
                        self.plot()
                        self.show_status()
                    else:
                        print(f"Invalid file number. Use 1-{len(self.raw_files)}")

                else:
                    print(f"Unknown command: {cmd_name}")
                    print("Type 'list' for help")

            except KeyboardInterrupt:
                print("\nExiting...")
                break
            except EOFError:
                break
            except Exception as e:
                print(f"Error: {e}")

        plt.close('all')

def main():
    if len(sys.argv) != 2:
        print("Usage: python plot_waveforms.py <design_name>")
        print("Example: python plot_waveforms.py samp_tgate")
        sys.exit(1)

    design_name = sys.argv[1]
    viewer = WaveformViewer(design_name)
    viewer.run()

if __name__ == "__main__":
    main()
