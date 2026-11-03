/** 飞书命令行小工具：验证真实收发（say 发送 / read 拉取）。 */
export declare function say(chatId: string, text: string): Promise<number>;
export declare function read(chatId: string): Promise<number>;
