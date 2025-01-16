top level `SB_XXXX.sp`
- `.lib "/users/kcaisley/helena/tech/tsmc65/default_testbench_header_55ulp.lib" tt`
- plus .param .options .probe, etc

From here, the quoted section pick the file, and the `tt` after picked the model corner

These are used to call a file like before, and pi
in PDK header `default_testbench_header_XXX.lib`, we have

```
*******************General Settings****************************************
.lib setting
    .model DIODE d
    .model NPN npn
    .model PNP pnp
    .include  'S:\technologies\tsmc65\v2.0\v2.0.lib'
.endl

************tt*************
.lib tt
	.option threads = 1   * run on multiple cores of computer
	.option monteinfo = 2 * monteinfo=1 only print histogram
                          * monteinfo=2 print all simulation results
    .param log_only=0
    .param rh=0
    .param lvs=0
    .lib 'default_testbench_header_65.lib' NOM_MODEL
    .lib 'default_testbench_header_65.lib' setting
.endl
```
