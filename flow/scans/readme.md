
| Method / Register     | fifo              | seq_gen                            | spi                                | gpio              | fast_spi_rx                       | pulse_gen                         |
| --------------------- | ----------------- | ---------------------------------- | ---------------------------------- | ----------------- | --------------------------------- | --------------------------------- |
| | | **Driver class methods** | | | | |
| `.start()`            | -                | sets `START`                       | sets `START`                       | -                | -                                 | sets `START`                      |
| `.reset()`            | -                | sets `RESET`                       | sets `RESET`                       | sets `RESET`       | sets `RESET`                      | sets `RESET`                      |
| `.is_ready()`         | -                | `@property`, gets `READY`          | -                                  | -                | -                                 | `@property`, gets `READY`         |
| `.is_done()`          | -                | alias of `.is_ready()`             | -                                  | -                | -                                 | alias of `.is_ready()`            |
| `.set_en()`           | -                | sets `EN_EXT_START`                | -                                  | `.set_output_en()` sets `OUTPUT_EN` | sets `EN`                  | sets `EN`                         |
| `.get_en()`           | -                | gets `EN_EXT_START`                | -                                  | `.get_output_en()` gets `OUTPUT_EN` | gets `EN`                  | gets `EN`                         |
| `.set_data()`         | via SiTCP FIFO    | writes seq memory                  | writes SPI memory                  | sets `OUTPUT`      | -                                 | -                                 |
| `.get_data()`         | via SiTCP FIFO    | reads seq memory                   | reads SPI memory                   | gets `INPUT`       | -                                 | -                                 |
| | | **Driver class registers** | | | | |
| `START` register      | -                | attribute                          | attribute                          | -                  | -                                 | attribute                         |
| `RESET` register      | -                | attribute                          | attribute                          | attribute          | attribute                         | attribute                         |
| `READY` register      | -                | attribute                          | attribute                          | -                  | -                                 | attribute                         |
| `EN` register         | -                | -                                  | attribute                          | -                  | attribute                         | attribute                         |
| | | **`HardwareLayer` methods** | | | | |
| `.clear()`            | `HardwareLayer`   | `HardwareLayer`                    | `HardwareLayer`                    | `HardwareLayer`    | `HardwareLayer`                   | `HardwareLayer`                   |
| `.wait_for_ready()`   | `HardwareLayer`   | `HardwareLayer`                    | `HardwareLayer`                    | `HardwareLayer`    | `HardwareLayer`                   | `HardwareLayer`                   |
