Accelerators are becoming less 'fixed-function', and more programmable. But this has the disadvantage of requiring a programming model. And the compilers for these aren't typically standardized or open source.

Some accelerators/coprocessors like SIMD vector units and FPUs exist directing in the instruction stream of the the CPU. Others are more seperate, as they can't run general purpose code. In these case, it's typical for them to use DMA with the host program building a command list.

video/image processing
video encoding/compression
graphics rendering / drawing
neural network accelerator (training and inference)
crytographic
audio/video DSP
programmable FPGA fabric
FPUs




energy efficiency is largerly a facet of run time. For computers which are 'always on', like an operating system, you have to think of the machine therefore as a collective of many programs starting and finishing.

Therefore, a system which has low collective CPU usage will be one which uses less power.
