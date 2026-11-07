// ============================================================
// blink_counter.v -- 8 位计数器 + LED 闪烁（vivado_cli 冒烟测试示例）
// 目标: 纯 PL 7 系列（如 xc7a35tcpg236-1）
// ============================================================
`timescale 1ns / 1ps

module blink_counter #(
    parameter integer COUNTER_W = 26
)(
    input  wire       clk,
    input  wire       rst_n,
    input  wire [3:0] sw,
    output wire [3:0] led
);

    reg [COUNTER_W-1:0] r_count;
    wire blink_bit = r_count[COUNTER_W-1];

    always @(posedge clk) begin
        if (!rst_n) begin
            r_count <= {COUNTER_W{1'b0}};
        end else begin
            r_count <= r_count + 1'b1;
        end
    end

    // 拨码开关反相点亮 LED（示例逻辑：低位跟随 blink 与 sw 异或）
    assign led[0] = blink_bit ^ sw[0];
    assign led[1] = blink_bit ^ sw[1];
    assign led[2] = blink_bit ^ sw[2];
    assign led[3] = blink_bit ^ sw[3];

endmodule
