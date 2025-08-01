// 8-bit Serial Shift Register with Parallel Load
// For SPI configuration interface
module shift_register_8bit (
    input  wire sclk,        // Serial clock
    input  wire sdi,         // Serial data input
    output wire sdo,         // Serial data output
    input  wire cs_b,        // Chip select (active low)

    // Asynchronous reset
    input  wire rst,
    
    // Parallel outputs
    output reg [7:0] cfg  // Configuration bits [cfg7:cfg0]
);

    // Internal shift register
    reg [7:0] shift_reg;
    
    // Serial data output (MSB first)
    assign sdo = shift_reg[7];

    // Shift register operation
    always @(posedge sclk or posedge rst) begin
        if (rst) begin
            shift_reg <= 8'b0;
        end else if (!cs_b) begin
            shift_reg <= {shift_reg[6:0], sdi};  // Shift in serial data
        end
    end

    // Parallel load on CS rising edge with async reset
    always @(posedge cs_b or posedge rst) begin
        if (rst) begin
            cfg <= 8'b0;  // Reset configuration register
        end else begin
            cfg <= shift_reg;
        end
    end

endmodule