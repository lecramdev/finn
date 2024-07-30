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


module $TOPMODULE$ #(
    int unsigned IBITS            = $IBITS$,
    int unsigned OBITS            = $OBITS$,
    int unsigned BBITS            = $BBITS$,
    int unsigned PE               = $PE$,
    int unsigned FOLD             = $FOLD$,
    int unsigned N_SHIFTS         = $N_SHIFTS$,
    logic        ISIGNED          = $ISIGNED$,
    logic        OSIGNED          = $OSIGNED$,
    string       RAM_STYLE        = "$RAM_STYLE$"
)(
	// Global Control
	(* X_INTERFACE_PARAMETER = "ASSOCIATED_BUSIF s_axilite:in0_V:out_V, ASSOCIATED_RESET ap_rst_n" *)
	(* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 ap_clk CLK" *)
	input	ap_clk,
	(* X_INTERFACE_PARAMETER = "POLARITY ACTIVE_LOW" *)
	input	ap_rst_n,

	//- AXI Stream - Input --------------
	output  in0_V_TREADY,
	input   in0_V_TVALID,
	input [((PE*IBITS+7)/8)*8-1:0]  in0_V_TDATA,

	//- AXI Stream - Output -------------
	input   out_V_TREADY,
	output  out_V_TVALID,
	output [((PE*OBITS+7)/8)*8-1:0]  out_V_TDATA
);

    localparam int SHIFTS[N_SHIFTS] = '{$SHIFTS$};

    pot_linear #(
        .IBITS(IBITS),
        .OBITS(OBITS),
        .BBITS(BBITS),
        .PE(PE),
        .FOLD(FOLD),
        .N_SHIFTS(N_SHIFTS),
        .SHIFTS(SHIFTS),
        .ISIGNED(ISIGNED),
        .OSIGNED(OSIGNED),
        .RAM_STYLE(RAM_STYLE)
    ) core (
        .clk(ap_clk),
        .rst_n(ap_rst_n),
        .irdy(in0_V_TREADY),
        .ivld(in0_V_TVALID),
        .idat(in0_V_TDATA),
        .ordy(out_V_TREADY),
        .ovld(out_V_TVALID),
        .odat(out_V_TDATA)
    );

endmodule
