`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company:
// Engineer:
//
// Create Date: 07/02/2024 01:01:48 PM
// Design Name:
// Module Name: pot_linear
// Project Name:
// Target Devices:
// Tool Versions:
// Description:
//
// Dependencies:
//
// Revision:
// Revision 0.01 - File Created
// Additional Comments:
//
//////////////////////////////////////////////////////////////////////////////////


module pot_linear #(
    int unsigned IBITS            = 18,
    int unsigned OBITS            = 4,
    int unsigned BBITS            = 10,
    int unsigned PE               = 6,
    int unsigned FOLD             = 1,
    int unsigned N_SHIFTS         = 4,
    int          SHIFTS[N_SHIFTS] = '{-8, -5, -4, -2},
    logic        ISIGNED          = 1,
    logic        OSIGNED          = 0,
    string       RAM_STYLE        = "block"
)(
    //- Global Control ------------------
    input	logic  clk,
    input	logic  rst_n,

    //- AXI Stream - Input --------------
    output	logic  irdy,
    input	logic  ivld,
    input	logic [IBITS*PE-1:0]  idat,

    //- AXI Stream - Output -------------
    input	logic  ordy,
    output	logic  ovld,
    output	logic [OBITS*PE-1:0]  odat
);

integer fd;
initial begin
    fd = $fopen("my_log.txt", "w");
    if (N_SHIFTS == 0) begin
        $error("At least one shift value required!");
        $finish;
    end
end

localparam int unsigned SBITS   = N_SHIFTS >= 2 ? $clog2(N_SHIFTS) : 1;
localparam int unsigned MEMBITS = SBITS + BBITS;
// localparam int unsigned TMPBITS = BBITS > OBITS ? BBITS+1 : OBITS+1;
localparam int unsigned TMPBITS = IBITS + 1;
localparam int          OUT_MIN = OSIGNED ? -(2**(OBITS-1)) : 0;
localparam int          OUT_MAX = OSIGNED ? 2**(OBITS-1)-1 : 2**OBITS-1;

// (* ram_style = "block" *)
logic[MEMBITS*PE-1:0] mem[0:FOLD-1];

initial $readmemh("./memdata.dat", mem);

logic[$clog2(FOLD)-1:0] ptr;
logic[$clog2(FOLD)-1:0] ptr_n;
assign ptr_n = (ptr == FOLD-1 ? 0 : ptr + 1);

always_ff @(posedge clk) begin
    if(rst_n == 0) begin
        ptr <= 0;
        ovld <= 0;
        odat <= 'x;
    end
    else begin
        if (!ovld || ordy) begin
            // logic signed[TMPBITS-1:0] result;
            logic signed[TMPBITS-1:0] tmp;
            logic[SBITS-1:0] shift;
            logic signed[BBITS-1:0] bias;
            for(int unsigned pe = 0; pe < PE; pe++) begin
                shift = mem[ptr][MEMBITS*pe+BBITS+:SBITS];
                bias  = mem[ptr][MEMBITS*pe+:BBITS];

                if (ISIGNED) begin
                    tmp = $signed(idat[IBITS*pe+:IBITS]) + bias;
                    $fdisplay(fd, "pe=%d; idat=%d; bias=%d; tmp=%d; mem=%b; ptr=%d", pe, idat[IBITS*pe+:IBITS], bias, tmp, mem[ptr], ptr);
                    $fflush(fd);
                end else begin
                    tmp = $unsigned(idat[IBITS*pe+:IBITS]) + bias;
                end

                if (N_SHIFTS == 1) begin
                    if (SHIFTS[0] >= 0)
                        tmp = tmp << SHIFTS[0];
                    else if (ISIGNED)
                        tmp = tmp >>> -SHIFTS[0];
                    else
                        tmp = tmp >> -SHIFTS[0];
                end else begin
                    foreach (SHIFTS[s]) begin
                        if (shift == s) begin
                            if (SHIFTS[s] >= 0)
                                tmp = tmp << SHIFTS[s];
                            else if (ISIGNED)
                                tmp = tmp >>> -SHIFTS[s];
                            else
                                tmp = tmp >> -SHIFTS[s];
                        end
                    end
                end

                if(!OSIGNED) begin
                    if(tmp[TMPBITS-1])
                        odat[OBITS*pe+:OBITS] <= '0;
                    else
                        odat[OBITS*pe+:OBITS] <= |tmp[OBITS+:TMPBITS-OBITS-1] ? '1 : tmp[OBITS-1:0];
                end
                else begin
                    odat[OBITS*pe+:OBITS] <=
                        (tmp[OBITS+:TMPBITS-OBITS] == '1) || (tmp[OBITS+:TMPBITS-OBITS] == '0) ? tmp[OBITS-1:0] :
                            {tmp[TMPBITS-1], {(OBITS-1){!tmp[TMPBITS-1]}}};
                end
            end
            ovld <= ivld;

            if (ivld)
                ptr <= ptr_n;
        end
    end
end

assign irdy = !ovld || ordy;

endmodule
