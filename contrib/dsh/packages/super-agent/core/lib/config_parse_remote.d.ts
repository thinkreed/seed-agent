/** 远端 daemon 配置解析（与主配置解析分开，保持单文件行数）。 */
export interface RemoteConfig {
    readonly url: string;
    readonly tokenEnv?: string;
}
export declare function parseRemote(raw: unknown): RemoteConfig;
