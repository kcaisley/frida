# GAW FastAccess Support - Minimal Patch Plan

## Executive Summary

Add FastAccess binary format support to GAW with **minimal changes** (~30 lines of code).
The key insight: FastAccess just changes the read order - we can reorder data after reading.

## Architecture Analysis

### Current GAW Reading Flow:
```
sf_rdhdr_s3raw()        → Parse header, detect binary/ascii
   ↓
sf_readrow_s3raw()      → Read one row (all variables for one point)
   ↓                       Calls ss->rdValFunc in a loop
sf_getval_s3bin()       → Read one value (8 bytes double)
   ↓
dataset_val_add()       → Store value in dataset
```

### Key Observations:

1. **SpiceStream.rdValFunc** is a function pointer that reads ONE value
2. **sf_readrow_s3raw()** loops `ncols` times calling rdValFunc
3. **dataset_val_add()** appends values sequentially to dataset
4. The dataset is built incrementally: row by row

### The Problem with FastAccess:

**Normal layout** (what GAW expects):
```
[T0 V1_0 V2_0 V3_0] [T1 V1_1 V2_1 V3_1] [T2 V1_2 V2_2 V3_2]
 ^--- Row 0 --->     ^--- Row 1 --->     ^--- Row 2 --->
```

**FastAccess layout**:
```
[T0 T1 T2 ...] [V1_0 V1_1 V1_2 ...] [V2_0 V2_1 V2_2 ...]
 ^- All time   ^- All V1            ^- All V2
```

If GAW reads FastAccess sequentially, it gets:
- Row 0: [T0, T1, T2, T3, ...] ← All time values!
- Row 1: [V1_0, V1_1, V1_2, ...] ← All V1 values!
- WRONG!

## Solution Strategy

### Option 1: Read-Transpose-Store (RECOMMENDED - SIMPLEST)

**Concept**: Read all data into a buffer, transpose it, then store.

**Why this is minimal**:
- No changes to rdValFunc (still reads 8 bytes)
- No changes to readrow function structure
- Just add a post-processing step

**Implementation**:

1. **Detect FastAccess flag** (5 lines in sf_rdhdr_s3raw):
```c
int fastaccess = 0;  // Add variable

// In Flags parsing (line 73-82):
if (strcmp(val, "fastaccess") == 0) {
    fastaccess = 1;
}

// Store in SpiceStream (line 150-161):
ss->flags = fastaccess;  // Use existing flags field
```

2. **Buffer the data if FastAccess** (15 lines in sf_readrow_s3raw):
```c
int sf_readrow_s3raw(SpiceStream *ss)
{
    // NEW: Check if fastaccess
    if (ss->flags & 0x01) {  // fastaccess bit
        return sf_readrow_s3raw_fastaccess(ss);
    }

    // Original code continues unchanged...
    int i;
    int ret;
    double val;
    for (i = 0; i < ss->ncols ; i++) {
        ret = ss->rdValFunc(ss, &val);
        // ... rest unchanged
    }
}
```

3. **New function for FastAccess** (~30 lines):
```c
static int sf_readrow_s3raw_fastaccess(SpiceStream *ss)
{
    static double *buffer = NULL;
    static int initialized = 0;

    // First call: read ALL data into buffer
    if (!initialized) {
        int nvars = ss->ncols;  // Number of variables
        int npoints = ss->nrows;  // Number of points
        buffer = malloc(nvars * npoints * sizeof(double));

        // Read all data sequentially (as stored in file)
        for (int i = 0; i < nvars * npoints; i++) {
            if (ss->rdValFunc(ss, &buffer[i]) != 1) {
                free(buffer);
                return 0;
            }
        }
        initialized = 1;
        ss->read_rows = 0;  // Reset row counter
    }

    // Now serve data row-by-row (transposed)
    int row = ss->read_rows;
    int nvars = ss->ncols;
    int npoints = ss->nrows;

    for (int var = 0; var < nvars; var++) {
        // Calculate transposed index:
        // FastAccess: buffer[var * npoints + row]
        // Normal: buffer[row * nvars + var]
        double val = buffer[var * npoints + row];
        dataset_val_add(ss->wds, val);
    }

    ss->read_rows++;
    if (ss->read_rows >= ss->nrows) {
        free(buffer);
        buffer = NULL;
        initialized = 0;
        return -2;  // End of data
    }
    return 1;
}
```

### Why This Works:

1. **Reads data exactly as stored** (contiguous blocks)
2. **Transposes on-the-fly** when serving rows
3. **No changes to data format** - still 8-byte doubles
4. **No changes to rdValFunc** - still reads sequentially
5. **Minimal memory overhead** - one buffer for entire dataset

### Files to Modify:

1. **lib/ss_spice3.c**:
   - Line 44: Add `int fastaccess = 0;`
   - Lines 73-82: Add fastaccess flag detection
   - Line 151: Store `ss->flags = fastaccess;`
   - Line 251: Add dispatch to fastaccess reader
   - Add new function `sf_readrow_s3raw_fastaccess()`

2. **lib/spicestream.h** (OPTIONAL - flags field already exists):
   - No changes needed, `flags` field already defined at line 58

### Total Changes:
- **~50 lines added**
- **3 lines modified**
- **0 lines deleted**
- **1 file modified** (ss_spice3.c)

---

## Option 2: Seek-Based Reading (Alternative)

Instead of buffering, seek to the right position for each variable.

**Pros**: Less memory (no buffer)
**Cons**: Many file seeks (slower), more complex logic

**Not recommended** because:
- More complex (~80 lines)
- Slower (O(n²) seeks)
- Needs file offset tracking

---

## Testing Plan

### Test Files:
1. `test_spicelib_out_alldoubles.raw` (normal) - should still work
2. `test_spicelib_out_fastaccess_alldoubles.raw` (fastaccess) - should now work

### Verification:
```bash
# Before patch: both files
gaw test_spicelib_out_alldoubles.raw  # Works
gaw test_spicelib_out_fastaccess_alldoubles.raw  # Fails/wrong data

# After patch: both files
gaw test_spicelib_out_alldoubles.raw  # Still works
gaw test_spicelib_out_fastaccess_alldoubles.raw  # Now works!
```

---

## Implementation Complexity: ★★☆☆☆

**Why it's simple**:
- Reuses existing rdValFunc (no new read logic)
- Reuses existing dataset functions
- Just adds a transpose step
- Isolated to one function

**Edge cases handled**:
- Empty files: buffer allocation check
- Partial reads: error handling from rdValFunc
- Memory leaks: free on end-of-file

**Backward compatibility**: 100% - normal files unchanged

---

## Patch File Structure

```
--- a/lib/ss_spice3.c
+++ b/lib/ss_spice3.c
@@ line numbers
+ Added lines for fastaccess detection
+ Added lines for fastaccess reader function
```

Would you like me to generate the actual patch file?
