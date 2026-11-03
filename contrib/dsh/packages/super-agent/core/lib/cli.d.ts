/** 命令行入口：run（真实运行） / panel（只读面板）。 */
/** 真实运行：配置驱动，接真实模型与渠道。 */
export declare function runApp(configPath: string | undefined, once: boolean): Promise<number>;
/** 端侧 daemon：只执行、不存会话状态（BYOM / 跨设备）。 */
export declare function daemonCommand(argv: string[]): Promise<number>;
export declare function showPanel(path: string, asJson?: boolean): number;
/** 真实体检：凭证、端点、gh、飞书、文件系统。 */
export declare function doctor(configPath?: string): Promise<number>;
/** 桌面控制台：常驻引擎 + 本地界面（默认 4780，独立应用窗口）。 */
export declare function desktopCommand(configPath?: string, argv?: string[]): Promise<number>;
