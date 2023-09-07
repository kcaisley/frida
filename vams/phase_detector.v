assign ff_rst = dn & up; // the AND gate

always @(posedge ref or posedge ff_rst or negedge rstN)
begin
    if (!rstN) up<=1'b0;
    else if (ff_rst) up <= 1'b0;
        else up <= 1'b1;
end
always @(posedge vcxo or posedge ff_rst or negedge rstN)
begin
    if (!rstN) dn<=1'b0;
    else if (ff_rst) dn <= 1'b0;
    else dn <= 1'b1;
end
