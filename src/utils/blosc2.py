#!/usr/bin/env python3
"""
Compress simulation data files using Blosc2
"""

import blosc2
import os
import time

def compress_file(input_path, output_path=None):
    """
    Compress a file using Blosc2
    
    Args:
        input_path: Path to input file
        output_path: Path to output file (default: input_path + '.blosc2')
    
    Returns:
        tuple: (original_size, compressed_size, compression_ratio, compression_time)
    """
    if output_path is None:
        output_path = input_path + '.blosc2'
    
    print(f"Compressing {input_path}...")
    
    start_time = time.time()
    
    # Read input file
    with open(input_path, 'rb') as f:
        data = f.read()
    
    original_size = len(data)
    
    # Compress with Blosc2
    cparams = {'cname': 'zstd', 'clevel': 5, 'nthreads': 0}
    compressed_data = blosc2.compress2(data, cparams=cparams)
    
    # Write compressed file
    with open(output_path, 'wb') as f:
        f.write(compressed_data)
    
    compressed_size = len(compressed_data)
    compression_time = time.time() - start_time
    compression_ratio = original_size / compressed_size
    
    print(f"  Original size: {original_size:,} bytes ({original_size / 1024 / 1024:.2f} MB)")
    print(f"  Compressed size: {compressed_size:,} bytes ({compressed_size / 1024 / 1024:.2f} MB)")
    print(f"  Compression ratio: {compression_ratio:.2f}x")
    print(f"  Compression time: {compression_time:.3f} seconds")
    print(f"  Output: {output_path}")
    print()
    
    return original_size, compressed_size, compression_ratio, compression_time

def decompress_file(input_path, output_path=None):
    """
    Decompress a Blosc2 compressed file
    
    Args:
        input_path: Path to compressed file
        output_path: Path to output file (default: removes .blosc2 extension)
    """
    if output_path is None:
        if input_path.endswith('.blosc2'):
            output_path = input_path[:-7]  # Remove .blosc2 extension
        else:
            output_path = input_path + '.decompressed'
    
    print(f"Decompressing {input_path} to {output_path}...")
    
    start_time = time.time()
    
    # Read compressed file
    with open(input_path, 'rb') as f:
        compressed_data = f.read()
    
    
    # Decompress
    data = blosc2.decompress(compressed_data)
    
    # Write decompressed file
    with open(output_path, 'wb') as f:
        f.write(data)
    
    decompression_time = time.time() - start_time
    print(f"  Decompressed in {decompression_time:.3f} seconds")
    print(f"  Output: {output_path}")
    print()

def main():
    """Main function to compress the simulation files"""
    
    # Files to compress (relative to repository root)
    files_to_compress = [
        "sincos.raw",
        "clock.raw"
    ]
    
    total_original = 0
    total_compressed = 0
    total_time = 0
    
    print("Blosc2 Compression Script")
    print("=" * 50)
    print()
    
    for file_path in files_to_compress:
        if os.path.exists(file_path):
            original_size, compressed_size, ratio, comp_time = compress_file(file_path)
            total_original += original_size
            total_compressed += compressed_size
            total_time += comp_time
        else:
            print(f"Warning: File {file_path} not found, skipping...")
            print()
    
    if total_original > 0:
        overall_ratio = total_original / total_compressed
        print("Summary:")
        print("-" * 30)
        print(f"Total original size: {total_original:,} bytes ({total_original / 1024 / 1024:.2f} MB)")
        print(f"Total compressed size: {total_compressed:,} bytes ({total_compressed / 1024 / 1024:.2f} MB)")
        print(f"Overall compression ratio: {overall_ratio:.2f}x")
        print(f"Total compression time: {total_time:.3f} seconds")
        print(f"Space saved: {total_original - total_compressed:,} bytes ({(total_original - total_compressed) / 1024 / 1024:.2f} MB)")

if __name__ == "__main__":
    main()