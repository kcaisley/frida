// Runtime output-divider control for a Xilinx 7-series PLLE2_ADV.
//
// The PLL uses fixed D=1 and M=8 with a 100--200 MHz Si570 input, giving an
// 800--1600 MHz VCO. REQUEST_N selects the paired clocks:
//
//   CLKOUT0 divide = 4*N -> sequencer/FastRX clock = 2*FIN/N
//   CLKOUT1 divide =   N -> OSERDES clock          = 8*FIN/N
//
// Legal N values 2..20 combine with the Si570 to cover 80--1600 MBd. The controller
// updates only the four CLKOUT0/CLKOUT1 DRP registers, following the
// read/modify/write transaction described by AMD XAPP888.

`timescale 1ns / 1ps
`default_nettype none

module pll_drp #(
    parameter integer LOCK_TIMEOUT_CYCLES = 20000
) (
    input wire CLK,
    input wire RST,

    // Command from the Basil GPIO2 block. APPLY_TOGGLE requests one update
    // whenever it differs from APPLIED_TOGGLE.
    input wire [4:0] REQUEST_N,
    input wire       APPLY_TOGGLE,

    // PLLE2_ADV status and DRP interface.
    input wire        PLL_LOCKED,
    input wire [15:0] DRP_DO,
    input wire        DRP_DRDY,
    output reg  [6:0] DRP_DADDR,
    output reg [15:0] DRP_DI,
    output reg        DRP_DEN,
    output reg        DRP_DWE,
    output reg        PLL_RESET,

    // Status returned through GPIO2.
    output reg        APPLIED_TOGGLE,
    output reg        BUSY,
    output wire       LOCKED,
    output reg        ERROR,
    output reg  [4:0] ACTIVE_N,

    // Synchronous to CLK. Clock-domain reset synchronizers at the consumers
    // provide asynchronous assertion and synchronous release.
    output wire DATAPATH_HOLD
);

    localparam [3:0] StateIdle      = 4'd0;
    localparam [3:0] StateRead      = 4'd1;
    localparam [3:0] StateWaitRead  = 4'd2;
    localparam [3:0] StateWrite     = 4'd3;
    localparam [3:0] StateWaitWrite = 4'd4;
    localparam [3:0] StateRelease   = 4'd5;
    localparam [3:0] StateWaitLock  = 4'd6;

    reg [3:0]  state;
    reg [1:0]  register_index;
    reg [4:0]  target_n;
    reg [31:0] lock_counter;

    // LOCKED is asynchronous to the bus/DRP clock.
    (* ASYNC_REG = "TRUE" *) reg [1:0] locked_sync;
    always @(posedge CLK or posedge RST) begin
        if (RST) begin
            locked_sync <= 2'b00;
        end else begin
            locked_sync <= {locked_sync[0], PLL_LOCKED};
        end
    end

    assign LOCKED        = locked_sync[1];
    assign DATAPATH_HOLD = BUSY | PLL_RESET | !locked_sync[1];

    function automatic [6:0] counter_address;
        input [1:0] index;
        begin
            case (index)
                2'd0: counter_address = 7'h08;  // CLKOUT0 ClkReg1
                2'd1: counter_address = 7'h09;  // CLKOUT0 ClkReg2
                2'd2: counter_address = 7'h0A;  // CLKOUT1 ClkReg1
                default: counter_address = 7'h0B;  // CLKOUT1 ClkReg2
            endcase
        end
    endfunction

    function automatic [6:0] counter_divide;
        input [1:0] index;
        input [4:0] n;
        begin
            if (index < 2)
                counter_divide = {n, 2'b00};  // 4*N, maximum 80
            else
                counter_divide = {2'b00, n};  // N, maximum 20
        end
    endfunction

    // Construct the new output-counter value while retaining DRP bits marked
    // reserved in XAPP888. Both outputs keep phase=0 and duty cycle=0.5.
    function automatic [15:0] merge_counter_register;
        input [15:0] old_value;
        input [ 6:0] address;
        input [ 6:0] divide_value;
        reg [5:0] high_time;
        reg [5:0] low_time;
        reg       edge_select;
        reg       no_count;
        begin
            if (divide_value == 1) begin
                high_time = 6'd1;
                low_time  = 6'd1;
                edge_select = 1'b0;
                no_count  = 1'b1;
            end else begin
                high_time = divide_value[6:1];
                low_time  = divide_value[6:1] + divide_value[0];
                edge_select = divide_value[0];
                no_count  = 1'b0;
            end

            case (address)
                7'h08, 7'h0A: begin
                    // ClkReg1: clear phase mux, retain reserved bit 12, and
                    // replace HIGH_TIME/LOW_TIME.
                    merge_counter_register = (old_value & 16'h1000) |
                        {4'b0000, high_time, low_time};
                end
                7'h09: begin
                    // CLKOUT0 ClkReg2: retain reserved bit 15 and disable the
                    // fractional-divider fields in bits 14:10.
                    merge_counter_register = (old_value & 16'h8000) |
                        {8'b00000000, edge_select, no_count, 6'b000000};
                end
                default: begin
                    // CLKOUT1 ClkReg2: retain reserved bits 15:10.
                    merge_counter_register = (old_value & 16'hFC00) |
                        {8'b00000000, edge_select, no_count, 6'b000000};
                end
            endcase
        end
    endfunction

    always @(posedge CLK or posedge RST) begin
        if (RST) begin
            state           <= StateIdle;
            register_index  <= 2'd0;
            target_n        <= 5'd2;
            lock_counter    <= 32'd0;
            DRP_DADDR       <= 7'd0;
            DRP_DI          <= 16'd0;
            DRP_DEN         <= 1'b0;
            DRP_DWE         <= 1'b0;
            PLL_RESET       <= 1'b0;
            APPLIED_TOGGLE  <= 1'b0;
            BUSY            <= 1'b0;
            ERROR           <= 1'b0;
            ACTIVE_N        <= 5'd2;
        end else begin
            // DEN and DWE are single-DCLK transaction pulses.
            DRP_DEN <= 1'b0;
            DRP_DWE <= 1'b0;

            case (state)
                StateIdle: begin
                    BUSY <= 1'b0;
                    if (APPLY_TOGGLE != APPLIED_TOGGLE) begin
                        APPLIED_TOGGLE <= APPLY_TOGGLE;
                        if ((REQUEST_N < 2) || (REQUEST_N > 20)) begin
                            ERROR <= 1'b1;
                        end else begin
                            target_n       <= REQUEST_N;
                            register_index <= 2'd0;
                            lock_counter   <= 32'd0;
                            ERROR          <= 1'b0;
                            BUSY           <= 1'b1;
                            PLL_RESET      <= 1'b1;
                            state          <= StateRead;
                        end
                    end
                end

                StateRead: begin
                    DRP_DADDR <= counter_address(register_index);
                    DRP_DEN   <= 1'b1;
                    DRP_DWE   <= 1'b0;
                    state     <= StateWaitRead;
                end

                StateWaitRead: begin
                    if (DRP_DRDY) begin
                        DRP_DI <= merge_counter_register(
                            DRP_DO,
                            counter_address(register_index),
                            counter_divide(register_index, target_n)
                        );
                        state <= StateWrite;
                    end
                end

                StateWrite: begin
                    DRP_DADDR <= counter_address(register_index);
                    DRP_DEN   <= 1'b1;
                    DRP_DWE   <= 1'b1;
                    state     <= StateWaitWrite;
                end

                StateWaitWrite: begin
                    if (DRP_DRDY) begin
                        if (register_index == 2'd3) begin
                            state <= StateRelease;
                        end else begin
                            register_index <= register_index + 1'b1;
                            state          <= StateRead;
                        end
                    end
                end

                StateRelease: begin
                    PLL_RESET    <= 1'b0;
                    lock_counter <= 32'd0;
                    state        <= StateWaitLock;
                end

                StateWaitLock: begin
                    if (locked_sync[1]) begin
                        ACTIVE_N <= target_n;
                        BUSY     <= 1'b0;
                        ERROR    <= 1'b0;
                        state    <= StateIdle;
                    end else if (lock_counter == LOCK_TIMEOUT_CYCLES - 1) begin
                        // Keep a failed PLL in reset until a new legal command
                        // retries the complete transaction.
                        PLL_RESET <= 1'b1;
                        BUSY      <= 1'b0;
                        ERROR     <= 1'b1;
                        state     <= StateIdle;
                    end else begin
                        lock_counter <= lock_counter + 1'b1;
                    end
                end

                default: begin
                    PLL_RESET <= 1'b1;
                    BUSY      <= 1'b0;
                    ERROR     <= 1'b1;
                    state     <= StateIdle;
                end
            endcase
        end
    end

endmodule

`default_nettype wire
